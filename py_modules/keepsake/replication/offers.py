"""Offers: one device says "here is a game", the other accepts it (slice 19a, ADR-0059).

The sending device prepares the game's shares and sends one ``offer`` message. The receiving
device keeps the offer until its user accepts or declines; nothing is written before that.

Accepting runs the copy, then registers the game in Steam through the Steam Operations
Executor (ADR-0015), moves the prefix into ``compatdata/<new appid>``, sets the program,
start folder, launch options, compatibility tool and artwork, and reads each one back. Every
folder and shortcut it will make is recorded before it is made, so "Stop and remove" can
undo exactly that and nothing else.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import os
import re
import shutil
import stat
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from . import activity, emuplan, emureceive, ongoing, policy, sendgame, transfer
from . import emulators as emu
from . import manifest as mf
from .jobs import Transfers
from .link import ServeError, Session
from .peers import clean_name
from .source import Shares

SCOPES = ("install", "prefix", "tool", "art")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
OFFER_ID = re.compile(r"^[0-9a-f]{16}$")
GAME_KEY = re.compile(r"^[A-Za-z0-9._:\- ]{1,200}$")
MAX_OFFERS = 16
PREFIX_PLACEHOLDER = ".keepsake-prefix-"
BUILT_IN_TOOLS = re.compile(r"^(proton_\w+|steamlinuxruntime\w*)$")
# The states the receiving device tells the sending one about (v0.30.2): every change after an
# answer, so a failure shows on both devices.
TOLD_STATES = ("transferring", "registering", "done", "failed", "declined", "removed")
MAX_REASON = 300
_PATH = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|/|~/)\S*")


def wire_reason(reason: str | None) -> str | None:
    """A reason fit to send to the other device: one line, short, and no device paths (principle 10)."""
    if not reason:
        return None
    text = _PATH.sub("a folder", " ".join(str(reason).split()))
    return text[:MAX_REASON]


class OfferError(Exception):
    pass


def only(members: list[str]) -> Any:
    """An exclude function keeping just ``members`` (paths relative to the root), what is inside them,
    and the folders on the way to them."""
    keep = {m.strip("/") for m in members}
    ancestors = {"/".join(m.split("/")[:i]) for m in keep for i in range(1, m.count("/") + 1)}

    def exclude(rel: str) -> bool:
        return not (rel in keep or rel in ancestors or any(rel.startswith(f"{m}/") for m in keep))

    return exclude


# The wire format


def validate(offer: Any) -> dict[str, Any]:
    """An offer from another device, checked field by field. Unknown fields are dropped."""
    if not isinstance(offer, dict):
        raise OfferError("the offer is not valid")
    offer_id = str(offer.get("id", ""))
    title = " ".join(str(offer.get("title", "")).split())
    if not OFFER_ID.match(offer_id) or not sendgame.TITLE.match(title):
        raise OfferError("the offer is not valid")
    shares_in = offer.get("shares")
    if not isinstance(shares_in, dict) or not shares_in or set(shares_in) - set(SCOPES):
        raise OfferError("the offer is not valid")
    shares = {}
    for scope, share in shares_in.items():
        if not (
            isinstance(share, dict)
            and HEX32.match(str(share.get("share", "")))
            and HEX64.match(str(share.get("root", "")))
            and isinstance(share.get("bytes"), int)
            and share["bytes"] >= 0
        ):
            raise OfferError("the offer is not valid")
        shares[scope] = {"share": share["share"], "root": share["root"], "bytes": share["bytes"]}
    if "install" not in shares and "prefix" not in shares:
        raise OfferError("the offer holds no game")
    update = None
    if offer.get("update") is not None:  # an update to a game already linked (ADR-0060)
        raw = offer["update"]
        base = raw.get("base") if isinstance(raw, dict) else None
        if (
            not isinstance(raw, dict)
            or not OFFER_ID.match(str(raw.get("link", "")))
            or not isinstance(base, dict)
            or set(base) - {"install", "prefix"}
            or not all(HEX64.match(str(v)) for v in base.values())
            or set(shares) - {"install", "prefix"}
        ):
            raise OfferError("the update is not valid")
        update = {"link": raw["link"], "base": dict(base)}
    refs = {}
    for name in ("exe", "startDir"):
        if update is not None:
            break  # an update changes files only: the shortcut stays as it is
        ref = offer.get(name)
        if not isinstance(ref, dict) or ref.get("scope") not in ("install", "prefix") or ref["scope"] not in shares:
            raise OfferError("the offer is not valid")
        path = str(ref.get("path", ""))
        refs[name] = {"scope": ref["scope"], "path": path if path == "." else mf.check_path(path)}
    options = str(offer.get("launchOptions") or "")
    if len(options) > sendgame.MAX_OPTIONS or any(ch in options for ch in "\r\n\x00"):
        raise OfferError("the offer's launch options are not valid")
    if re.search(r"\{(?!install\}|prefix\}|home\})[a-z]+\}", options):
        raise OfferError("the offer's launch options are not valid")
    tool = offer.get("compatTool")
    if tool is not None and not sendgame.TOOL_NAME.match(str(tool)):
        raise OfferError("the offer's compatibility tool is not valid")
    art = []
    for item in offer.get("art") or []:
        if not isinstance(item, dict) or item.get("assetType") not in (0, 1, 2, 3) or "art" not in shares:
            raise OfferError("the offer's artwork is not valid")
        name = str(item.get("file", ""))
        if not re.fullmatch(r"(capsule|hero|logo|header)\.(png|jpg|jpeg)", name):
            raise OfferError("the offer's artwork is not valid")
        art.append({"assetType": item["assetType"], "file": name})
    game_key = offer.get("gameKey")
    if game_key is not None and not GAME_KEY.match(str(game_key)):
        raise OfferError("the offer's game key is not valid")
    pull = offer.get("pull")  # the pull request this offer answers (v0.31.0)
    if pull is not None and not OFFER_ID.match(str(pull)):
        raise OfferError("the offer is not valid")
    return {
        "id": offer_id,
        "title": title,
        "from": clean_name((offer.get("from") or {}).get("name") if isinstance(offer.get("from"), dict) else None),
        "shares": shares,
        "exe": refs.get("exe"),
        "startDir": refs.get("startDir"),
        "update": update,
        "launchOptions": options,
        "droppedOptions": [str(x)[:200] for x in offer.get("droppedOptions") or []][:10],
        "compatTool": tool,
        "art": art,
        "gameKey": game_key,
        "savesEnabled": bool(offer.get("savesEnabled")),
        "pull": pull,
    }


def _existing(folder: str) -> str:
    """The nearest folder that exists, for a free-space reading before anything is made."""
    path = os.path.abspath(folder)
    while not os.path.isdir(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)
    return path


def safe_folder(title: str) -> str:
    name = re.sub(r"[^\w .,'()&+-]", "", title).strip(" .")
    return name[:80] or "Game"


def _remove_tree(path: str) -> None:
    def writable(func: Any, target: str, _exc: Any) -> None:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        func(target)

    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    elif sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:  # pragma: no cover - Python 3.11
        shutil.rmtree(path, onerror=writable)


# The sending side


async def send_offer(connection: Any, wire: dict[str, Any]) -> None:
    """Tell a paired device about a game on offer (the ``offer`` request, ADR-0059)."""
    reply = await connection.request({"type": "offer", "offer": wire})
    if reply.get("type") != "offer-received" or reply.get("id") != wire["id"]:
        raise OfferError("the other device did not take the offer")


class Outgoing:
    """Offers this device made: their shares, kept across a restart so a transfer can resume."""

    def __init__(self, path: str, work_dir: str, shares: Shares) -> None:
        self.path = path
        self.work_dir = work_dir
        self.shares = shares
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        with self._lock:
            data = read_json(self.path, default={})
        offers = data.get("offers") if isinstance(data, dict) else None
        return offers if isinstance(offers, dict) else {}

    def _save(self, offers: dict[str, Any]) -> None:
        with self._lock:
            atomic_write_json(self.path, {"version": 1, "offers": offers})

    def restore(self) -> int:
        """Offer again, after a restart, every share this device had offered."""
        count = 0
        for record in self._load().values():
            for scope in record.get("shares", {}).values():
                try:
                    with open(scope["manifestFile"], encoding="utf-8") as handle:
                        manifest = json.load(handle)
                except (OSError, ValueError, KeyError):
                    continue
                self.shares.add(scope["root"], manifest, {record["peer"]}, share_id=scope["share"])
                count += 1
        return count

    def prepare(self, plan: sendgame.Plan, peer_id: str, extra: dict[str, Any]) -> dict[str, Any]:
        """Hash the game and offer its shares to ``peer_id``. Slow for a large game: run in a thread."""
        offers = self._load()
        if len(offers) >= MAX_OFFERS:
            raise OfferError(f"at most {MAX_OFFERS} games can be on offer; withdraw one first")
        offer_id = sendgame.new_offer_id()
        folder = os.path.join(self.work_dir, offer_id)
        os.makedirs(folder, exist_ok=True)
        art_folder = sendgame.stage_art(plan, os.path.join(folder, "art"))
        manifests = sendgame.build_manifests(plan, art_folder)
        roots = {**plan.roots, **({"art": art_folder} if art_folder else {})}
        record_shares, wire_shares = {}, {}
        for scope, manifest in manifests.items():
            manifest_file = os.path.join(folder, f"{scope}.json")
            atomic_write_json(manifest_file, manifest)
            share = self.shares.add(roots[scope], manifest, {peer_id})
            record_shares[scope] = {"share": share.id, "root": roots[scope], "manifestFile": manifest_file}
            wire_shares[scope] = {"share": share.id, "root": manifest["root"], "bytes": mf.total_bytes(manifest)}
        wire = {
            "id": offer_id,
            "title": plan.title,
            "shares": wire_shares,
            "exe": plan.exe,
            "startDir": plan.start_dir,
            "launchOptions": plan.launch_options,
            "droppedOptions": plan.dropped_options,
            "compatTool": plan.compat_tool,
            "art": [{"assetType": a["assetType"], "file": a["file"]} for a in plan.art],
            **extra,
        }
        offers[offer_id] = {"peer": peer_id, "title": plan.title, "shares": record_shares, "created": time.time()}
        self._save(offers)
        return wire

    def prepare_emulator(self, plan: emuplan.EmuPlan, peer_id: str, extra: dict[str, Any]) -> dict[str, Any]:
        """Hash an emulator game's parts and offer them to ``peer_id`` (R26 stage 2). Slow: run in a thread."""
        offers = self._load()
        if len(offers) >= MAX_OFFERS:
            raise OfferError(f"at most {MAX_OFFERS} games can be on offer; withdraw one first")
        offer_id = sendgame.new_offer_id()
        folder = os.path.join(self.work_dir, offer_id)
        os.makedirs(folder, exist_ok=True)
        record_shares, wire_shares = {}, {}
        for part, path in plan.roots.items():
            if part == "rom":
                root, exclude = path, only(plan.rom_files)
            elif os.path.isfile(path):
                root, exclude = os.path.dirname(path), only([os.path.basename(path)])
            else:
                root, exclude = path, (lambda _rel: False)
            manifest = mf.build(root, exclude)
            manifest_file = os.path.join(folder, f"{part}.json")
            atomic_write_json(manifest_file, manifest)
            share = self.shares.add(root, manifest, {peer_id})
            record_shares[part] = {"share": share.id, "root": root, "manifestFile": manifest_file}
            wire_shares[part] = {"share": share.id, "root": manifest["root"], "bytes": mf.total_bytes(manifest)}
        wire = {
            "kind": "emulator",
            "id": offer_id,
            "system": plan.system,
            "unit": plan.unit,
            "emulator": plan.emulator,
            "shares": wire_shares,
            **extra,
        }
        offers[offer_id] = {"peer": peer_id, "title": plan.unit, "shares": record_shares, "created": time.time()}
        self._save(offers)
        return wire

    def prepare_parts(
        self,
        kind: str,
        title: str,
        parts: dict[str, tuple[str, builtins.list[str]]],
        peer_id: str,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        """Offer chosen top-level ``members`` of folders to ``peer_id``, for an offer kind another module
        owns (R29 stage 1b, ADR-0092): ``{part: (root, members)}``. Slow: run in a thread."""
        offers = self._load()
        if len(offers) >= MAX_OFFERS:
            raise OfferError(f"at most {MAX_OFFERS} games can be on offer; withdraw one first")
        offer_id = sendgame.new_offer_id()
        folder = os.path.join(self.work_dir, offer_id)
        os.makedirs(folder, exist_ok=True)
        record_shares, wire_shares = {}, {}
        for part, (root, members) in parts.items():
            manifest = mf.build(root, only(members))
            manifest_file = os.path.join(folder, f"{part}.json")
            atomic_write_json(manifest_file, manifest)
            share = self.shares.add(root, manifest, {peer_id})
            record_shares[part] = {"share": share.id, "root": root, "manifestFile": manifest_file}
            wire_shares[part] = {
                "share": share.id,
                "root": manifest["root"],
                "bytes": mf.total_bytes(manifest),
                "members": sorted(members),
            }
        wire = {"kind": kind, "id": offer_id, "shares": wire_shares, **extra}
        offers[offer_id] = {"peer": peer_id, "title": title, "shares": record_shares, "created": time.time()}
        self._save(offers)
        return wire

    def prepare_update(
        self,
        link_id: str,
        title: str,
        scopes: dict[str, str],
        keep: dict[str, builtins.list[str]],
        base: dict[str, str],
        peer_id: str,
        extra: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Offer a linked game's changed files. Returns the offer and the roots it carries."""
        offers = self._load()
        if len(offers) >= MAX_OFFERS:
            raise OfferError(f"at most {MAX_OFFERS} games can be on offer; withdraw one first")
        offer_id = sendgame.new_offer_id()
        folder = os.path.join(self.work_dir, offer_id)
        os.makedirs(folder, exist_ok=True)
        manifests = ongoing.scan(scopes, keep)
        changed = {s: m for s, m in manifests.items() if base.get(s) != m["root"]}
        if not changed:
            raise OfferError("nothing has changed since the last sync")
        record_shares, wire_shares = {}, {}
        for scope, manifest in changed.items():
            manifest_file = os.path.join(folder, f"{scope}.json")
            atomic_write_json(manifest_file, manifest)
            share = self.shares.add(scopes[scope], manifest, {peer_id})
            record_shares[scope] = {"share": share.id, "root": scopes[scope], "manifestFile": manifest_file}
            wire_shares[scope] = {"share": share.id, "root": manifest["root"], "bytes": mf.total_bytes(manifest)}
        wire = {
            "id": offer_id,
            "title": title,
            "shares": wire_shares,
            "update": {"link": link_id, "base": {s: base[s] for s in changed if s in base}},
            **extra,
        }
        offers[offer_id] = {
            "peer": peer_id,
            "title": title,
            "shares": record_shares,
            "created": time.time(),
            "update": True,
        }
        self._save(offers)
        return wire, {s: m["root"] for s, m in manifests.items()}

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": k,
                "title": v.get("title"),
                "peer": v.get("peer"),
                "created": v.get("created"),
                "remoteState": v.get("remoteState", "offered"),
                "remoteReason": v.get("remoteReason"),
            }
            for k, v in sorted(self._load().items(), key=lambda kv: -float(kv[1].get("created") or 0))
        ]

    def record_state(
        self, peer_id: str, offer_id: Any, state: Any, reason: Any, progress: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """The other device's news about an offer this device made to it, and only to it.

        ``progress`` holds the bar's numbers (v0.31.0). Returns the offer with ``stateChanged``
        when anything changed, else None.
        """
        if not isinstance(offer_id, str) or not OFFER_ID.match(offer_id) or state not in TOLD_STATES:
            raise ServeError("that is not an offer state")
        offers = self._load()
        record = offers.get(offer_id)
        if record is None or record.get("peer") != peer_id:
            raise ServeError("no such offer was made to this device")
        reason = wire_reason(reason) if isinstance(reason, str) else None
        numbers = activity.clean_progress(progress or {})
        changed = record.get("remoteState") != state or record.get("remoteReason") != reason
        if not changed and all(record.get(k) == v for k, v in numbers.items()):
            return None
        record.update(remoteState=state, remoteReason=reason, remoteAt=time.time(), **numbers)
        self._save(offers)
        return {
            "id": offer_id,
            "title": record.get("title"),
            "state": state,
            "reason": reason,
            "stateChanged": changed,
        }

    def activity(self, peer_names: dict[str, str]) -> builtins.list[dict[str, Any]]:
        """Each offer as a bar, as the receiving device last described it (v0.31.0)."""
        return [
            activity.sending(k, v, peer_names.get(str(v.get("peer")), "the other device"))
            for k, v in sorted(self._load().items(), key=lambda kv: -float(kv[1].get("created") or 0))
        ]

    def peer_of(self, offer_id: str) -> str | None:
        record = self._load().get(offer_id)
        return str(record["peer"]) if record else None

    def redacted(self) -> builtins.list[dict[str, Any]]:
        """For the Device checks' export: states only, no titles, names or paths."""
        return [
            {
                "id": k[:6],
                "remoteState": v.get("remoteState", "offered"),
                "remoteReason": v.get("remoteReason"),
                "scopes": sorted(v.get("shares", {})),
                "ageSeconds": int(time.time() - float(v.get("created") or 0)),
            }
            for k, v in self._load().items()
        ]

    def withdraw(self, offer_id: str) -> None:
        offers = self._load()
        record = offers.pop(offer_id, None)
        if record is None:
            raise OfferError("that offer has gone")
        for scope in record.get("shares", {}).values():
            self.shares.remove(scope["share"])
        self._save(offers)
        _remove_tree(os.path.join(self.work_dir, offer_id))  # the manifests and the artwork copies only


# The receiving side


class Incoming:
    """Offers this device received, and accepting them through to a game in Steam."""

    def __init__(
        self,
        path: str,
        transfers: Transfers,
        enqueue_op: Callable[[str, dict[str, Any]], int],
        places: Callable[[], dict[str, str]],
        on_done: Callable[[dict[str, Any]], None] | None = None,
        on_change: Callable[[], None] | None = None,
        on_offer: Callable[[dict[str, Any]], None] | None = None,
        on_state: Callable[[str, dict[str, Any]], None] | None = None,
        kinds: dict[str, Any] | None = None,
    ) -> None:
        self.path = path
        # Offer kinds other modules own (ADR-0092): each has validate, targets and finish, so Replication
        # carries them without reaching into those modules (P13).
        self.kinds = dict(kinds or {})
        self.transfers = transfers
        self.enqueue_op = enqueue_op
        self.places = places  # libraryRoot, compatdata, tools, art and home on this device
        self.on_done = on_done
        self.on_change = on_change
        self.on_offer = on_offer  # told about each new offer, so a game set to auto can take its update
        self.on_state = on_state  # told when an offer's state changes, to tell the sending device (v0.30.2)
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        with self._lock:
            data = read_json(self.path, default={})
        offers = data.get("offers") if isinstance(data, dict) else None
        return offers if isinstance(offers, dict) else {}

    def _save(self, offers: dict[str, Any]) -> None:
        with self._lock:
            atomic_write_json(self.path, {"version": 1, "offers": offers})

    def _update(self, offer_id: str, **changes: Any) -> dict[str, Any]:
        offers = self._load()
        record: dict[str, Any] | None = offers.get(offer_id)
        if record is None:
            raise OfferError("that offer has gone")
        before = record.get("state")
        record.update(changes)
        self._save(offers)
        self._changed()
        if record.get("state") != before:
            self._tell(offer_id, record)
        return record

    def _tell(self, offer_id: str, record: dict[str, Any]) -> None:
        if self.on_state and record.get("state") in TOLD_STATES:
            self.on_state(offer_id, record)

    def fail(self, offer_id: str, reason: str) -> None:
        """An offer that cannot go on: shown as failed, with the reason, on both devices."""
        try:
            self._update(offer_id, state="failed", reason=reason)
        except OfferError:
            pass  # removed meanwhile

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    # From the other device

    async def handle_offer(self, session: Session, message: dict[str, Any]) -> dict[str, Any]:
        """The ``offer`` request from a paired device (ADR-0059). Nothing is written but the offer itself."""
        try:
            offer = validate(message.get("offer"))
        except (OfferError, mf.ManifestError) as exc:
            raise ServeError(str(exc)) from exc
        offers = self._load()
        if offer["id"] not in offers and sum(1 for r in offers.values() if r["state"] == "offered") >= MAX_OFFERS:
            raise ServeError("that device already has too many offers waiting")
        offers.setdefault(
            offer["id"], {"offer": offer, "peer": session.peer_id, "state": "offered", "received": time.time()}
        )
        new = offer["id"] not in self._load()
        self._save(offers)
        self._changed()
        if new and self.on_offer:
            self.on_offer(offer)
        return {"type": "offer-received", "id": offer["id"]}

    async def handle_emu_offer(self, session: Session, message: dict[str, Any]) -> dict[str, Any]:
        """The ``emu-offer`` request (R26 stage 2): an emulator game, checked by its own validator."""
        raw = message.get("offer")
        try:
            clean = emuplan.validate(raw)
        except emuplan.EmuPlanError as exc:
            raise ServeError(str(exc)) from exc
        if not OFFER_ID.match(clean["id"]):
            raise ServeError("the offer is not valid")
        sender = (
            (raw.get("from") or {}).get("name") if isinstance(raw, dict) and isinstance(raw.get("from"), dict) else None
        )
        offer = {
            **clean,
            "title": clean["unit"],
            "from": clean_name(sender),
            "compatTool": None,
            "art": [],
            "update": None,
            "launchOptions": "",
            "droppedOptions": [],
            "gameKey": None,
            "savesEnabled": False,
            "pull": None,
        }
        offers = self._load()
        if offer["id"] not in offers and sum(1 for r in offers.values() if r["state"] == "offered") >= MAX_OFFERS:
            raise ServeError("that device already has too many offers waiting")
        new = offer["id"] not in offers
        offers.setdefault(
            offer["id"], {"offer": offer, "peer": session.peer_id, "state": "offered", "received": time.time()}
        )
        self._save(offers)
        self._changed()
        if new and self.on_offer:
            self.on_offer(offer)
        return {"type": "offer-received", "id": offer["id"]}

    def kind_handler(self, kind: str) -> Callable[[Session, dict[str, Any]], Awaitable[dict[str, Any]]]:
        """The request handler for an offer kind another module owns (``looks-offer``, ADR-0092)."""

        async def handle(session: Session, message: dict[str, Any]) -> dict[str, Any]:
            owner = self.kinds.get(kind)
            raw = message.get("offer")
            if owner is None:
                raise ServeError(f"this device does not take {kind} offers")
            try:
                clean = owner.validate(raw)
            except ValueError as exc:
                raise ServeError(str(exc)) from exc
            if not OFFER_ID.match(str(clean.get("id", ""))):
                raise ServeError("the offer is not valid")
            sender = (
                (raw.get("from") or {}).get("name")
                if isinstance(raw, dict) and isinstance(raw.get("from"), dict)
                else None
            )
            offer = {
                **clean,
                "kind": kind,
                "from": clean_name(sender),
                "compatTool": None,
                "art": [],
                "update": None,
                "launchOptions": "",
                "droppedOptions": [],
                "gameKey": None,
                "savesEnabled": False,
                "pull": None,
            }
            offers = self._load()
            if offer["id"] not in offers and sum(1 for r in offers.values() if r["state"] == "offered") >= MAX_OFFERS:
                raise ServeError("that device already has too many offers waiting")
            new = offer["id"] not in offers
            offers.setdefault(
                offer["id"], {"offer": offer, "peer": session.peer_id, "state": "offered", "received": time.time()}
            )
            self._save(offers)
            self._changed()
            if new and self.on_offer:
                self.on_offer(offer)
            return {"type": "offer-received", "id": offer["id"]}

        return handle

    def _emu_places(self) -> tuple[str, str]:
        home = self.places().get("home", "")
        setup = emu.emudeck(home) or emu.retrodeck(home)
        if not home or setup is None:
            raise OfferError("this device has no emulator setup (EmuDeck or RetroDECK)")
        return home, setup["romsPath"]

    # The user's choices

    def list(self) -> list[dict[str, Any]]:
        out = []
        for offer_id, record in sorted(self._load().items(), key=lambda kv: -float(kv[1].get("received") or 0)):
            offer = record["offer"]
            out.append(
                {
                    "id": offer_id,
                    "title": offer["title"],
                    "from": offer["from"],
                    "peer": record["peer"],
                    "state": record["state"],
                    "reason": record.get("reason"),
                    "bytes": sum(s["bytes"] for s in offer["shares"].values()),
                    "compatTool": offer["compatTool"],
                    "toolOffered": "tool" in offer["shares"],
                    "droppedOptions": offer["droppedOptions"],
                    "appid": record.get("appid"),
                    "jobs": record.get("jobs", {}),
                    "update": bool(offer.get("update")),
                    "link": (offer.get("update") or {}).get("link"),
                }
            )
        return out

    def dismiss(self, offer_id: str) -> None:
        """Forget a finished offer. The game it installed stays: this only clears the list."""
        offers = self._load()
        record = offers.get(offer_id)
        if record is None or record["state"] != "done":
            raise OfferError("only a finished game can be cleared from the list")
        offers.pop(offer_id)
        self._save(offers)
        self._changed()

    def decline(self, offer_id: str) -> None:
        offers = self._load()
        record = offers.get(offer_id)
        if record is None or record["state"] != "offered":
            raise OfferError("only an offer you have not accepted can be declined")
        offers.pop(offer_id)
        self._save(offers)
        self._changed()
        self._tell(offer_id, {**record, "state": "declined", "reason": None})

    def space_check(self, sizes: dict[str, int], tool: str | None) -> dict[str, Any]:
        """Before the other device reads a game's files: does it fit here? (v0.31.0)

        ``sizes`` is bytes per scope. Scopes on one file system add up; each needs the margin.
        Writes nothing.
        """
        places = self.places()
        if sizes.get("install") and (not places.get("library") or not os.path.isdir(places["library"])):
            return {"ok": False, "reason": "choose where games are installed first (Settings, Install)"}
        if sizes.get("prefix") and (not places.get("compatdata") or not os.path.isdir(places["compatdata"])):
            return {"ok": False, "reason": "Steam's compatdata folder was not found on this device"}
        tool_needed = (
            bool(tool)
            and not BUILT_IN_TOOLS.match(str(tool))
            and not os.path.isdir(os.path.join(places.get("tools", ""), str(tool)))
        )
        where = {"install": places.get("library"), "prefix": places.get("compatdata"), "art": places.get("art")}
        if tool_needed:
            where["tool"] = places.get("tools")
        by_device: dict[int, tuple[str, int]] = {}
        for scope, size in sizes.items():
            folder = where.get(scope)
            if not folder or not size:
                continue
            existing = _existing(folder)
            device = os.stat(existing).st_dev
            known = by_device.get(device, (existing, 0))
            by_device[device] = (known[0], known[1] + int(size))
        needed_all = free_all = 0
        for folder, size in by_device.values():
            needed, free = policy.space_needed(size), shutil.disk_usage(folder).free
            if free < needed:
                return {"ok": False, "needed": needed, "free": free, "reason": None}
            needed_all, free_all = needed_all + needed, max(free_all, free)
        return {"ok": True, "needed": needed_all, "free": free_all, "reason": None}

    async def handle_space(self, session: Session, message: dict[str, Any]) -> dict[str, Any]:
        """The ``space-check`` request from a paired device about to send a game (v0.31.0)."""
        sizes = message.get("bytes")
        tool = message.get("compatTool")
        if (
            not isinstance(sizes, dict)
            or set(sizes) - set(SCOPES)
            or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 2**53 for v in sizes.values())
            or (tool is not None and not sendgame.TOOL_NAME.match(str(tool)))
        ):
            raise ServeError("that is not a space check")
        result = await asyncio.to_thread(self.space_check, {str(k): int(v) for k, v in sizes.items()}, tool)
        return {"type": "space", **result}

    async def handle_stop(self, session: Session, message: dict[str, Any]) -> dict[str, Any]:
        """The ``offer-stop`` request: the sending device pressed Stop and remove (v0.31.0)."""
        offer_id = message.get("id")
        record = self._load().get(offer_id) if isinstance(offer_id, str) and OFFER_ID.match(offer_id) else None
        if record is None or record.get("peer") != session.peer_id:
            raise ServeError("no such game is coming from your device")
        await self.stop(str(offer_id))
        return {"type": "offer-stopped", "id": offer_id}

    def activity(self, peer_names: dict[str, str]) -> builtins.list[dict[str, Any]]:
        """Each received offer as a bar (v0.31.0)."""
        out = []
        for offer_id, record in sorted(self._load().items(), key=lambda kv: -float(kv[1].get("received") or 0)):
            jobs = {j: self.transfers.jobs[j] for j in record.get("jobs", {}).values() if j in self.transfers.jobs}
            out.append(
                activity.receiving(offer_id, record, jobs, peer_names.get(str(record["peer"]), record["offer"]["from"]))
            )
        return out

    def preflight(self, offer_id: str, copy_tool: bool) -> dict[str, Any]:
        """Where everything would go, and whether it fits. Raises OfferError when it cannot start."""
        record = self._load().get(offer_id)
        if record is None:
            raise OfferError("that offer has gone")
        offer, places = record["offer"], self.places()
        targets: dict[str, str] = {}
        owner = self.kinds.get(str(offer.get("kind")))
        if owner is not None:
            try:
                targets = owner.targets(offer, offer_id)
            except (ValueError, OSError) as exc:
                raise OfferError(str(exc)) from exc
            for scope, target in targets.items():
                parent = os.path.dirname(target)
                needed = policy.space_needed(offer["shares"][scope]["bytes"])
                if shutil.disk_usage(parent).free < needed:
                    raise OfferError(f"not enough space in {parent}")
            return {"targets": targets, "toolMissing": False}
        if offer.get("kind") == "emulator":
            home, roms = self._emu_places()
            try:
                targets = emureceive.targets(offer, offer_id, home, roms)
            except (emureceive.EmuReceiveError, emuplan.EmuPlanError) as exc:
                raise OfferError(str(exc)) from exc
            for scope, target in targets.items():
                parent = os.path.dirname(target)
                needed = policy.space_needed(offer["shares"][scope]["bytes"])
                if shutil.disk_usage(parent).free < needed:
                    raise OfferError(f"not enough space in {parent}")
            return {"targets": targets, "toolMissing": False}
        if "install" in offer["shares"]:
            if not places.get("library") or not os.path.isdir(places["library"]):
                raise OfferError("choose where games are installed first (Settings, Install)")
            targets["install"] = os.path.join(places["library"], safe_folder(offer["title"]))
            if os.path.lexists(targets["install"]):
                raise OfferError(f"{targets['install']} already exists; rename or remove it first")
        if "prefix" in offer["shares"]:
            if not places.get("compatdata") or not os.path.isdir(places["compatdata"]):
                raise OfferError("Steam's compatdata folder was not found on this device")
            targets["prefix"] = os.path.join(places["compatdata"], f"{PREFIX_PLACEHOLDER}{offer_id}")
        tool = offer["compatTool"]
        tool_missing = (
            bool(tool)
            and not BUILT_IN_TOOLS.match(str(tool))
            and not os.path.isdir(os.path.join(places.get("tools", ""), str(tool)))
        )
        if tool_missing:
            if copy_tool and "tool" in offer["shares"]:
                targets["tool"] = os.path.join(places["tools"], str(tool))
            elif "tool" in offer["shares"]:
                raise OfferError(f"this device does not have {tool}; choose to copy it from the other device")
            else:
                raise OfferError(f"this device does not have {tool}, and the other device cannot send it; install it")
        if offer["art"] and "art" in offer["shares"]:
            targets["art"] = os.path.join(places["art"], offer_id)
        by_device: dict[int, tuple[str, int]] = {}
        for scope, target in targets.items():
            parent = os.path.dirname(target)
            os.makedirs(parent, exist_ok=True)
            device = os.stat(parent).st_dev
            known = by_device.get(device, (parent, 0))
            by_device[device] = (known[0], known[1] + offer["shares"][scope]["bytes"])
        for parent, size in by_device.values():
            free = shutil.disk_usage(parent).free
            if free < policy.space_needed(size):
                raise OfferError(
                    f"not enough space in {parent}: {policy.space_needed(size) // 2**30} GiB needed with margin, "
                    f"{free // 2**30} GiB free"
                )
        return {"targets": targets, "toolMissing": tool_missing}

    def accept(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        """Start the copy, on the event loop. Only from a user action."""
        self.start_jobs(offer_id, self.begin(offer_id, copy_tool))
        return self._public(offer_id)

    def start_jobs(self, offer_id: str, jobs: builtins.list[transfer.Job]) -> None:
        """Start the copies ``begin`` planned. Must run on the event loop: a transfer is an asyncio task.

        A copy that cannot start fails the offer with the reason, so it never sits "transferring"
        with nothing running (the v0.30.1 stall).
        """
        for job in jobs:
            try:
                self.transfers.start(job)
            except (transfer.TransferError, OSError, RuntimeError) as exc:
                for started in jobs:
                    task = self.transfers.tasks.get(started.id)
                    if task is not None:
                        task.cancel()
                self.fail(offer_id, f"the copy could not start: {exc}")
                return

    def begin(self, offer_id: str, copy_tool: bool = False) -> builtins.list[transfer.Job]:
        """Check, record and plan the copy without starting it (safe in a worker thread)."""
        record = self._load().get(offer_id)
        if record is None or record["state"] != "offered":
            raise OfferError("that offer is not waiting for an answer")
        checked = self.preflight(offer_id, copy_tool)
        offer = record["offer"]
        # Everything this offer will make is recorded first (ADR-0045 rule 4).
        record = self._update(offer_id, state="transferring", targets=checked["targets"], created=[], jobs={})
        jobs, planned = {}, []
        for scope, target in checked["targets"].items():
            share = offer["shares"][scope]
            job = transfer.Job(
                id=f"{offer_id}-{scope}",
                peer_id=record["peer"],
                share=share["share"],
                root=share["root"],
                target=target,
                peers=[record["peer"]],
            )
            planned.append(job)
            jobs[scope] = job.id
        self._update(offer_id, jobs=jobs)
        return planned

    def _public(self, offer_id: str) -> dict[str, Any]:
        return next(o for o in self.list() if o["id"] == offer_id)

    def accept_update(
        self, offer_id: str, scopes: dict[str, str], keep: dict[str, builtins.list[str]]
    ) -> dict[str, Any]:
        """``begin_update`` then start, on the event loop."""
        self.start_jobs(offer_id, self.begin_update(offer_id, scopes, keep))
        return self._public(offer_id)

    def begin_update(
        self, offer_id: str, scopes: dict[str, str], keep: dict[str, builtins.list[str]]
    ) -> builtins.list[transfer.Job]:
        """Apply an update into the game's existing folders, keeping this device's saves and settings.

        The folders are the game's own, not this offer's: "Stop and remove" never deletes them, it
        only stops the copy, and a stopped update leaves the game exactly as it was.
        """
        record = self._load().get(offer_id)
        if record is None or record["state"] != "offered" or not record["offer"].get("update"):
            raise OfferError("that update is not waiting for an answer")
        offer = record["offer"]
        targets = {}
        for scope in offer["shares"]:
            target = scopes.get(scope)
            if not target or not os.path.isdir(target):
                raise OfferError(f"the game's {scope} folder was not found on this device")
            targets[scope] = target
        for scope, target in targets.items():
            needed = policy.space_needed(offer["shares"][scope]["bytes"])
            if shutil.disk_usage(os.path.dirname(target)).free < needed:
                raise OfferError(f"not enough space beside {target} for the update")
        self._update(offer_id, state="transferring", updateTargets=targets, jobs={})
        jobs, planned = {}, []
        for scope, target in targets.items():
            share = offer["shares"][scope]
            job = transfer.Job(
                id=f"{offer_id}-{scope}",
                peer_id=record["peer"],
                share=share["share"],
                root=share["root"],
                target=target,
                peers=[record["peer"]],
                keep=list(keep.get(scope, [])),
            )
            planned.append(job)
            jobs[scope] = job.id
        self._update(offer_id, jobs=jobs)
        return planned

    # As the copy and the Steam operations finish

    def job_finished(self, job: transfer.Job) -> None:
        for offer_id, record in self._load().items():
            if job.id not in record.get("jobs", {}).values() or record["state"] != "transferring":
                continue
            if job.state != "done":
                if job.state == "failed":
                    self._update(offer_id, state="failed", reason=job.reason or "the copy failed")
                return
            done = set(record.get("doneScopes", [])) | {next(s for s, j in record["jobs"].items() if j == job.id)}
            record = self._update(offer_id, doneScopes=sorted(done))
            if done >= set(record["jobs"]):
                if record["offer"].get("kind") in self.kinds:
                    self._kind_finish(offer_id)
                elif record["offer"].get("kind") == "emulator":
                    self._emu_finish(offer_id)
                elif record["offer"].get("update"):
                    record = self._update(offer_id, state="done")  # files only: the shortcut stays as it is
                    if self.on_done:
                        self.on_done(record)
                else:
                    self._register(offer_id)

    def _kind_finish(self, offer_id: str) -> None:
        """Hand the copied parts to the module that owns the offer kind, which puts them in place."""
        record = self._load()[offer_id]
        offer = record["offer"]
        try:
            done = self.kinds[offer["kind"]].finish(offer, record["targets"])
        except (OSError, ValueError) as exc:
            self._update(offer_id, state="failed", reason=f"the copy could not be put in place: {exc}")
            return
        record = self._update(
            offer_id, state="done", placed=done["placed"], skipped=done["skipped"], reason=done.get("reason")
        )
        if self.on_done:
            self.on_done(record)

    def _emu_finish(self, offer_id: str) -> None:
        record = self._load()[offer_id]
        offer = record["offer"]
        try:
            home, roms = self._emu_places()
            done = emureceive.finish(offer, record["targets"], home, roms)
        except (OSError, OfferError, emuplan.EmuPlanError) as exc:
            self._update(offer_id, state="failed", reason=f"the copy could not be put in place: {exc}")
            return
        placed = done["placed"].get("rom", [])
        record = self._update(offer_id, placed=done["placed"], skipped=done["skipped"])
        # The shortcut points at the playlist if there is one, else the game's first file or folder.
        main = next((p for p in placed if p.lower().endswith(".m3u")), placed[0] if placed else None)
        launch = emureceive.launch(home, offer["system"], os.path.join(roms, offer["system"], main)) if main else None
        if launch is None:
            reason = (
                "Copied. No shortcut was made: add it with Steam ROM Manager on this device."
                if placed
                else "Nothing new: this device already has the game."
            )
            record = self._update(offer_id, state="done", reason=reason)
            if self.on_done:
                self.on_done(record)
            return
        self._update(offer_id, launch=launch)
        payload = {
            "name": offer["title"],
            "exe": launch["exe"],
            "startDir": launch["startDir"],
            "launchOptions": launch["args"],
        }
        op_id = self.enqueue_op("add-shortcut", payload)
        self._update(offer_id, state="registering", ops={str(op_id): "add"})

    def _resolve(self, record: dict[str, Any], ref: dict[str, str], prefix_final: str | None = None) -> str:
        targets = record["targets"]
        base = (prefix_final or targets["prefix"]) if ref["scope"] == "prefix" else targets["install"]
        return base if ref["path"] == "." else os.path.join(base, *ref["path"].split("/"))

    def _roots(self, record: dict[str, Any], prefix_final: str | None = None) -> dict[str, str]:
        targets = record["targets"]
        return {
            "{install}": targets.get("install", ""),
            "{prefix}": prefix_final or targets.get("prefix", ""),
            "{home}": self.places().get("home", ""),
        }

    def _register(self, offer_id: str) -> None:
        record = self._load()[offer_id]
        offer = record["offer"]
        payload = {
            "name": offer["title"],
            "exe": self._resolve(record, offer["exe"]),
            "startDir": self._resolve(record, offer["startDir"]),
            "launchOptions": sendgame.local_options(offer["launchOptions"], self._roots(record)),
        }
        if offer["compatTool"]:
            payload["compatTool"] = offer["compatTool"]
        op_id = self.enqueue_op("add-shortcut", payload)
        self._update(offer_id, state="registering", ops={str(op_id): "add"})

    def op_finished(self, op_id: int, ok: bool, result: dict[str, Any]) -> dict[str, Any] | None:
        for offer_id, record in self._load().items():
            role = record.get("ops", {}).get(str(op_id))
            if role is None:
                continue
            if role == "add":
                if not ok or not isinstance(result.get("appid"), int):
                    self._update(offer_id, state="failed", reason=str(result.get("error") or "Steam did not add it"))
                    return self._public(offer_id)
                self._added(offer_id, int(result["appid"]), str(op_id))
            else:
                done = set(record.get("opsDone", [])) | {str(op_id)}
                failed = list(record.get("opsFailed", [])) + ([role] if not ok else [])
                record = self._update(offer_id, opsDone=sorted(done), opsFailed=failed)
                if set(record["ops"]) <= done:
                    self._finish(offer_id)
            return self._public(offer_id)
        return None

    def _added(self, offer_id: str, appid: int, add_op: str) -> None:
        record = self._update(offer_id, appid=appid, created=["shortcut"])
        offer, targets = record["offer"], record["targets"]
        final = None
        if "prefix" in targets:
            final = os.path.join(os.path.dirname(targets["prefix"]), str(appid))
            if os.path.isdir(final) and not os.listdir(final):
                os.rmdir(final)  # an empty folder Steam may have made already
            if os.path.lexists(final):
                self._update(offer_id, state="failed", reason=f"{final} already exists; Haversack will not replace it")
                return
            record = self._update(offer_id, prefixFinal=final)
            os.replace(targets["prefix"], final)
        ops: dict[str, str] = {k: v for k, v in record["ops"].items()}
        if offer.get("kind") == "emulator":
            launch = record["launch"]
            fields = (
                ("set-shortcut-exe", launch["exe"]),
                ("set-shortcut-start-dir", launch["startDir"]),
                ("set-launch-options", launch["args"]),
            )
        else:
            fields = (
                ("set-shortcut-exe", self._resolve(record, offer["exe"], final)),
                ("set-shortcut-start-dir", self._resolve(record, offer["startDir"], final)),
                ("set-launch-options", sendgame.local_options(offer["launchOptions"], self._roots(record, final))),
            )
        for kind, value in fields:
            ops[str(self.enqueue_op(kind, {"appid": appid, "value": value}))] = kind
        if offer["compatTool"]:
            ops[str(self.enqueue_op("set-compat-tool", {"appid": appid, "value": offer["compatTool"]}))] = "tool"
        for item in offer["art"]:
            payload = {
                "appid": appid,
                "assetType": item["assetType"],
                "imageType": "jpg" if "jp" in item["file"] else "png",
            }
            ops[str(self.enqueue_op("set-artwork", payload | {"file": item["file"]}))] = f"art:{item['file']}"
        self._update(offer_id, ops=ops, opsDone=[add_op])

    def _finish(self, offer_id: str) -> None:
        record = self._load()[offer_id]
        failed = record.get("opsFailed", [])
        reason = None
        if "tool" in failed and "tool" in record["targets"]:
            reason = "Restart Steam so it finds the compatibility tool, then choose it in the game's properties."
        elif failed:
            reason = f"Steam did not keep: {', '.join(failed)}. Check the game's properties."
        record = self._update(offer_id, state="done", reason=reason)
        if self.on_done:
            self.on_done(record)

    def staged_file(self, op: dict[str, Any]) -> str:
        """The copied artwork for a claimed ``set-artwork`` operation this module queued."""
        if op.get("module") != "replication" or op.get("kind") != "set-artwork" or op.get("state") != "claimed":
            raise OfferError("that operation has no staged file")
        for record in self._load().values():
            if str(op["id"]) in record.get("ops", {}) and "art" in record.get("targets", {}):
                path = os.path.join(record["targets"]["art"], str(op["payload"]["file"]))
                if os.path.dirname(os.path.realpath(path)) == os.path.realpath(record["targets"]["art"]):
                    return path
        raise OfferError("that operation has no staged file")

    async def stop(self, offer_id: str) -> None:
        """ "Stop and remove" for an accepted game: undo exactly what this offer made."""
        record = self._load().get(offer_id)
        if record is None:
            raise OfferError("that offer has gone")
        for job_id in record.get("jobs", {}).values():
            if job_id in self.transfers.jobs:
                await self.transfers.stop(job_id)
        places = self.places()
        # Only a folder this offer recorded, and only directly inside one of the places it may write.
        allowed = {os.path.realpath(places[k]) for k in ("library", "compatdata", "tools", "art") if places.get(k)}
        for path in [*record.get("targets", {}).values(), record.get("prefixFinal")]:
            if path and os.path.realpath(os.path.dirname(path)) in allowed:
                _remove_tree(path)
        if record.get("appid") and "shortcut" in record.get("created", []):
            self.enqueue_op("remove-shortcut", {"appid": int(record["appid"])})
        offers = self._load()
        gone = offers.pop(offer_id, None)
        self._save(offers)
        self._changed()
        if gone is not None:
            self._tell(offer_id, {**gone, "state": "removed", "reason": None})

    def redacted(self) -> builtins.list[dict[str, Any]]:
        """For the Device checks' export: states and sizes only, no titles, names or paths."""
        out = []
        for offer_id, record in self._load().items():
            jobs = []
            for scope, job_id in record.get("jobs", {}).items():
                job = self.transfers.jobs.get(job_id)
                task = self.transfers.tasks.get(job_id)
                jobs.append(
                    {
                        "scope": scope,
                        "state": job.state if job else "done" if scope in record.get("doneScopes", []) else "missing",
                        "running": task is not None and not task.done(),
                        "received": job.received if job else None,
                        "total": job.total if job else None,
                        "held": job.held if job else None,
                        "reason": wire_reason(job.reason) if job else None,
                    }
                )
            out.append(
                {
                    "id": offer_id[:6],
                    "state": record.get("state"),
                    "reason": wire_reason(record.get("reason")),
                    "update": bool(record["offer"].get("update")),
                    "bytes": sum(s["bytes"] for s in record["offer"]["shares"].values()),
                    "ageSeconds": int(time.time() - float(record.get("received") or 0)),
                    "jobs": jobs,
                }
            )
        return out
