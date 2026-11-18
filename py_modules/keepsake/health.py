"""Health checks (build prompt section 15).

:func:`run` is pure: the app gathers the facts and this module turns them into
checks, so every rule can be tested without Decky, Steam or the cloud. Each
check is ``{id, label, status, detail, items}`` with ``status`` one of ``ok``,
``info``, ``warn`` or ``fail``. :func:`summary` gives the worst status, shown
as the badge in the Quick Access Menu.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

OK = "ok"
INFO = "info"
WARN = "warn"
FAIL = "fail"
_RANK = {OK: 0, INFO: 0, WARN: 1, FAIL: 2}

SESSION_STALE_SECONDS = 6 * 3600
DAY = 24 * 3600


def _check(check_id: str, label: str, status: str, detail: str, items: Sequence[str] = ()) -> dict[str, Any]:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "items": list(items)}


def summary(checks: Sequence[Mapping[str, Any]]) -> str:
    worst = OK
    for check in checks:
        if _RANK.get(str(check.get("status")), 0) > _RANK[worst]:
            worst = str(check["status"])
    return worst


def _age_text(seconds: float) -> str:
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))} minutes ago"
    if seconds < 2 * DAY:
        return f"{int(seconds // 3600)} hours ago"
    return f"{int(seconds // DAY)} days ago"


def _cloud(cloud: Mapping[str, Any]) -> dict[str, Any]:
    label = "Cloud sign-in and reachability"
    name = str(cloud.get("name") or "OneDrive")
    if cloud.get("store") in (None, "local"):
        return _check(
            "cloud",
            label,
            WARN,
            "Snapshots go to a test store on this device only. Choose a cloud in Settings to sync between devices.",
        )
    if not cloud.get("signedIn"):
        return _check("cloud", label, FAIL, f"{name} is not signed in or set up. Finish it in Settings.")
    if cloud.get("problem"):
        return _check("cloud", label, FAIL, f"{name} sign-in needs attention: {cloud['problem']}.")
    if cloud.get("reachable") is False:
        return _check("cloud", label, WARN, f"Set up, but {name} could not be reached: {cloud.get('error')}.")
    if cloud.get("reachable") is True:
        return _check("cloud", label, OK, f"Set up and {name} answered.")
    return _check("cloud", label, OK, f"{name} is set up. Run the checks to test the connection.")


def _last_sync(games: Sequence[Mapping[str, Any]], now: float) -> dict[str, Any]:
    label = "Last push and pull per synced game"
    if not games:
        return _check("last-sync", label, INFO, "No games are set to sync yet.")
    items = []
    never = 0
    for game in games:
        state = game.get("state") or {}
        push, pull = state.get("lastPush"), state.get("lastPull")
        if not state.get("base"):
            never += 1
        parts = [
            f"pushed {_age_text(now - push)}" if push else "never pushed",
            f"pulled {_age_text(now - pull)}" if pull else "never pulled",
        ]
        if state.get("pending"):
            parts.append("waiting for the cloud")
        items.append(f"{game['name']}: {', '.join(parts)}")
    pending = sum(1 for g in games if (g.get("state") or {}).get("pending"))
    if never or pending:
        detail = f"{never} not synced yet, {pending} waiting for the cloud."
        return _check("last-sync", label, WARN, detail, items)
    return _check("last-sync", label, OK, f"{len(games)} games synced.", items)


def _sessions(games: Sequence[Mapping[str, Any]], now: float) -> dict[str, Any]:
    stale = [
        g["name"]
        for g in games
        if (g.get("state") or {}).get("sessionOpen")
        and not g.get("running")
        and now - float((g["state"]["sessionOpen"] or {}).get("started", now)) > SESSION_STALE_SECONDS
    ]
    if stale:
        return _check(
            "sessions",
            "Sessions left open",
            WARN,
            "A game session was never closed, for example because Steam was stopped. The next idle pass saves it.",
            stale,
        )
    return _check("sessions", "Sessions left open", OK, "None.")


def _flagged(games: Sequence[Mapping[str, Any]], field: str) -> list[str]:
    return [str(g["name"]) for g in games if (g.get("state") or {}).get(field)]


def run(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    now = float(facts.get("now") or time.time())
    games: Sequence[Mapping[str, Any]] = facts.get("games") or []
    checks = [_cloud(facts.get("cloud") or {}), _last_sync(games, now), _sessions(games, now)]

    quarantined = _flagged(games, "quarantined")
    checks.append(
        _check(
            "quarantine",
            "Quarantined snapshots",
            WARN if quarantined else OK,
            "Kept on this device, not uploaded. Review them in History." if quarantined else "None.",
            quarantined,
        )
    )
    conflicts = _flagged(games, "conflict")
    checks.append(
        _check(
            "conflicts",
            "Unresolved conflicts",
            WARN if conflicts else OK,
            f"{len(conflicts)} games wait for your choice in Conflicts." if conflicts else "None.",
            conflicts,
        )
    )
    mismatches: Sequence[str] = facts.get("mismatches") or []
    checks.append(
        _check(
            "prefix",
            "Prefix mismatches",
            FAIL if mismatches else OK,
            "A running game used a different prefix from the one found. Sync is blocked for it."
            if mismatches
            else "None.",
            mismatches,
        )
    )
    unseen = [str(g["name"]) for g in games if g.get("playedWithoutKeepsake")]
    checks.append(
        _check(
            "played-without",
            "Played without Keepsake running",
            WARN if unseen else OK,
            "Steam recorded a play Keepsake did not see. The idle pass saves the result." if unseen else "None.",
            unseen,
        )
    )
    checks.append(_integrity(facts.get("integrity") or {}, now))
    checks.append(_manifest(facts.get("manifest") or {}, now))
    checks.append(_ludusavi(facts.get("ludusavi") or {}, bool(games)))
    checks.append(_python_modules(facts.get("pythonModules") or {}, str(facts.get("store") or "")))
    return checks


def _integrity(scrub: Mapping[str, Any], now: float) -> dict[str, Any]:
    """The cloud integrity check (ADR-0050): snapshots whose files are damaged or missing."""
    last = float(scrub.get("lastRun") or 0)
    if not last:
        return _check("integrity", "Cloud integrity", INFO, "Not checked yet. Keepsake checks once a week.")
    damaged = [
        f"{game.get('name', key)}: {len(game.get('bad', [])) + len(game.get('missing', []))} snapshots"
        for key, game in sorted((scrub.get("games") or {}).items())
        if game.get("bad") or game.get("missing")
    ]
    if damaged:
        return _check(
            "integrity",
            "Cloud integrity",
            WARN,
            "Some snapshots in the cloud are damaged or missing, so they cannot be restored. Your current saves are "
            "fine. Open the game and choose Repair to save a fresh copy from this device.",
            damaged,
        )
    return _check(
        "integrity", "Cloud integrity", OK, f"Every checked snapshot is intact (checked {_age_text(now - last)})."
    )


def _python_modules(modules: Mapping[str, Any], store: str) -> dict[str, Any]:
    """Stdlib modules Decky's frozen Python may leave out (ADR-0030), in words: what each missing one stops."""
    label = "Python modules in this Decky build"
    missing = []
    if modules.get("xml") is False:
        missing.append("xml (needed for WebDAV and S3)")
    if modules.get("sqlite3") is False:
        missing.append("sqlite3 (needed for the Installer and the module state)")
    if not missing:
        return _check("python-modules", label, OK, "Everything Keepsake uses is present.")
    if store in ("webdav", "s3") and modules.get("xml") is False:
        return _check(
            "python-modules",
            label,
            FAIL,
            "This Decky build's Python has no XML module, so WebDAV and S3 cannot work. "
            "Choose OneDrive, Google Drive or the local store in Settings.",
            missing,
        )
    return _check(
        "python-modules",
        label,
        WARN,
        "Some features are not available with this Decky build. Save sync with OneDrive, Google Drive or "
        "the local store still works.",
        missing,
    )


def _manifest(status: Mapping[str, Any], now: float) -> dict[str, Any]:
    label = "Manifest age"
    if not status.get("available"):
        return _check("manifest", label, FAIL, "The save location manifest has not been downloaded yet.")
    fetched = float(status.get("fetched") or 0)
    age = _age_text(now - fetched) if fetched else "at an unknown time"
    if status.get("stale"):
        return _check("manifest", label, WARN, f"Downloaded {age}. Update it from the Games page.")
    return _check("manifest", label, OK, f"Downloaded {age}.")


def _ludusavi(found: Mapping[str, Any], syncing: bool) -> dict[str, Any]:
    label = "decky-ludusavi"
    if not found.get("installed"):
        return _check("ludusavi", label, OK, "Not installed.")
    if found.get("disabled"):
        return _check("ludusavi", label, OK, "Installed but disabled in Decky.")
    if syncing:
        return _check(
            "ludusavi",
            label,
            WARN,
            "decky-ludusavi is installed and active. Turn off its automatic sync for games Keepsake syncs, "
            "or the two will overwrite each other's work.",
        )
    return _check("ludusavi", label, INFO, "Installed. No games are synced by Keepsake yet.")


def detect_decky_plugin(decky_home: str | None, needle: str) -> dict[str, Any]:
    """Find an installed Decky plugin whose ``plugin.json`` name contains ``needle``, read-only.

    Disabled plugins are listed by name under ``disabled_plugins`` in Decky's
    ``settings/loader.json`` (verified in the Tuning Advisor register, item 11).
    """
    result: dict[str, Any] = {"installed": False, "disabled": False, "name": None}
    if not decky_home:
        return result
    plugins = os.path.join(decky_home, "plugins")
    try:
        folders = sorted(os.listdir(plugins))
    except OSError:
        return result
    for folder in folders:
        try:
            with open(os.path.join(plugins, folder, "plugin.json"), encoding="utf-8") as handle:
                name = json.load(handle).get("name")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(name, str) and needle.lower() in name.lower():
            result.update(installed=True, name=name)
            break
    if result["installed"]:
        try:
            with open(os.path.join(decky_home, "settings", "loader.json"), encoding="utf-8") as handle:
                disabled = json.load(handle).get("disabled_plugins", [])
            result["disabled"] = isinstance(disabled, list) and result["name"] in disabled
        except (OSError, ValueError, AttributeError):
            pass
    return result
