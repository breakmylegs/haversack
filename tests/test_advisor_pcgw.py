"""PCGamingWiki for Advisor (ADR-0031): optional, off by default, the user's own bot login, cached. Synthetic data."""

import json

import pytest

from keepsake import net
from keepsake.advisor import pcgw
from test_advisor import make_advisor, report, snapshot


class Message:
    def __init__(self, pairs):
        self.pairs = pairs

    def items(self):
        return list(self.pairs)


def test_repeated_set_cookie_headers_are_kept():
    headers = net._headers(Message([("Set-Cookie", "a=1; path=/"), ("Content-Type", "x"), ("set-cookie", "b=2")]))
    assert headers == {"set-cookie": "a=1; path=/\nb=2", "content-type": "x"}
    assert net._headers(None) == {}


class Wiki:
    """A fake PCGamingWiki: login token, login, then Cargo queries; records every request."""

    def __init__(self, login="Success", cargo_error=None, status=200, rows=None):
        self.login_result, self.cargo_error, self.status, self.calls = login, cargo_error, status, []
        self.rows = (
            rows
            if rows is not None
            else [{"title": {"Page": "Example Quest", "Upscaling": "FSR 2,XeSS", "FrameGen": "FSR 3"}}]
        )

    def __call__(self, method, url, headers=None, body=None, timeout=None, allowed=None, suffixes=None):
        net.check_url(url, allowed, suffixes or ())
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "body": body, "allowed": allowed}
        )
        if self.status != 200:
            return net.HttpResponse(self.status, {}, b"")
        if "meta=tokens" in url:
            return net.HttpResponse(
                200,
                {"set-cookie": "wiki_session=s1; path=/\nother=o1"},
                json.dumps({"query": {"tokens": {"logintoken": "t+\\"}}}).encode(),
            )
        if "action=login" in url:
            return net.HttpResponse(
                200, {"set-cookie": "wikiUserID=u1"}, json.dumps({"login": {"result": self.login_result}}).encode()
            )
        if self.cargo_error:
            error, self.cargo_error = self.cargo_error, (None if self.cargo_error == "once" else self.cargo_error)
            if error == "once":
                error = "permissiondenied"
            return net.HttpResponse(200, {}, json.dumps({"error": {"code": error}}).encode())
        return net.HttpResponse(200, {}, json.dumps({"cargoquery": self.rows}).encode())


def test_login_then_query_with_session_cookies():
    wiki = Wiki()
    client = pcgw.PcgwClient("Someone@keepsake", "synthetic-bot-password", "Keepsake/test", wiki)
    found = client.game(1999999101, None)
    assert found["upscaling"] == ["FSR 2", "XeSS"] and found["frameGen"] == ["FSR 3"]
    assert found["url"] == "https://www.pcgamingwiki.com/wiki/Example_Quest" and "CC BY-NC-SA" in found["attribution"]
    login = next(c for c in wiki.calls if "action=login" in c["url"])
    assert login["method"] == "POST" and b"lgpassword=synthetic-bot-password" in login["body"]
    assert login["headers"]["Cookie"] == "wiki_session=s1; other=o1"
    query = wiki.calls[-1]
    assert "Steam_AppID+HOLDS" in query["url"] and "wikiUserID=u1" in query["headers"]["Cookie"]
    assert {frozenset(c["allowed"]) for c in wiki.calls} == {frozenset({"www.pcgamingwiki.com"})}  # one host only


def test_login_and_query_failures_are_explained():
    with pytest.raises(pcgw.PcgwError, match="rejected the sign-in"):
        pcgw.PcgwClient("u", "p", "ua", Wiki(login="Failed")).game(1, None)
    with pytest.raises(pcgw.PcgwError, match="Cargo"):
        pcgw.PcgwClient("u", "p", "ua", Wiki(cargo_error="permissiondenied")).game(1, None)
    with pytest.raises(pcgw.PcgwError, match="rate limiting"):
        pcgw.PcgwClient("u", "p", "ua", Wiki(status=429)).game(1, None)
    with pytest.raises(pcgw.PcgwError, match="bot user name and bot password"):
        pcgw.PcgwClient("", "", "ua", Wiki()).game(1, None)
    expired = Wiki(cargo_error="once")
    assert pcgw.PcgwClient("u", "p", "ua", expired).game(1, None)["page"] == "Example Quest"  # signed in again once
    assert sum("action=login" in c["url"] for c in expired.calls) == 2
    unsafe = Wiki()
    assert pcgw.PcgwClient("u", "p", "ua", unsafe).game(None, 'Quote" OR 1=1') is None and unsafe.calls == []
    assert pcgw.PcgwClient("u", "p", "ua", Wiki(rows=[])).game(1, None) is None


def test_upscaler_families():
    assert pcgw.upscaler_supported("AMD FidelityFX Super Resolution 2", ["FSR 3.1"])
    assert not pcgw.upscaler_supported("DLSS", ["FSR 2", "XeSS"])
    assert pcgw.upscaler_supported("anything", [])


def test_advisor_uses_pcgw_only_when_switched_on_and_logged_in(tmp_path):
    advisor, _calls = make_advisor(tmp_path)
    wiki = Wiki()
    login = {"set": False}
    advisor._pcgw_client = lambda: pcgw.PcgwClient("u", "p", "ua", wiki) if login["set"] else None
    own = [str(tmp_path / "settings" / "advisor.json"), str(tmp_path / "runtime" / "advisor-cache")]
    before = snapshot(str(tmp_path), own)
    advisor._fetch_reports = lambda appid, name: {
        "reports": [{**report(), "data": {**report()["data"], "game_graphics_settings": "- Upscaling: DLSS Quality\n"}}]
    }
    advisor.set_game(1999999101)
    assert advisor.view()["pcgw"]["enabled"] is False and wiki.calls == []  # off by default: nothing sent
    advisor.save_settings({"sourcePcgw": True})
    advisor.set_game(1999999101)
    assert "bot user name and bot password" in advisor.view()["pcgw"]["error"]  # asks for the login
    login["set"] = True
    advisor.set_game(1999999101)
    view = advisor.view()
    assert view["pcgw"]["data"]["upscaling"] == ["FSR 2", "XeSS"]
    assert any("PCGamingWiki does not list DLSS" in f for f in view["recommendations"][0]["flags"])
    assert "From PCGamingWiki, CC BY-NC-SA." in view["attribution"]
    calls = len(wiki.calls)
    advisor.set_game(1999999101)
    assert len(wiki.calls) == calls and advisor.view()["pcgw"]["cached"]  # cached for 7 days
    wiki.status = 429
    advisor.load_reports(True)
    stale = advisor.view()["pcgw"]
    assert stale["cached"] and stale["data"]["page"] == "Example Quest" and "rate limiting" in stale["error"]
    assert snapshot(str(tmp_path), own) == before  # still read-only (P16)


def test_pcgw_login_is_a_backend_secret(tmp_path):
    from keepsake.backends import CredentialStore

    store = CredentialStore(str(tmp_path))
    assert store.configured("pcgw") is False
    assert store.save("pcgw", {"username": "Someone@keepsake", "password": "synthetic"}) == {
        "username": "Someone@keepsake",
        "password": "",
        "passwordSet": True,
        "configured": True,
    }
