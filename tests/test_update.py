import json

import pytest

from keepsake.net import HttpResponse, NetError
from keepsake.update import (
    INSTALL_TYPE,
    RELEASES_URL,
    Updater,
    parse_releases,
    parse_sums,
    parse_version,
    select_latest,
    startup_notice,
)

DIGEST = "ab" * 32


def release(tag, prerelease=False, draft=False, assets=True, body="Notes"):
    version = tag[1:]
    items = []
    if assets:
        items = [
            {"name": f"Keepsake-v{version}.zip", "browser_download_url": f"https://github.com/r/{tag}/zip"},
            {"name": "SHA256SUMS", "browser_download_url": f"https://github.com/r/{tag}/sums"},
        ]
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": "2026-11-14T10:00:00Z",
        "body": body,
        "assets": items,
        "extra_field": "dropped from cache",
    }


class FakeGitHub:
    def __init__(self, releases, sums=None):
        self.releases = releases
        self.sums = sums or {}
        self.calls = []
        self.etag = '"v1"'
        self.status_override = None
        self.raise_error = False

    def __call__(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        if self.raise_error:
            raise NetError("offline")
        if url == RELEASES_URL:
            if self.status_override:
                return HttpResponse(status=self.status_override)
            if (headers or {}).get("If-None-Match") == self.etag:
                return HttpResponse(status=304)
            return HttpResponse(status=200, headers={"etag": self.etag}, body=json.dumps(self.releases).encode())
        if url in self.sums:
            return HttpResponse(status=200, body=self.sums[url].encode())
        return HttpResponse(status=404)


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_parse_version_ordering():
    assert parse_version("1.2.3") > parse_version("1.2.3-beta.9")
    assert parse_version("1.2.3-beta.2") > parse_version("1.2.3-beta.1")
    assert parse_version("1.10.0") > parse_version("1.9.9")
    assert parse_version("v0.2.0") == parse_version("0.2.0")
    for bad in ("1.2", "1.2.3-rc.1", "latest", "1.2.3-beta", ""):
        assert parse_version(bad) is None


def test_parse_releases_skips_drafts_and_bad_tags_and_sorts():
    payload = [
        release("v0.2.0"),
        release("v0.3.0", draft=True),
        release("nightly"),
        release("v0.2.1-beta.1"),
        release("v0.10.0", assets=False),
        "junk",
    ]
    releases = parse_releases(payload)
    assert [r.tag for r in releases] == ["v0.10.0", "v0.2.1-beta.1", "v0.2.0"]
    beta = releases[1]
    assert beta.prerelease is True  # from the tag even if the flag is missing
    assert releases[0].complete is False
    assert releases[2].zip_url == "https://github.com/r/v0.2.0/zip"


def test_select_latest_respects_channel_and_completeness():
    releases = parse_releases([release("v0.3.0", assets=False), release("v0.2.1-beta.1"), release("v0.2.0")])
    assert select_latest(releases, "stable").tag == "v0.2.0"
    assert select_latest(releases, "prerelease").tag == "v0.2.1-beta.1"


def test_parse_sums():
    text = f"{DIGEST}  Keepsake-v0.2.0.zip\n{'CD' * 32} *Other.zip\nnot a line\n{'zz' * 32}  Bad.zip\n"
    assert parse_sums(text) == {"Keepsake-v0.2.0.zip": DIGEST, "Other.zip": "cd" * 32}


def test_check_finds_update_and_notifies_once(tmp_path):
    gh = FakeGitHub([release("v0.2.1"), release("v0.2.0")])
    updater = Updater(str(tmp_path), "0.2.0", gh, clock=Clock())
    first = updater.check("stable")
    assert first["updateAvailable"] is True
    assert first["latest"]["version"] == "0.2.1"
    assert first["notify"] is True
    assert [r["tag"] for r in first["releases"]] == ["v0.2.1", "v0.2.0"]
    assert updater.check("stable", force=True)["notify"] is False


def test_check_throttles_to_once_a_day_and_uses_etag(tmp_path):
    gh = FakeGitHub([release("v0.2.0")])
    clock = Clock()
    updater = Updater(str(tmp_path), "0.2.0", gh, clock=clock)
    updater.check("stable")
    updater.check("stable")
    assert len(gh.calls) == 1
    clock.now += 24 * 3600
    result = updater.check("stable")
    assert len(gh.calls) == 2
    assert gh.calls[1][1]["If-None-Match"] == '"v1"'
    assert result["releases"][0]["tag"] == "v0.2.0"  # served from cache after 304
    updater.check("stable", force=True)
    assert len(gh.calls) == 3


def test_rate_limit_and_offline_fail_quietly_with_cache(tmp_path):
    gh = FakeGitHub([release("v0.2.1")])
    updater = Updater(str(tmp_path), "0.2.0", gh, clock=Clock())
    updater.check("stable")
    gh.status_override = 403
    limited = updater.check("stable", force=True)
    assert limited["error"] == "rate-limited"
    assert limited["updateAvailable"] is True
    gh.raise_error = True
    offline = updater.check("stable", force=True)
    assert offline["error"] == "offline"
    assert offline["latest"]["tag"] == "v0.2.1"


def test_check_with_no_cache_and_offline(tmp_path):
    gh = FakeGitHub([])
    gh.raise_error = True
    result = Updater(str(tmp_path), "0.2.0", gh, clock=Clock()).check("stable")
    assert result["error"] == "offline"
    assert result["latest"] is None and result["updateAvailable"] is False


def test_cache_drops_unused_fields(tmp_path):
    gh = FakeGitHub([release("v0.2.0")])
    Updater(str(tmp_path), "0.2.0", gh, clock=Clock()).check("stable")
    cached = json.loads((tmp_path / "update-state.json").read_text())
    assert "extra_field" not in cached["releases"][0]


def make_ready(tmp_path, current="0.2.0", sums_text=None):
    gh = FakeGitHub(
        [release("v0.2.1"), release("v0.2.0"), release("v0.1.0", assets=False)],
        sums={
            "https://github.com/r/v0.2.1/sums": sums_text or f"{DIGEST}  Keepsake-v0.2.1.zip\n",
            "https://github.com/r/v0.2.0/sums": f"{'cd' * 32}  Keepsake-v0.2.0.zip\n",
        },
    )
    updater = Updater(str(tmp_path), current, gh, clock=Clock())
    updater.check("stable")
    return updater, gh


def test_prepare_returns_decky_arguments(tmp_path):
    updater, _ = make_ready(tmp_path)
    result = updater.prepare("v0.2.1", busy_reason=None)
    assert result == {
        "ok": True,
        "artifact": "https://github.com/r/v0.2.1/zip",
        "name": "Keepsake",
        "version": "dev",
        "displayVersion": "0.2.1",
        "sha256": DIGEST,
        "installType": INSTALL_TYPE["update"],
    }


def test_prepare_rollback_is_a_downgrade(tmp_path):
    updater, _ = make_ready(tmp_path, current="0.2.1")
    result = updater.prepare("v0.2.0", busy_reason=None)
    assert result["ok"] is True
    assert result["installType"] == INSTALL_TYPE["downgrade"]


def test_prepare_refused_while_busy_without_network(tmp_path):
    updater, gh = make_ready(tmp_path)
    calls_before = len(gh.calls)
    assert updater.prepare("v0.2.1", busy_reason="sync") == {"ok": False, "reason": "busy", "detail": "sync"}
    assert len(gh.calls) == calls_before


@pytest.mark.parametrize(
    ("tag", "sums_text", "reason"),
    [
        ("v9.9.9", None, "unknown-release"),
        ("v0.1.0", None, "incomplete-release"),
        ("v0.2.1", f"{DIGEST}  Something-else.zip\n", "sums-missing-zip"),
    ],
)
def test_prepare_refusals(tmp_path, tag, sums_text, reason):
    updater, _ = make_ready(tmp_path, sums_text=sums_text)
    assert updater.prepare(tag, busy_reason=None)["reason"] == reason


def test_prepare_sums_download_failure(tmp_path):
    updater, gh = make_ready(tmp_path)
    gh.sums.clear()
    assert updater.prepare("v0.2.1", busy_reason=None)["reason"] == "sums-unavailable"
    gh.raise_error = True
    assert updater.prepare("v0.2.1", busy_reason=None)["reason"] == "offline"


def test_prepare_rejects_zip_on_disallowed_host(tmp_path):
    payload = [release("v0.2.1")]
    payload[0]["assets"][0]["browser_download_url"] = "https://evil.example.com/Keepsake-v0.2.1.zip"
    gh = FakeGitHub(payload, sums={"https://github.com/r/v0.2.1/sums": f"{DIGEST}  Keepsake-v0.2.1.zip\n"})
    updater = Updater(str(tmp_path), "0.2.0", gh, clock=Clock())
    updater.check("stable")
    assert updater.prepare("v0.2.1", busy_reason=None)["reason"] == "disallowed-host"


def test_startup_notice_once_after_version_change(tmp_path):
    assert startup_notice(str(tmp_path), "0.2.0") is None
    assert startup_notice(str(tmp_path), "0.2.0") is None
    assert startup_notice(str(tmp_path), "0.2.1") == {"from": "0.2.0", "to": "0.2.1"}
    assert startup_notice(str(tmp_path), "0.2.1") is None
