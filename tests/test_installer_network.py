"""Network install through the Installer and the app (ADR-0033): staging, clean-up, locations. Synthetic only."""

import asyncio
import json
import os

import pytest

from helpers import Device
from keepsake.backends import CredentialStore
from keepsake.installer import remote
from keepsake.installer.service import InstallerError
from test_installer import FakeUdisks, env  # noqa: F401 (the fixture)
from test_installer_remote import Reply, Script

ISO = b"synthetic iso bytes"


def stage(installer, name="disc.iso"):
    path = os.path.join(installer.downloads_dir(), name)
    with open(path, "wb") as handle:
        handle.write(ISO)
    return path


def test_a_downloaded_iso_is_deleted_when_its_install_ends(env):  # noqa: F811
    installer, _ops, tmp_path, _prefix, _library = env
    disc = (tmp_path / "DISC").as_posix()
    os.makedirs(disc)
    open(disc + "/setup.exe", "wb").close()
    installer.runner = FakeUdisks(disc)
    path = stage(installer)
    job = installer.start(path, "Net Game", True)
    assert job["staged"] == os.path.realpath(path).replace(os.sep, "/") and os.path.exists(path)
    assert installer.clean_downloads() == []  # in use by an active install
    job = installer.cancel(job["id"])
    assert job["stagedRemoved"] is True and job["unmounted"] is True and not os.path.exists(path)


def test_a_failed_start_deletes_the_download_and_leftovers_are_cleaned(env):  # noqa: F811
    installer, _ops, _tmp, _prefix, _library = env
    path = stage(installer)
    with pytest.raises(InstallerError, match="title"):
        installer.start(path, "bad/title", True)
    assert not os.path.exists(path)
    stage(installer, "old.iso")
    stage(installer, "half.iso.part")
    assert installer.clean_downloads() == ["half.iso.part", "old.iso"]
    assert os.listdir(installer.downloads_dir()) == []


def test_a_staged_path_outside_the_downloads_folder_is_never_deleted(env):  # noqa: F811
    installer, _ops, tmp_path, _prefix, _library = env
    own = tmp_path / "mine.iso"
    own.write_bytes(ISO)
    installer.runner = FakeUdisks((tmp_path / "DISC").as_posix())
    job = installer.start(str(own), "My Game", True)
    installer.cancel(job["id"])
    assert own.exists()


def test_locations_keep_passwords_in_the_credential_store_and_never_return_them(tmp_path):
    credentials = CredentialStore(str(tmp_path))
    store = remote.LocationStore(str(tmp_path), credentials)
    listed = store.save("https://nas.example/games/", "player", "s3cret-pw")
    assert listed == [
        {"id": listed[0]["id"], "url": "https://nas.example/games/", "username": "player", "passwordSet": True}
    ]
    assert "s3cret-pw" not in (tmp_path / remote.LOCATIONS_FILE).read_text()
    assert "s3cret-pw" in (tmp_path / "netinstall-secrets.json").read_text()
    store.save("https://nas.example/iso/", "player", "", listed[0]["id"])  # empty keeps the password
    assert store.get(listed[0]["id"]) == (
        {"id": listed[0]["id"], "url": "https://nas.example/iso/", "username": "player"},
        "s3cret-pw",
    )
    with pytest.raises(remote.RemoteError, match="only sent over https"):
        store.save("http://nas.example/", "player", "pw")
    assert store.forget(listed[0]["id"]) == []
    assert json.loads((tmp_path / "netinstall-secrets.json").read_text()) == {}


@pytest.fixture
def device(env, tmp_path):  # noqa: F811
    installer, *_ = env
    a = Device(tmp_path / "dev", "a", 4171510507)
    a.app.installer = installer
    disc = (tmp_path / "DISC").as_posix()
    os.makedirs(disc, exist_ok=True)
    open(disc + "/setup.exe", "wb").close()
    installer.runner = FakeUdisks(disc)
    return a


async def finished(app):
    for _ in range(400):
        status = await app.installer_net_status()
        if not status["running"]:
            return status
        await asyncio.sleep(0.02)
    raise AssertionError("the download did not finish")


def test_app_browses_downloads_and_prepares_the_install(device):
    a = device
    a.app._net_connect = Script(
        {
            "https://nas.example/games/": Reply(200, {}, b'<a href="Disc%20One.iso">d</a><a href="Old/">o</a>'),
            "https://nas.example/games/Disc%20One.iso": Reply(200, {"Content-Length": str(len(ISO))}, ISO),
        }
    )
    access = {"url": "https://nas.example/games/", "username": "player", "password": "pw"}

    async def go():
        listing = await a.app.installer_net_browse(access)
        started = await a.app.installer_net_download(access, listing["entries"][1]["url"], "Disc One")
        return listing, started, await finished(a.app)

    listing, started, status = asyncio.run(go())
    assert [e["name"] for e in listing["entries"]] == ["Old", "Disc One.iso"]
    assert started["running"] is True and started["name"] == "Disc One.iso"
    job = a.app.installer.get(status["job"])
    assert job["state"] == "choose-installer" and job["installers"] == ["setup.exe"]
    assert os.path.basename(job["staged"]) == "Disc One.iso"
    events = [args[0] for event, args in a.events if event == "keepsake_netinstall_progress"]
    assert events[-1]["running"] is False and events[-1]["job"] == job["id"]


def test_app_refuses_another_host_and_reports_redirects(device):
    a = device
    a.app._net_connect = Script({"https://nas.example/a.iso": Reply(302, {"Location": "https://mirror.example/a.iso"})})
    access = {"url": "https://nas.example/"}

    async def go():
        with pytest.raises(ValueError, match="location you chose"):
            await a.app.installer_net_download(access, "https://other.example/a.iso", "A")
        await a.app.installer_net_download(access, "https://nas.example/a.iso", "A")
        return await finished(a.app)

    status = asyncio.run(go())
    assert status["redirectHost"] == "mirror.example" and "job" not in status
    assert os.listdir(a.app.installer.downloads_dir()) == []


def test_app_cancel_stops_the_download(device):
    a = device

    class Slow(Reply):
        def read(self, n=-1):
            asyncio.run_coroutine_threadsafe(a.app.installer_net_cancel(), loop[0]).result()
            return b"x" * 10

    loop = [None]
    a.app._net_connect = Script({"https://nas.example/a.iso": Slow(200, {"Content-Length": "1000"})})

    async def go():
        loop[0] = asyncio.get_running_loop()
        await a.app.installer_net_download({"url": "https://nas.example/"}, "https://nas.example/a.iso", "A")
        return await finished(a.app)

    status = asyncio.run(go())
    assert status["cancelled"] is True and os.listdir(a.app.installer.downloads_dir()) == []


def test_the_installer_must_be_on(tmp_path):
    a = Device(tmp_path, "a", 4171510507)
    with pytest.raises(ValueError, match="Installer module is off"):
        asyncio.run(a.app.installer_net_browse({"url": "https://nas.example/"}))
