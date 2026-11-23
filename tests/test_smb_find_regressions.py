"""v0.30.2: Find shares and Browse with Windows ways of writing addresses and user names.

Picking a found server, or browsing a remembered location with credentials, must list the
shares or say plainly why not. Windows paths (``\\\\server\\share``, ``DOMAIN\\user``) never leak
into SMB paths. Against the fake share server; synthetic data only.
"""

import asyncio

import pytest

from keepsake.installer import lanfind, smbshare
from keepsake.installer.smbshare import Address
from test_installer import env  # noqa: F401 - the fixture
from test_installer_smb import LAN, FakeServer, device  # noqa: F401 - the fixture


@pytest.mark.parametrize(
    ("typed", "address"),
    [
        ("\\\\nas\\Games", Address("nas", 445, "Games", "")),
        ("\\\\nas\\Games\\Old\\", Address("nas", 445, "Games", "Old")),
        ("smb:\\\\nas\\Games", Address("nas", 445, "Games", "")),
        ("smb://\\\\NAS\\Games", Address("nas", 445, "Games", "")),
        ("smb://nas.local/Games\\Old", Address("nas.local", 445, "Games", "Old")),
        ("\\\\192.168.1.20\\Games", Address("192.168.1.20", 445, "Games", "")),
        ("  smb://nas.local/Games/  ", Address("nas.local", 445, "Games", "")),
    ],
)
def test_windows_addresses_become_share_addresses(typed, address):
    assert smbshare.is_smb(typed)
    assert smbshare.parse(typed) == address
    assert "\\" not in smbshare.parse(typed).url()


def test_backslashes_never_reach_a_host_or_folder_name():
    for typed in ("smb://\\\\nas\\Games", "\\\\nas\\Games\\Sub\\Deeper"):
        parsed = smbshare.parse(typed)
        assert "\\" not in parsed.host and "\\" not in parsed.share and "\\" not in parsed.path
    assert not smbshare.is_smb("https://nas.local/Games/") and not smbshare.is_smb("C:\\Games")


@pytest.mark.parametrize(
    ("typed", "split"),
    [
        ("WORKGROUP\\player", ("WORKGROUP", "player")),
        ("GAMING-PC\\player", ("GAMING-PC", "player")),
        ("player@example.com", ("", "player@example.com")),  # a Microsoft account stays whole
        ("player", ("", "player")),
        ("\\player", ("", "\\player")),
        ("", ("", "")),
    ],
)
def test_domain_user_names(typed, split):
    assert smbshare.split_user(typed) == split


def test_connect_sends_the_domain_separately(monkeypatch):
    class Recorder:
        SIGN_WHEN_SUPPORTED = 1

        def __init__(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs

        def connect(self, ip, port, timeout):
            return True

        def close(self):
            pass

    monkeypatch.setattr(smbshare, "pysmb", lambda: Recorder)
    conn = smbshare._connect("192.168.1.20", 445, "nas.local", "WORKGROUP\\player", "pw")
    assert conn.args[:2] == ("player", "pw") and conn.kwargs["domain"] == "WORKGROUP"


def run(coro):
    return asyncio.run(coro)


def test_picking_a_found_server_lists_its_shares_or_says_plainly_why_not(device, monkeypatch):  # noqa: F811
    app = device.app
    app._smb_connect, app._net_resolve = FakeServer(), LAN
    server = {"name": "NAS", "address": "192.168.1.20", "url": "smb://192.168.1.20/", "via": ["netbios"]}
    monkeypatch.setattr(lanfind, "find_servers", lambda *a, **k: {"servers": [server], "methods": {"netbios": 1}})

    async def go():
        found = await app.installer_net_find_smb()
        picked = found["servers"][0]["url"]
        listed = await app.installer_net_browse({"url": picked, "username": "player", "password": "pw"}, picked)
        with pytest.raises(ValueError) as refused:
            await app.installer_net_browse({"url": picked, "username": "", "password": ""}, picked)
        return listed, str(refused.value)

    listed, refused = run(go())
    assert listed["url"] == "smb://192.168.1.20/" and [e["name"] for e in listed["entries"]] == ["Games"]
    assert refused == "the share refused the user name or password (or needs one)"


def test_a_remembered_windows_location_with_credentials_browses(device):  # noqa: F811
    app = device.app
    server = FakeServer()
    app._smb_connect, app._net_resolve = server, LAN

    async def go():
        saved = await app.installer_net_remember({"url": "\\\\NAS\\Games", "username": "player", "password": "pw"})
        access = {"locationId": saved[0]["id"], "allowHosts": []}
        top = await app.installer_net_browse(access, "")
        inner = await app.installer_net_browse(access, top["entries"][0]["url"])
        typed = await app.installer_net_browse(access, "\\\\nas\\Games\\Old")
        return saved, top, inner, typed

    saved, top, inner, typed = run(go())
    assert saved[0]["url"] == "smb://nas/Games/"
    assert top["url"] == "smb://nas/Games/" and {e["kind"] for e in top["entries"]} == {"folder", "iso"}
    assert inner["url"] == "smb://nas/Games/Old/" and typed["url"] == "smb://nas/Games/Old/"
    assert all(host == "nas" for _ip, _port, host, _user in server.connects)


def test_a_typed_windows_address_browses_without_remembering(device):  # noqa: F811
    app = device.app
    app._smb_connect, app._net_resolve = FakeServer(), LAN
    for typed in ("smb://\\\\nas\\Games", "\\\\nas\\Games"):
        listing = run(app.installer_net_browse({"url": typed, "username": "player", "password": "pw"}))
        assert listing["url"] == "smb://nas/Games/" and listing["entries"]


def test_an_unexpected_fault_is_a_plain_message_not_a_raw_exception(device, monkeypatch):  # noqa: F811
    app = device.app
    app._smb_connect, app._net_resolve = FakeServer(), LAN

    def broken(*args):
        raise AttributeError("'NoneType' object has no attribute 'listShares'")

    monkeypatch.setattr(smbshare, "list_folder", broken)
    with pytest.raises(ValueError, match=r"^Haversack could not browse that location \(AttributeError\)\. Check"):
        run(app.installer_net_browse({"url": "smb://nas/", "username": "player", "password": "pw"}))

    def search_broken(*args, **kwargs):
        raise KeyError("servers")

    monkeypatch.setattr(lanfind, "find_servers", search_broken)
    with pytest.raises(ValueError, match=r"could not search your network \(KeyError\)"):
        run(app.installer_net_find_smb())
