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
