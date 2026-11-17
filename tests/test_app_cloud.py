"""Sign-in and OneDrive snapshots through the app, against a fake login and a fake Graph."""

import asyncio
import json
import os
import urllib.parse

import pytest

from fake_graph import FakeGraph, http_transport
from helpers import make_fake_steam, shortcut_entry
from keepsake import auth, clients, net
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

CLIENT = "00001111-aaaa-2222-bbbb-3333cccc4444"
APPID = 4171510507
KEY = f"shortcut:7:{APPID}"


class Router:
    """Sends login requests to a scripted login and everything else to the fake Graph."""

    def __init__(self, fake):
        self.fake = fake
        self.token_calls = 0

    def __call__(self, method, url, headers=None, body=None, dest=None, **kw):
        if url == auth.DEVICECODE_URL:
            return net.HttpResponse(
                200,
                body=json.dumps(
                    {
                        "device_code": "D",
                        "user_code": "WXYZ-1234",
                        "verification_uri": "https://www.microsoft.com/link",
                        "expires_in": 900,
                        "interval": 1,
                    }
                ).encode(),
            )
        if url == auth.TOKEN_URL:
            self.token_calls += 1
            fields = dict(urllib.parse.parse_qsl(body.decode()))
            assert fields["client_id"] == CLIENT
            if fields["grant_type"] == auth.DEVICE_GRANT and self.token_calls == 1:
                return net.HttpResponse(400, body=b'{"error":"authorization_pending"}')
            return net.HttpResponse(
                200, body=json.dumps({"access_token": "good", "refresh_token": "R", "expires_in": 3600}).encode()
            )
        return http_transport(method, url, headers, body, dest=dest)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    fake = FakeGraph()
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home, users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]}, prefixes=[(None, APPID)]
    )
    saves = root / "steamapps/compatdata" / str(APPID) / "pfx/drive_c/users/steamuser/AppData/Local/ExampleQuest"
    saves.mkdir(parents=True)
    (saves / "slot.sav").write_bytes(b"progress")
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    events = []

    async def emit(event, *args):
        events.append((event, args))

    app = KeepsakeApp(
        paths,
        emit=emit,
        proc_root=str(tmp_path / "proc"),
        version="0.6.0",
        home=str(home),
        auto_refresh_manifest=False,
        transport=Router(fake),
        graph_base_url=fake.base_url,
    )
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        '---\nExample Quest:\n  files:\n    "<winLocalAppData>/ExampleQuest":\n      tags:\n        - save\n'
    )
    app.manifest.import_file(str(manifest_file))
    yield app, fake, events, paths
    fake.close()


def test_sign_in_registers_device_and_snapshots_go_to_onedrive(setup, monkeypatch):
    app, fake, events, paths = setup
    monkeypatch.setattr(clients, "ONEDRIVE_CLIENT_ID", "")  # no built-in client: the user's own ID is needed

    async def run():
        with pytest.raises(auth.AuthError, match="client ID"):
            await app.start_signin()
        await app.set_setting("onedriveClientId", CLIENT)
        shown = await app.start_signin()
        for _ in range(200):
            if events:
                break
            await asyncio.sleep(0.02)
        status = await app.cloud_status()
        await app.set_setting("snapshotStore", "onedrive")
        snap = await app.snapshot_game(KEY)
        listing = await app.list_snapshots(KEY)
        tested = await app.test_cloud()
        return shown, status, snap, listing, tested

    shown, status, snap, listing, tested = asyncio.run(run())
    assert shown["userCode"] == "WXYZ-1234"
    assert events[0] == ("keepsake_signin", ({"status": "signed-in", "registered": True},))
    assert status["signedIn"] is True and status["signingIn"] is False
    device_id = app.settings.get("deviceId")
    assert f"registry/devices/{device_id}.json" in fake.files
    assert snap["status"] == "published"
    assert any(k.startswith("games/example-quest/blobs/") for k in fake.files)
    assert listing["snapshots"][0]["snapId"] == snap["snapId"]
    assert tested == {"ok": True, "folder": "Keepsake"}
    token_text = open(os.path.join(paths.settings_dir, auth.TOKEN_FILE)).read()
    log_text = open(os.path.join(paths.log_dir, "keepsake.jsonl")).read()
    assert '"R"' in token_text and "WXYZ-1234" not in log_text and '"R"' not in log_text


def test_sign_out_removes_tokens(setup):
    app, _, _, paths = setup
    os.makedirs(paths.settings_dir, exist_ok=True)
    auth.TokenStore(paths.settings_dir).save({"refresh_token": "R", "access_token": "good", "expires_at": 9e9})
    assert asyncio.run(app.cloud_status())["signedIn"] is True
    asyncio.run(app.sign_out())
    assert asyncio.run(app.cloud_status())["signedIn"] is False


def test_settings_validation(setup):
    app, _, _, _ = setup
    with pytest.raises(ValueError):
        asyncio.run(app.set_setting("onedriveClientId", "not-a-guid"))
    with pytest.raises(ValueError):
        asyncio.run(app.set_setting("snapshotStore", "dropbox"))
