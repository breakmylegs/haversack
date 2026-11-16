"""Installer module (v2 slice 21): udisks handling, file lists and ranking, the job flow, and app wiring."""

import asyncio
import os

import pytest

from keepsake.installer import files, udisks
from keepsake.installer.service import Installer, InstallerError, windows_path
from keepsake.statedb import StateDB
from keepsake.steamops import SteamOps
from keepsake.store import LocalFolderStore
from test_app_ux import Device


class FakeUdisks:
    def __init__(self, mount_point, fail_mount=False):
        self.calls, self.mount_point, self.fail_mount = [], mount_point, fail_mount

    def __call__(self, command):
        self.calls.append(command[1])
        if command[1] == "loop-setup":
            return f"Mapped file {command[-1]} as /dev/loop7.\n"
        if command[1] == "mount":
            if self.fail_mount:
                raise udisks.UdisksError("Not authorized")
            return f"Mounted /dev/loop7 at {self.mount_point}\n"
        return ""


def test_mount_iso_parses_udisks_and_detaches_on_failure(tmp_path):
    ok = FakeUdisks("/run/media/deck/GAME_DISC")
    assert udisks.mount_iso("/home/deck/game.iso", ok) == ("/dev/loop7", "/run/media/deck/GAME_DISC")
    assert ok.calls == ["loop-setup", "mount"]
    failing = FakeUdisks("x", fail_mount=True)
    with pytest.raises(udisks.UdisksError):
        udisks.mount_iso("/home/deck/game.iso", failing)
    assert failing.calls == ["loop-setup", "mount", "unmount", "loop-delete"]  # nothing left attached
    with pytest.raises(udisks.UdisksError, match="loop device"):
        udisks.mount_iso("/x.iso", lambda command: "nothing useful")


def write(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def test_ranking_excludes_installers_and_prefers_the_title():
    paths = [
        ("/g/Example Quest/unins000.exe", 2_000_000),
        ("/g/Example Quest/vcredist_x64.exe", 9_000_000),
        ("/g/Example Quest/CrashReporter.exe", 3_000_000),
        ("/g/Example Quest/ExampleQuest.exe", 40_000_000),
        ("/g/Example Quest/Launcher.exe", 50_000_000),
        ("/g/Example Quest/tools/editor.exe", 30_000_000),
        ("/g/Example Quest/readme.txt", 10),
    ]
    ranked = [os.path.basename(r["path"]) for r in files.rank_game_exes(paths, "Example Quest")]
    assert ranked[0] == "ExampleQuest.exe"
    assert not {"unins000.exe", "vcredist_x64.exe", "CrashReporter.exe", "readme.txt"} & set(ranked)


def test_find_installers_prefers_setup_at_the_root(tmp_path):
    for rel in ("setup.exe", "autorun.exe", "redist/vcredist.exe", "data/deep/x/y.exe", "Game.exe"):
        write(str(tmp_path / rel))
    assert files.find_installers(str(tmp_path))[:2] == ["setup.exe", "autorun.exe"]
    assert "data/deep/x/y.exe" not in files.find_installers(str(tmp_path))


def test_add_shortcut_operation_and_library_setting_are_validated(tmp_path):
    from keepsake.settings import SettingsError, _validate
    from keepsake.steamops import SteamOpsError

    db = StateDB(str(tmp_path / "k.db"))
    ops = SteamOps(db)
    ok = {"name": "Install: Game", "exe": "/a/setup.exe", "startDir": "/a", "launchOptions": ""}
    assert ops.enqueue("installer", "add-shortcut", ok) > 0  # needs no app ID: Steam assigns it
    for missing in ok:
        with pytest.raises(SteamOpsError):
            ops.enqueue("installer", "add-shortcut", {k: v for k, v in ok.items() if k != missing})
    db.close()
    assert _validate("libraryRoot", " /run/media/card/Games/ ") == "/run/media/card/Games"
    assert _validate("libraryRoot", "") == ""
    for bad in ("Games", 5, "/a\x00b"):
        with pytest.raises(SettingsError):
            _validate("libraryRoot", bad)


def test_windows_path():
    assert windows_path("/home/deck/Games/Example Quest") == "Z:\\home\\deck\\Games\\Example Quest"


@pytest.fixture
def env(tmp_path):
    db = StateDB(str(tmp_path / "k.db"))
    ops = SteamOps(db)
    prefix = tmp_path / "compatdata" / "3000000001"
    library = tmp_path / "Games"
    installer = Installer(
        db,
        ops,
        lambda: str(library).replace(os.sep, "/"),
        lambda appid: str(prefix) if appid == 3000000001 else None,
        runner=FakeUdisks("/run/media/deck/DISC"),
        has_udisks=lambda: True,
    )
    yield installer, ops, tmp_path, prefix, library
    db.close()


def finish_all(installer, ops, appid=None, ok=True):
    while (op := ops.claim()) is not None:
        result = {"appid": appid} if op["kind"] == "add-shortcut" else {"readBack": op["payload"].get("value")}
        ops.finish(op["id"], ok, result)
        installer.op_finished(op["id"], ok, result)


def test_folder_install_flow_retargets_the_same_shortcut(env):
    installer, ops, tmp_path, prefix, library = env
    source = tmp_path / "gog"
    write(str(source / "setup_example_quest.exe"))
    job = installer.start(str(source), "Example Quest")
    assert job["state"] == "choose-installer" and job["installers"] == ["setup_example_quest.exe"]
    assert job["windowsTarget"].endswith("\\Games\\Example Quest")
    job = installer.create_shortcut(job["id"], "setup_example_quest.exe")
    assert job["state"] == "creating-shortcut"
    finish_all(installer, ops, appid=3000000001)
    assert installer.get(job["id"])["state"] == "run-installer"
    # The installer program writes the game; Wine's own files appear in the prefix too.
    write(str(library / "Example Quest" / "ExampleQuest.exe"), b"g" * 5000)
    write(str(library / "Example Quest" / "unins000.exe"))
    write(str(prefix / "pfx" / "drive_c" / "windows" / "system32" / "notepad.exe"), b"w" * 9000)
    assert installer.installer_exited(999) is None  # another app closing changes nothing
    job = installer.installer_exited(3000000001)
    assert job["state"] == "choose-game"
    names = [os.path.basename(c["path"]) for c in job["candidates"]]
    assert names == ["ExampleQuest.exe"]  # uninstaller and Wine's notepad never offered
    with pytest.raises(InstallerError):
        installer.retarget(job["id"], "/somewhere/else.exe")
    exe = job["candidates"][0]["path"]
    job = installer.retarget(job["id"], exe)
    assert job["state"] == "retargeting"
    queued = [o for o in ops.list() if o["state"] == "pending"]
    assert sorted(o["kind"] for o in queued) == [
        "set-launch-options",
        "set-shortcut-exe",
        "set-shortcut-name",
        "set-shortcut-start-dir",
    ]
    assert {o["payload"]["appid"] for o in queued} == {3000000001}
    assert next(o for o in queued if o["kind"] == "set-shortcut-exe")["payload"]["value"] == exe
    assert next(o for o in queued if o["kind"] == "set-launch-options")["payload"]["value"] == ""
    first = ops.claim()
    ops.finish(first["id"], True, {})
    installer.op_finished(first["id"], True, {})
    assert installer.get(job["id"])["state"] == "retargeting"  # done only when every change is confirmed
    finish_all(installer, ops)
    assert installer.get(job["id"])["state"] == "done"


def test_iso_install_mounts_read_only_passes_the_mount_and_detaches(env):
    installer, ops, tmp_path, _prefix, _library = env
    iso = tmp_path / "disc.iso"
    iso.write_bytes(b"iso")
    disc = (tmp_path / "DISC").as_posix()  # stands in for the udisks mount point
    write(disc + "/setup.exe")
    installer.runner = FakeUdisks(disc)
    job = installer.start(str(iso), "Disc Game")
    assert job["kind"] == "iso" and job["mount"] == disc and job["installers"] == ["setup.exe"]
    assert installer.runner.calls == ["loop-setup", "mount"]
    installer.create_shortcut(job["id"], "setup.exe")
    add = ops.claim()
    assert add["payload"]["exe"] == disc + "/setup.exe"
    assert add["payload"]["launchOptions"] == f'STEAM_COMPAT_MOUNTS="{disc}" %command%'
    ops.finish(add["id"], False, {"error": "Steam said no"})
    installer.op_finished(add["id"], False, {"error": "Steam said no"})
    failed = installer.get(job["id"])
    assert failed["state"] == "failed" and failed["unmounted"] is True
    assert installer.runner.calls[-2:] == ["unmount", "loop-delete"]


def test_refusals(env, tmp_path):
    installer, _ops, _tmp, _prefix, _library = env
    with pytest.raises(InstallerError, match="title"):
        installer.start(str(tmp_path), "bad/title")
    with pytest.raises(InstallerError, match="iso"):
        installer.start(str(tmp_path / "missing.zip"), "Game")
    installer.has_udisks = lambda: False
    (tmp_path / "x.iso").write_bytes(b"x")
    with pytest.raises(InstallerError, match="udisksctl"):
        installer.start(str(tmp_path / "x.iso"), "Game")
    job = installer.start(str(tmp_path), "Folder Game")
    with pytest.raises(InstallerError):
        installer.create_shortcut(job["id"], "not-listed.exe")
    assert installer.cancel(job["id"])["state"] == "cancelled"
    with pytest.raises(InstallerError, match="already finished"):
        installer.cancel(job["id"])


def test_app_routes_an_unsynced_exit_and_op_results_to_the_installer(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    source = tmp_path / "gog"
    write(str(source / "setup.exe"))

    async def go():
        await a.app.start()
        status = await a.app.installer_status()
        job = await a.app.installer_start(str(source), "Folder Game")
        await a.app.installer_create_shortcut(job["id"], "setup.exe")
        op = await a.app.steam_ops_claim()
        await a.app.steam_ops_finish(op["id"], True, {"appid": 3000000077})
        after_add = await a.app.installer_status()
        handled = await a.app.on_game_event("exit", 3000000077)
        after_exit = await a.app.installer_status()
        await a.app.stop()
        return status, after_add, handled, after_exit

    status, after_add, handled, after_exit = asyncio.run(go())
    assert status["running"] is True and status["libraryRoot"].endswith("/Games")
    assert after_add["jobs"][0]["state"] == "run-installer" and after_add["jobs"][0]["appid"] == 3000000077
    assert handled == {"handled": 0}  # Saves does not sync it ...
    assert after_exit["jobs"][0]["state"] == "choose-game"  # ... but the Installer heard it close
    assert ("keepsake_toast", ("Folder Game: choose the game's program in Keepsake, Installer.",)) in a.events
