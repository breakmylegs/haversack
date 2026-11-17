"""Built-in sign-in clients (ADR-0032). Synthetic client IDs only."""

import asyncio

import pytest

import test_app_cloud
from keepsake import auth, clients
from keepsake.auth import GOOGLE, TokenManager, TokenStore
from test_app_cloud import CLIENT
from test_backends import Recorder

setup = test_app_cloud.setup  # the fake login and fake Graph app fixture
OTHER = "99998888-ffff-7777-eeee-6666dddd5555"


@pytest.fixture
def builtin(monkeypatch):
    def set_ids(onedrive="", google=("", "")):
        monkeypatch.setattr(clients, "ONEDRIVE_CLIENT_ID", onedrive)
        monkeypatch.setattr(clients, "GOOGLE_CLIENT_ID", google[0])
        monkeypatch.setattr(clients, "GOOGLE_CLIENT_SECRET", google[1])

    return set_ids


async def signed_in(app, events):
    shown = await app.start_signin()
    for _ in range(200):
        if events:
            break
        await asyncio.sleep(0.02)
    return shown


def test_shipped_constants_are_empty_until_the_owner_supplies_them():
    # Remove this test in the change that fills them in (ADR-0032: nothing is released before that).
    assert clients.ONEDRIVE_CLIENT_ID == "" and clients.GOOGLE_CLIENT_ID == "" and clients.GOOGLE_CLIENT_SECRET == ""


def test_onedrive_signs_in_with_the_built_in_client_and_no_client_id_saved(setup, builtin):
    app, _, events, _ = setup
    builtin(onedrive=CLIENT)  # the fake login accepts only CLIENT

    async def run():
        status = await app.cloud_status()
        await signed_in(app, events)
        return status, await app.cloud_status()

    before, after = asyncio.run(run())
    assert before["clientIdSet"] is True and before["builtInClient"]["onedrive"] is True
    assert before["ownClient"]["onedrive"] is False
    assert events[0][1][0]["status"] == "signed-in" and after["signedIn"] is True
    assert app.token_store.load()["client_id"] == CLIENT


def test_a_saved_own_client_id_wins_over_the_built_in_one(setup, builtin):
    app, _, events, _ = setup
    builtin(onedrive=OTHER)

    async def run():
        await app.set_setting("onedriveClientId", CLIENT)
        await signed_in(app, events)
        return await app.cloud_status()

    status = asyncio.run(run())
    assert status["ownClient"]["onedrive"] is True and events[0][1][0]["status"] == "signed-in"
    assert app.token_store.load()["client_id"] == CLIENT


def test_an_older_sign_in_keeps_refreshing_with_its_own_client_after_the_id_is_cleared(setup, builtin):
    app, _, _, _ = setup
    builtin(onedrive=OTHER)
    app.token_store.save({"client_id": CLIENT, "access_token": "old", "refresh_token": "R", "expires_at": 0})
    asyncio.run(app.set_setting("onedriveClientId", ""))
    assert app.tokens.access_token() == "good"  # the fake login refuses any client but CLIENT


def test_no_client_at_all_still_asks_for_one(setup, builtin):
    app, _, _, _ = setup
    builtin()
    assert asyncio.run(app.cloud_status())["clientIdSet"] is False
    with pytest.raises(auth.AuthError, match="client ID"):
        asyncio.run(app.start_signin())


def test_google_client_choice(builtin):
    builtin(google=("built-in-id", "built-in-secret"))
    own = {"clientId": "own-id", "clientSecret": "own-secret"}
    assert clients.google_client({"clientId": "", "clientSecret": ""}) == ("built-in-id", "built-in-secret")
    assert clients.google_client({"clientId": "own-id", "clientSecret": ""}) == ("built-in-id", "built-in-secret")
    assert clients.google_client(own) == ("own-id", "own-secret")
    assert clients.google_secret_for("built-in-id", own) == "built-in-secret"
    assert clients.google_secret_for("own-id", own) == "own-secret"
    assert clients.google_builtin() is True
    builtin(google=("built-in-id", ""))
    assert clients.google_builtin() is False  # half a client is no client


def test_google_refresh_sends_the_secret_of_the_client_the_sign_in_was_made_with(tmp_path, builtin):
    builtin(google=("built-in-id", "built-in-secret"))
    own = {"clientId": "own-id", "clientSecret": "own-secret"}
    store = TokenStore(str(tmp_path), GOOGLE.token_file)
    transport = Recorder([(200, {"access_token": "new", "expires_in": 3600})] * 2)
    manager = TokenManager(
        store,
        lambda: clients.google_client(own)[0],
        transport=transport,
        provider=GOOGLE,
        client_secret=lambda client_id: clients.google_secret_for(client_id, own),
    )
    store.save({"client_id": "built-in-id", "access_token": "old", "refresh_token": "rt", "expires_at": 0})
    manager.access_token()
    store.save({"client_id": "own-id", "access_token": "old", "refresh_token": "rt", "expires_at": 0})
    manager.access_token()
    sent = [(form["client_id"], form["client_secret"]) for _, form in transport.calls]
    assert sent == [("built-in-id", "built-in-secret"), ("own-id", "own-secret")]
