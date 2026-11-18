"""Replication's device links for the app: the listener switch, pairing, paired devices (slice 17).

The listener is off until the user switches it on, and the pairing window opens only from a
user action (P17, ADR-0016). Addresses are typed by the user or come from a paired device's
record; nothing here reaches a cloud store (ADR-0045).
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import secrets
from collections.abc import Callable
from typing import Any

from . import discovery, link, netinfo, policy
from .peers import PeerStore

HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,62})(\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}))*\.?$")
OVERLAY_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
KEEP_ENDED = 8


class ReplicationError(Exception):
    pass


def parse_address(text: str, default_port: int = link.DEFAULT_PORT) -> tuple[str, int]:
    """``host``, ``host:port`` or ``[v6]:port``, as the user typed it. No scheme, path or user."""
    text = str(text or "").strip()
    if not text or len(text) > 300 or any(c in text for c in "/@?#\\ "):
        raise ReplicationError("type the other device's address, such as 192.168.1.20 or 192.168.1.20:47110")
    host, port_text = text, ""
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            raise ReplicationError("that address is not valid")
        host, rest = text[1:end], text[end + 1 :]
        if rest and not rest.startswith(":"):
            raise ReplicationError("that address is not valid")
        port_text = rest[1:]
    elif text.count(":") == 1:
        host, port_text = text.split(":")
    port = default_port
    if port_text:
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            raise ReplicationError("the port is a number from 1 to 65535")
        port = int(port_text)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not HOSTNAME.match(host):
            raise ReplicationError("that address is not valid") from None
    return host, port


def is_overlay(host: str) -> bool:
    """Tailscale's address ranges: a link through them may be relayed, so speed is explained."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".ts.net")
    return any(address in network for network in OVERLAY_NETWORKS)


Bind = str | Callable[[], list[str]]


class Links:
    def __init__(
        self,
        me: link.Identity,
        store: PeerStore,
        bind: Bind,
        port: int = link.DEFAULT_PORT,
        discovery: bool = False,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.me = me
        self.store = store
        self.bind = bind
        self.port = port
        self.discovery = discovery  # answer mDNS queries while the listener is on (ADR-0056)
        self.on_change = on_change
        self.listener: link.Listener | None = None
        self.responder: asyncio.DatagramTransport | None = None
        self.discovery_problem: str | None = None
        self.initiated: dict[str, link.Pairing] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def hosts(self) -> list[str]:
        return [self.bind] if isinstance(self.bind, str) else list(self.bind())

    async def set_listener(self, on: bool) -> dict[str, Any]:
        if on and self.listener is None:
            hosts = self.hosts()
            if not hosts:
                raise ReplicationError(
                    "this device has no home network or VPN address to listen on; connect to a network first"
                )
            listener = link.Listener(self.me, self.store, hosts if len(hosts) > 1 else hosts[0], self.port)
            listener.on_change = self.on_change
            await listener.start()
            self.listener = listener
            await self._start_discovery(listener.bound_port)
        elif not on and self.listener is not None:
            listener, self.listener = self.listener, None
            if self.responder is not None:
                self.responder.close()
                self.responder = None
            await listener.stop()
        return self.status()

    async def _start_discovery(self, port: int) -> None:
        if not self.discovery:
            return
        try:
            self.responder = await discovery.start_responder(self.me.device_id, lambda: self.me.name, port)
            self.discovery_problem = None
        except OSError as exc:
            # Discovery is a convenience: typing the address still works.
            self.discovery_problem = f"other devices cannot find this one automatically ({exc.strerror or exc})"

    async def find(self, seconds: float = 2.0) -> list[dict[str, Any]]:
        """Keepsake devices answering on the LAN, marked when already paired."""
        try:
            found = await discovery.browse(self.me.device_id, seconds)
        except OSError as exc:
            raise ReplicationError(f"could not look for devices ({exc.strerror or exc})") from exc
        paired = {p["id"] for p in self.store.list()}
        return [d | {"paired": d["id"] in paired} for d in found]

    def wake(self, peer_id: str) -> int:
        if self.store.get(peer_id) is None:
            raise ReplicationError("that device is not paired")
        macs = self.store.wake_addresses(peer_id)
        if not macs:
            raise ReplicationError("that device has not said how to wake it; connect to it once while it is on")
        return netinfo.wake(macs)

    async def close(self) -> None:
        for pairing in self.initiated.values():
            link.cancel(pairing)
        for task in list(self._tasks):
            task.cancel()
        await self.set_listener(False)

    def open_pairing(self) -> dict[str, Any]:
        if self.listener is None:
            raise ReplicationError("switch on Replication's listener first, so the other device can reach this one")
        self.listener.open_pairing()
        return self.status()

    def close_pairing(self) -> dict[str, Any]:
        if self.listener is not None:
            self.listener.close_pairing()
        return self.status()

    def pair_with(self, address: str) -> dict[str, Any]:
        host, port = parse_address(address)
        if any(p.state in ("connecting", "compare", "waiting") for p in self.initiated.values()):
            raise ReplicationError("a pairing is already under way")
        pairing = link.Pairing(secrets.token_hex(8), "initiator", f"{host}:{port}")
        self.initiated[pairing.id] = pairing
        self._trim(self.initiated)
        task = asyncio.create_task(link.pair_as_initiator(self.me, self.store, pairing, host, port))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return pairing.public()

    def _pairing(self, pairing_id: str) -> link.Pairing:
        pairing = self.initiated.get(pairing_id)
        if pairing is None and self.listener is not None:
            pairing = self.listener.pairings.get(pairing_id)
        if pairing is None:
            raise ReplicationError("that pairing has ended")
        return pairing

    def answer(self, pairing_id: str, ok: bool) -> dict[str, Any]:
        try:
            link.answer(self._pairing(pairing_id), ok)
        except link.LinkError as exc:
            raise ReplicationError(str(exc)) from exc
        return self.status()

    def cancel(self, pairing_id: str) -> dict[str, Any]:
        link.cancel(self._pairing(pairing_id))
        return self.status()

    @staticmethod
    def _trim(pairings: dict[str, link.Pairing]) -> None:
        ended = [p for p in pairings.values() if p.ended_at is not None]
        for pairing in sorted(ended, key=lambda p: p.ended_at or 0)[:-KEEP_ENDED]:
            pairings.pop(pairing.id, None)

    def status(self) -> dict[str, Any]:
        pairings = list(self.initiated.values())
        if self.listener is not None:
            self._trim(self.listener.pairings)
            pairings += list(self.listener.pairings.values())
        listener = self.listener
        return {
            "available": link.available(),
            "listener": {
                "on": listener is not None,
                "addresses": self.hosts() if listener else [],
                "port": listener.bound_port if listener else self.port,
                "pairingOpen": bool(listener and listener.pairing_open()),
                "pairingSecondsLeft": listener.window_seconds_left() if listener else 0,
            },
            "discovery": {"on": self.responder is not None, "problem": self.discovery_problem if listener else None},
            "peers": self.store.list(),
            "pairings": [p.public() for p in pairings],
        }

    async def check(self, peer_id: str, address: str | None = None) -> dict[str, Any]:
        """Connect to a paired device and time a round trip."""
        peer = self.store.get(peer_id)
        if peer is None:
            raise ReplicationError("that device is not paired")
        host, port = parse_address(address or peer["address"])
        try:
            connection = await link.connect(self.me, self.store, peer_id, host, port)
        except link.LinkError as exc:
            return {"ok": False, "reason": str(exc)}
        try:
            rtt = min([await connection.ping() for _ in range(3)])
        except link.LinkError as exc:
            return {"ok": False, "reason": str(exc)}
        finally:
            await connection.close()
        return {
            "ok": True,
            "address": f"{host}:{port}",
            "rttMs": round(rtt, 1),
            "slow": rtt > policy.SLOW_RTT_MS,
            "overlay": is_overlay(host),
        }

    async def remove(self, peer_id: str) -> dict[str, Any]:
        """Forget a paired device: its key is deleted and its connections closed."""
        if not self.store.remove(peer_id):
            raise ReplicationError("that device is not paired")
        if self.listener is not None:
            await self.listener.drop(peer_id)
        return self.status()


def _firewalld_running(proc_root: str) -> bool:
    try:
        names = os.listdir(proc_root)
    except OSError:
        return False
    for pid in names:
        if not pid.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, pid, "comm"), encoding="utf-8", errors="replace") as handle:
                if handle.read().strip() == "firewalld":
                    return True
        except OSError:
            continue
    return False


def firewall_advice(platform: str, proc_root: str = "/proc") -> str:
    """What the user may need to allow, in plain words (ADR-0056). Keepsake never changes a firewall."""
    port = f"TCP {link.DEFAULT_PORT} and UDP {discovery.PORT}"
    if platform == "windows":
        return (
            "The first time the listener starts, Windows asks whether Python may use the network. "
            f"Allow it on private networks only. If you said no, allow {port} in Windows Defender Firewall."
        )
    if _firewalld_running(proc_root):
        return (
            "This device runs firewalld. Fedora-based systems such as Bazzite allow ports above 1024 on home "
            f"networks by default; if you changed that, allow {port}."
        )
    return f"No firewall was found on this device. If your network blocks devices from each other, allow {port}."


def health_checks(links: Links | None, host: str, proc_root: str = "/proc") -> list[dict[str, Any]]:
    def check(id_: str, label: str, status: str, detail: str, items: list[str] | None = None) -> dict[str, Any]:
        return {"id": id_, "label": label, "status": status, "detail": detail, "items": items or []}

    if not link.available():
        return [
            check(
                "replication-link",
                "Encrypted link",
                "fail",
                "This device's Python cannot make Replication's encrypted link (it has no TLS-PSK), so Replication "
                "stays off. A Keepsake or system update may bring it.",
            )
        ]
    checks = [check("replication-link", "Encrypted link", "ok", "This device can make the encrypted link.")]
    if links is None:
        return checks
    status = links.status()
    listener = status["listener"]
    if listener["on"]:
        where = ", ".join(listener["addresses"]) or "no address"
        detail = f"Listening on {where}, port {listener['port']}."
        checks.append(check("replication-listener", "Listener", "ok", detail))
        problem = status["discovery"]["problem"]
        checks.append(
            check(
                "replication-discovery",
                "Found on the network",
                "warn" if problem else "ok",
                problem or "Other devices can find this one.",
            )
        )
    else:
        checks.append(
            check(
                "replication-listener",
                "Listener",
                "info",
                "Off: other devices cannot reach this one. Switch it on in Devices to pair or to receive games.",
            )
        )
    platform = "windows" if host == "windows" or os.name == "nt" else "linux"
    checks.append(check("replication-firewall", "Firewall", "info", firewall_advice(platform, proc_root)))
    peers = status["peers"]
    checks.append(
        check(
            "replication-peers",
            "Paired devices",
            "info",
            f"{len(peers)} paired." if peers else "None yet. Pair a device in Devices.",
            [p["name"] for p in peers],
        )
    )
    return checks
