"""Network install over HTTP (ADR-0033) against a real local server and a scripted one. Synthetic data only."""

import hashlib
import http.server
import os
import threading
from typing import ClassVar

import pytest

from keepsake.installer import remote
from keepsake.installer.remote import Cancelled, RedirectElsewhere, RemoteError, Session

DATA = bytes(range(256)) * 4096  # 1 MiB of synthetic bytes
SHA = hashlib.sha256(DATA).hexdigest()
PLENTY = lambda path: 1 << 50  # noqa: E731


class Handler(http.server.BaseHTTPRequestHandler):
    mode = "normal"  # normal, drop-once, ignore-range, wrong-range, redirect
    requests: ClassVar[list] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        Handler.requests.append((self.path, dict(self.headers)))
        if self.path == "/games/":
            body = (
                b'<a href="../">Parent</a><a href="Alpha%20Disc.iso">x</a><a href=\'Sub/\'>Sub</a>'
                b'<a href="notes.txt">n</a><a href="http://elsewhere.test/b.iso">e</a><a href="?C=N">sort</a>'
                b'<a href=/games/Beta.ISO>b</a><a href="/other/c.iso">c</a><a href="Sub/deeper/d.iso">d</a>'
            )
            return self._send(200, body)
        if self.path == "/moved.iso":
            self.send_response(302)
            self.send_header("Location", "/games/disc.iso")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if self.path != "/games/disc.iso":
            return self._send(404, b"")
        start = 0
        wanted = self.headers.get("Range")
        if wanted and Handler.mode != "ignore-range":
            start = int(wanted.split("=")[1].rstrip("-"))
            if Handler.mode == "wrong-range":
                start += 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(DATA) - 1}/{len(DATA)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(DATA) - start))
        self.end_headers()
        if Handler.mode in ("drop-once", "wrong-range", "ignore-range") and not wanted:
            self.wfile.write(DATA[start : start + 300_000])  # then the connection drops
            self.wfile.flush()
            self.close_connection = True
            return
        self.wfile.write(DATA[start:])

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    Handler.mode, Handler.requests = "normal", []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_listing_shows_folders_and_isos_one_level_down_only(server):
    entries = remote.list_folder(Session(f"{server}/games/"), f"{server}/games")
    assert [(e["name"], e["kind"]) for e in entries] == [
        ("Sub", "folder"),
        ("Alpha Disc.iso", "iso"),
        ("Beta.ISO", "iso"),
    ]
    assert entries[1]["url"] == f"{server}/games/Alpha%20Disc.iso"


def test_download_streams_reports_progress_and_checks_the_checksum(server, tmp_path):
    seen = []
    path = remote.download(
        Session(server),
        f"{server}/games/disc.iso",
        str(tmp_path),
        sha256=SHA.upper(),
        progress=lambda done, total: seen.append((done, total)),
        free_space=PLENTY,
    )
    assert open(path, "rb").read() == DATA and os.path.basename(path) == "disc.iso"
    assert seen[-1] == (len(DATA), len(DATA)) and os.listdir(tmp_path) == ["disc.iso"]


@pytest.mark.parametrize("mode", ["drop-once", "ignore-range"])
def test_a_dropped_connection_resumes_or_restarts_and_the_file_is_whole(server, tmp_path, mode):
    Handler.mode = mode
    path = remote.download(Session(server), f"{server}/games/disc.iso", str(tmp_path), sha256=SHA, free_space=PLENTY)
    assert open(path, "rb").read() == DATA
    ranges = [h.get("Range") for p, h in Handler.requests]
    assert ranges[0] is None and ranges[1] == "bytes=300000-"


def test_a_resume_from_the_wrong_place_fails_and_leaves_nothing(server, tmp_path):
    Handler.mode = "wrong-range"
    with pytest.raises(RemoteError, match="wrong place"):
        remote.download(Session(server), f"{server}/games/disc.iso", str(tmp_path), free_space=PLENTY)
    assert os.listdir(tmp_path) == []


def test_a_wrong_checksum_fails_and_leaves_nothing(server, tmp_path):
    with pytest.raises(RemoteError, match="does not match"):
        remote.download(Session(server), f"{server}/games/disc.iso", str(tmp_path), sha256="0" * 64, free_space=PLENTY)
    assert os.listdir(tmp_path) == []


def test_low_space_refuses_before_downloading(server, tmp_path):
    with pytest.raises(RemoteError, match="not enough free space"):
        remote.download(Session(server), f"{server}/games/disc.iso", str(tmp_path), free_space=lambda p: 1024**3)
    assert os.listdir(tmp_path) == []


def test_cancel_deletes_the_partial_file(server, tmp_path):
    with pytest.raises(Cancelled):
        remote.download(
            Session(server), f"{server}/games/disc.iso", str(tmp_path), cancelled=lambda: True, free_space=PLENTY
        )
    assert os.listdir(tmp_path) == []


def test_same_host_redirect_is_followed_and_missing_files_are_plain(server, tmp_path):
    path = remote.download(Session(server), f"{server}/moved.iso", str(tmp_path), free_space=PLENTY)
    assert os.path.basename(path) == "moved.iso" and open(path, "rb").read() == DATA
    with pytest.raises(RemoteError, match="nothing was found"):
        remote.download(Session(server), f"{server}/games/none.iso", str(tmp_path), free_space=PLENTY)


# A scripted server for what a local plain-HTTP one cannot show: https, other hosts, credentials.


class Reply:
    def __init__(self, status, headers=None, body=b""):
        self.status, self.headers, self.body = status, headers or {}, body

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, n=-1):
        out, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
        return out

    def close(self):
        pass


class Script:
    def __init__(self, replies):
        self.replies, self.calls = dict(replies), []

    def __call__(self, scheme, host, port):
        script = self

        class Conn:
            def request(self, method, target, headers):
                script.calls.append((f"{scheme}://{host}{target}", headers))
                self.key = f"{scheme}://{host}{target}"

            def getresponse(self):
                return script.replies[self.key]

            def close(self):
                pass

        return Conn()


def public(host):
    return ["203.0.113.7"]


def test_credentials_go_only_to_the_typed_host_and_only_over_https(tmp_path):
    script = Script(
        {
            "https://nas.example/a.iso": Reply(302, {"Location": "https://cdn.example/a.iso"}),
            "https://cdn.example/a.iso": Reply(200, {"Content-Length": "3"}, b"abc"),
        }
    )
    session = Session("https://nas.example/", "player", "pw", connect=script, resolve=public)
    with pytest.raises(RedirectElsewhere) as info:
        remote.download(session, "https://nas.example/a.iso", str(tmp_path), free_space=PLENTY)
    assert info.value.host == "cdn.example"
    allowed = Session("https://nas.example/", "player", "pw", allowed={"cdn.example"}, connect=script, resolve=public)
    remote.download(allowed, "https://nas.example/a.iso", str(tmp_path), free_space=PLENTY)
    sent = {url: "Authorization" in headers for url, headers in script.calls}
    assert sent == {"https://nas.example/a.iso": True, "https://cdn.example/a.iso": False}


def test_https_never_drops_to_plain_http(tmp_path):
    script = Script({"https://nas.example/a.iso": Reply(301, {"Location": "http://nas.example/a.iso"})})
    with pytest.raises(RemoteError, match="plain http"):
        remote.download(Session("https://nas.example/", connect=script), "https://nas.example/a.iso", str(tmp_path))


def test_plain_http_only_on_the_local_network_and_never_with_a_password(tmp_path):
    script = Script({"http://nas.example/a.iso": Reply(200, {"Content-Length": "3"}, b"abc")})
    with pytest.raises(RemoteError, match="not on your local network"):
        remote.download(
            Session("http://nas.example/", connect=script, resolve=public), "http://nas.example/a.iso", str(tmp_path)
        )
    local = Session("http://nas.example/", connect=script, resolve=lambda h: ["192.168.1.20"])
    assert remote.download(local, "http://nas.example/a.iso", str(tmp_path), free_space=PLENTY).endswith("a.iso")
    with pytest.raises(RemoteError, match="only sent over https"):
        Session("http://nas.example/", "player", "pw")


def test_private_address_rules():
    assert remote.host_is_private("192.168.0.4") and remote.host_is_private("127.0.0.1")
    assert remote.host_is_private("fe80::1") and remote.host_is_private("[fd00::5]")
    assert not remote.host_is_private("203.0.113.7") and not remote.host_is_private("224.0.0.251")
    assert not remote.host_is_private("nas.local", lambda h: ["10.0.0.2", "198.51.100.1"])  # every address must be
    assert not remote.host_is_private("nas.local", lambda h: [])

    def broken(host):
        raise OSError("no DNS")

    assert not remote.host_is_private("nas.local", broken)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "ftp://nas/x",
        "https://",
        "https://user:pw@nas/x",
        "https://nas/x?y=1",
        "https://nas/x#y",
        "https://nas:99999/",
        "https://nas/\x00",
        "https://nas/" + "a" * 2001,
    ],
)
def test_addresses_that_are_refused(bad):
    with pytest.raises(RemoteError):
        remote.check_location(bad)


def test_names_and_checksums():
    assert remote.file_name("https://nas/a/My%20Game.iso") == "My Game.iso"
    for bad in ("https://nas/a/", "https://nas/setup.exe", "https://nas/%2e.iso", "https://nas/a%2Fb.iso"):
        with pytest.raises(RemoteError):
            remote.file_name(bad)
    assert remote.check_sha256("") is None
    with pytest.raises(RemoteError):
        remote.check_sha256("abc")


@pytest.mark.parametrize("location", ["https://[::1]x/a.iso", "https://nas.example:99999/a.iso", "ftp://nas.example/a"])
def test_a_malformed_redirect_is_refused_not_a_crash(tmp_path, location):
    script = Script({"https://nas.example/a.iso": Reply(302, {"Location": location})})
    with pytest.raises(RemoteError, match="cannot use"):
        remote.download(Session("https://nas.example/", connect=script), "https://nas.example/a.iso", str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_too_many_redirects(tmp_path):
    script = Script({"https://nas.example/a.iso": Reply(302, {"Location": "/a.iso"})})
    with pytest.raises(RemoteError, match="too many"):
        remote.download(Session("https://nas.example/", connect=script), "https://nas.example/a.iso", str(tmp_path))


def test_a_file_over_the_cap_is_refused(tmp_path):
    script = Script({"https://nas.example/a.iso": Reply(200, {"Content-Length": str(10**6)}, b"x")})
    with pytest.raises(RemoteError, match="larger than"):
        remote.download(
            Session("https://nas.example/", connect=script),
            "https://nas.example/a.iso",
            str(tmp_path),
            free_space=PLENTY,
            max_file=1000,
        )
    assert os.listdir(tmp_path) == []
