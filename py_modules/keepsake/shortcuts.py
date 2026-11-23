"""Quick menu shortcuts (layout v3 addendum, ADR-0073): what Keepsake's quick access menu panel shows.

Every page or action a feature adds registers here, so the list grows with the app. Each entry
says its kind (a page to open, an action to run, or a status line), the module it belongs to,
and any feature it needs. Only entries whose module is on and whose feature is available on this
device are offered or shown. The user's choice and order are kept in the ``qamShortcuts``
setting; "Open Keepsake" is always there and is not part of the list.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
MAX_CHOSEN = 30
# With Open Keepsake, always last. The reconnect line keeps the Reconnect buttons helped controllers
# have had in the quick menu since v0.40.0 (ADR-0082).
DEFAULT = ["sync-now", "status-transfers", "status-conflicts", "status-reconnect"]

# id, kind, label, module, feature (None: none needed), page target (section, tab) for pages
REGISTRY: list[dict[str, Any]] = [
    # Pages: open one page of the full interface
    {"id": "page-games", "kind": "page", "label": "Games", "module": "saves", "open": ["saves", "games"]},
    {"id": "page-conflicts", "kind": "page", "label": "Conflicts", "module": "saves", "open": ["saves", "conflicts"]},
    {"id": "page-history", "kind": "page", "label": "History", "module": "saves", "open": ["saves", "history"]},
    {
        "id": "page-devices",
        "kind": "page",
        "label": "Other devices",
        "module": "replication",
        "open": ["games-devices", "devices"],
    },
    {
        "id": "page-advisor",
        "kind": "page",
        "label": "Advisor for this game",
        "module": "advisor",
        "open": ["play", "advisor"],
    },
    {"id": "page-install", "kind": "page", "label": "Install", "module": "installer", "open": ["install", "install"]},
    {"id": "page-storage", "kind": "page", "label": "Storage", "module": "core", "open": ["device", "storage"]},
    {
        "id": "page-diagnostics",
        "kind": "page",
        "label": "Diagnostics",
        "module": "core",
        "open": ["diagnostics", "health"],
    },
    {
        "id": "page-device-checks",
        "kind": "page",
        "label": "Device checks",
        "module": "core",
        "open": ["diagnostics", "checks"],
    },
    {"id": "page-settings", "kind": "page", "label": "Settings", "module": "core", "open": ["settings", "general"]},
    {"id": "page-device", "kind": "page", "label": "Device status", "module": "core", "open": ["device", "status"]},
    {"id": "page-power", "kind": "page", "label": "Power", "module": "device", "open": ["device", "power"]},
    {"id": "page-battery", "kind": "page", "label": "Battery", "module": "device", "open": ["device", "power"]},
    {
        "id": "page-controllers",
        "kind": "page",
        "label": "Controllers",
        "module": "core",
        "open": ["device", "controllers"],
    },
    {
        "id": "page-reconnect",
        "kind": "page",
        "label": "Reconnect help",
        "module": "device",
        "open": ["device", "controllers"],
    },
    {"id": "page-fans", "kind": "page", "label": "Fans", "module": "device", "open": ["device", "fans"]},
    {
        "id": "page-more-device",
        "kind": "page",
        "label": "More device settings",
        "module": "device",
        "open": ["device", "status"],
    },
    # Actions: run straight from the quick access menu, with a toast
    {"id": "sync-now", "kind": "action", "label": "Sync now", "module": "saves"},
    {"id": "sync-current", "kind": "action", "label": "Sync this game now", "module": "saves"},
    {"id": "backup-current", "kind": "action", "label": "Back up this game now", "module": "saves"},
    {"id": "check-updates", "kind": "action", "label": "Check for updates", "module": "core", "feature": "updates"},
    {"id": "send-current", "kind": "action", "label": "Send this game to another device", "module": "replication"},
    {"id": "get-game", "kind": "action", "label": "Get a game from another device", "module": "replication"},
    {"id": "run-device-checks", "kind": "action", "label": "Run all device checks", "module": "core"},
    {
        "id": "next-mode",
        "kind": "action",
        "label": "Next performance mode",
        "module": "device",
        "feature": "performance",
    },
    {
        "id": "charge-limit",
        "kind": "action",
        "label": "Charge limit on or off",
        "module": "device",
        "feature": "charge-limit",
    },
    # Status lines
    {"id": "status-conflicts", "kind": "status", "label": "Open conflicts", "module": "saves"},
    {"id": "status-transfers", "kind": "status", "label": "Games moving between devices", "module": "replication"},
    {"id": "status-reconnect", "kind": "status", "label": "Controller reconnect buttons", "module": "device"},
]


def check_registry(registry: list[dict[str, Any]] = REGISTRY) -> None:
    """Every entry well formed, every ID unique (the tests call this)."""
    seen = set()
    for entry in registry:
        if not ID.match(entry["id"]) or entry["id"] in seen or entry["kind"] not in ("page", "action", "status"):
            raise ValueError(f"bad shortcut {entry['id']}")
        if entry["kind"] == "page" and len(entry.get("open") or []) != 2:
            raise ValueError(f"page shortcut {entry['id']} needs a section and a tab")
        seen.add(entry["id"])


def clean_choice(value: Any) -> list[str]:
    """The setting's value: shortcut IDs in order, no repeats. Unknown IDs are kept, so a later
    version's shortcuts survive a downgrade; they are simply not shown until they exist."""
    if not isinstance(value, list) or len(value) > MAX_CHOSEN:
        raise ValueError("quick menu shortcuts are a list of up to 30")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not ID.match(item):
            raise ValueError("that is not a shortcut")
        if item not in out:
            out.append(item)
    return out


def available(
    modules: Mapping[str, bool], features: Iterable[str], registry: list[dict[str, Any]] = REGISTRY
) -> list[dict[str, Any]]:
    """Shortcuts this device can show now: their module is on (Core always is) and their feature is here."""
    have = set(features)
    return [
        dict(entry)
        for entry in registry
        if (entry["module"] == "core" or modules.get(entry["module"], False))
        and (entry.get("feature") is None or entry["feature"] in have)
    ]


def shown(chosen: list[str] | None, offered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The chosen shortcuts, in the user's order, that are available here. ``None`` means the defaults."""
    by_id = {e["id"]: e for e in offered}
    return [by_id[i] for i in (DEFAULT if chosen is None else chosen) if i in by_id]
