"""Replication's device links for the app: the listener switch, pairing, paired devices (slice 17).

The listener is off until the user switches it on, and the pairing window opens only from a
user action (P17, ADR-0016). Addresses are typed by the user or come from a paired device's
record; nothing here reaches a cloud store (ADR-0045).
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import secrets
from typing import Any

from . import link, policy
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


class Links:
    def __init__(self, me: link.Identity, store: PeerStore, bind_host: str, port: int = link.DEFAULT_PORT) -> None:
        self.me = me
        self.store = store
        self.bind_host = bind_host
        self.port = port
        self.listener: link.Listener | None = None
        self.initiated: dict[str, link.Pairing] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def set_listener(self, on: bool) -> dict[str, Any]:
        if on and self.listener is None:
            listener = link.Listener(self.me, self.store, self.bind_host, self.port)
            await listener.start()
            self.listener = listener
        elif not on and self.listener is not None:
            listener, self.listener = self.listener, None
            await listener.stop()
        return self.status()

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
                "address": self.bind_host,
                "port": listener.bound_port if listener else self.port,
                "pairingOpen": bool(listener and listener.pairing_open()),
                "pairingSecondsLeft": listener.window_seconds_left() if listener else 0,
            },
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
