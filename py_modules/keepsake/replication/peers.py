"""Paired devices and their link keys (slice 17, ADR-0054).

Each paired device has a random 256-bit key, created at pairing and known only to the two
devices. The file is owner-only, and keys never leave this module except to the TLS layer:
``public`` is what the interface sees.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any

from ..fsutil import atomic_write_json, read_json

DEVICE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_NAME = 40
MAX_PEERS = 16
KEY_BYTES = 32


class PeerError(Exception):
    pass


def clean_name(name: Any) -> str:
    text = "".join(ch for ch in str(name or "") if ch.isprintable()).strip()
    return text[:MAX_NAME] or "Unnamed device"


def check_device_id(device_id: Any) -> str:
    if not isinstance(device_id, str) or not DEVICE_ID.match(device_id):
        raise PeerError("that device's identity is not valid")
    return device_id


class PeerStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = read_json(self.path, default={})
        except (OSError, ValueError):
            return {}
        peers = data.get("peers") if isinstance(data, dict) else None
        if not isinstance(peers, dict):
            return {}
        out = {}
        for device_id, peer in peers.items():
            if not (isinstance(peer, dict) and DEVICE_ID.match(str(device_id))):
                continue
            try:
                key = bytes.fromhex(str(peer.get("key", "")))
            except ValueError:
                continue
            if len(key) == KEY_BYTES:
                out[str(device_id)] = peer
        return out

    def _save(self, peers: dict[str, dict[str, Any]]) -> None:
        atomic_write_json(self.path, {"version": 1, "peers": peers}, mode=0o600)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            peers = self._load()
        return sorted((self.public(device_id, peer) for device_id, peer in peers.items()), key=lambda p: p["name"])

    @staticmethod
    def public(device_id: str, peer: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": device_id,
            "name": clean_name(peer.get("name")),
            "address": str(peer.get("address") or ""),
            "pairedAt": float(peer.get("pairedAt") or 0),
            "lastSeen": float(peer.get("lastSeen") or 0),
        }

    def get(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            peer = self._load().get(device_id)
        return self.public(device_id, peer) if peer else None

    def key(self, device_id: str | None) -> bytes | None:
        if not device_id:
            return None
        with self._lock:
            peer = self._load().get(device_id)
        return bytes.fromhex(peer["key"]) if peer else None

    def add(self, device_id: str, name: str, key: bytes, address: str) -> dict[str, Any]:
        check_device_id(device_id)
        if len(key) != KEY_BYTES:
            raise PeerError("a link key is 32 bytes")
        with self._lock:
            peers = self._load()
            if device_id not in peers and len(peers) >= MAX_PEERS:
                raise PeerError(f"at most {MAX_PEERS} devices can be paired; remove one first")
            now = time.time()
            peers[device_id] = {
                "name": clean_name(name),
                "key": key.hex(),
                "address": str(address)[:255],
                "pairedAt": now,
                "lastSeen": now,
            }
            self._save(peers)
            return self.public(device_id, peers[device_id])

    def remove(self, device_id: str) -> bool:
        with self._lock:
            peers = self._load()
            if peers.pop(device_id, None) is None:
                return False
            self._save(peers)
            return True

    def seen(self, device_id: str, address: str | None = None) -> None:
        with self._lock:
            peers = self._load()
            peer = peers.get(device_id)
            if peer is None:
                return
            peer["lastSeen"] = time.time()
            if address:
                peer["address"] = str(address)[:255]
            self._save(peers)
