"""Installer module (v2 slice 21): udisks handling, file lists and ranking, the job flow, and app wiring."""

import asyncio
import json
import os

import pytest

from helpers import Device
from keepsake.installer import files, udisks
from keepsake.installer.service import Installer, InstallerError, windows_path
from keepsake.statedb import StateDB
from keepsake.steamops import SteamOps


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
        home=lambda: tmp_path.as_posix(),  # the synthetic sources and library sit inside "home"
        running=lambda appid, prefix: False,
        work_dir=str(tmp_path / "work"),
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
    assert add["payload"]["launchOptions"] == ""  # inside home: the runtime container already sees it
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


def test_app_routes_a_game_exit_and_op_results_to_the_installer(tmp_path):
    a = Device(tmp_path, "a", 4171510507)
    source = tmp_path / "a" / "home" / "gog"  # inside the device home, as a download would be
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
    assert handled == {"handled": 1}  # passed on for every game (ADR-0098) ...
    assert after_exit["jobs"][0]["state"] == "choose-game"  # ... so the Installer heard it close
    assert ("keepsake_toast", ("Folder Game: choose the game's program in Haversack, Installer.",)) in a.events


# Slice 22


class FakeLinks:
    """A link table standing in for symlinks, which Windows test runs cannot create."""

    def __init__(self):
        self.links = {}

    def symlink(self, target, link):
        assert link not in self.links
        self.links[link] = target

    def shim(self):
        import types

        def lexists(p):
            return p in self.links or os.path.lexists(p)

        path = types.SimpleNamespace(
            join=os.path.join,
            isfile=os.path.isfile,
            isdir=os.path.isdir,
            lexists=lexists,
            islink=self.links.__contains__,
        )
        return types.SimpleNamespace(path=path, readlink=self.links.__getitem__, unlink=self.links.pop)


SYSTEM_REG = (
    'WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n\n[Software\\\\Wine] 1700000000\n"Version"="win10"\n'
)


def make_prefix(prefix):
    write(str(prefix / "pfx" / "system.reg"), SYSTEM_REG.encode())
    os.makedirs(prefix / "pfx" / "dosdevices", exist_ok=True)


def test_cd_drive_links_the_disc_sets_cdrom_and_is_removed_at_the_end(env, monkeypatch):
    from keepsake.installer import cdrom

    installer, ops, tmp_path, prefix, _library = env
    fake = FakeLinks()
    monkeypatch.setattr(cdrom, "os", fake.shim())
    installer.symlink = fake.symlink
    iso = tmp_path / "disc.iso"
    iso.write_bytes(b"iso")
    disc = (tmp_path / "DISC").as_posix()
    write(disc + "/setup.exe")
    installer.runner = FakeUdisks(disc)
    job = installer.start(str(iso), "Disc Game")
    installer.create_shortcut(job["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    with pytest.raises(InstallerError, match="once"):
        installer.add_cd_drive(job["id"])  # Proton has not made the prefix yet: nothing is touched
    assert fake.links == {}
    make_prefix(prefix)
    installer.running = lambda appid, pfx: True
    with pytest.raises(InstallerError, match="quit"):
        installer.add_cd_drive(job["id"])
    installer.running = lambda appid, pfx: False
    fake.links[os.path.join(str(prefix), "pfx", "dosdevices", "d:")] = "/media/other"  # d: is taken
    job = installer.add_cd_drive(job["id"])
    dosdevices = os.path.join(str(prefix), "pfx", "dosdevices")
    assert job["cdDrive"]["letter"] == "e"
    assert fake.links[os.path.join(dosdevices, "e:")] == disc
    assert fake.links[os.path.join(dosdevices, "e::")] == "/dev/loop7"
    reg = (prefix / "pfx" / "system.reg").read_text()
    assert "[Software\\\\Wine\\\\Drives]" in reg and '"e:"="cdrom"' in reg and '"Version"="win10"' in reg
    assert os.listdir(tmp_path / "work" / "registry-backups")  # the original was kept first
    assert installer.add_cd_drive(job["id"])["cdDrive"]["letter"] == "e"  # asking twice changes nothing
    installer.cancel(job["id"])
    assert fake.links == {os.path.join(dosdevices, "d:"): "/media/other"}  # only Keepsake's own links go


def test_cd_drive_is_idempotent_and_leaves_changed_links_alone(tmp_path, monkeypatch):
    from keepsake.installer import cdrom

    fake = FakeLinks()
    monkeypatch.setattr(cdrom, "os", fake.shim())
    prefix = tmp_path / "compatdata" / "3000000005"
    make_prefix(prefix)
    first = cdrom.add_drive(str(prefix), "/run/media/deck/DISC", "/dev/loop7", str(tmp_path / "b"), fake.symlink)
    again = cdrom.add_drive(str(prefix), "/run/media/deck/DISC", "/dev/loop7", str(tmp_path / "b"), fake.symlink)
    assert first["letter"] == again["letter"] == "d" and again["links"] == []  # the same disc is not added twice
    drive, raw = first["links"]
    fake.links[drive] = "/somewhere/else"  # changed by someone else since
    removed = cdrom.remove_links(first["links"], {drive: "/run/media/deck/DISC", raw: "/dev/loop7"})
    assert removed == [raw] and fake.links == {drive: "/somewhere/else"}


def test_cd_drive_refusals(env):
    installer, _ops, tmp_path, _prefix, _library = env
    job = installer.start(str(tmp_path), "Folder Game")
    with pytest.raises(InstallerError, match="ISO"):
        installer.add_cd_drive(job["id"])


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="symlinks need POSIX")
def test_cd_drive_with_real_symlinks(tmp_path):
    from keepsake.installer import cdrom

    prefix = tmp_path / "compatdata" / "3000000002"
    make_prefix(prefix)
    made = cdrom.add_drive(str(prefix), "/run/media/deck/DISC", "/dev/loop7", str(tmp_path / "backups"))
    assert made["letter"] == "d" and os.readlink(prefix / "pfx" / "dosdevices" / "d:") == "/run/media/deck/DISC"
    assert cdrom.remove_links(made["links"], {made["links"][0]: "/run/media/deck/DISC", made["links"][1]: "/dev/loop7"})
    assert not os.path.lexists(prefix / "pfx" / "dosdevices" / "d:")


def test_sources_outside_home_are_passed_to_the_runtime(env, monkeypatch):
    from keepsake.installer import service

    installer, ops, _tmp, _prefix, _library = env
    installer.home = lambda: "/home/deck"
    installer.library_root = lambda: "/run/media/deck/SD/Games"
    monkeypatch.setattr(service.files, "find_installers", lambda root: ["setup.exe"])
    monkeypatch.setattr(service.os.path, "isfile", lambda p: str(p).endswith(".iso"))
    monkeypatch.setattr(service.os.path, "realpath", lambda p: p)
    job = installer.start("/home/deck/Downloads/disc.iso", "Disc Game")
    assert job["compatMounts"] == "/run/media/deck:/run/media/deck/SD/Games/Disc Game"
    installer.create_shortcut(job["id"], "setup.exe")
    options = ops.claim()["payload"]["launchOptions"]
    assert options == 'STEAM_COMPAT_MOUNTS="/run/media/deck:/run/media/deck/SD/Games/Disc Game" %command%'
    assert files.compat_mounts(["/home/deck/Games/X", "/home/deck"], "/home/deck") == ""
    assert files.compat_mounts(["/home/deckard/X"], "/home/deck") == "/home/deckard/X"  # not a prefix match
    with pytest.raises(ValueError):
        files.compat_mounts(["/mnt/a:b"], "/home/deck")
    # Only the folder discs are mounted under goes into the launch option (ADR-0053), so a colon in a disc's
    # own name is harmless; a colon in the library folder still cannot be carried, so that is refused.
    installer.library_root = lambda: "/run/media/deck/SD:X/Games"
    with pytest.raises(InstallerError):
        installer.start("/home/deck/Downloads/disc.iso", "Disc Game")
    assert installer.runner.calls[-2:] == ["unmount", "loop-delete"]  # refused, and the disc released


def test_mounted_sources_finds_network_shares_and_removable_drives():
    mounts = "\n".join(
        [
            "/dev/nvme0n1p8 /home ext4 rw 0 0",
            "//nas/games /mnt/nas\\040games cifs rw 0 0",
            "nas:/export /mnt/nfs nfs4 rw 0 0",
            "gvfsd-fuse /run/user/1000/gvfs fuse.gvfsd-fuse rw 0 0",
            "/dev/mmcblk0p1 /run/media/deck/SDCARD ext4 rw 0 0",
            "/dev/sda1 /run/media/deck/USB exfat rw 0 0",
            "/dev/sdb1 /boot vfat rw 0 0",
            "proc /proc proc rw 0 0",
        ]
    )
    found = files.mounted_sources(mounts, ("/run/media/deck/",))
    assert found["network"] == ["/mnt/nas games", "/mnt/nfs", "/run/user/1000/gvfs"]
    assert found["removable"] == ["/run/media/deck/SDCARD", "/run/media/deck/USB"]  # /boot is not offered


def test_remove_shortcut_only_for_a_stopped_installer_shortcut(env):
    installer, ops, tmp_path, _prefix, _library = env
    write(str(tmp_path / "src" / "setup.exe"))
    job = installer.start(str(tmp_path / "src"), "Stopped Game")
    with pytest.raises(InstallerError):
        installer.remove_shortcut(job["id"])  # still running and no shortcut yet
    installer.create_shortcut(job["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    installer.cancel(job["id"])
    job = installer.remove_shortcut(job["id"])
    op = ops.claim()
    assert op["kind"] == "remove-shortcut" and op["payload"] == {"appid": 3000000001}
    ops.finish(op["id"], True, {})
    assert installer.op_finished(op["id"], True, {})["shortcutRemoved"] is True
    with pytest.raises(InstallerError):
        installer.remove_shortcut(job["id"])  # once only


def test_health_reports_discs_leftover_shortcuts_and_waiting_changes():
    from keepsake.installer.service import health_checks

    now = 1_800_000_000.0
    jobs = [
        {"title": "A", "state": "cancelled", "device": "/dev/loop7", "updated": now},  # not released
        {"title": "B", "state": "run-installer", "device": "/dev/loop8", "updated": now - 13 * 3600},  # stale
        {"title": "C", "state": "run-installer", "device": "/dev/loop9", "updated": now - 60},  # in use
        {"title": "D", "state": "failed", "appid": 3000000003, "updated": now},  # shortcut left
        {"title": "E", "state": "failed", "appid": 3000000004, "shortcutRemoved": True, "updated": now},
        {"title": "F", "state": "cancelled", "device": "/dev/loop6", "unmounted": True, "updated": now},
    ]
    ops = [
        {"module": "installer", "kind": "set-artwork", "state": "pending", "created": now - 3600},
        {"module": "installer", "kind": "add-shortcut", "state": "pending", "created": now - 10},
        {"module": "core", "kind": "probe", "state": "pending", "created": now - 3600},
    ]
    checks = {c["id"]: c for c in health_checks(jobs, ops, now)}
    assert checks["installer-discs"]["items"] == ["A", "B"]
    assert checks["installer-shortcuts"]["items"] == ["D"]
    assert checks["installer-steam-ops"]["items"] == ["set-artwork"]
    assert health_checks([], [], now)[0]["status"] == "ok"


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
KEY = "a" * 32


class FakeGrid:
    def __init__(self):
        self.calls = []

    def fetch(self, url, headers=None, allowed=None, **kw):
        from keepsake import net

        net.check_url(url, allowed)
        self.calls.append((url, dict(headers or {})))
        if "/search/" in url:
            data = [{"id": 77, "name": "Example Quest", "verified": True}]
        elif "logos" in url:
            data = []
        else:
            data = [{"url": "https://cdn2.steamgriddb.com/grid/abc.png"}, {"url": "https://cdn2.steamgriddb.com/x.png"}]
        return net.HttpResponse(200, {}, json.dumps({"success": True, "data": data}).encode())

    def fetch_to_file(self, url, dest, max_bytes=None, allowed=None, **kw):
        from keepsake import net

        net.check_url(url, allowed)
        self.calls.append((url, {}))
        with open(dest, "wb") as handle:
            handle.write(PNG)
        return net.HttpResponse(200, {})


def test_artwork_is_approved_and_the_switch_still_stops_downloads(tmp_path, monkeypatch):
    from keepsake.installer import artwork

    assert artwork.available() is True  # image host approved by Peter, 16 November 2026 (ADR-0027)
    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", False)
    grid = FakeGrid()
    client = artwork.SteamGridDB(lambda: KEY, grid.fetch, grid.fetch_to_file)
    assert artwork.available() is False
    assert [c["assetType"] for c in client.choose(77)] == [0, 3, 1]  # no logo on SteamGridDB: skipped
    with pytest.raises(artwork.ArtworkError, match="approval"):
        client.download("https://cdn2.steamgriddb.com/grid/abc.png", str(tmp_path / "x"))
    assert not any("cdn2" in url for url, _h in grid.calls)  # nothing fetched from the unapproved host
    with pytest.raises(artwork.ArtworkError, match="key"):
        artwork.SteamGridDB(lambda: "", grid.fetch).search("x")


def test_artwork_flow_when_approved(env, monkeypatch):
    from keepsake.installer import artwork

    installer, ops, tmp_path, _prefix, library = env
    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", True)
    grid = FakeGrid()
    installer.art = artwork.SteamGridDB(lambda: KEY, grid.fetch, grid.fetch_to_file)
    write(str(tmp_path / "src" / "setup.exe"))
    job = installer.start(str(tmp_path / "src"), "Example Quest")
    with pytest.raises(InstallerError, match="once the shortcut"):
        installer.queue_artwork(job["id"], 77)
    installer.create_shortcut(job["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    write(str(library / "Example Quest" / "ExampleQuest.exe"), b"g" * 5000)
    job = installer.installer_exited(3000000001)
    installer.retarget(job["id"], job["candidates"][0]["path"])
    finish_all(installer, ops)
    assert installer.search_artwork(job["id"]) == [{"id": 77, "name": "Example Quest", "verified": True}]
    installer.queue_artwork(job["id"], 77)
    for url, headers in grid.calls:
        assert ("Authorization" in headers) == url.startswith("https://www.steamgriddb.com/")  # key only to the API
    queued = [ops.claim() for _ in range(3)]
    assert [(o["kind"], o["payload"]["assetType"], o["payload"]["imageType"]) for o in queued] == [
        ("set-artwork", 0, "png"),
        ("set-artwork", 3, "png"),
        ("set-artwork", 1, "png"),
    ]
    staged = installer.staged_file({**ops.get(queued[0]["id"])})
    assert open(staged, "rb").read() == PNG
    ops.finish(queued[0]["id"], True, {})
    assert installer.op_finished(queued[0]["id"], True, {})["artwork"] == {"job1-capsule.png": True}
    assert not os.path.exists(staged)  # the staged copy goes once Steam has it
    with pytest.raises(InstallerError):
        installer.staged_file(ops.get(queued[0]["id"]))  # no longer claimed


def test_artwork_refuses_non_images(tmp_path, monkeypatch):
    from keepsake import net
    from keepsake.installer import artwork

    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", True)

    def html(url, dest, **kw):
        with open(dest, "wb") as handle:
            handle.write(b"<html>")
        return net.HttpResponse(200, {})

    client = artwork.SteamGridDB(lambda: KEY, FakeGrid().fetch, html)
    with pytest.raises(artwork.ArtworkError, match="PNG"):
        client.download("https://cdn2.steamgriddb.com/a.png", str(tmp_path / "a"))
    assert not (tmp_path / "a").exists()
    with pytest.raises(net.DisallowedHost):
        client.download("https://evil.example/a.png", str(tmp_path / "b"))


def test_artwork_key_and_ops_validation(tmp_path):
    from keepsake.backends import BackendConfigError, CredentialStore
    from keepsake.steamops import SteamOpsError

    store = CredentialStore(str(tmp_path))
    with pytest.raises(BackendConfigError):
        store.save("steamgriddb", {"apiKey": "not a key!"})
    assert store.save("steamgriddb", {"apiKey": KEY}) == {"apiKey": "", "apiKeySet": True, "configured": True}
    db = StateDB(str(tmp_path / "k.db"))
    ops = SteamOps(db)
    good = {"appid": 3000000001, "assetType": 0, "imageType": "png", "file": "job1-capsule.png"}
    assert ops.enqueue("installer", "set-artwork", good)
    for bad in ({"assetType": 5}, {"imageType": "webp"}, {"file": "../x.png"}, {"file": "a/b.png"}):
        with pytest.raises(SteamOpsError):
            ops.enqueue("installer", "set-artwork", {**good, **bad})
    with pytest.raises(SteamOpsError):
        ops.enqueue("installer", "remove-shortcut", {})
    db.close()


def test_app_announces_the_installed_game_and_hands_off_to_games(tmp_path, monkeypatch):
    from keepsake.installer import artwork

    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", True)
    a = Device(tmp_path, "a", 4171510507)
    source = tmp_path / "a" / "home" / "gog"  # inside the device home, as a download would be
    write(str(source / "setup.exe"))
    heard = []

    async def go():
        await a.app.start()

        async def listener(payload):
            heard.append(payload)

        a.app.bus.subscribe("game_installed", "test", listener)
        job = await a.app.installer_start(str(source), "Folder Game")
        await a.app.installer_create_shortcut(job["id"], "setup.exe")
        op = await a.app.steam_ops_claim()
        await a.app.steam_ops_finish(op["id"], True, {"appid": 4171510507})
        target = a.app.installer.get(job["id"])["target"]
        write(target + "/FolderGame.exe", b"g" * 4000)
        job = await a.app.installer_finished_installing(job["id"])
        await a.app.installer_retarget(job["id"], job["candidates"][0]["path"])
        while (op := await a.app.steam_ops_claim()) is not None:
            await a.app.steam_ops_finish(op["id"], True, {})
        handoff = await a.app.installer_handoff(job["id"])
        # Artwork finishing later on the same, done job does not announce the game again.
        grid = FakeGrid()
        a.app.installer.art = artwork.SteamGridDB(lambda: KEY, grid.fetch, grid.fetch_to_file)
        await a.app.installer_artwork_apply(job["id"], 77)
        while (op := await a.app.steam_ops_claim()) is not None:
            await a.app.steam_ops_finish(op["id"], True, {})
        health = await a.app.modules_status()
        await a.app.stop()
        return handoff, health

    handoff, health = asyncio.run(go())
    # Announced once, when the retarget finished.
    assert heard == [{"event": "game_installed", "gameKey": None, "appid": 4171510507, "title": "Folder Game"}]
    assert handoff == {"key": a.key, "replication": True}  # Moving games is on by default (ADR-0098)
    assert ("keepsake_toast", ("Folder Game is installed. Start it from your library.",)) in a.events
    installer = next(m for m in health["modules"] if m["name"] == "installer")
    assert {c["id"] for c in installer["health"]} >= {"udisksctl", "installer-discs", "installer-shortcuts"}


def test_forget_appid_removes_only_finished_installs_of_that_game(env):
    installer, _ops, _tmp, _prefix, _library = env

    def job(state, appid):
        installer.db.execute(
            "INSERT INTO installer_jobs (title, state, data, created, updated) VALUES (?, ?, ?, 0, 0)",
            ("Example Quest", state, json.dumps({"appid": appid})),
        )

    job("done", 3000000001)
    job("failed", 3000000001)
    job("run-installer", 3000000001)  # still running: kept
    job("done", 3000000002)  # another game: kept
    assert installer.forget_appid(3000000001) == 2  # ADR-0065
    assert sorted((j["state"], j["appid"]) for j in installer.jobs()) == [
        ("done", 3000000002),
        ("run-installer", 3000000001),
    ]
