"""The sending side: folders offered to paired devices (slice 18a, ADR-0057).

A share is a folder and its manifest, offered to named paired devices only. They can ask for
the manifest and for single chunks, nothing else: no listing, no paths outside the manifest.
Every chunk is hashed again before it is sent, so a file that changed since the offer is
refused rather than sent wrong.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import stat
from dataclasses import dataclass, field
from typing import Any

from . import manifest as mf
from .link import Reply, ServeError, Session


@dataclass
class Share:
    id: str
    root: str
    manifest: dict[str, Any]
    peers: set[str]
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.files = {e["path"]: e for e in self.manifest["entries"] if e["type"] == "file"}


class Shares:
    def __init__(self) -> None:
        self._shares: dict[str, Share] = {}

    def add(self, root: str, manifest: dict[str, Any], peers: set[str], share_id: str | None = None) -> Share:
        """Offer a folder. ``share_id`` keeps an offer's ID across a restart."""
        share = Share(share_id or secrets.token_hex(16), os.path.abspath(root), manifest, set(peers))
        self._shares[share.id] = share
        return share

    def remove(self, share_id: str) -> None:
        self._shares.pop(share_id, None)

    def get(self, share_id: str) -> Share | None:
        return self._shares.get(share_id)

    def _share(self, session: Session, message: dict[str, Any]) -> Share:
        share = self._shares.get(str(message.get("share", "")))
        if share is None or session.peer_id not in share.peers:
            raise ServeError("that folder is not offered to this device")
        return share

    async def serve_manifest(self, session: Session, message: dict[str, Any]) -> Reply:
        share = self._share(session, message)
        return {"root": share.manifest["root"]}, mf.canonical(share.manifest)

    async def serve_chunk(self, session: Session, message: dict[str, Any]) -> Reply:
        share = self._share(session, message)
        entry = share.files.get(str(message.get("path", "")))
        index = message.get("index")
        if entry is None or not isinstance(index, int) or not 0 <= index < len(entry["chunks"]):
            raise ServeError("that chunk is not part of the offer")
        data = await asyncio.to_thread(read_chunk, share.root, entry, index)
        return {"path": entry["path"], "index": index}, data

    def handlers(self) -> dict[str, Any]:
        return {"manifest": self.serve_manifest, "chunk": self.serve_chunk}


def read_chunk(root: str, entry: dict[str, Any], index: int) -> bytes:
    """One chunk, from the file the manifest names, checked against its hash before sending."""
    path = os.path.join(root, *entry["path"].split("/"))
    real = os.path.realpath(path)
    if os.path.commonpath([real, os.path.realpath(root)]) != os.path.realpath(root):
        raise ServeError("that file is no longer inside the offered folder")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ServeError("that entry is no longer a file")
        os.lseek(fd, index * mf.CHUNK, os.SEEK_SET)
        size = mf.chunk_sizes(int(entry["size"]))[index]
        data = b""
        while len(data) < size:
            block = os.read(fd, size - len(data))
            if not block:
                break
            data += block
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != entry["chunks"][index]:
        raise ServeError("the file changed on the other device since it was offered; offer it again")
    return data
