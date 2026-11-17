"""WebDAV folder installs (ADR-0033) against a real local server answering PROPFIND. Synthetic data only."""

import asyncio
import http.server
import os
import random
import threading
from typing import ClassVar

import pytest

from keepsake.backends import CredentialStore
from keepsake.installer import remote, webdav
from keepsake.installer.remote import RemoteError
from keepsake.store import LocalFolderStore
from test_app_ux import Device
from test_installer import FakeUdisks, env  # noqa: F401 (the fixture)
from test_installer_remote import Reply, Script

ISO = b"synthetic webdav iso"


def multistatus(base, items):
    rows = [
        f"<d:response><d:href>{base}</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>"
    ]
    for href, folder, size in items:
        kind = "<d:collection/>" if folder else ""
        length = "" if folder else f"<d:getcontentlength>{size}</d:getcontentlength>"
        rows.append(
            f"<d:response><d:href>{href}</d:href><d:propstat><d:prop><d:resourcetype>{kind}</d:resourcetype>{length}</d:prop></d:propstat></d:response>"
        )
    return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{"".join(rows)}</d:multistatus>'.encode()


class Dav(http.server.BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def log_message(self, *args):
        pass

    def do_PROPFIND(self):
        length = int(self.headers.get("Content-Length") or 0)
        Dav.seen.append(("PROPFIND", self.path, self.headers.get("Depth"), self.rfile.read(length)))
        if self.path != "/dav/games/":
            return self._send(404, b"")
        body = multistatus(
            "/dav/games/",
            [
                ("/dav/games/Old/", True, 0),
                ("/dav/games/Disc%20One.iso", False, len(ISO)),
                ("/dav/games/notes.txt", False, 5),
                ("/dav/games/Old/deeper.iso", False, 1),
                ("http://elsewhere.test/dav/games/x.iso", False, 1),
            ],
        )
        self._send(207, body)

    def do_GET(self):
        Dav.seen.append(("GET", self.path, None, b""))
        if self.path == "/dav/games/Disc%20One.iso":
            return self._send(200, ISO)
        self._send(404, b"")

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    Dav.seen = []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Dav)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_addresses_map_both_ways():
    assert webdav.to_http("davs://nas.local/dav/") == "https://nas.local/dav/"
    assert webdav.to_http("dav://nas.local") == "http://nas.local/"
    assert webdav.to_dav("https://nas.local/a/") == "davs://nas.local/a/"
    assert webdav.is_dav("DAVS://x/") and not webdav.is_dav("https://x/")
    for bad in ("https://nas/", "smb://nas/", "davs://[::1]x/"):
        with pytest.raises(RemoteError):
            webdav.to_http(bad)


def test_propfind_lists_one_level_and_downloads_with_get(server, tmp_path):
    session = webdav.DavSession(webdav.to_http(f"dav://{server}/dav/games/"))
    entries = webdav.list_folder(session, f"http://{server}/dav/games")
    assert [(e["name"], e["kind"]) for e in entries] == [("Old", "folder"), ("Disc One.iso", "iso")]
    assert entries[0]["url"] == f"dav://{server}/dav/games/Old/"
    assert entries[1]["url"] == f"dav://{server}/dav/games/Disc%20One.iso" and entries[1]["size"] == len(ISO)
    method, _path, depth, body = Dav.seen[0]
    assert method == "PROPFIND" and depth == "1" and b"resourcetype" in body
    path = remote.download(session, webdav.to_http(entries[1]["url"]), str(tmp_path), free_space=lambda p: 1 << 50)
    assert open(path, "rb").read() == ISO and Dav.seen[-1][0] == "GET"


def test_listing_errors_are_plain(server):
    session = webdav.DavSession(f"http://{server}/dav/")
    with pytest.raises(RemoteError, match="nothing was found"):
        webdav.list_folder(session, f"http://{server}/dav/missing/")


@pytest.mark.parametrize("status", [200, 405])
def test_a_plain_web_server_is_told_apart(status):
    script = Script({"https://nas.example/www/": Reply(status, {}, b"<html>listing</html>")})
    session = webdav.DavSession("https://nas.example/www/", connect=script)
    with pytest.raises(RemoteError, match="does not answer as a WebDAV folder"):
        webdav.list_folder(session, "https://nas.example/www/")


def test_hostile_xml_is_refused():
    base = "https://nas.example/dav/"
    for body in (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><d:multistatus xmlns:d="DAV:"/>',
        b"<not xml",
    ):
        with pytest.raises(RemoteError):
            webdav.parse_multistatus(body, base)


@pytest.mark.parametrize("seed", range(200))
def test_fuzzed_hrefs_stay_one_level_under_the_folder(seed):
    rng = random.Random(seed)
    pieces = [
        "/dav/",
        "games/",
        "../",
        "a.iso",
        "B.ISO",
        "%2F",
        "%2e%2e/",
        "//evil.example/",
        "?q",
        "x/",
        "%00",
        "é",
        ":",
        "\\",
    ]
    hrefs = ["".join(rng.choice(pieces) for _ in range(rng.randint(1, 6))) for _ in range(20)]
    body = multistatus("/dav/", [(h, rng.random() < 0.4, 3) for h in hrefs])
    for entry in webdav.parse_multistatus(body, "https://nas.example/dav/"):
        assert entry["url"].startswith("davs://nas.example/dav/")
        assert "/" not in entry["name"] and entry["name"] not in (".", "..")
        assert entry["kind"] == "folder" or entry["name"].lower().endswith(".iso")


def test_only_get_and_propfind_are_ever_sent():
    with pytest.raises(RemoteError, match="only reads"):
        remote.Session("https://nas.example/").open("https://nas.example/x", method="DELETE")


def test_locations_keep_the_dav_form_and_refuse_a_password_over_dav(tmp_path):
    store = remote.LocationStore(str(tmp_path), CredentialStore(str(tmp_path)))
    assert store.save("DAVS://nas.example/dav", "player", "pw")[0]["url"] == "davs://nas.example/dav"
    with pytest.raises(RemoteError, match="only sent over https"):
        store.save("dav://nas.example/dav/", "player", "pw")


@pytest.fixture
def device(env, tmp_path):  # noqa: F811
    installer, *_ = env
    a = Device(tmp_path / "dev", "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    a.app.installer = installer
    disc = (tmp_path / "DISC").as_posix()
    os.makedirs(disc, exist_ok=True)
    open(disc + "/setup.exe", "wb").close()
    installer.runner = FakeUdisks(disc)
    return a


def test_app_installs_from_a_webdav_folder(device):
    a = device
    script = Script(
        {
            "https://nas.example/dav/": Reply(
                207, {}, multistatus("/dav/", [("/dav/Disc%20One.iso", False, len(ISO))])
            ),
            "https://nas.example/dav/Disc%20One.iso": Reply(200, {"Content-Length": str(len(ISO))}, ISO),
        }
    )
    a.app._net_connect = script
    access = {"url": "davs://nas.example/dav/", "username": "player", "password": "pw"}

    async def go():
        listing = await a.app.installer_net_browse(access)
        await a.app.installer_net_download(access, listing["entries"][0]["url"], "Disc One")
        for _ in range(400):
            status = await a.app.installer_net_status()
            if not status["running"]:
                return listing, status
            await asyncio.sleep(0.02)
        raise AssertionError("did not finish")

    listing, status = asyncio.run(go())
    assert (
        listing["url"] == "davs://nas.example/dav/"
        and listing["entries"][0]["url"] == "davs://nas.example/dav/Disc%20One.iso"
    )
    assert script.methods == ["PROPFIND", "GET"]
    assert all("Authorization" in headers for _url, headers in script.calls)  # https, same host
    assert a.app.installer.get(status["job"])["state"] == "choose-installer"
