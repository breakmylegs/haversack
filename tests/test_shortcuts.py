"""Quick menu shortcuts (layout v3 addendum, ADR-0073): the registry, defaults, ordering and hiding."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import pytest

from keepsake import shortcuts
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.settings import SettingsError, SettingsStore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_ON = {"saves": True, "advisor": True, "replication": True, "installer": True, "device": True}


def test_registry_is_well_formed_and_defaults_exist() -> None:
    shortcuts.check_registry()
    ids = {e["id"] for e in shortcuts.REGISTRY}
    assert set(shortcuts.DEFAULT) <= ids
    assert shortcuts.DEFAULT == ["sync-now", "status-transfers", "status-conflicts", "status-reconnect"]
    with pytest.raises(ValueError):
        shortcuts.check_registry([*shortcuts.REGISTRY, dict(shortcuts.REGISTRY[0])])  # a repeated ID


def test_page_targets_are_sidebar_pages() -> None:
    """Every page shortcut opens a page that exists in the static sidebar (src/routeData.ts)."""
    with open(os.path.join(ROOT, "src", "routeData.ts"), encoding="utf-8") as handle:
        layout = handle.read()
    body = layout[layout.index("export const LAYOUT") : layout.index("export const MOVED")]
    starts = [(m.start(), m.group(1)) for m in re.finditer(r'^    id: "([a-z-]+)",$', body, re.M)]
    pages = set()
    for i, (at, sid) in enumerate(starts):
        segment = body[at : starts[i + 1][0] if i + 1 < len(starts) else len(body)]
        pages |= {(sid, page) for page in re.findall(r'\{ id: "([a-z-]+)", title:', segment)}
    assert ("device", "fans") in pages and ("device", "storage") in pages and ("device", "controllers") in pages
    assert len({sid for sid, _ in pages}) == 7  # the redesign's seven sections (ADR-0095)
    for entry in shortcuts.REGISTRY:
        if entry["kind"] == "page":
            assert tuple(entry["open"]) in pages, entry["id"]


def test_available_hides_modules_that_are_off_and_missing_features() -> None:
    offered = {e["id"] for e in shortcuts.available({"saves": True}, [])}
    assert "sync-now" in offered and "page-settings" in offered  # Core is always on
    assert "status-transfers" not in offered and "page-fans" not in offered
    assert "check-updates" not in offered  # needs the "updates" feature
    assert "check-updates" in {e["id"] for e in shortcuts.available({"saves": True}, ["updates"])}
    assert "next-mode" not in {e["id"] for e in shortcuts.available(ALL_ON, [])}


def test_shown_keeps_order_drops_unavailable_and_uses_defaults() -> None:
    offered = shortcuts.available(ALL_ON, ["updates"])
    assert [e["id"] for e in shortcuts.shown(None, offered)] == shortcuts.DEFAULT
    chosen = ["page-fans", "future-thing", "sync-now"]
    assert [e["id"] for e in shortcuts.shown(chosen, offered)] == ["page-fans", "sync-now"]
    assert [e["id"] for e in shortcuts.shown(chosen, shortcuts.available({"saves": True}, []))] == ["sync-now"]
    assert shortcuts.shown([], offered) == []


def test_clean_choice() -> None:
    assert shortcuts.clean_choice(["sync-now", "sync-now", "page-fans"]) == ["sync-now", "page-fans"]
    assert shortcuts.clean_choice(["later-feature"]) == ["later-feature"]  # survives a downgrade
    for bad in ("sync-now", [1], ["Bad ID"], ["x" * 50], ["a"] * 31 + ["b"]):
        with pytest.raises(ValueError):
            shortcuts.clean_choice(bad)


def test_the_setting_is_checked(tmp_path: Any) -> None:
    store = SettingsStore(str(tmp_path))
    assert store.get("qamShortcuts") is None
    store.set("qamShortcuts", ["page-fans", "sync-now"])
    assert store.get("qamShortcuts") == ["page-fans", "sync-now"]
    with pytest.raises(SettingsError):
        store.set("qamShortcuts", ["Not An ID"])
    store.set("qamShortcuts", None)
    assert store.get("qamShortcuts") is None


def make_app(tmp_path: Any) -> KeepsakeApp:
    paths = PluginPaths(
        settings_dir=str(tmp_path / "settings"),
        runtime_dir=str(tmp_path / "runtime"),
        log_dir=str(tmp_path / "logs"),
        plugin_dir=str(tmp_path / "plugin"),
    )
    return KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), auto_refresh_manifest=False)


def test_app_offers_defaults_and_follows_the_setting(tmp_path: Any) -> None:
    app = make_app(tmp_path)
    found = asyncio.run(app.qam_shortcuts())
    assert found["defaults"] == shortcuts.DEFAULT and found["chosen"] == shortcuts.DEFAULT
    assert all(e["id"] in {a["id"] for a in found["available"]} for e in found["shown"])
    asyncio.run(app.set_setting("qamShortcuts", ["page-settings", "sync-now"]))
    assert [e["id"] for e in asyncio.run(app.qam_shortcuts())["shown"]][:1] == ["page-settings"]


def test_run_shortcut_refuses_pages_and_unknown_ids(tmp_path: Any) -> None:
    app = make_app(tmp_path)
    for bad in ("page-settings", "no-such-thing", "status-conflicts"):
        with pytest.raises(ValueError):
            asyncio.run(app.run_shortcut(bad))
