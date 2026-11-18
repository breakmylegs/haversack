"""Replication's encrypted link and pairing (slice 17, ADR-0054).

Every connection is TLS 1.2 with ``ECDHE-PSK-CHACHA20-POLY1305`` from stdlib ``ssl``: a fresh
key exchange each time (forward secret), authenticated by a 256-bit key the two devices
agreed at pairing. Nothing is compressed (ADR-0045).

Pairing runs over the same cipher with a public key, so it is an unauthenticated key
exchange until the user confirms. Both screens then show a 6-digit code bound to this TLS
session (``tls-unique``) and to two nonces, one committed before the other is revealed. A
device in the middle has one chance in a million per attempt, and cannot try codes offline.
Only after both users confirm does the initiator send the new link key.

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
PAIR_IDENTITY = "keepsake-pair/1"
PAIR_KEY = hashlib.sha256(b"keepsake pairing v1").digest()  # public on purpose: the code carries the trust
MAX_FRAME = 64 * 1024
HANDSHAKE_TIMEOUT = 10.0
FRAME_TIMEOUT = 30.0
PAIR_WINDOW = 120.0
PAIR_ATTEMPTS = 3
CONFIRM_TIMEOUT = 120.0
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


def comparison_code(binding: bytes, nonce_i: bytes, nonce_r: bytes, id_i: str, id_r: str) -> str:
    """The 6 digits both screens show. Every part is length-prefixed so no two inputs collide."""
    digest = hashlib.sha256(b"keepsake sas v1")
    for part in (binding, nonce_i, nonce_r, id_i.encode(), id_r.encode()):
        digest.update(struct.pack(">I", len(part)) + part)
    return f"{int.from_bytes(digest.digest()[:8], 'big') % 1_000_000:06d}"


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
    role: str  # "initiator" (typed the address) or "responder" (opened the window)
    address: str
    state: str = "connecting"  # connecting, compare, waiting, paired, failed, cancelled
    code: str | None = None
    peer_id: str | None = None
    peer_name: str | None = None
    reason: str | None = None
    confirmed: asyncio.Future[bool] | None = None
    ended_at: float | None = None
    announced: bool = False  # the app has told the user about this request

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "address": self.address,
            "state": self.state,
            "code": self.code if self.state in ("compare", "waiting") else None,
            "peerName": self.peer_name,
            "reason": self.reason,
        }


def answer(pairing: Pairing, ok: bool) -> None:
    """The user's answer to "do both screens show this code?"."""
    if pairing.state != "compare" or pairing.confirmed is None or pairing.confirmed.done():
        raise LinkError("this pairing is not waiting for an answer")
    pairing.confirmed.set_result(bool(ok))


def cancel(pairing: Pairing) -> None:
    if pairing.state in ("paired", "failed", "cancelled"):
        return
    pairing.state, pairing.reason = "cancelled", "Cancelled on this device."
    if pairing.confirmed is not None and not pairing.confirmed.done():
        pairing.confirmed.set_result(False)


@dataclass
class Identity:
    device_id: str
    name: str
    wake: list[str] = field(default_factory=list)  # hardware addresses, for Wake-on-LAN (ADR-0056)


async def _await_user(pairing: Pairing, timeout: float) -> bool:
    assert pairing.confirmed is not None
    try:
        return await asyncio.wait_for(asyncio.shield(pairing.confirmed), timeout)
    except TimeoutError:
        return False


async def _compare(
    pairing: Pairing,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    code: str,
    confirm_timeout: float,
    changed: Callable[[], None] | None = None,
) -> None:
    """Show the code, send this user's answer, read the other's. Both must say the codes match."""
    pairing.code = code
    pairing.confirmed = asyncio.get_running_loop().create_future()
    pairing.state = "compare"
    if changed:
        changed()  # the code is ready to show
    ours = await _await_user(pairing, confirm_timeout)
    await send_frame(writer, {"type": "pair-confirm", "ok": ours})
    if not ours:
        raise LinkError("the codes were not confirmed on this device")
    pairing.state = "waiting"
    theirs = await expect(reader, "pair-confirm", confirm_timeout + FRAME_TIMEOUT)
    if theirs.get("ok") is not True:
        raise LinkError("the other device said the codes did not match")


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
) -> None:
    """Pair with a device whose pairing window is open. Ends with ``pairing.state`` set."""
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await _dial(
            host,
            port,
            client_context(PAIR_IDENTITY, PAIR_KEY),
            f"{host}:{port} did not accept pairing; open its pairing window and try again",
        )
        binding = checked_session(writer)
        nonce_i = secrets.token_bytes(32)
        await send_frame(
            writer,
            {
                "type": "pair-commit",
                "v": PROTOCOL,
                "deviceId": me.device_id,
                "name": me.name,
                "commit": hashlib.sha256(nonce_i).hexdigest(),
            },
        )
        answer = await expect(reader, "pair-nonce")
        peer_id = check_device_id(answer.get("deviceId"))
        if peer_id == me.device_id:
            raise LinkError("a device cannot pair with itself")
        nonce_r = _hex(answer, "nonce", 32)
        pairing.peer_id, pairing.peer_name = peer_id, clean_name(answer.get("name"))
        await send_frame(writer, {"type": "pair-reveal", "nonce": nonce_i.hex()})
        code = comparison_code(binding, nonce_i, nonce_r, me.device_id, peer_id)
        await _compare(pairing, reader, writer, code, confirm_timeout)
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
    _window_until: float = 0.0
    _attempts_left: int = 0
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
        self.close_pairing()
        if self._server is not None:
            self._server.close()
            for session in list(self._sessions):
                await _close(session.writer)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 5)
            self._server = None

    # The pairing window

    def open_pairing(self, seconds: float = PAIR_WINDOW) -> float:
        """Accept up to ``PAIR_ATTEMPTS`` pairing handshakes for ``seconds``. Only from a user action."""
        self._window_until = self.clock() + seconds
        self._attempts_left = PAIR_ATTEMPTS
        return self._window_until

    def close_pairing(self) -> None:
        self._window_until, self._attempts_left = 0.0, 0
        for pairing in self.pairings.values():
            if pairing.confirmed is not None and not pairing.confirmed.done():
                pairing.confirmed.set_result(False)

    def pairing_open(self) -> bool:
        return self._attempts_left > 0 and self.clock() < self._window_until

    def window_seconds_left(self) -> int:
        return max(0, int(self._window_until - self.clock())) if self.pairing_open() else 0

    # Authentication

    def _blocked(self, address: str) -> bool:
        now = self.clock()
        recent = [t for t in self._failures.get(address, []) if now - t < FAILURE_WINDOW]
        self._failures[address] = recent
        return len(recent) >= FAILURE_LIMIT

    def _failed(self, address: str) -> None:
        self._failures.setdefault(address, []).append(self.clock())

    def _lookup(self, seen: dict[str, str]) -> Callable[[str | None], bytes | None]:
        def lookup(identity: str | None) -> bytes | None:
            seen["identity"] = identity or ""
            if identity == PAIR_IDENTITY:
                if not self.pairing_open():
                    return None
                self._attempts_left -= 1
                return PAIR_KEY
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
                await asyncio.wait_for(writer.start_tls(server_context(self._lookup(seen))), HANDSHAKE_TIMEOUT)
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

    # Responding to a pairing

    async def _pair(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, binding: bytes, address: str
    ) -> None:
        pairing = Pairing(secrets.token_hex(8), "responder", address)
        self.pairings[pairing.id] = pairing
        self._changed()
        try:
            commit = await expect(reader, "pair-commit")
            if commit.get("v") != PROTOCOL:
                raise LinkError("the other device runs a different Keepsake version; update both")
            peer_id = check_device_id(commit.get("deviceId"))
            if peer_id == self.me.device_id:
                raise LinkError("a device cannot pair with itself")
            committed = _hex(commit, "commit", 32)
            pairing.peer_id, pairing.peer_name = peer_id, clean_name(commit.get("name"))
            nonce_r = secrets.token_bytes(32)
            await send_frame(
                writer,
                {"type": "pair-nonce", "deviceId": self.me.device_id, "name": self.me.name, "nonce": nonce_r.hex()},
            )
            nonce_i = _hex(await expect(reader, "pair-reveal"), "nonce", 32)
            if not hmac.compare_digest(hashlib.sha256(nonce_i).digest(), committed):
                raise LinkError("the other device's pairing answer did not match what it promised")
            code = comparison_code(binding, nonce_i, nonce_r, peer_id, self.me.device_id)
            await _compare(pairing, reader, writer, code, self.confirm_timeout, self._changed)
            key = _hex(await expect(reader, "pair-key"), "key", KEY_BYTES)
            self.store.add(peer_id, pairing.peer_name, key, address)
            await send_frame(writer, {"type": "pair-done"})
            pairing.state = "paired"
            self.close_pairing()
        except (OSError, ssl.SSLError) as exc:
            _fail(pairing, f"the connection dropped ({type(exc).__name__})")
        except (LinkError, PeerError, policy.PolicyError) as exc:
            _fail(pairing, str(exc))
            with contextlib.suppress(Exception):  # tell the initiator why, if it is still there
                await send_frame(writer, {"type": "error", "reason": str(exc)})
        finally:
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
