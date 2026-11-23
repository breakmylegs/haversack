"""Sending looks to the other handheld (R29 stage 1b, ADR-0092): what is offered and where it lands.

Three parts, each chosen by the user, each a set of top-level names inside one folder:

- ``themes``: CSS Loader themes, ``<homebrew>/themes/<folder>`` with a ``theme.json`` (presets are themes);
- ``sounds``: Audio Loader packs, ``<homebrew>/sounds/<folder>`` with a ``pack.json``;
- ``animations``: the boot and sleep videos Haversack has set on the sender (only those three names).

On the receiver, each part is staged beside its destination and then moved in name by name, never
over anything that exists (the rule emulator games follow, ADR-0087). Themes and sound packs go to
the receiver's own ``themes`` and ``sounds`` folders, where the plugins find them. Videos go to
Haversack's own ``looks/animations/From <device>`` folder: they become choices on Device, Looks, and
nothing changes on the receiver's screen until the user picks one there.

No paths cross the wire: only part names, top-level member names, share ids, byte counts and the
sender's chosen device name (P10). Replication carries the offer through an offer-kind handler the
app registers (``Handler``), so it never reaches into this module (P13).
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Any

from . import animations as anim

KIND = "looks"
PARTS = ("themes", "sounds", "animations")
MANIFESTS = {"themes": "theme.json", "sounds": "pack.json"}
MAX_MEMBERS = 300
MEMBER = re.compile(r"^[^/\\\x00]{1,120}$")
OFFER_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
STAGING = ".haversack-looks-"
LABELS = {"themes": "theme", "sounds": "sound pack", "animations": "video"}


class LookPlanError(ValueError):
    pass


def _safe(name: str) -> bool:
    return bool(MEMBER.match(name)) and not name.startswith(".")


def _members(folder: str, manifest: str) -> list[str]:
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    out = []
    for name in names:
        path = os.path.join(folder, name)
        if _safe(name) and not os.path.islink(path) and os.path.isdir(path):
            if os.path.isfile(os.path.join(path, manifest)):
                out.append(name)
    return out[:MAX_MEMBERS]


def available(homebrew: str, animations: anim.Animations) -> dict[str, list[str]]:
    """What this device could send: theme folders, sound pack folders, and the videos Haversack set."""
    videos = animations.status()["videos"]
    return {
        "themes": _members(os.path.join(homebrew, "themes"), MANIFESTS["themes"]),
        "sounds": _members(os.path.join(homebrew, "sounds"), MANIFESTS["sounds"]),
        "animations": sorted(anim.VIDEOS[k] for k, v in videos.items() if v["who"] == "haversack"),
    }


def plan(homebrew: str, animations: anim.Animations, parts: list[str]) -> dict[str, tuple[str, list[str]]]:
    """``{part: (root folder, members)}`` for the parts the user chose, leaving out empty ones."""
    if not parts or any(p not in PARTS for p in parts):
        raise LookPlanError("choose themes, sound packs or animations to send")
    found = available(homebrew, animations)
    roots = {
        "themes": os.path.join(homebrew, "themes"),
        "sounds": os.path.join(homebrew, "sounds"),
        "animations": animations.folder,
    }
    out = {p: (roots[p], found[p]) for p in dict.fromkeys(parts) if found[p]}
    if not out:
        raise LookPlanError("there is nothing of that kind on this device to send")
    return out


def validate(raw: Any) -> dict[str, Any]:
    """The receiver's check of a looks offer: known parts and safe member names only."""
    if not isinstance(raw, dict) or raw.get("kind") != KIND or not OFFER_ID.match(str(raw.get("id", ""))):
        raise LookPlanError("the offer is not valid")
    shares = raw.get("shares")
    if not isinstance(shares, dict) or not shares or set(shares) - set(PARTS):
        raise LookPlanError("the offer is not valid")
    clean: dict[str, Any] = {}
    for part, share in shares.items():
        if not isinstance(share, dict):
            raise LookPlanError("the offer is not valid")
        members = share.get("members")
        if not isinstance(members, list) or not members or len(members) > MAX_MEMBERS:
            raise LookPlanError("the offer is not valid")
        names = [m for m in members if isinstance(m, str)]
        if len(names) != len(members) or not all(_safe(n) for n in names):
            raise LookPlanError("the offer has a name this device will not use")
        if part == "animations" and set(names) - set(anim.VIDEOS.values()):
            raise LookPlanError("the offer has a video this device will not use")
        size = share.get("bytes")
        if not isinstance(share.get("share"), str) or not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise LookPlanError("the offer is not valid")
        clean[part] = {
            "share": share["share"],
            "root": str(share.get("root") or ""),
            "bytes": size,
            "members": sorted(set(names)),
        }
    return {"kind": KIND, "id": raw["id"], "shares": clean}


def destination(part: str, homebrew: str, runtime_dir: str, sender: str) -> str:
    if part in MANIFESTS:
        return os.path.join(homebrew, part)
    folder = re.sub(r"[^\w .,()-]", "", f"From {sender or 'your other device'}")[:60].strip()
    return os.path.join(runtime_dir, "looks", "animations", folder or "From your other device")


def describe(shares: dict[str, Any]) -> str:
    """ "3 themes, 1 sound pack and 2 videos"."""
    bits = []
    for part in PARTS:
        if part in shares:
            n = len(shares[part]["members"])
            bits.append(f"{n} {LABELS[part]}{'' if n == 1 else 's'}")
    return bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + " and " + bits[-1]


class Handler:
    """The offer kind Replication's ``Incoming`` calls for ``looks`` offers (ADR-0092)."""

    kind = KIND
    request = "looks-offer"

    def __init__(self, homebrew: Any, runtime_dir: str, enabled: Any) -> None:
        self.homebrew = homebrew  # callables, so a moved home or a module switched off is seen at once
        self.runtime_dir = runtime_dir
        self.enabled = enabled

    def validate(self, raw: Any) -> dict[str, Any]:
        clean = validate(raw)
        return {**clean, "title": f"Looks: {describe(clean['shares'])}"}

    def targets(self, offer: dict[str, Any], offer_id: str) -> dict[str, str]:
        """A staging folder beside each part's destination, on the same disk."""
        if not self.enabled():
            raise LookPlanError("switch on Looks in Settings, Modules on this device first")
        out: dict[str, str] = {}
        for part in offer["shares"]:
            final = destination(part, self.homebrew(), self.runtime_dir, str(offer.get("from") or ""))
            os.makedirs(final, exist_ok=True)
            out[part] = os.path.join(final, f"{STAGING}{part}-{offer_id}")
            if os.path.lexists(out[part]):
                raise LookPlanError("an earlier copy of this offer is still in the way")
        return out

    def finish(self, offer: dict[str, Any], staged: dict[str, str]) -> dict[str, Any]:
        """Move each staged theme, pack or video in where nothing of that name exists."""
        placed: dict[str, list[str]] = {}
        skipped: dict[str, list[str]] = {}
        for part, path in staged.items():
            final = destination(part, self.homebrew(), self.runtime_dir, str(offer.get("from") or ""))
            placed[part], skipped[part] = [], []
            if not os.path.isdir(path):
                continue
            wanted = set(offer["shares"][part]["members"])
            for name in sorted(os.listdir(path)):
                source, dest = os.path.join(path, name), os.path.join(final, name)
                if name not in wanted:
                    continue  # only what was offered
                if os.path.lexists(dest):
                    skipped[part].append(name)
                    continue
                os.replace(source, dest)
                placed[part].append(name)
            shutil.rmtree(path, ignore_errors=True)
        got = sum(len(v) for v in placed.values())
        kept = sum(len(v) for v in skipped.values())
        reason = f"{got} added" + (f"; {kept} already here, left as they are" if kept else "")
        if placed.get("animations"):
            reason += ". Choose the videos on Device, Looks"
        return {"placed": placed, "skipped": {k: v for k, v in skipped.items() if v}, "reason": reason + "."}
