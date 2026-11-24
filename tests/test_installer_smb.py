"""Windows share installs (ADR-0034) against a fake pysmb connection. Synthetic data only."""

import asyncio
import hashlib
import os
import socket
from typing import ClassVar

import pytest

from helpers import Device
from keepsake.installer import remote, smbshare, udisks
from keepsake.installer.remote import Cancelled, RemoteError
from keepsake.installer.smbshare import Share
from test_installer import FakeUdisks, env  # noqa: F401 (the fixture)

DATA = bytes(range(256)) * 40_000  # about 10 MiB: three chunks
SHA = hashlib.sha256(DATA).hexdigest()
PLENTY = lambda path: 1 << 50  # noqa: E731
LAN = lambda host: ["192.168.1.20"]  # noqa: E731


class Device_:
    def __init__(self, name, kind=0, special=False):
        self.name, self.type, self.isSpecial = name, kind, special


class File:
    def __init__(self, name, directory=False, size=0):
        self.filename, self.isDirectory, self.file_size = name, directory, size


class OperationFailure(Exception):
    pass


class FakeServer:
    """Scripts what a share returns; ``drops`` makes the next N reads fail part-way."""

    def __init__(self, smb2=True, password="pw"):
        self.smb2, self.password = smb2, password
        self.files = {("Games", "/Disc One.iso"): DATA}
        self.connects = []
        self.drops = 0
        self.reads = []

    def __call__(self, ip, port, host, username, password):
        self.connects.append((ip, port, host, username))
        if password != self.password:
            raise RemoteError("the share refused the user name or password (or needs one)")
        server = self

        class Conn:
            def isUsingSMB2(self):
                return server.smb2

            def listShares(self, timeout):
                return [Device_("Games"), Device_("IPC$", 3, True), Device_("ADMIN$", 0, True), Device_("printer", 1)]

            def listPath(self, share, path, timeout):
                if share != "Games":
                    raise OperationFailure("no such share")
                return [
                    File("."),
                    File(".."),
                    File("Old", True),
                    File("Disc One.iso", size=len(DATA)),
                    File("readme.txt"),
                ]

            def getAttributes(self, share, path, timeout):
                if (share, path) not in server.files:
                    raise OperationFailure("missing")
                return File(path, size=len(server.files[(share, path)]))

            def retrieveFileFromOffset(self, share, path, sink, offset, length, timeout):
                server.reads.append((offset, length))
                data = server.files[(share, path)][offset : offset + length]
                if server.drops:
                    server.drops -= 1
                    sink.write(data[:1000])
                    raise ConnectionResetError("dropped")
                sink.write(data)
                return (None, len(data))

            def close(self):
                pass

        return Conn()


def share(server, url="smb://nas.local/Games/", username="player", password="pw"):
    return Share(url, username, password, connect=server, resolve=LAN)


def test_addresses():
    assert smbshare.parse("smb://NAS.local/Games/Disc%20One.iso") == smbshare.Address(
        "nas.local", 445, "Games", "Disc One.iso"
    )
    assert smbshare.parse("smb://nas:4450/").url() == "smb://nas:4450/"
    for bad in (
        "http://nas/x",
        "smb://",
        "smb://u:p@nas/x",
        "smb://nas/x?y",
        "smb://nas/../x",
        "smb://[::1]x/",
        "smb://nas/a%2Fb",
    ):
        with pytest.raises(RemoteError):
            smbshare.parse(bad)


def test_shares_folders_and_isos_are_listed(tmp_path):
    server = FakeServer()
    assert smbshare.list_folder(share(server), "smb://nas.local/") == [
        {"name": "Games", "url": "smb://nas.local/Games/", "kind": "folder"}
    ]
    entries = smbshare.list_folder(share(server), "smb://nas.local/Games/")
    assert [(e["name"], e["kind"]) for e in entries] == [("Old", "folder"), ("Disc One.iso", "iso")]
    assert entries[1]["url"] == "smb://nas.local/Games/Disc%20One.iso" and entries[1]["size"] == len(DATA)
    assert server.connects[0] == ("192.168.1.20", 445, "nas.local", "player")  # the checked address
    with pytest.raises(RemoteError, match="may not have access"):
        smbshare.list_folder(share(server), "smb://nas.local/Other/")


def test_download_in_chunks_with_progress_and_checksum(tmp_path):
    seen = []
    path = smbshare.download(
        share(FakeServer()),
        "smb://nas.local/Games/Disc%20One.iso",
        str(tmp_path),
        sha256=SHA,
        progress=lambda d, t: seen.append((d, t)),
        free_space=PLENTY,
    )
    assert open(path, "rb").read() == DATA and os.listdir(tmp_path) == ["Disc One.iso"]
    assert seen[-1] == (len(DATA), len(DATA)) and len(seen) == 3


def test_a_dropped_connection_reconnects_and_resumes_where_it_stopped(tmp_path):
    server = FakeServer()
    server.drops = 2
    path = smbshare.download(
        share(server), "smb://nas.local/Games/Disc%20One.iso", str(tmp_path), sha256=SHA, free_space=PLENTY
    )
    assert open(path, "rb").read() == DATA
    assert server.reads[1][0] == 1000 and len(server.connects) == 3


def test_failures_leave_nothing_behind(tmp_path):
    url = "smb://nas.local/Games/Disc%20One.iso"
    server = FakeServer()
    server.drops = 99
    with pytest.raises(RemoteError, match="kept dropping"):
        smbshare.download(share(server), url, str(tmp_path), free_space=PLENTY)
    with pytest.raises(RemoteError, match="does not match"):
        smbshare.download(share(FakeServer()), url, str(tmp_path), sha256="0" * 64, free_space=PLENTY)
    with pytest.raises(RemoteError, match="not enough free space"):
        smbshare.download(share(FakeServer()), url, str(tmp_path), free_space=lambda p: 1024**3)
    with pytest.raises(Cancelled):
        smbshare.download(share(FakeServer()), url, str(tmp_path), cancelled=lambda: True, free_space=PLENTY)
    with pytest.raises(RemoteError, match="larger than"):
        smbshare.download(share(FakeServer()), url, str(tmp_path), free_space=PLENTY, max_file=1000)
    with pytest.raises(RemoteError, match="may not have access"):
        smbshare.download(share(FakeServer()), "smb://nas.local/Games/none.iso", str(tmp_path), free_space=PLENTY)
    assert os.listdir(tmp_path) == []


def test_only_local_smb2_servers_with_the_right_password(tmp_path):
    with pytest.raises(RemoteError, match="only offers SMB 1"):
        smbshare.list_folder(share(FakeServer(smb2=False)), "smb://nas.local/")
    public = Share("smb://nas.example/", "player", "pw", connect=FakeServer(), resolve=lambda h: ["203.0.113.9"])
    with pytest.raises(RemoteError, match="not on your local network"):
        smbshare.list_folder(public, "smb://nas.example/")
    mixed = Share("smb://nas.example/", connect=FakeServer(), resolve=lambda h: ["10.0.0.5", "203.0.113.9"])
    with pytest.raises(RemoteError, match="not on your local network"):
        smbshare.list_folder(mixed, "smb://nas.example/")
    with pytest.raises(RemoteError, match="refused the user name"):
        smbshare.list_folder(share(FakeServer(), password="wrong"), "smb://nas.local/")
    with pytest.raises(RemoteError, match="location you chose"):
        smbshare.list_folder(share(FakeServer()), "smb://other.local/")


def test_the_name_is_resolved_once():
    calls = []

    def resolve(host):
        calls.append(host)
        return ["192.168.1.20"] if len(calls) == 1 else ["203.0.113.9"]  # a rebinding answer comes second

    s = Share("smb://nas.local/Games/", "player", "pw", connect=FakeServer(), resolve=resolve)
    smbshare.list_folder(s, "smb://nas.local/Games/")
    smbshare.list_folder(s, "smb://nas.local/Games/")
    assert calls == ["nas.local"]


def test_vendored_pysmb_loads_without_tqdm_or_twisted():
    cls = smbshare.pysmb()
    assert cls.__name__ == "SMBConnection" and cls.SIGN_WHEN_SUPPORTED == 1
    import sys

    assert not [m for m in sys.modules if m.split(".")[0] in ("tqdm", "twisted")]


def test_connect_asks_for_signing_direct_tcp_and_ntlmv2_and_closes_on_refusal(monkeypatch):
    made = []

    class Recorder:
        SIGN_WHEN_SUPPORTED, SIGN_WHEN_REQUIRED = 1, 2

        def __init__(self, *args, **kwargs):
            self.args, self.kwargs, self.closed, self.ok = args, kwargs, False, True
            made.append(self)

        def connect(self, ip, port, timeout):
            self.target = (ip, port, timeout)
            return self.ok

        def close(self):
            self.closed = True

    monkeypatch.setattr(smbshare, "pysmb", lambda: Recorder)
    conn = smbshare._connect("192.168.1.20", 445, "nas.local", "player", "pw")
    assert conn.args == ("player", "pw", "KEEPSAKE", "NAS")
    assert conn.kwargs == {"domain": "", "use_ntlm_v2": True, "sign_options": 1, "is_direct_tcp": True}
    assert conn.target == ("192.168.1.20", 445, smbshare.TIMEOUT) and not conn.closed
    Recorder.connect = lambda self, ip, port, timeout: False
    with pytest.raises(RemoteError, match="refused the user name"):
        smbshare._connect("192.168.1.20", 445, "nas.local", "player", "wrong")
    assert made[-1].closed


def test_real_pysmb_refuses_a_closed_port_cleanly():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # nothing listens here once closed
    s = Share(f"smb://127.0.0.1:{port}/Games/", "player", "pw")
    with pytest.raises(RemoteError, match="could not open the share"):
        smbshare.list_folder(s, f"smb://127.0.0.1:{port}/Games/")


def test_locations_accept_smb(tmp_path):
    from keepsake.backends import CredentialStore

    store = remote.LocationStore(str(tmp_path), CredentialStore(str(tmp_path)))
    listed = store.save("smb://NAS.local/Games", "player", "pw")
    assert listed[0]["url"] == "smb://nas.local/Games/" and listed[0]["passwordSet"] is True


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


def test_app_installs_from_a_share(device, monkeypatch):
    a = device
    server = FakeServer()
    a.app._smb_connect = server
    a.app._net_resolve = LAN
    access = {"url": "smb://nas.local/", "username": "player", "password": "pw"}

    async def go():
        shares = await a.app.installer_net_browse(access)
        listing = await a.app.installer_net_browse(access, shares["entries"][0]["url"])
        await a.app.installer_net_download(access, listing["entries"][1]["url"], "Disc One")
        for _ in range(400):
            status = await a.app.installer_net_status()
            if not status["running"]:
                return listing, status
            await asyncio.sleep(0.02)
        raise AssertionError("did not finish")

    listing, status = asyncio.run(go())
    assert listing["url"] == "smb://nas.local/Games/"
    job = a.app.installer.get(status["job"])
    assert job["state"] == "choose-installer" and os.path.basename(job["staged"]) == "Disc One.iso"


class FakeMount:
    """Keepsake's network ISO mount (ADR-0067), as a plain file: what udisks would see."""

    made: ClassVar[list["FakeMount"]] = []

    def __init__(self, point, handler, fail=False):
        self.point, self.handler, self.fail, self.closed = point, handler, fail, False
        FakeMount.made.append(self)

    def start(self):
        if self.fail:
            from keepsake.installer.netfuse import FuseError

            raise FuseError("fusermount3 did not mount the share")
        os.makedirs(self.point, exist_ok=True)
        path = os.path.join(self.point, self.handler.name.decode())
        with open(path, "wb") as handle:
            handle.write(self.handler.reader.read(0, 16))  # reads go through the share
        return path

    def close(self):
        self.closed = True


async def _finish(app):
    for _ in range(400):
        status = await app.installer_net_status()
        if not status["running"]:
            return status
        await asyncio.sleep(0.02)
    raise AssertionError("did not finish")


def test_app_installs_from_a_share_in_place_once_approved(device):
    a = device
    a.app._smb_connect = FakeServer()
    a.app._net_resolve = LAN
    a.app._netfuse_available = lambda: None  # as if fusermount3 were approved and present
    a.app._netfuse_mount = FakeMount
    a.app.installer.on_released = a.app._net_mount_released
    FakeMount.made.clear()
    access = {"url": "smb://nas.local/", "username": "player", "password": "pw"}

    async def go():
        listing = await a.app.installer_net_browse(access, "smb://nas.local/Games/")
        await a.app.installer_net_download(access, listing["entries"][1]["url"], "Disc One")
        return await _finish(a.app)

    status = asyncio.run(go())
    assert status.get("inPlace") is True
    job = a.app.installer.get(status["job"])
    assert job["netMount"] and "staged" not in job  # nothing was copied
    assert not os.listdir(a.app.installer.downloads_dir())
    a.app.installer.cancel(job["id"])
    assert FakeMount.made[-1].closed and not a.app._net_mounts  # released with the disc


def test_app_copies_when_the_in_place_mount_fails(device):
    a = device
    a.app._smb_connect = FakeServer()
    a.app._net_resolve = LAN
    a.app._netfuse_available = lambda: None
    a.app._netfuse_mount = lambda point, handler: FakeMount(point, handler, fail=True)
    access = {"url": "smb://nas.local/", "username": "player", "password": "pw"}

    async def go():
        listing = await a.app.installer_net_browse(access, "smb://nas.local/Games/")
        await a.app.installer_net_download(access, listing["entries"][1]["url"], "Disc One")
        return await _finish(a.app)

    status = asyncio.run(go())
    job = a.app.installer.get(status["job"])
    assert os.path.basename(job["staged"]) == "Disc One.iso" and not a.app._net_mounts and FakeMount.made[-1].closed


def test_until_approved_the_iso_is_copied(device):
    a = device
    a.app._smb_connect = FakeServer()
    a.app._net_resolve = LAN
    a.app._netfuse_mount = lambda point, handler: pytest.fail("nothing is mounted before approval")
    access = {"url": "smb://nas.local/", "username": "player", "password": "pw"}

    async def go():
        listing = await a.app.installer_net_browse(access, "smb://nas.local/Games/")
        await a.app.installer_net_download(access, listing["entries"][1]["url"], "Disc One")
        return await _finish(a.app)

    status = asyncio.run(go())
    assert "staged" in a.app.installer.get(status["job"])


def test_an_iso_a_mounted_share_will_not_open_in_place_is_copied_then_installed(device, tmp_path):
    a = device
    share = tmp_path / "mnt" / "nas"
    share.mkdir(parents=True)
    (share / "Disc Two.iso").write_bytes(b"disc two" * 1000)
    mounts = tmp_path / "mounts"
    mounts.write_text(f"//nas/games {share.as_posix()} cifs rw 0 0\n")
    a.app.installer.mounts_file = str(mounts)
    working = a.app.installer.runner

    def refuse_share(command):
        if command[1] == "loop-setup" and "/mnt/nas/" in command[-1]:
            raise udisks.UdisksError("Error opening file: Operation not permitted")
        return working(command)

    a.app.installer.runner = refuse_share
    toasts = []

    async def emit(event, *args):
        toasts.append((event, args))

    a.app.emit = emit

    async def go():
        started = await a.app.installer_start(str(share / "Disc Two.iso"), "Disc Two")
        return started, await _finish(a.app)

    started, status = asyncio.run(go())
    assert started["copying"] is True
    job = a.app.installer.get(status["job"])
    assert os.path.basename(job["staged"]) == "Disc Two.iso" and job["state"] == "choose-installer"
    assert any("copied to this device first" in str(args) for event, args in toasts if event == "keepsake_toast")
