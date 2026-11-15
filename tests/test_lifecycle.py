import asyncio
import os
import time

import pytest

from helpers import make_fake_steam, shortcut_entry, write_fake_proc
from keepsake import lifecycle
from keepsake.app import KeepsakeApp
from keepsake.engine import SnapshotEngine
from keepsake.freeze import SIGCONT, SIGSTOP
from keepsake.paths import PluginPaths
from keepsake.store import LocalFolderStore
from keepsake.sync import SyncEngine

APPID = 4171510507
KEY = f"shortcut:7:{APPID}"
UID = os.getuid() if hasattr(os, "getuid") else -1


# Pure helpers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(APPID, APPID), (APPID - 2**32, APPID), ((APPID << 32) | 0x02000000, APPID), ("620", 620), (0, 0)],
)
def test_normalise_appid(raw, expected):
    assert lifecycle.normalise_appid(raw) == expected


GATE = "/home/deck/homebrew/plugins/Keepsake/bin/keepsake-gate"


@pytest.mark.parametrize(
    ("original", "wrapped"),
    [
        ("", f"{GATE} %command%"),
        ("PROTON_LOG=1 %command% -windowed", f"PROTON_LOG=1 {GATE} %command% -windowed"),
        ("-windowed -nointro", f"{GATE} %command% -windowed -nointro"),
        ("%command% %command%", f"{GATE} %command% %command%"),
    ],
)
def test_wrap_launch_options(original, wrapped):
    plugin_dir = "/home/deck/homebrew/plugins/Keepsake"
    assert lifecycle.wrap_launch_options(original, plugin_dir) == wrapped
    assert lifecycle.wrap_launch_options(wrapped, plugin_dir) == wrapped  # idempotent


def test_wrap_quotes_paths_with_spaces():
    assert lifecycle.wrap_launch_options("", "/home/a b/Keepsake").startswith("'/home/a b/Keepsake/bin/keepsake-gate'")


def test_launch_options_original_is_kept_exactly_and_never_overwritten(tmp_path):
    store = lifecycle.LaunchOptionsStore(str(tmp_path))
    original = '  PROTON_LOG=1 %command%  -a "x y"  '
    store.save_original(5, original)
    store.save_original(5, "wrapped by mistake")
    assert store.original(5) == original
    store.forget(5)
    assert store.original(5) is None


def test_gate_files_token_handshake(tmp_path):
    files = lifecycle.GateFiles(str(tmp_path))
    assert files.waiting_token(9) is None
    os.makedirs(files.dir)
    with open(os.path.join(files.dir, "9.waiting"), "w") as h:
        h.write("deadbeefcafe0001\n")
    assert files.waiting_token(9) == "deadbeefcafe0001"
    files.release(9, "deadbeefcafe0001")
    with open(os.path.join(files.dir, "9.ready")) as h:
        assert h.read() == "deadbeefcafe0001"
    with open(os.path.join(files.dir, "9.waiting"), "w") as h:
        h.write("../../etc/passwd")
    assert files.waiting_token(9) is None


def test_played_without_keepsake():
    assert not lifecycle.played_without_keepsake(0, None)
    assert lifecycle.played_without_keepsake(1000, None)
    assert not lifecycle.played_without_keepsake(1100, 1000.0)
    assert lifecycle.played_without_keepsake(1200, 1000.0)


def test_wait_for_times_out():
    clock = [0.0]
    assert not lifecycle.wait_for(
        lambda: False, 1.0, sleep=lambda s: clock.__setitem__(0, clock[0] + s), clock=lambda: clock[0]
    )
    assert lifecycle.wait_for(lambda: True, 1.0)


# App: launch gate and exit


class Harness:
    def __init__(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        root = make_fake_steam(
            home, users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]}, prefixes=[(None, APPID)]
        )
        self.saves = root / "steamapps/compatdata" / str(APPID) / "pfx/drive_c/users/steamuser/AppData/Local/EQ"
        self.saves.mkdir(parents=True)
        self.proc = tmp_path / "proc"
        self.paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
        self.events = []
        self.kills = []

        async def emit(event, *args):
            self.events.append((event, args))

        self.app = KeepsakeApp(
            self.paths,
            emit=emit,
            proc_root=str(self.proc),
            version="0.8.0",
            home=str(home),
            auto_refresh_manifest=False,
        )
        self.app.freezer._kill = lambda pid, sig: self.kills.append((pid, sig))
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(
            '---\nExample Quest:\n  files:\n    "<winLocalAppData>/EQ":\n      tags:\n        - save\n'
        )
        self.app.manifest.import_file(str(manifest_file))
        self.app.settings._data["launchPullTimeout"] = 5
        asyncio.run(self.app.update_game_config(KEY, {"enabled": True}))

    def run(self, coro):
        return asyncio.run(coro)

    def start_game(self):
        write_fake_proc(str(self.proc), 700, 1, "game.exe", uid=UID, env={"SteamAppId": str(APPID)})

    def stop_game(self):
        import shutil

        shutil.rmtree(self.proc / "700", ignore_errors=True)

    def other_device_saves(self, data):
        """Publish a newer snapshot from another device into the same local test store."""
        store = LocalFolderStore(os.path.join(self.paths.runtime_dir, "local-test-store"))
        other_rt = os.path.join(self.paths.runtime_dir, "..", "other")
        os.makedirs(other_rt, exist_ok=True)
        engine = SnapshotEngine(store, other_rt, other_rt, "eeeeee00-0000-0000-0000-000000000000", "Other", "t")
        other_saves = os.path.join(other_rt, "saves")
        os.makedirs(os.path.join(other_saves, "EQ"), exist_ok=True)
        with open(os.path.join(other_saves, "EQ", "slot.sav"), "wb") as h:
            h.write(data)
        base = engine.get_meta("example-quest", self.app._sync().status("example-quest")["base"])
        result = engine.take(
            "example-quest", {"winLocalAppData": ["EQ/slot.sav"]}, {"winLocalAppData": other_saves}, "auto-exit", base
        )
        assert result["status"] == "published", result
        return result


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


def prime(h):
    (h.saves / "slot.sav").write_bytes(b"chapter 1")
    assert h.run(h.app.sync_push(KEY))["status"] == "published"


def test_cloud_newer_is_restored_while_frozen_then_released(h):
    prime(h)
    h.other_device_saves(b"chapter 2 from other device")
    h.start_game()
    result = h.run(h.app._launch({"key": KEY, "appid": APPID, "name": "Example Quest", "prefix": None}))
    assert result["action"] == "restored"
    assert (h.saves / "slot.sav").read_bytes() == b"chapter 2 from other device"
    assert h.kills == [(700, SIGSTOP), (700, SIGCONT)]
    assert h.app.freezer.recorded() == []


def test_game_not_found_in_time_is_never_restored_under(h, monkeypatch):
    monkeypatch.setattr(lifecycle, "FIND_PROCESS_SECONDS", 0.2)
    prime(h)
    h.other_device_saves(b"newer")
    calls = []
    monkeypatch.setattr(h.app, "_wait_for_processes", lambda game: calls.append(1) or [])
    result = h.run(h.app._launch({"key": KEY, "appid": APPID, "name": "Example Quest"}))
    assert result["reason"] == "cloud-newer-game-running"
    assert (h.saves / "slot.sav").read_bytes() == b"chapter 1"
    assert ("keepsake_toast", (lifecycle.TOAST_CLOUD_NEWER,)) in h.events
    assert h.kills == []


def test_timeout_releases_game_and_late_pull_cannot_restore(h, monkeypatch):
    prime(h)
    h.other_device_saves(b"newer")
    h.start_game()
    h.app.settings._data["launchPullTimeout"] = 0.3
    late = {}
    original_pull = SyncEngine.pull

    def slow_pull(self, ctx):
        time.sleep(0.8)
        late["running_after_timeout"] = ctx.running()
        return original_pull(self, ctx)

    monkeypatch.setattr(SyncEngine, "pull", slow_pull)
    result = h.run(h.app._launch({"key": KEY, "appid": APPID, "name": "Example Quest", "prefix": None}))
    time.sleep(1.5)  # let the abandoned pull finish
    assert result["reason"] == "timeout"
    assert ("keepsake_toast", (lifecycle.TOAST_TIMEOUT,)) in h.events
    assert h.kills[-1] == (700, SIGCONT)
    assert late["running_after_timeout"] is True
    assert (h.saves / "slot.sav").read_bytes() == b"chapter 1"


def test_unexpected_failure_still_releases_the_game(h, monkeypatch):
    prime(h)
    h.start_game()

    def boom(self, ctx):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(SyncEngine, "pull", boom)
    with pytest.raises(RuntimeError):
        h.run(h.app._launch({"key": KEY, "appid": APPID, "name": "Example Quest", "prefix": None}))
    assert h.kills == [(700, SIGSTOP), (700, SIGCONT)]
    assert h.app.freezer.recorded() == []


def test_strict_mode_waits_for_token_and_releases_it(h):
    prime(h)
    h.other_device_saves(b"newer")
    asyncio.run(h.app.update_game_config(KEY, {"launchGate": "strict"}))
    gate = lifecycle.GateFiles(h.paths.runtime_dir)
    os.makedirs(gate.dir, exist_ok=True)
    with open(os.path.join(gate.dir, f"{APPID}.waiting"), "w") as handle:
        handle.write("0123456789abcdef")
    result = h.run(h.app._launch({"key": KEY, "appid": APPID, "name": "Example Quest", "prefix": None}))
    assert result["action"] == "restored"
    with open(os.path.join(gate.dir, f"{APPID}.ready")) as handle:
        assert handle.read() == "0123456789abcdef"
    assert h.kills == []  # nothing to freeze: the game had not started


def test_exit_pushes_once_the_game_has_gone(h):
    prime(h)
    (h.saves / "slot.sav").write_bytes(b"chapter 3")
    result = h.run(h.app._exit({"key": KEY, "appid": APPID, "name": "Example Quest", "prefix": None}))
    assert result["status"] == "published"
    assert ("keepsake_toast", ("Saved Example Quest to the cloud.",)) in h.events


def test_events_dispatch_for_any_id_shape(h, monkeypatch):
    started = []

    async def fake_launch(game):
        started.append(game["key"])

    monkeypatch.setattr(h.app, "_launch", fake_launch)

    async def run():
        out = await h.app.on_game_event("start", (APPID << 32) | 0x02000000)
        await asyncio.sleep(0.05)
        return out

    assert h.run(run()) == {"handled": 1}
    assert started == [KEY]
    assert h.run(h.app.on_game_event("start", 12345)) == {"handled": 0}


def test_strict_wrap_and_unwrap_round_trip_exactly(h):
    original = 'PROTON_LOG=1 %command% -a "x y"'
    wrapped = h.run(h.app.strict_wrap(KEY, original))
    assert "keepsake-gate" in wrapped["options"] and wrapped["options"].endswith('%command% -a "x y"')
    assert h.app.game_configs.get(KEY)["launchGate"] == "strict"
    restored = h.run(h.app.strict_unwrap(KEY))
    assert restored["options"] == original
    assert h.app.game_configs.get(KEY)["launchGate"] == "freeze"
    with pytest.raises(ValueError):
        h.run(h.app.strict_unwrap(KEY))


def test_played_without_keepsake_warns_once_and_saves(h, monkeypatch):
    prime(h)
    (h.saves / "slot.sav").write_bytes(b"played offline from Keepsake")
    real_discover = h.app.discover_games
    steam_saw = int(time.time()) + 3600  # Steam recorded a play Keepsake never saw start

    async def discover(refresh=False):
        result = await real_discover(refresh)
        for game in result["games"]:
            game["last_played"] = steam_saw
        return result

    monkeypatch.setattr(h.app, "discover_games", discover)
    first = h.run(h.app.idle_pass())
    second = h.run(h.app.idle_pass())
    toasts = [e for e in h.events if "played while Keepsake was not running" in str(e)]
    assert len(toasts) == 1
    assert first[0]["push"] == "published" and first[0]["playedWithoutKeepsake"] is True
    assert second[0]["push"] == "no-change"
