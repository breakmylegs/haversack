"""Replication's encrypted link and pairing (slice 17, ADR-0054, pairing by code ADR-0070).

Every connection is TLS 1.2 with ``ECDHE-PSK-CHACHA20-POLY1305`` from stdlib ``ssl``: a fresh
key exchange each time (forward secret), authenticated by a 256-bit key the two devices
agreed at pairing. Nothing is compressed (ADR-0045).

Pairing (ADR-0070) runs over the same cipher with a public key, so it is an unauthenticated
key exchange until the code checks out:

1. The requester sends a pairing request. The receiver accepts requests whenever its listener
   is on, at most three in two minutes, and an address or device ID with five failed attempts
   is locked out for ten minutes.
2. The receiver's user presses Accept (or Decline; no answer in 120 seconds declines).
3. The receiver shows a random 6-digit code, and the user types it on the requester.
4. The two devices prove they hold the same code without sending it: twenty rounds, one per
   bit, each a commitment (HMAC under a fresh nonce, bound to this TLS session's
   ``tls-unique``, both device IDs, the sender's role and the round) sent before either nonce
   is revealed, compared in constant time. A device in the middle has to guess each bit
   before it can learn it, so it has one chance in about a million per attempt, and nothing
   to try offline. Both devices check every round.
5. Only then does the requester send the new link key.

Frames are a 4-byte big-endian length and a JSON object with a ``type``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import secrets
import ssl
import struct
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from . import policy
from .peers import KEY_BYTES, PeerError, PeerStore, check_device_id, clean_name

PROTOCOL = 1
DEFAULT_PORT = 47110  # clear of 8080, 8384, 27040 and 1714 to 1764
CIPHERS = "ECDHE-PSK-CHACHA20-POLY1305"
PAIR_IDENTITY = "keepsake-pair/2"  # pairing by code (ADR-0070); devices with the old pairing refuse cleanly
PAIR_KEY = hashlib.sha256(b"keepsake pairing v2").digest()  # public on purpose: the code carries the trust
PAIR_PROTOCOL = 2
MAX_FRAME = 64 * 1024
HANDSHAKE_TIMEOUT = 10.0
FRAME_TIMEOUT = 30.0
CONFIRM_TIMEOUT = 120.0  # to accept a request, and to type the code
REQUEST_LIMIT = 3  # pairing requests a receiver takes ...
REQUEST_WINDOW = 120.0  # ... in this many seconds
LOCKOUT_FAILURES = 5  # failed pairing attempts from one address or device ID ...
LOCKOUT_SECONDS = 600.0  # ... lock it out for this long
CODE_BITS = 20  # 10**6 < 2**20: one round per bit of the code
MAX_CONNECTIONS = 8
FAILURE_LIMIT = 5  # failed handshakes from one address ...
FAILURE_WINDOW = 60.0  # ... within this many seconds block it for the same time

Clock = Callable[[], float]


class LinkError(Exception):
    pass


class Refused(LinkError):
    """The other device answered, and said no: retrying will not help."""


def available() -> bool:
    """Whether this Python's ``ssl`` can do TLS-PSK. Without it Replication stays off (fail closed)."""
    return bool(getattr(ssl, "HAS_PSK", False)) and hasattr(ssl.SSLContext, "set_psk_client_callback")


def _context(server: bool) -> ssl.SSLContext:
    if not available():
        raise LinkError("this device's Python cannot make Replication's encrypted link (no TLS-PSK)")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2  # the PSK suites below are TLS 1.2
    context.set_ciphers(CIPHERS)
    if not server:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # no certificates: the PSK authenticates both ends
    return policy.require_no_compression(context)


def client_context(identity: str, key: bytes) -> ssl.SSLContext:
    context = _context(server=False)
    context.set_psk_client_callback(lambda _hint: (identity, key))  # type: ignore[attr-defined]  # Python 3.13+
    return context


def server_context(lookup: Callable[[str | None], bytes | None]) -> ssl.SSLContext:
    context = _context(server=True)
    context.set_psk_server_callback(lambda identity: lookup(identity) or b"")  # type: ignore[attr-defined]
    return context


def checked_session(writer: asyncio.StreamWriter) -> bytes:
    """After the handshake: the agreed cipher, no compression, and the session's ``tls-unique``."""
    tls = writer.get_extra_info("ssl_object")
    if tls is None:
        raise LinkError("the connection is not encrypted")
    policy.check_uncompressed(tls)
    cipher = tls.cipher()
    if not cipher or cipher[0] != CIPHERS or tls.version() != "TLSv1.2":
        raise LinkError("the connection did not use Replication's cipher")
    binding = tls.get_channel_binding("tls-unique")
    if not binding:
        raise LinkError("the connection has no session binding")
    return bytes(binding)


async def send_frame(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise LinkError("message too large")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()


async def read_frame(reader: asyncio.StreamReader, timeout: float = FRAME_TIMEOUT) -> dict[str, Any]:
    try:
        header = await asyncio.wait_for(reader.readexactly(4), timeout)
        (size,) = struct.unpack(">I", header)
        if size > MAX_FRAME:
            raise LinkError("message too large")
        body = await asyncio.wait_for(reader.readexactly(size), timeout)
    except asyncio.IncompleteReadError as exc:
        raise LinkError("the other device closed the connection") from exc
    except TimeoutError as exc:
        raise LinkError("the other device stopped answering") from exc
    try:
        message = json.loads(body)
    except ValueError as exc:
        raise LinkError("a message was not valid") from exc
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise LinkError("a message was not valid")
    if message["type"] == "error":
        raise Refused(str(message.get("reason") or "the other device refused")[:200])
    return message


async def expect(reader: asyncio.StreamReader, kind: str, timeout: float = FRAME_TIMEOUT) -> dict[str, Any]:
    message = await read_frame(reader, timeout)
    if message["type"] != kind:
        raise LinkError(f"expected {kind}, got {message['type'][:40]}")
    return message


def new_code() -> str:
    """The receiver's 6-digit code: random, shown only on its screen, never sent."""
    return f"{secrets.randbelow(1_000_000):06d}"


def check_code(text: Any) -> str:
    code = "".join(str(text or "").split())
    if len(code) != 6 or not code.isdigit():
        raise LinkError("the code is 6 digits")
    return code


def commitment(nonce: bytes, binding: bytes, id_req: str, id_recv: str, role: str, index: int, bit: int) -> bytes:
    """One round's commitment. Every part is length-prefixed so no two inputs collide."""
    mac = hmac.new(nonce, b"keepsake passkey v1", hashlib.sha256)
    for part in (binding, id_req.encode(), id_recv.encode(), role.encode(), struct.pack(">II", index, bit)):
        mac.update(struct.pack(">I", len(part)) + part)
    return mac.digest()


async def prove_code(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    code: str,
    binding: bytes,
    id_req: str,
    id_recv: str,
    role: str,
    first_timeout: float = FRAME_TIMEOUT,
) -> None:
    """Twenty commit-then-reveal rounds proving both devices hold ``code``; raises on the first mismatch."""
    value = int(check_code(code))
    other = "recv" if role == "req" else "req"
    for index in range(CODE_BITS):
        bit = (value >> index) & 1
        nonce = secrets.token_bytes(16)
        mine = {"type": "pair-c", "i": index, "c": commitment(nonce, binding, id_req, id_recv, role, index, bit).hex()}
        timeout = first_timeout if index == 0 else FRAME_TIMEOUT
        if role == "req":
            await send_frame(writer, mine)
            theirs = await expect(reader, "pair-c", timeout)
            await send_frame(writer, {"type": "pair-n", "i": index, "n": nonce.hex()})
            revealed = await expect(reader, "pair-n")
        else:
            theirs = await expect(reader, "pair-c", timeout)
            await send_frame(writer, mine)
            revealed = await expect(reader, "pair-n")
        if theirs.get("i") != index or revealed.get("i") != index:
            raise LinkError("the other device's pairing answer was out of order")
        expected = commitment(_hex(revealed, "n", 16), binding, id_req, id_recv, other, index, bit)
        if not hmac.compare_digest(expected, _hex(theirs, "c", 32)):
            with contextlib.suppress(Exception):
                await send_frame(writer, {"type": "error", "reason": "the code was wrong"})
            raise LinkError("the code was wrong")
        if role == "recv":
            await send_frame(writer, {"type": "pair-n", "i": index, "n": nonce.hex()})


def _hex(message: dict[str, Any], name: str, size: int) -> bytes:
    try:
        value = bytes.fromhex(str(message.get(name, "")))
    except ValueError as exc:
        raise LinkError(f"{name} was not valid") from exc
    if len(value) != size:
        raise LinkError(f"{name} was not valid")
    return value


@dataclass
class Pairing:
    """One pairing attempt, shown to the user until it ends."""

    id: str
    role: str  # "initiator" (sent the request) or "responder" (received it)
    address: str
    # connecting, waiting-accept, enter-code, request, show-code, checking, paired, declined, failed, cancelled
    state: str = "connecting"
    code: str | None = None  # the responder's code, shown only while it waits for it to be typed
    peer_id: str | None = None
    peer_name: str | None = None
    reason: str | None = None
    answer: asyncio.Future[bool] | None = None  # the responder's Accept or Decline
    entered: asyncio.Future[str | None] | None = None  # the code typed on the initiator
    ended_at: float | None = None
    announced: bool = False  # the app has told the user about this request
    two_way: bool = False  # the app has made this device reachable after the pairing (ADR-0072)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "address": self.address,
            "state": self.state,
            "code": self.code,  # set only on the receiver, and cleared when the attempt ends
            "peerName": self.peer_name,
            "reason": self.reason,
        }


def answer(pairing: Pairing, ok: bool) -> None:
    """The receiving user's Accept or Decline."""
    if pairing.state != "request" or pairing.answer is None or pairing.answer.done():
        raise LinkError("this pairing request is not waiting for an answer")
    pairing.answer.set_result(bool(ok))


def enter_code(pairing: Pairing, code: Any) -> None:
    """The code the user typed on the requesting device. One entry per attempt."""
    if pairing.state != "enter-code" or pairing.entered is None or pairing.entered.done():
        raise LinkError("this pairing is not waiting for a code")
    pairing.entered.set_result(check_code(code))


def cancel(pairing: Pairing) -> None:
    if pairing.state in ("paired", "failed", "cancelled", "declined"):
        return
    pairing.state, pairing.reason = "cancelled", "Cancelled on this device."
    for future in (pairing.answer, pairing.entered):
        if future is not None and not future.done():
            future.set_result(None if future is pairing.entered else False)  # type: ignore[arg-type]


@dataclass
class Identity:
    device_id: str
    name: str
    wake: list[str] = field(default_factory=list)  # hardware addresses, for Wake-on-LAN (ADR-0056)


async def _await(future: asyncio.Future[Any], timeout: float) -> Any:
    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout)
    except TimeoutError:
        return None


async def _dial(
    host: str, port: int, context: ssl.SSLContext, refused: str
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect, then handshake, so "not reachable" and "refused" are told apart."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), HANDSHAKE_TIMEOUT)
    except (OSError, TimeoutError) as exc:
        raise LinkError(f"could not reach {host}:{port}; check the address and that its listener is on") from exc
    try:
        await asyncio.wait_for(writer.start_tls(context, server_hostname=None), HANDSHAKE_TIMEOUT)
    except (OSError, TimeoutError, ssl.SSLError) as exc:
        await _close(writer)
        raise LinkError(refused) from exc
    return reader, writer


async def pair_as_initiator(
    me: Identity,
    store: PeerStore,
    pairing: Pairing,
    host: str,
    port: int = DEFAULT_PORT,
    confirm_timeout: float = CONFIRM_TIMEOUT,
    changed: Callable[[], None] | None = None,
) -> None:
    """Send a pairing request; once accepted, take the typed code and prove it. Ends with ``pairing.state`` set."""
    writer: asyncio.StreamWriter | None = None

    def show(state: str) -> None:
        pairing.state = state
        if changed:
            changed()

    try:
        reader, writer = await _dial(
            host,
            port,
            client_context(PAIR_IDENTITY, PAIR_KEY),
            f"{host}:{port} did not take the request: switch on Let other devices reach this one there, "
            "update Keepsake on both, or wait two minutes and try again",
        )
        binding = checked_session(writer)
        await send_frame(
            writer, {"type": "pair-request", "v": PAIR_PROTOCOL, "deviceId": me.device_id, "name": me.name}
        )
        show("waiting-accept")
        reply = await read_frame(reader, confirm_timeout + FRAME_TIMEOUT)
        if reply.get("type") == "pair-declined":
            pairing.state = "declined"
            pairing.reason = (
                "The other device did not answer in time."
                if reply.get("reason") == "timed out"
                else "The other device declined."
            )
            return
        if reply.get("type") == "error":
            raise LinkError(str(reply.get("reason") or "the other device ended the pairing"))
        if reply.get("type") != "pair-accepted":
            raise LinkError("the other device sent something unexpected")
        peer_id = check_device_id(reply.get("deviceId"))
        if peer_id == me.device_id:
            raise LinkError("a device cannot pair with itself")
        pairing.peer_id, pairing.peer_name = peer_id, clean_name(reply.get("name"))
        pairing.entered = asyncio.get_running_loop().create_future()
        show("enter-code")
        code = await _await(pairing.entered, confirm_timeout)
        if code is None:
            raise LinkError("no code was entered in time" if pairing.state != "cancelled" else "cancelled")
        show("checking")
        await prove_code(reader, writer, code, binding, me.device_id, peer_id, "req")
        key = secrets.token_bytes(KEY_BYTES)
        await send_frame(writer, {"type": "pair-key", "key": key.hex()})
        await expect(reader, "pair-done")
        store.add(peer_id, pairing.peer_name, key, f"{host}:{port}")
        pairing.state = "paired"
    except (OSError, TimeoutError, ssl.SSLError) as exc:
        _fail(pairing, f"the connection dropped ({type(exc).__name__})")
    except (LinkError, PeerError, policy.PolicyError) as exc:
        _fail(pairing, str(exc))
        if writer is not None:
            with contextlib.suppress(Exception):
                await send_frame(writer, {"type": "error", "reason": str(exc)})
    finally:
        await _close(writer)
        pairing.ended_at = time.monotonic()
        if changed:
            changed()


def _fail(pairing: Pairing, reason: str) -> None:
    if pairing.state != "cancelled":
        pairing.state, pairing.reason = "failed", reason


async def _close(writer: asyncio.StreamWriter | None) -> None:
    if writer is None:
        return
    writer.close()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(writer.wait_closed(), 2)


# A handler answers with a frame, or with a frame and raw bytes that follow it (ADR-0057).
Reply = dict[str, Any] | tuple[dict[str, Any], bytes]
Handler = Callable[["Session", dict[str, Any]], Awaitable[Reply]]
MAX_BLOB = 64 * 1024 * 1024  # a manifest or one chunk


class ServeError(Exception):
    """A refusal a handler may show the other device. Its text must hold no local path (P10)."""


@dataclass(eq=False)
class Session:
    """A connection from a paired device, after authentication."""

    peer_id: str
    address: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter


@dataclass
class Listener:
    """The Replication listener. It exists only while switched on: no socket otherwise (P17)."""

    me: Identity
    store: PeerStore
    host: str | list[str]  # one address, or several (ADR-0056)
    port: int = DEFAULT_PORT
    clock: Clock = time.monotonic
    confirm_timeout: float = CONFIRM_TIMEOUT
    handlers: dict[str, Handler] = field(default_factory=dict)
    on_change: Callable[[], None] | None = None
    _server: asyncio.Server | None = None
    _requests: list[float] = field(default_factory=list)
    _pair_failures: dict[str, list[float]] = field(default_factory=dict)
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _sessions: set[Session] = field(default_factory=set)
    _connections: int = 0
    pairings: dict[str, Pairing] = field(default_factory=dict)

    async def start(self) -> None:
        if not available():
            raise LinkError("this device's Python cannot make Replication's encrypted link (no TLS-PSK)")
        self._server = await asyncio.start_server(self._accept, self.host, self.port)

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            return 0
        return int(self._server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        self.end_requests()
        if self._server is not None:
            self._server.close()
            for session in list(self._sessions):
                await _close(session.writer)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 5)
            self._server = None

    # Pairing requests (ADR-0070): taken whenever the listener is on, within limits

    def end_requests(self) -> None:
        """The listener is going: every waiting request is declined."""
        for pairing in self.pairings.values():
            cancel(pairing)

    def locked(self, key: str) -> bool:
        """Five failed pairing attempts from one address or device ID in ten minutes lock it out."""
        now = self.clock()
        recent = [t for t in self._pair_failures.get(key, []) if now - t < LOCKOUT_SECONDS]
        self._pair_failures[key] = recent
        return len(recent) >= LOCKOUT_FAILURES

    def _pair_failed(self, address: str, peer_id: str | None) -> None:
        for key in [f"address:{address}"] + ([f"device:{peer_id}"] if peer_id else []):
            self._pair_failures.setdefault(key, []).append(self.clock())

    def _take_request(self, address: str) -> bool:
        now = self.clock()
        self._requests = [t for t in self._requests if now - t < REQUEST_WINDOW]
        if self.locked(f"address:{address}") or len(self._requests) >= REQUEST_LIMIT:
            return False
        self._requests.append(now)
        return True

    # Authentication

    def _blocked(self, address: str) -> bool:
        now = self.clock()
        recent = [t for t in self._failures.get(address, []) if now - t < FAILURE_WINDOW]
        self._failures[address] = recent
        return len(recent) >= FAILURE_LIMIT

    def _failed(self, address: str) -> None:
        self._failures.setdefault(address, []).append(self.clock())

    def _lookup(self, seen: dict[str, str], address: str) -> Callable[[str | None], bytes | None]:
        def lookup(identity: str | None) -> bytes | None:
            seen["identity"] = identity or ""
            if identity == PAIR_IDENTITY:
                return PAIR_KEY if self._take_request(address) else None
            return self.store.key(identity)

        return lookup

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername") or ("?", 0)
        address = str(peer[0])
        if self._blocked(address) or self._connections >= MAX_CONNECTIONS:
            await _close(writer)
            return
        self._connections += 1
        seen: dict[str, str] = {}
        try:
            try:
                await asyncio.wait_for(writer.start_tls(server_context(self._lookup(seen, address))), HANDSHAKE_TIMEOUT)
                binding = checked_session(writer)
            except (OSError, TimeoutError, ssl.SSLError, LinkError, policy.PolicyError):
                self._failed(address)
                return
            identity = seen.get("identity", "")
            if identity == PAIR_IDENTITY:
                await self._pair(reader, writer, binding, address)
            else:
                await self._serve(Session(identity, address, reader, writer))
        finally:
            self._connections -= 1
            await _close(writer)

    # Responding to a pairing request

    async def _pair(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, binding: bytes, address: str
    ) -> None:
        pairing = Pairing(secrets.token_hex(8), "responder", address)
        self.pairings[pairing.id] = pairing
        try:
            request = await expect(reader, "pair-request")
            if request.get("v") != PAIR_PROTOCOL:
                raise LinkError("the other device runs a different Keepsake version; update both")
            peer_id = check_device_id(request.get("deviceId"))
            if peer_id == self.me.device_id:
                raise LinkError("a device cannot pair with itself")
            if self.locked(f"device:{peer_id}"):
                raise LinkError("too many failed pairing attempts from that device; wait ten minutes")
            pairing.peer_id, pairing.peer_name = peer_id, clean_name(request.get("name"))
            pairing.answer = asyncio.get_running_loop().create_future()
            pairing.state = "request"
            self._changed()  # "<name> wants to pair": Accept or Decline
            accepted = await _await(pairing.answer, self.confirm_timeout)
            if not accepted:
                timed_out = accepted is None and pairing.state == "request"
                await send_frame(writer, {"type": "pair-declined", "reason": "timed out" if timed_out else "declined"})
                if pairing.state != "cancelled":
                    pairing.state = "declined"
                    pairing.reason = "No answer in time." if timed_out else "Declined on this device."
                self._pair_failed(address, peer_id)
                return
            await send_frame(writer, {"type": "pair-accepted", "deviceId": self.me.device_id, "name": self.me.name})
            pairing.code = new_code()
            pairing.state = "show-code"
            self._changed()
            await prove_code(
                reader, writer, pairing.code, binding, peer_id, self.me.device_id, "recv", self.confirm_timeout
            )
            pairing.state = "checking"
            key = _hex(await expect(reader, "pair-key"), "key", KEY_BYTES)
            self.store.add(peer_id, pairing.peer_name, key, address)
            await send_frame(writer, {"type": "pair-done"})
            pairing.state = "paired"
        except (OSError, ssl.SSLError) as exc:
            _fail(pairing, f"the connection dropped ({type(exc).__name__})")
            self._pair_failed(address, pairing.peer_id)
        except (LinkError, PeerError, policy.PolicyError) as exc:
            _fail(pairing, str(exc))
            self._pair_failed(address, pairing.peer_id)
            with contextlib.suppress(Exception):  # tell the requester why, if it is still there
                await send_frame(writer, {"type": "error", "reason": str(exc)})
        finally:
            pairing.code = None if pairing.state != "show-code" else pairing.code
            pairing.ended_at = self.clock()
            self._changed()

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    # Serving a paired device

    async def _serve(self, session: Session) -> None:
        if self.store.key(session.peer_id) is None:
            return
        self._sessions.add(session)
        try:
            hello = await expect(session.reader, "hello")
            if hello.get("deviceId") != session.peer_id:
                raise LinkError("the device's hello did not match its key")
            await send_frame(
                session.writer,
                {
                    "type": "hello",
                    "v": PROTOCOL,
                    "deviceId": self.me.device_id,
                    "name": self.me.name,
                    "wake": self.me.wake,
                },
            )
            self.store.seen(session.peer_id, wake=hello.get("wake"))
            while True:
                message = await read_frame(session.reader, timeout=300)
                if self.store.key(session.peer_id) is None:
                    break  # revoked while connected
                reply: Reply
                if message["type"] == "ping":
                    reply = {"type": "pong"}
                elif message["type"] in self.handlers:
                    try:
                        reply = await self.handlers[message["type"]](session, message)
                    except ServeError as exc:
                        reply = {"type": "error", "reason": str(exc)[:200]}
                    except (OSError, ValueError):
                        reply = {"type": "error", "reason": "the other device could not read that file"}
                else:
                    reply = {"type": "error", "reason": f"unknown request {message['type'][:40]}"}
                if isinstance(reply, tuple):
                    header, data = reply
                    await send_frame(session.writer, {**header, "type": "blob", "size": len(data)})
                    session.writer.write(data)
                    await session.writer.drain()
                else:
                    await send_frame(session.writer, reply)
        except (LinkError, OSError, ssl.SSLError):
            pass
        finally:
            self._sessions.discard(session)

    async def drop(self, peer_id: str) -> None:
        """Close every connection from a device, after it is removed."""
        for session in [s for s in self._sessions if s.peer_id == peer_id]:
            await _close(session.writer)


class Connection:
    """A connection to a paired device."""

    def __init__(self, peer_id: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.peer_id = peer_id
        self.reader = reader
        self.writer = writer
        self.peer_name = ""

    async def request(self, message: dict[str, Any], timeout: float = FRAME_TIMEOUT) -> dict[str, Any]:
        try:
            await send_frame(self.writer, message)
            return await read_frame(self.reader, timeout)
        except (OSError, ssl.SSLError) as exc:
            raise LinkError("the connection to the other device dropped") from exc

    async def request_blob(
        self, message: dict[str, Any], max_size: int = MAX_BLOB, timeout: float = FRAME_TIMEOUT
    ) -> tuple[dict[str, Any], bytes]:
        """A request answered by a frame and raw bytes, such as a manifest or a chunk."""
        header = await self.request(message, timeout)
        size = header.get("size")
        if header["type"] != "blob" or not isinstance(size, int) or not 0 <= size <= max_size:
            raise LinkError("the other device sent an unexpected answer")
        try:
            data = await asyncio.wait_for(self.reader.readexactly(size), timeout)
        except asyncio.IncompleteReadError as exc:
            raise LinkError("the other device closed the connection") from exc
        except TimeoutError as exc:
            raise LinkError("the other device stopped sending") from exc
        except (OSError, ssl.SSLError) as exc:
            raise LinkError("the connection to the other device dropped") from exc
        return header, data

    async def ping(self) -> float:
        """Round trip in milliseconds."""
        started = time.perf_counter()
        await self.request({"type": "ping"})
        return (time.perf_counter() - started) * 1000

    async def close(self) -> None:
        await _close(self.writer)


async def connect(me: Identity, store: PeerStore, peer_id: str, host: str, port: int = DEFAULT_PORT) -> Connection:
    """Open an authenticated connection to a paired device."""
    key = store.key(peer_id)
    if key is None:
        raise LinkError("that device is not paired")
    reader, writer = await _dial(
        host, port, client_context(me.device_id, key), "the other device refused this device's key; pair them again"
    )
    connection = Connection(peer_id, reader, writer)
    try:
        checked_session(writer)
        hello = await connection.request(
            {"type": "hello", "v": PROTOCOL, "deviceId": me.device_id, "name": me.name, "wake": me.wake}
        )
        if hello.get("type") != "hello" or hello.get("deviceId") != peer_id:
            raise LinkError("a different device answered at that address")
        connection.peer_name = clean_name(hello.get("name"))
    except (LinkError, policy.PolicyError, OSError, ssl.SSLError) as exc:
        await connection.close()
        raise LinkError(str(exc)) from exc
    store.seen(peer_id, f"{host}:{port}", wake=hello.get("wake"))
    return connection
