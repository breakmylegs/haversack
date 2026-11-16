"""Proton version and launch options (v2 spec 8.1, slice 15, ADR-0029). Recommend only.

Nothing here applies a value or runs a string. Launch options from community
reports are untrusted text: they are parsed so the page can explain them,
flag anything that runs a command and suggest a merge with what is already
set. The user copies them and sets them in Steam (P16).

Steam's launch option shape is ``ENV=value ... wrapper ... %command% game-args``;
without ``%command%`` Steam passes the whole string to the game as arguments.

Proton signal order (spec 8.1, research 6.3): what works on the paired peer for
the same game (once Replication exists), then community reports, then the
newest installed GE-Proton for non-Steam titles. Parsing is ported from Tuning
Advisor (ADR-0013); the order and the installed-tool fallback are Keepsake's.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Any

COMMAND = "%command%"
MAX_LEN = 500
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_RE = re.compile(r"[;&|`<>]|\$\(")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
FSR4_ENV_RE = re.compile(r"FSR_?4", re.I)
STACK_WRAPPERS = {"~/lsfg": "lsfg-vk", "~/fgmod/fgmod": "optiscaler"}
WHERE_LAUNCH = "Steam, the game's Properties, General, Launch Options"
WHERE_LAUNCH_SHORTCUT = "Steam, the shortcut's Properties, Shortcut, Launch Options"
WHERE_PROTON = (
    "Steam, the game's Properties, Compatibility, turn on Force the use of a specific Steam Play "
    "compatibility tool, then pick it from the list"
)
WHERE_DEFAULT = (
    "Steam, the game's Properties, Compatibility, turn off Force the use of a specific Steam Play compatibility tool"
)
GE_DIR_RE = re.compile(r"^GE-Proton(\d+)-(\d+)$")


def clean(text: Any) -> str:
    return CONTROL_RE.sub(" ", str(text or "")).strip()[:MAX_LEN]


def split(text: str) -> list[str]:
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()  # unbalanced quotes: still show something


def parse(text: Any) -> dict[str, Any]:
    raw = clean(text)
    tokens = split(raw)
    env: list[str] = []
    wrappers: list[str] = []
    args: list[str] = []
    has_command = COMMAND in tokens
    seen_command = False
    for token in tokens:
        if token == COMMAND:
            seen_command = True
        elif not has_command or seen_command:
            args.append(token)
        elif ENV_RE.match(token) and not wrappers:
            env.append(token)
        else:
            wrappers.append(token)
    return {
        "raw": raw,
        "env": env,
        "wrappers": wrappers,
        "args": args,
        "has_command": has_command,
        "shell": bool(SHELL_RE.search(raw)),
    }


def join(parsed: dict[str, Any]) -> str:
    parts = list(parsed["env"]) + list(parsed["wrappers"])
    if parsed["env"] or parsed["wrappers"] or parsed["has_command"]:
        parts.append(COMMAND)
    parts += parsed["args"]
    return " ".join(shlex.quote(p) if p != COMMAND and (" " in p or not p) else p for p in parts)


def flags_for(parsed: dict[str, Any], selected: dict[str, str]) -> list[str]:
    flags: list[str] = []
    if parsed["shell"]:
        flags.append("Contains shell operators such as ; | & or $( ). Check every part before you use it.")
    for token in parsed["wrappers"]:
        tool = STACK_WRAPPERS.get(token)
        if tool is None:
            flags.append(f"Runs {token} before the game. Only use it if you know what it is and have it installed.")
        elif selected.get("framegen") != tool and selected.get("upscaler") != tool:
            flags.append(f"{token} needs {tool}, which is not in your selected tools.")
    if parsed["args"] and not parsed["has_command"]:
        flags.append("Has no %command%, so Steam passes the whole string to the game as arguments.")
    return flags


def drop_fsr4(parsed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    kept = [e for e in parsed["env"] if not FSR4_ENV_RE.search(e.split("=", 1)[0])]
    if len(kept) == len(parsed["env"]):
        return parsed, []
    return dict(parsed, env=kept), [
        "An FSR 4 setting was removed. FSR 4 is not officially available on handheld chips under Proton."
    ]


def merge(current: dict[str, Any], recommended: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Combine current options with the recommendation: recommended values win per variable; wrappers are kept."""
    notes: list[str] = []
    env: dict[str, str] = {}
    for item in current["env"]:
        env[item.split("=", 1)[0]] = item
    for item in recommended["env"]:
        name = item.split("=", 1)[0]
        if name in env and env[name] != item:
            notes.append(f"Changes {env[name]} to {item}.")
        env[name] = item
    wrappers: list[str] = []
    for token in current["wrappers"]:
        suffix = "" if STACK_WRAPPERS.get(token) else " Remove it if you no longer use it."
        notes.append(f"Keeps {token} from your current options.{suffix}")
        wrappers.append(token)
    for token in recommended["wrappers"]:
        if token not in wrappers:
            wrappers.append(token)
    args = list(current["args"] if current["has_command"] else [])
    for token in recommended["args"]:
        if token not in args:
            args.append(token)
    if not current["has_command"] and current["args"]:
        notes.append(
            "Your current options had no %command%, so they were game arguments. They are kept after %command%."
        )
        args = current["args"] + [a for a in args if a not in current["args"]]
    merged = {
        "env": list(env.values()),
        "wrappers": wrappers,
        "args": args,
        "has_command": True,
        "shell": current["shell"] or recommended["shell"],
    }
    return merged, notes


def launch_section(
    rec_launch: Any, current_launch: Any, selected: dict[str, str], shortcut: bool
) -> dict[str, Any] | None:
    recommended = parse(rec_launch)
    current = parse(current_launch)
    if not recommended["raw"]:
        return None
    recommended, fsr_flags = drop_fsr4(recommended)
    rec_text = join(recommended)
    section: dict[str, Any] = {
        "recommended": rec_text,
        "current": current["raw"],
        "where": WHERE_LAUNCH_SHORTCUT if shortcut else WHERE_LAUNCH,
        "flags": fsr_flags + flags_for(recommended, selected),
        "merged": None,
        "mergeNotes": [],
        "sameAsCurrent": False,
    }
    if current["raw"]:
        merged, notes = merge(current, recommended)
        merged_text = join(merged)
        if merged_text in (current["raw"], join(current)):
            section["sameAsCurrent"] = True
        elif merged_text != rec_text:
            section["merged"], section["mergeNotes"] = merged_text, notes
    return section


# Proton

GE_VERSION_RE = re.compile(r"(\d+)[-.](\d+)")
PROTON_VERSION_RE = re.compile(r"^\d+(\.\d+)?(-\d+)?$")
GE_INSTALL = (
    "GE-Proton is not built into Steam. Install it with ProtonUp-Qt or ProtonPlus in Desktop Mode, then restart Steam."
)


def proton_name(tool: Any, version: Any) -> dict[str, Any] | None:
    tool_text = clean(tool).casefold()
    version_text = clean(version)
    v = version_text.casefold()
    if not tool_text and not version_text:
        return None
    if "native" in tool_text or "linux" in tool_text:
        return {"name": "None. Native Linux build", "force": False, "installNote": None}
    if "ge" in tool_text.split() or "eggroll" in tool_text or "(ge)" in tool_text or tool_text.startswith("ge-proton"):
        match = GE_VERSION_RE.search(version_text or tool_text)
        name = f"GE-Proton{match.group(1)}-{match.group(2)}" if match else "GE-Proton (latest)"
        return {"name": name, "force": True, "installNote": GE_INSTALL}
    if v in ("", "default"):
        return {"name": "Steam's default", "force": False, "installNote": None}
    if "experimental" in v:
        return {"name": "Proton Experimental", "force": True, "installNote": None}
    if "hotfix" in v:
        return {"name": "Proton Hotfix", "force": True, "installNote": None}
    if PROTON_VERSION_RE.match(version_text):
        return {"name": f"Proton {version_text.split('-')[0]}", "force": True, "installNote": None}
    return {"name": clean(f"{clean(tool)} {version_text}"), "force": True, "installNote": None}


def installed_ge_proton(steam_roots: list[str]) -> list[str]:
    """GE-Proton builds in each Steam root's ``compatibilitytools.d``, newest first. Read-only."""
    found: dict[str, tuple[int, int]] = {}
    for root in steam_roots:
        folder = os.path.join(root, "compatibilitytools.d")
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            match = GE_DIR_RE.match(name)
            if match and os.path.isdir(os.path.join(folder, name)):
                found[name] = (int(match.group(1)), int(match.group(2)))
    return sorted(found, key=lambda n: found[n], reverse=True)


def proton_section(
    reports: list[dict[str, Any]], current_tool: Any, shortcut: bool, installed_ge: list[str]
) -> dict[str, Any] | None:
    """The Proton advice and the signal it came from (peer, reports, installed GE-Proton)."""
    named, signal, as_reported = None, None, ""
    for rec in reports:
        compat = rec.get("compat") or {}
        named = proton_name(compat.get("tool"), compat.get("tool_version"))
        if named:
            signal = "report"
            as_reported = clean(f"{clean(compat.get('tool'))} {clean(compat.get('tool_version'))}")
            break
    if named is None and shortcut and installed_ge:
        named = {"name": installed_ge[0], "force": True, "installNote": None}
        signal = "installed"
    if named is None:
        return None
    current = clean(current_tool)
    if named["force"] and current and named["name"].casefold() in current.casefold():
        matches = True
    else:
        matches = not named["force"] and not current
    if named["force"] and named["name"].startswith("GE-Proton") and named["name"] in installed_ge:
        named = dict(named, installNote=None)  # already installed
    return {
        "recommended": named["name"],
        "force": named["force"],
        "signal": signal,
        "signalText": {
            "report": "From the top community report.",
            "installed": "No report names one, so the newest GE-Proton you have installed.",
        }[signal or "report"],
        "installNote": named["installNote"],
        "current": current or "Steam's default",
        "matches": matches,
        "where": WHERE_PROTON if named["force"] else WHERE_DEFAULT,
        "asReported": as_reported,
        "peer": "Replication is not set up, so a working tool on your other device is not checked yet.",
    }
