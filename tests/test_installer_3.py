"""R6, Installer III (ADR-0053): disc sets, the install queue with resume after a restart, and runtime hints.
Synthetic discs, prefixes and games only."""

import os

import pytest

from keepsake.installer import cdrom, files
from keepsake.installer.service import InstallerError
from test_installer import FakeLinks, env, finish_all, make_prefix, write  # noqa: F401 - the fixture


class DiscUdisks:
    """Mounts each ISO at its own folder and loop device, like udisks does for different discs."""

    def __init__(self, tmp_path):
        self.tmp_path, self.calls, self.attached = tmp_path, [], {}

    def __call__(self, command):
        self.calls.append(command[1:])
        if command[1] == "loop-setup":
            iso = command[-1]
            device = f"/dev/loop{len(self.attached) + 7}"
            self.attached[device] = iso
            return f"Mapped file {iso} as {device}.\n"
        if command[1] == "mount":
            device = command[-1]
            name = os.path.splitext(os.path.basename(self.attached[device]))[0].upper()
            point = (self.tmp_path / "media" / name).as_posix()
            os.makedirs(point, exist_ok=True)
            write(point + "/setup.exe")
            return f"Mounted {device} at {point}\n"
        return ""

    def detached(self):
        return [c[-1] for c in self.calls if c[0] == "loop-delete"]


def disc_set(tmp_path, *names):
    folder = tmp_path / "Example Quest"
    folder.mkdir(exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"iso")
    return folder


def links_shim(fake):
    shim = fake.shim()

    def replace(source, target):
        fake.links[target] = fake.links.pop(source)

    shim.replace = replace
    return shim


# Disc sets


def test_the_other_discs_of_a_set_are_offered_in_order(tmp_path):
    folder = disc_set(tmp_path, "Disc 2.iso", "Disc 1.iso", "Disc 3.ISO", "manual.pdf")
    assert files.sibling_discs(str(folder / "Disc 1.iso")) == ["Disc 2.iso", "Disc 3.ISO"]
    assert files.sibling_discs(str(tmp_path / "nowhere" / "x.iso")) == []


def test_a_disc_swap_repoints_the_drive_and_lets_the_old_disc_go(env, monkeypatch):  # noqa: F811
    installer, ops, tmp_path, prefix, _library = env
    fake = FakeLinks()
    monkeypatch.setattr(cdrom, "os", links_shim(fake))
    installer.symlink = fake.symlink
    installer.runner = udisks = DiscUdisks(tmp_path)
    folder = disc_set(tmp_path, "Disc 1.iso", "Disc 2.iso")
    job = installer.start(str(folder / "Disc 1.iso"), "Example Quest")
    assert job["otherDiscs"] == ["Disc 2.iso"]
    assert job["compatMounts"] == ""  # the mount folder is inside the synthetic home here
    with pytest.raises(InstallerError, match="disc drive first"):
        installer.swap_disc(job["id"], "Disc 2.iso")
    installer.create_shortcut(job["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    make_prefix(prefix)
    job = installer.add_cd_drive(job["id"])
    drive = os.path.join(str(prefix), "pfx", "dosdevices", "d:")
    assert fake.links[drive].endswith("/media/DISC 1")
    with pytest.raises(InstallerError, match="other discs"):
        installer.swap_disc(job["id"], "../../etc/passwd.iso")
    swapped = installer.swap_disc(job["id"], "Disc 2.iso")  # allowed while the installer runs
    assert fake.links[drive].endswith("/media/DISC 2") and fake.links[drive + ":"] == swapped["device"]
    assert swapped["mount"].endswith("/media/DISC 2") and swapped["otherDiscs"] == ["Disc 1.iso"]
    assert udisks.detached() == ["/dev/loop7"]  # disc 1 is released
    back = installer.swap_disc(job["id"], "Disc 1.iso")  # and back again, if the installer asks
    assert fake.links[drive].endswith("/media/DISC 1") and back["otherDiscs"] == ["Disc 2.iso"]
    assert not any(link.endswith(".keepsake-swap") for link in fake.links)


def test_a_drive_changed_outside_keepsake_is_left_alone(env, monkeypatch):  # noqa: F811
    installer, ops, tmp_path, prefix, _library = env
    fake = FakeLinks()
    monkeypatch.setattr(cdrom, "os", links_shim(fake))
    installer.symlink = fake.symlink
    installer.runner = udisks = DiscUdisks(tmp_path)
    folder = disc_set(tmp_path, "Disc 1.iso", "Disc 2.iso")
    job = installer.start(str(folder / "Disc 1.iso"), "Example Quest")
    installer.create_shortcut(job["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    make_prefix(prefix)
    installer.add_cd_drive(job["id"])
    drive = os.path.join(str(prefix), "pfx", "dosdevices", "d:")
    fake.links[drive] = "/somewhere/else"
    with pytest.raises(InstallerError, match="outside Keepsake"):
        installer.swap_disc(job["id"], "Disc 2.iso")
    assert fake.links[drive] == "/somewhere/else"
    assert udisks.detached() == ["/dev/loop8"]  # the disc mounted for the swap is released again


# The install queue


def test_installs_queue_and_start_one_after_another(env):  # noqa: F811
    installer, _ops, tmp_path, _prefix, _library = env
    first = tmp_path / "first"
    second = tmp_path / "second"
    for folder in (first, second):
        write(str(folder / "setup.exe"))
    active = installer.start(str(first), "First Game")
    queued = installer.start(str(second), "Second Game", queue=True)
    assert active["state"] == "choose-installer" and queued["state"] == "queued"
    installer.cancel(active["id"])
    started = installer.get(queued["id"])
    assert started["state"] == "choose-installer" and started["installers"] == ["setup.exe"]


def test_a_queued_install_starts_at_once_when_nothing_else_runs(env):  # noqa: F811
    installer, _ops, tmp_path, _prefix, _library = env
    write(str(tmp_path / "only" / "setup.exe"))
    assert installer.start(str(tmp_path / "only"), "Only Game", queue=True)["state"] == "choose-installer"


def test_a_queued_install_that_cannot_start_fails_and_the_next_one_goes(env):  # noqa: F811
    installer, _ops, tmp_path, _prefix, _library = env
    write(str(tmp_path / "busy" / "setup.exe"))
    write(str(tmp_path / "gone" / "setup.exe"))
    write(str(tmp_path / "next" / "setup.exe"))
    busy = installer.start(str(tmp_path / "busy"), "Busy Game")
    gone = installer.start(str(tmp_path / "gone"), "Gone Game", queue=True)
    nxt = installer.start(str(tmp_path / "next"), "Next Game", queue=True)
    os.remove(tmp_path / "gone" / "setup.exe")
    os.rmdir(tmp_path / "gone")
    installer.cancel(busy["id"])
    assert installer.get(gone["id"])["state"] == "failed" and "folder" in installer.get(gone["id"])["error"]
    assert installer.get(nxt["id"])["state"] == "choose-installer"


def test_a_queued_install_can_be_cancelled_and_bad_ones_are_refused(env):  # noqa: F811
    installer, _ops, tmp_path, _prefix, _library = env
    write(str(tmp_path / "a" / "setup.exe"))
    write(str(tmp_path / "b" / "setup.exe"))
    installer.start(str(tmp_path / "a"), "Game A")
    queued = installer.start(str(tmp_path / "b"), "Game B", queue=True)
    assert installer.cancel(queued["id"])["state"] == "cancelled"
    with pytest.raises(InstallerError, match="title"):
        installer.start(str(tmp_path / "b"), "bad/title", queue=True)
    with pytest.raises(InstallerError, match="iso"):
        installer.start(str(tmp_path / "missing.zip"), "Game C", queue=True)


def test_after_a_restart_discs_are_mounted_again_or_the_install_fails_plainly(env):  # noqa: F811
    installer, ops, tmp_path, _prefix, _library = env
    installer.runner = DiscUdisks(tmp_path)
    folder = disc_set(tmp_path, "One.iso", "Two.iso")
    early = installer.start(str(folder / "One.iso"), "Early Game")
    os.rename(early["mount"], early["mount"] + "-gone")  # the restart unmounted it
    resumed = installer.resume()
    assert [j["id"] for j in resumed] == [early["id"]]
    assert os.path.isdir(installer.get(early["id"])["mount"])
    # Later in the flow, a disc that comes back at another place would break the shortcut: fail plainly.
    installer.create_shortcut(early["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    job = installer.get(early["id"])
    data_mount = job["mount"]
    os.rename(data_mount, data_mount + "-gone2")
    installer.runner.attached.clear()

    def elsewhere(command):
        if command[1] == "mount":
            point = (tmp_path / "media" / "ELSEWHERE").as_posix()
            os.makedirs(point, exist_ok=True)
            return f"Mounted {command[-1]} at {point}\n"
        return DiscUdisks.__call__(installer.runner_original, command)

    installer.runner_original = DiscUdisks(tmp_path)
    installer.runner = elsewhere
    installer.resume()
    failed = installer.get(early["id"])
    assert failed["state"] == "failed" and "different place" in failed["error"]


# Runtime hints


def test_runtime_installers_shipped_with_a_game_are_listed_as_guidance():
    listing = {
        "_CommonRedist/vcredist/2015/VC_redist.x64.exe": (1, 0.0),
        "_CommonRedist/DirectX/Jun2010/DXSETUP.exe": (1, 0.0),
        "Redist/dotNetFx40_Full_x86_x64.exe": (1, 0.0),
        "Redist/PhysX_9.21_SystemSoftware.msi": (1, 0.0),
        "Game.exe": (1, 0.0),
        "readme.txt": (1, 0.0),
        "_CommonRedist/vcredist/vcredist_readme.txt": (1, 0.0),  # named like one, but not a program
    }
    found = files.find_runtimes(listing, {"DISC/oalinst.exe": (1, 0.0)})
    assert sorted(f["runtime"] for f in found) == sorted(
        ["DirectX", "Visual C++ runtime", "PhysX", ".NET Framework", "OpenAL"]
    )
    assert "Game.exe" not in [f["path"] for f in found]
    assert len(files.find_runtimes({f"r/vcredist{n}.exe": (1, 0.0) for n in range(30)})) == 20  # capped


def test_runtimes_are_found_when_the_installer_closes(env):  # noqa: F811
    installer, ops, tmp_path, _prefix, library = env
    source = tmp_path / "src"
    write(str(source / "setup.exe"))
    write(str(source / "_CommonRedist" / "vcredist_x64.exe"))
    job = installer.start(str(source), "Redist Game")
    installer.create_shortcut(job["id"], "setup.exe")
    finish_all(installer, ops, appid=3000000001)
    write(str(library / "Redist Game" / "Game.exe"), b"x" * 2000)
    done = installer.installer_exited(3000000001)
    assert done["runtimes"] == [{"runtime": "Visual C++ runtime", "path": "_CommonRedist/vcredist_x64.exe"}]
