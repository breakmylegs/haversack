"""Installing straight from a network ISO (ADR-0067): the FUSE protocol, range reads, and the copy fallback."""

from __future__ import annotations

import asyncio
import errno
import os
import stat
import struct

import pytest

from keepsake import devicechecks
from keepsake.installer import inplace, netfuse, udisks
from keepsake.installer.service import InPlaceFailed, Installer
from keepsake.statedb import StateDB
from keepsake.steamops import SteamOps

DATA = bytes(range(256)) * 4096  # 1 MiB of known bytes


class Source:
    def __init__(self, data=DATA, fail=False):
        self.data, self.size, self.fail, self.reads = data, len(data), fail, []

    def read(self, offset, length):
        self.reads.append((offset, length))
        if self.fail:
            raise OSError(errno.EIO, "gone")
        return self.data[offset : offset + length]


def request(opcode, body=b"", node=netfuse.ROOT_ID, unique=9):
    header = netfuse.IN_HEADER.pack(netfuse.IN_HEADER.size + len(body), opcode, unique, node, 1000, 1000, 42, 0, 0)
    return header + body


def answer(reply):
    length, error, unique = netfuse.OUT_HEADER.unpack_from(reply)
    assert length == len(reply)
    return -error, unique, reply[netfuse.OUT_HEADER.size :]


@pytest.fixture
def handler():
    return netfuse.Handler("Game Disc.iso", Source(), clock=lambda: 1_000_000)


# The protocol


def test_init_negotiates_only_what_the_kernel_offers(handler):
    offered = netfuse.FUSE_ASYNC_READ | netfuse.FUSE_MAX_PAGES | (1 << 3)
    error, unique, body = answer(handler.handle(request(netfuse.INIT, struct.pack("<IIII", 7, 38, 131072, offered))))
    assert (error, unique, len(body)) == (0, 9, 64)
    major, minor, readahead, flags, _bg, _cong, max_write, _gran, max_pages = struct.unpack_from("<IIIIHHIIH", body)
    assert (major, minor, readahead, max_write, max_pages) == (7, 31, 131072, 4096, 256)
    assert flags == netfuse.FUSE_ASYNC_READ | netfuse.FUSE_MAX_PAGES
    assert answer(handler.handle(request(netfuse.INIT, struct.pack("<IIII", 7, 26, 0, 0))))[2][4:8] == struct.pack(
        "<I", 26
    )  # an older kernel keeps its own minor
    assert answer(handler.handle(request(netfuse.INIT, struct.pack("<IIII", 8, 0, 0, 0))))[0] == errno.EPROTO


def test_lookup_finds_only_the_one_file(handler):
    error, _u, body = answer(handler.handle(request(netfuse.LOOKUP, b"Game Disc.iso\x00")))
    assert error == 0
    node, _gen, entry_valid, attr_valid, _n1, _n2 = struct.unpack_from("<QQQQII", body)
    assert (node, entry_valid, attr_valid) == (netfuse.FILE_ID, 3600, 3600)
    attr = netfuse.ATTR.unpack_from(body, 40)
    assert attr[0] == netfuse.FILE_ID and attr[1] == len(DATA) and stat.S_ISREG(attr[9]) and attr[9] & 0o777 == 0o400
    assert answer(handler.handle(request(netfuse.LOOKUP, b"other.iso\x00")))[0] == errno.ENOENT
    assert (
        answer(handler.handle(request(netfuse.LOOKUP, b"Game Disc.iso\x00", node=netfuse.FILE_ID)))[0] == errno.ENOENT
    )
    assert answer(handler.handle(request(netfuse.GETATTR, b"\x00" * 16, node=7)))[0] == errno.ENOENT


def test_getattr_root_is_a_read_only_folder(handler):
    error, _u, body = answer(handler.handle(request(netfuse.GETATTR, b"\x00" * 16)))
    attr = netfuse.ATTR.unpack_from(body, 16)
    assert error == 0 and stat.S_ISDIR(attr[9]) and attr[9] & 0o777 == 0o500 and attr[1] == 0
    file_attr = netfuse.ATTR.unpack_from(answer(handler.handle(request(netfuse.GETATTR, b"\x00" * 16, node=2)))[2], 16)
    assert file_attr[1] == len(DATA) and file_attr[2] == len(DATA) // 512


@pytest.mark.parametrize("flags", [os.O_WRONLY, os.O_RDWR, os.O_RDONLY | os.O_WRONLY])
def test_opening_for_writing_is_refused(handler, flags):
    assert answer(handler.handle(request(netfuse.OPEN, struct.pack("<II", flags, 0), node=2)))[0] == errno.EROFS


def test_open_read_and_folders(handler):
    error, _u, body = answer(handler.handle(request(netfuse.OPEN, struct.pack("<II", os.O_RDONLY, 0), node=2)))
    assert error == 0 and struct.unpack_from("<QII", body)[1] == netfuse.FOPEN_KEEP_CACHE
    assert answer(handler.handle(request(netfuse.OPEN, struct.pack("<II", 0, 0))))[0] == errno.EISDIR
    assert answer(handler.handle(request(netfuse.OPENDIR, struct.pack("<II", 0, 0), node=2)))[0] == errno.ENOTDIR
    assert answer(handler.handle(request(netfuse.OPENDIR, struct.pack("<II", 0, 0))))[0] == 0
    read = struct.pack("<QQIIQII", 0, 4096, 8192, 0, 0, 0, 0)
    assert answer(handler.handle(request(netfuse.READ, read, node=2)))[2] == DATA[4096 : 4096 + 8192]
    huge = struct.pack("<QQIIQII", 0, 0, 4 * netfuse.MAX_READ, 0, 0, 0, 0)
    assert len(answer(handler.handle(request(netfuse.READ, huge, node=2)))[2]) == netfuse.MAX_READ
    assert answer(handler.handle(request(netfuse.READ, read)))[0] == errno.EISDIR


def test_a_failing_share_answers_eio_and_bad_requests_einval():
    broken = netfuse.Handler("a.iso", Source(fail=True))
    read = struct.pack("<QQIIQII", 0, 0, 10, 0, 0, 0, 0)
    assert answer(broken.handle(request(netfuse.READ, read, node=2)))[0] == errno.EIO
    assert answer(broken.handle(request(netfuse.READ, b"\x00", node=2)))[0] == errno.EINVAL
    with pytest.raises(netfuse.FuseError):
        broken.handle(b"\x00" * 10)
    with pytest.raises(netfuse.FuseError):
        netfuse.Handler("../a.iso", Source())


def test_readdir_lists_the_file_and_continues_from_an_offset(handler):
    def names(offset, size=4096):
        body = answer(handler.handle(request(netfuse.READDIR, struct.pack("<QQIIQII", 0, offset, size, 0, 0, 0, 0))))[2]
        out, at = [], 0
        while at < len(body):
            ino, off, length, kind = struct.unpack_from("<QQII", body, at)
            out.append((ino, off, body[at + 24 : at + 24 + length].decode(), kind))
            at += (24 + length + 7) // 8 * 8
        return out

    assert names(0) == [(1, 1, ".", 4), (1, 2, "..", 4), (2, 3, "Game Disc.iso", 8)]
    assert names(2) == [(2, 3, "Game Disc.iso", 8)]
    assert names(3) == []
    assert names(0, size=32) == [(1, 1, ".", 4)]  # only what fits
    assert answer(handler.handle(request(netfuse.READDIR, b"\x00" * 40, node=2)))[0] == errno.ENOTDIR
    assert answer(handler.handle(request(netfuse.READDIRPLUS, b"\x00" * 40)))[0] == errno.ENOSYS


def test_the_rest(handler):
    for opcode in netfuse.NO_REPLY:
        assert handler.handle(request(opcode, b"\x00" * 16)) is None
    assert answer(handler.handle(request(16, b"\x00" * 40, node=2)))[0] == errno.ENOSYS  # WRITE
    assert answer(handler.handle(request(netfuse.ACCESS, struct.pack("<II", os.W_OK, 0))))[0] == errno.EACCES
    assert answer(handler.handle(request(netfuse.ACCESS, struct.pack("<II", os.R_OK, 0))))[0] == 0
    for opcode in (netfuse.RELEASE, netfuse.RELEASEDIR, netfuse.FLUSH):
        assert answer(handler.handle(request(opcode, b"\x00" * 24, node=2)))[0] == 0
    blocks = struct.unpack_from("<Q", answer(handler.handle(request(netfuse.STATFS)))[2])[0]
    assert blocks == len(DATA) // 4096


# Reads


def test_block_cache_reads_across_blocks_and_keeps_recent_ones():
    source = Source()
    cache = netfuse.BlockCache(source, block=4096, blocks=2)
    try:
        assert cache.read(4000, 200) == DATA[4000:4200]  # two blocks
        assert cache.read(4096, 10) == DATA[4096:4106]  # cached
        assert cache.read(len(DATA) - 5, 100) == DATA[-5:]
        assert cache.read(len(DATA), 10) == b"" and cache.read(0, 0) == b""
        cache._ahead.shutdown(wait=True)
        assert (0, 4096) in source.reads and source.reads.count((4096, 4096)) <= 2
        assert len(cache._cache) <= 2
    finally:
        cache.close()


class FakeResponse:
    def __init__(self, status, content_range, data):
        self.status, self._range, self._data = status, content_range, data

    def getheader(self, name):
        return self._range if name == "Content-Range" else None

    def read(self, size):
        return self._data[:size]

    def close(self):
        pass


class FakeSession:
    def __init__(self, ranged=True, wrong=False, short=False):
        self.ranged, self.wrong, self.short, self.asked = ranged, wrong, short, []

    def open(self, url, headers):
        spec = headers["Range"][len("bytes=") :]
        start, end = (int(x) for x in spec.split("-"))
        self.asked.append((start, end))
        if not self.ranged:
            return FakeResponse(200, None, DATA), url
        begin = start + 1 if self.wrong and start else start
        data = DATA[begin : end + 1][: (1 if self.short and start else None)]
        return FakeResponse(206, f"bytes {begin}-{end}/{len(DATA)}", data), url


def test_http_ranges():
    session = FakeSession()
    source = netfuse.HttpRange(session, "https://nas.local/a.iso")
    assert source.size == len(DATA) and session.asked == [(0, 0)]
    assert source.read(100, 50) == DATA[100:150] and session.asked[-1] == (100, 149)
    assert source.read(len(DATA) - 10, 100) == DATA[-10:]
    with pytest.raises(netfuse.FuseError, match="cannot send parts"):
        netfuse.HttpRange(FakeSession(ranged=False), "https://nas.local/a.iso")
    with pytest.raises(OSError, match="wrong part"):
        netfuse.HttpRange(FakeSession(wrong=True), "u").read(10, 5)
    with pytest.raises(OSError, match="less than asked"):
        netfuse.HttpRange(FakeSession(short=True), "u").read(10, 5)


class FakeConn:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.closed = False

    def getAttributes(self, service, path, timeout):
        assert (service, path) == ("Games", "/Disc/a.iso")
        return type("Attrs", (), {"file_size": len(DATA)})()

    def retrieveFileFromOffset(self, service, path, out, offset, length, timeout):
        if self.fail_times[0] > 0:
            self.fail_times[0] -= 1
            raise ConnectionResetError
        out.write(DATA[offset : offset + length])

    def close(self):
        self.closed = True


class FakeShare:
    def __init__(self, failures=0):
        self.failures, self.opened = [failures], 0

    def open(self):
        self.opened += 1
        return FakeConn(self.failures)


def test_smb_ranges_reconnect_once():
    share = FakeShare()
    source = netfuse.SmbRange(share, "smb://nas.local/Games/Disc/a.iso")
    assert source.size == len(DATA) and source.read(10, 20) == DATA[10:30]
    flaky = FakeShare(failures=1)
    assert netfuse.SmbRange(flaky, "smb://nas.local/Games/Disc/a.iso").read(0, 4) == DATA[:4] and flaky.opened == 2
    dead = FakeShare(failures=5)
    with pytest.raises(OSError, match="stopped answering"):
        netfuse.SmbRange(dead, "smb://nas.local/Games/Disc/a.iso").read(0, 4)
    with pytest.raises(netfuse.FuseError):
        netfuse.SmbRange(share, "smb://nas.local/Games/Disc/readme.txt")
    source.close()


def test_in_place_waits_for_the_register_approval(monkeypatch):
    assert netfuse.FUSERMOUNT_APPROVED is True  # approved on 22 November 2026
    monkeypatch.setattr(netfuse, "FUSERMOUNT_APPROVED", False)
    assert "fusermount3 to be approved" in netfuse.available()
    monkeypatch.setattr(netfuse, "FUSERMOUNT_APPROVED", True)
    if os.name != "posix":
        assert netfuse.available() == "installing in place needs Linux"
    else:
        assert netfuse.available(which=lambda name: None) == "fusermount3 is not installed"
    monkeypatch.setattr(netfuse, "FUSERMOUNT_APPROVED", False)
    with pytest.raises(netfuse.FuseError):
        netfuse.Mount("/tmp/x", netfuse.Handler("a.iso", Source())).start()


# Already-mounted shares (option A)


def _mounts(tmp_path, share, fstype="cifs"):
    mounts = tmp_path / "mounts"
    mounts.write_text(f"/dev/sda1 / ext4 rw 0 0\n//nas/g {share.as_posix()} {fstype} rw 0 0\n")
    return str(mounts)


def test_network_filesystem(tmp_path):
    share = tmp_path / "share"
    (share / "deep").mkdir(parents=True)
    mounts = _mounts(tmp_path, share)
    assert inplace.network_filesystem(str(share / "deep" / "a.iso"), mounts) == "cifs"
    assert inplace.network_filesystem(str(share), mounts) == "cifs"
    assert inplace.network_filesystem(str(tmp_path / "local.iso"), mounts) is None
    assert (
        inplace.network_filesystem(str(share / "a.iso"), _mounts(tmp_path, share, "fuse.kio-fuse")) == "fuse.kio-fuse"
    )
    assert inplace.network_filesystem(str(share / "a.iso"), _mounts(tmp_path, share, "ext4")) is None
    assert inplace.network_filesystem(str(share / "a.iso"), str(tmp_path / "missing")) is None


def test_copy_iso(tmp_path):
    source = tmp_path / "share" / "Game.iso"
    source.parent.mkdir()
    source.write_bytes(DATA)
    seen = []
    copied = inplace.copy_iso(str(source), str(tmp_path / "staging"), progress=lambda d, t: seen.append((d, t)))
    assert open(copied, "rb").read() == DATA and seen[-1] == (len(DATA), len(DATA))
    with pytest.raises(inplace.CopyCancelled):
        inplace.copy_iso(str(source), str(tmp_path / "s2"), cancelled=lambda: True)
    assert os.listdir(tmp_path / "s2") == []  # the partial copy is gone
    with pytest.raises(ValueError, match="free space"):
        inplace.copy_iso(str(source), str(tmp_path / "s3"), free_space=lambda p: 10)
    (tmp_path / "share" / "notes.txt").write_text("x")
    with pytest.raises(ValueError, match="iso"):
        inplace.copy_iso(str(tmp_path / "share" / "notes.txt"), str(tmp_path / "s4"))


def test_find_network_iso_and_loop_test(tmp_path):
    share = tmp_path / "share"
    (share / ".hidden").mkdir(parents=True)
    (share / ".hidden" / "skip.iso").write_bytes(b"x")
    (share / "Games").mkdir()
    (share / "Games" / "Disc 1.iso").write_bytes(b"x")
    path, fstype = inplace.find_network_iso(_mounts(tmp_path, share))
    assert (os.path.normpath(path), fstype) == (str(share / "Games" / "Disc 1.iso"), "cifs")
    assert inplace.find_network_iso(_mounts(tmp_path, share, "ext4")) is None
    calls = []

    def runner(command):
        calls.append(command[1])
        return "Mapped file x as /dev/loop3.\n" if command[1] == "loop-setup" else ""

    assert inplace.loop_test("x.iso", runner) is None and calls == ["loop-setup", "unmount", "loop-delete"]

    def refusing(command):
        raise udisks.UdisksError("Error opening x.iso: Permission denied")

    assert "Permission denied" in inplace.loop_test("x.iso", refusing)
    assert inplace.loop_test("x.iso", lambda c: "nothing") == "udisksctl did not report a loop device"


class Udisks:
    def __init__(self, refuse_loop=False):
        self.refuse_loop, self.calls = refuse_loop, []

    def __call__(self, command):
        self.calls.append(command[1])
        if command[1] == "loop-setup":
            if self.refuse_loop:
                raise udisks.UdisksError("Error opening file: Operation not permitted")
            return f"Mapped file {command[-1]} as /dev/loop7.\n"
        if command[1] == "mount":
            return "Mounted /dev/loop7 at /run/media/deck/DISC\n"
        return ""


def _installer(tmp_path, runner, share):
    tmp_path.mkdir(exist_ok=True)
    db = StateDB(str(tmp_path / "k.db"))
    installer = Installer(
        db,
        SteamOps(db),
        lambda: (tmp_path / "Games").as_posix(),
        lambda appid: None,
        runner=runner,
        has_udisks=lambda: True,
        home=lambda: tmp_path.as_posix(),
        running=lambda appid, prefix: False,
        work_dir=str(tmp_path / "work"),
    )
    installer.mounts_file = _mounts(tmp_path, share)
    return installer, db


def test_an_iso_on_a_mounted_share_opens_in_place_or_asks_for_a_copy(tmp_path):
    share = tmp_path / "share"
    share.mkdir()
    iso = share / "Game.iso"
    iso.write_bytes(b"x")
    released = []
    installer, db = _installer(tmp_path, Udisks(), share)
    installer.on_released = released.append
    job = installer.start(str(iso), "Example Quest")
    assert job["inPlace"] == "cifs" and "netMount" not in job
    installer.cancel(job["id"])
    assert released and released[0].get("device") == "/dev/loop7"
    db.close()
    refusing, db = _installer(tmp_path / "b", Udisks(refuse_loop=True), share)
    with pytest.raises(InPlaceFailed) as failed:
        refusing.start(str(iso), "Example Quest")
    assert failed.value.source == os.path.realpath(str(iso)).replace(os.sep, "/") and failed.value.fstype == "cifs"
    with pytest.raises(udisks.UdisksError):  # Keepsake's own mount: no copy loop, a plain failure
        refusing.start(str(iso), "Example Quest", net_mount="m1")
    local = tmp_path / "local.iso"
    local.write_bytes(b"x")
    with pytest.raises(udisks.UdisksError):  # a local ISO that fails is not copied
        refusing.start(str(local), "Example Quest")
    db.close()


# The device check


@pytest.mark.parametrize(
    ("found", "status"),
    [
        (
            {
                "udisks": True,
                "fusermount3": True,
                "devFuse": True,
                "approved": False,
                "inPlace": "x",
                "iso": {"fstype": "cifs", "error": None},
            },
            "pass",
        ),
        (
            {
                "udisks": True,
                "fusermount3": True,
                "devFuse": True,
                "approved": False,
                "inPlace": "x",
                "iso": {"fstype": "cifs", "error": "denied"},
            },
            "warn",
        ),
        (
            {"udisks": True, "fusermount3": False, "devFuse": True, "approved": False, "inPlace": "x", "iso": None},
            "skip",
        ),
        (
            {"udisks": False, "fusermount3": True, "devFuse": True, "approved": False, "inPlace": "x", "iso": None},
            "fail",
        ),
    ],
)
def test_device_check(found, status):
    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"network-iso": probe})
    outcome = asyncio.run(devicechecks.run("network-iso", ctx))
    assert outcome["status"] == status and outcome["title"] == "Network ISO in place"
    assert "off until fusermount3 is approved" in outcome["found"]
    if status in ("pass", "warn"):
        assert outcome["details"]["fstype"] == "cifs"
    bare = asyncio.run(devicechecks.run("network-iso", devicechecks.Context("", "", "", "", {}, "")))
    assert bare["status"] == "skip"


def test_sharper_edges():
    big = netfuse.Handler("a.iso", Source(DATA * 8))
    plain = answer(big.handle(request(netfuse.INIT, struct.pack("<IIII", 7, 38, 0, 0))))[2]
    assert struct.unpack_from("<I", plain, 12)[0] == 0  # the kernel offered nothing: nothing is asked for
    huge = struct.pack("<QQIIQII", 0, 0, 4 * netfuse.MAX_READ, 0, 0, 0, 0)
    assert len(answer(big.handle(request(netfuse.READ, huge, node=2)))[2]) == netfuse.MAX_READ


class WholeFileSession(FakeSession):
    def open(self, url, headers):
        return FakeResponse(200, f"bytes 0-0/{len(DATA)}", DATA), url  # a 200 is the whole file, whatever it says


def test_a_200_answer_is_never_taken_for_a_part():
    with pytest.raises(netfuse.FuseError):
        netfuse.HttpRange(WholeFileSession(), "u")


def test_the_deepest_mount_decides_whatever_the_order(tmp_path):
    share = tmp_path / "share"
    share.mkdir()
    mounts = tmp_path / "mounts"
    mounts.write_text(f"//nas/g {share.as_posix()} cifs rw 0 0\n/dev/sda1 {tmp_path.as_posix()} ext4 rw 0 0\n")
    assert inplace.network_filesystem(str(share / "a.iso"), str(mounts)) == "cifs"
