"""Sending a game: what to copy, and the offer that describes it (slice 19a, ADR-0059).

A non-Steam game is copied as up to four shares:
- ``install``: the game's folder, when it is not inside its prefix;
- ``prefix``: its ``compatdata/<appid>`` folder (Proton prefix);
- ``tool``: its compatibility tool from ``compatibilitytools.d``, for a device that lacks it;
- ``art``: its custom artwork, under neutral names.

The offer names files by share and relative path only. Launch options have this device's
folders replaced by ``{install}``, ``{prefix}`` and ``{home}``. Anything else that looks like
a local path (a mounted disc, for example) is dropped and listed, never sent (P10).
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import manifest as mf

ART = {"p": 0, "": 3, "_hero": 1, "_logo": 2}  # grid file suffix to Steam's library asset type
ART_NAMES = {0: "capsule", 1: "hero", 2: "logo", 3: "header"}
TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
TITLE = re.compile(r'^[^/\\:*?"<>|\x00-\x1f]{1,80}$')
PLACEHOLDERS = ("{install}", "{prefix}", "{home}")
MAX_OPTIONS = 1000
LOCAL_PATH = re.compile(r"(?<![\w{}])/(?:home|var|run|media|mnt|tmp|opt|usr|srv)(?:/\S*)?")
DEVICE_ONLY_ENV = ("STEAM_COMPAT_MOUNTS=",)  # always this device's own mounts (the Installer sets it)


class SendError(Exception):
    pass


def unquote(value: str | None) -> str:
    value = (value or "").strip()
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def within(path: str, root: str) -> bool:
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def rel(path: str, root: str) -> str:
    return os.path.relpath(os.path.realpath(path), os.path.realpath(root)).replace(os.sep, "/")


def exclude_for(scope: str) -> Callable[[str], bool]:
    """Caches, temporary files, crash dumps and logs are never copied (spec 8.2, Exclusions)."""

    def exclude(path: str) -> bool:
        lower = path.lower()
        name = lower.rsplit("/", 1)[-1]
        if name.endswith((".dxvk-cache", ".dmp", ".log")) or name.startswith("vkd3d-proton.cache"):
            return True
        if name in ("crashdumps", "crashes", "shadercache"):
            return True
        if scope == "prefix":
            if lower in ("pfx/drive_c/windows/temp", "pfx/drive_c/windows/logs"):
                return True
            if re.fullmatch(r"pfx/drive_c/users/[^/]+/(appdata/local/)?temp", lower):
                return True
        return False

    return exclude


def install_root(exe: str, start_dir: str, library_root: str, home: str) -> str:
    """The game's own folder: its top folder in the library, else its start folder. Never home itself."""
    if library_root and within(exe, library_root) and rel(exe, library_root).count("/") >= 1:
        top = rel(exe, library_root).split("/")[0]
        root = os.path.join(os.path.realpath(library_root), top)
    else:
        root = os.path.realpath(start_dir or os.path.dirname(exe))
    real_home = os.path.realpath(home)
    if root in ("/", real_home, os.path.realpath(library_root or "/")) or within(real_home, root):
        raise SendError("the game's folder could not be told apart from your home folder; move it into its own folder")
    if rel(root, real_home).split("/")[0] in (".steam", ".local", ".var") and "compatibilitytools.d" not in root:
        raise SendError("the game's folder is inside Steam's own folders; this is not supported")
    return root


def canonical_options(options: str, roots: dict[str, str]) -> tuple[str, list[str]]:
    """Launch options with this device's folders as placeholders, and what had to be dropped."""
    text = " ".join(str(options or "").split())
    for placeholder, root in sorted(roots.items(), key=lambda kv: -len(kv[1] or "")):
        if root:
            text = text.replace(os.path.realpath(root), placeholder).replace(root, placeholder)
    kept, dropped = [], []
    for token in text.split(" "):
        if not token:
            continue
        if token.startswith(DEVICE_ONLY_ENV) or LOCAL_PATH.search(token):
            dropped.append(token)
        else:
            kept.append(token)
    return " ".join(kept)[:MAX_OPTIONS], dropped


def local_options(options: str, roots: dict[str, str]) -> str:
    """The other way: placeholders back to this device's folders."""
    text = str(options or "")
    for placeholder in PLACEHOLDERS:
        text = text.replace(placeholder, roots.get(placeholder, placeholder))
    return text


@dataclass
class Plan:
    title: str
    roots: dict[str, str]  # scope to this device's folder
    exe: dict[str, str]  # {"scope", "path"}
    start_dir: dict[str, str]
    launch_options: str
    dropped_options: list[str]
    compat_tool: str | None
    art: list[dict[str, Any]] = field(default_factory=list)  # {"assetType", "source", "file"}


def plan(game: dict[str, Any], home: str, library_root: str, tools_dir: str) -> Plan:
    """What sending ``game`` (a discovery entry) would copy. Raises SendError when it cannot be sent."""
    if game.get("kind") != "shortcut":
        raise SendError("only non-Steam games can be sent; Steam installs its own games")
    title = " ".join(str(game.get("name") or "").split())
    if not TITLE.match(title):
        raise SendError("the game's name cannot be used as a folder name; rename the shortcut first")
    exe = unquote(game.get("exe"))
    if not exe or not os.path.isfile(exe):
        raise SendError("the game's program was not found on this device")
    start = unquote(game.get("start_dir")) or os.path.dirname(exe)
    prefix = game.get("prefix")
    roots: dict[str, str] = {}
    if prefix and os.path.isdir(prefix):
        roots["prefix"] = os.path.realpath(prefix)
    if "prefix" in roots and within(exe, roots["prefix"]):
        exe_ref = {"scope": "prefix", "path": rel(exe, roots["prefix"])}
    else:
        roots["install"] = install_root(exe, start, library_root, home)
        exe_ref = {"scope": "install", "path": rel(exe, roots["install"])}
    start_ref = exe_ref | {"path": os.path.dirname(exe_ref["path"]) or "."}
    for scope, root in roots.items():
        if within(start, root):
            start_ref = {"scope": scope, "path": rel(start, root)}
            break
    tool = str(game.get("compat_tool") or "") or None
    if tool and not TOOL_NAME.match(tool):
        tool = None
    if tool and os.path.isdir(os.path.join(tools_dir, tool)):
        roots["tool"] = os.path.realpath(os.path.join(tools_dir, tool))
    placeholder_roots = {"{install}": roots.get("install", ""), "{prefix}": roots.get("prefix", ""), "{home}": home}
    options, dropped = canonical_options(str(game.get("launch_options") or ""), placeholder_roots)
    art = []
    grid = os.path.join(str(game.get("steam_root") or ""), "userdata", str(game.get("user_id") or ""), "config", "grid")
    for name in game.get("artwork") or []:
        stem, ext = os.path.splitext(str(name))
        suffix = stem[len(str(game.get("appid"))) :] if stem.startswith(str(game.get("appid"))) else None
        if suffix in ART and ext.lower() in (".png", ".jpg", ".jpeg"):
            asset = ART[suffix]
            art.append(
                {"assetType": asset, "source": os.path.join(grid, name), "file": f"{ART_NAMES[asset]}{ext.lower()}"}
            )
    return Plan(title, roots, exe_ref, start_ref, options, dropped, tool, art)


def stage_art(plan_: Plan, folder: str) -> str | None:
    """Copy the artwork under neutral names into its own folder, so it can be shared like the rest."""
    if not plan_.art:
        return None
    os.makedirs(folder, exist_ok=True)
    for item in plan_.art:
        shutil.copyfile(item["source"], os.path.join(folder, item["file"]))
    return folder


def new_offer_id() -> str:
    return secrets.token_hex(8)


def build_manifests(plan_: Plan, art_folder: str | None) -> dict[str, dict[str, Any]]:
    """One manifest per share. Hashing a large game takes a while: run this in a worker thread."""
    manifests = {scope: mf.build(root, exclude_for(scope)) for scope, root in plan_.roots.items()}
    if art_folder:
        manifests["art"] = mf.build(art_folder)
    return manifests


def sizes(plan_: Plan) -> dict[str, int]:
    """Bytes each share would carry, without hashing: for the space check before sending (v0.31.0).

    It walks the same files the manifest would take (the same exclusions, no symbolic links), so
    it is a fair estimate of what the other device must hold.
    """
    out: dict[str, int] = {}
    for scope, root in plan_.roots.items():
        exclude = exclude_for(scope)
        total = 0
        for folder, dirs, files in os.walk(root):
            inner = os.path.relpath(folder, root).replace(os.sep, "/")
            inner = "" if inner == "." else inner + "/"
            dirs[:] = [d for d in dirs if not exclude(inner + d) and not os.path.islink(os.path.join(folder, d))]
            for name in files:
                path = os.path.join(folder, name)
                if exclude(inner + name) or os.path.islink(path):
                    continue
                try:
                    total += os.path.getsize(path)
                except OSError:
                    continue  # gone since the listing: the manifest will not have it either
        out[scope] = total
    art = 0
    for item in plan_.art:
        try:
            art += os.path.getsize(str(item.get("source")))
        except OSError:
            continue
    if art:
        out["art"] = art
    return out
