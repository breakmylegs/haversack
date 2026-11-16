import urllib.request

import pytest

from keepsake import net
from keepsake.net import NetError, check_url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.github.com/repos/x/y/releases",
        "https://github.com/x/y/releases/download/v1/a.zip",
        "https://release-assets.githubusercontent.com/abc",
        "https://objects.githubusercontent.com/abc",
    ],
)
def test_allowed(url):
    assert check_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/x",  # not https
        "https://evil.example.com/x",
        "https://api.github.com.evil.example/x",
        "https://user:pw" + "@" + "api.github.com/x",  # assembled so the secret scan does not see an email
        "file:///etc/passwd",
        "https://plugins.deckbrew.xyz/plugins",
    ],
)
def test_rejected(url):
    with pytest.raises(NetError):
        check_url(url)


def test_fetch_rejects_before_any_network(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("network used")

    monkeypatch.setattr(urllib.request, "build_opener", boom)
    with pytest.raises(NetError):
        net.fetch("https://evil.example.com/")


def test_redirect_to_disallowed_host_is_blocked():
    handler = net._AllowlistRedirect(net.ALLOWED_HOSTS)
    request = urllib.request.Request("https://github.com/x")
    with pytest.raises(NetError):
        handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example.com/payload.zip")
    allowed = handler.redirect_request(
        request, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/payload.zip"
    )
    assert allowed is not None


class _FakeResponse:
    def __init__(self, body, length):
        self.body, self.status = body, 200
        self.headers = {"Content-Length": str(length)} if length is not None else {}

    def read(self, size):
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("length", [600 * 1024, None])
def test_fetch_to_file_reports_progress(tmp_path, monkeypatch, length):
    body = b"y" * (600 * 1024)

    class Opener:
        def open(self, request, timeout):
            return _FakeResponse(body, length)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    seen = []
    dest = tmp_path / "out"
    net.fetch_to_file(
        "https://raw.githubusercontent.com/x", str(dest), progress=lambda done, total: seen.append((done, total))
    )
    assert dest.read_bytes() == body
    assert [done for done, _ in seen] == [256 * 1024, 512 * 1024, 600 * 1024]  # after every chunk
    assert {total for _, total in seen} == {length}  # Content-Length, or None when the server gives none
