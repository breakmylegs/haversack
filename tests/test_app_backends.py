"""Choosing and checking a WebDAV, S3 or Google Drive backend through the app (slice 10)."""

import asyncio

import pytest

from fake_clouds import FakeDrive, FakeS3, FakeWebDav
from fake_graph import http_transport
from helpers import make_fake_steam, shortcut_entry
from keepsake import backends
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

APPID = 4171510507
KEY = f"shortcut:7:{APPID}"
MANIFEST = '---\nExample Quest:\n  files:\n    "<winLocalAppData>/ExampleQuest":\n      tags:\n        - save\n'


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_https", lambda value, label: value)  # the fakes speak plain HTTP
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home, users={"7": [shortcut_entry(APPID - 2**32, "Example Quest", "/g.exe")]}, prefixes=[(None, APPID)]
    )
    saves = root / "steamapps/compatdata" / str(APPID) / "pfx/drive_c/users/steamuser/AppData/Local/ExampleQuest"
    saves.mkdir(parents=True)
    drive = FakeDrive()
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    instance = KeepsakeApp(
        paths,
        proc_root=str(tmp_path / "proc"),
        version="0.10.0",
        home=str(home),
        auto_refresh_manifest=False,
        google_transport=http_transport,
        google_api=(drive.api, drive.upload),
        endpoint_transport=lambda url: http_transport,
    )
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(MANIFEST)
    instance.manifest.import_file(str(manifest_file))
    yield instance, saves, drive
    drive.close()


def test_webdav_backend_is_checked_registered_and_used_for_sync(app):
    instance, saves, _ = app
    fake = FakeWebDav(password="pw")

    async def go():
        public = await instance.set_backend_config(
            "webdav", {"url": fake.base_url, "username": "user", "password": "pw"}
        )
        instance.settings.set("snapshotStore", "webdav")
        status = await instance.cloud_status()
        checked = await instance.test_cloud()
        (saves / "slot.sav").write_bytes(b"progress")
        pushed = await instance.sync_push(KEY)
        return public, status, checked, pushed

    try:
        public, status, checked, pushed = asyncio.run(go())
    finally:
        fake.close()
    assert public["password"] == "" and public["passwordSet"] is True
    assert status["store"] == "webdav" and status["signedIn"] is True and status["name"] == "WebDAV"
    assert checked == {"ok": True, "registered": True}
    device = instance.settings.get("deviceId")
    assert f"registry/devices/{device}.json" in fake.files and f"registry/probe/{device}.json" in fake.files
    assert pushed["status"] == "published"
    assert any(name.startswith("games/example-quest/snapshots/") for name in fake.files)


def test_a_webdav_server_without_create_only_writes_is_refused(app):
    instance, _, _ = app
    fake = FakeWebDav(password="pw")
    fake.ignore_create_only = True

    async def go():
        await instance.set_backend_config("webdav", {"url": fake.base_url, "username": "user", "password": "pw"})
        return await instance.test_cloud("webdav")

    try:
        result = asyncio.run(go())
    finally:
        fake.close()
    assert result["ok"] is False and "If-None-Match" in result["error"]


def test_s3_backend_check(app):
    instance, _, _ = app
    fake = FakeS3()

    async def go():
        await instance.set_backend_config(
            "s3",
            {"endpoint": fake.endpoint, "bucket": FakeS3.BUCKET, "accessKey": "AKIDEXAMPLE", "secretKey": "x" * 20},
        )
        return await instance.test_cloud("s3")

    try:
        result = asyncio.run(go())
    finally:
        fake.close()
    assert result["ok"] is True
    assert any(k.startswith("keepsake/registry/devices/") for k in fake.files)


def test_unconfigured_backends_explain_what_is_missing(app):
    instance, _, _ = app
    for backend in ("webdav", "s3"):
        result = asyncio.run(instance.test_cloud(backend))
        assert result["ok"] is False and "first" in result["error"]


def test_google_drive_backend_uses_the_google_tokens(app):
    instance, _, drive = app
    instance.google_tokens.store.save(
        {"client_id": "c", "access_token": "good", "refresh_token": "rt", "expires_at": 9e12}
    )
    instance.settings.set("snapshotStore", "gdrive")

    async def go():
        return await instance.cloud_status(), await instance.test_cloud(), await instance.health_checks(False)

    status, checked, health = asyncio.run(go())
    assert status["store"] == "gdrive" and status["signedIn"] is True and status["googleSignedIn"] is True
    assert checked["ok"] is True
    assert any(name.startswith("registry/devices/") for name in drive.names())
    cloud_check = next(c for c in health["checks"] if c["id"] == "cloud")
    assert "Google Drive" in cloud_check["detail"]
