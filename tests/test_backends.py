"""Keys and passwords the user enters (slice 10, the strip, ADR-0098): the SteamGridDB key and network passwords."""

import os
import stat

import pytest

from keepsake.backends import BackendConfigError, CredentialStore

# Assembled at runtime so the file holds no secret-shaped literal.
KEY = "abcd" * 8
SECRET = "pass" + "word-123"


def test_secrets_are_never_returned_and_blank_keeps_them(tmp_path):
    store = CredentialStore(str(tmp_path))
    saved = store.save("steamgriddb", {"apiKey": KEY})
    assert saved == {"apiKey": "", "apiKeySet": True, "configured": True}
    store.save("steamgriddb", {"apiKey": ""})  # blank keeps the stored key
    assert store.load("steamgriddb")["apiKey"] == KEY


@pytest.mark.parametrize(
    ("kind", "values", "message"),
    [
        ("steamgriddb", {"apiKey": "short"}, "16 to 64"),
        ("steamgriddb", {"unknown": "x"}, "unknown"),
        ("webdav", {"url": "https://dav.example.test/"}, "unknown"),  # the cloud stores went in the strip
    ],
)
def test_invalid_settings_are_refused(tmp_path, kind, values, message):
    with pytest.raises(BackendConfigError, match=message):
        CredentialStore(str(tmp_path)).save(kind, values)


def test_configured_needs_the_key_and_clear_forgets_it(tmp_path):
    store = CredentialStore(str(tmp_path))
    assert store.configured("steamgriddb") is False
    store.save("steamgriddb", {"apiKey": KEY})
    assert store.configured("steamgriddb") is True
    store.clear("steamgriddb")
    assert store.configured("steamgriddb") is False


def test_old_cloud_settings_are_left_alone(tmp_path):
    """Files from before the strip stay where they are, so reinstalling v0.60.0 finds them."""
    (tmp_path / "webdav.json").write_text('{"url": "https://dav.example.test/"}')
    store = CredentialStore(str(tmp_path))
    store.save("steamgriddb", {"apiKey": KEY})
    store.clear("steamgriddb")
    assert (tmp_path / "webdav.json").exists()


def test_network_passwords_are_kept_per_location(tmp_path):
    store = CredentialStore(str(tmp_path))
    store.keyed_set("netinstall", "smb://nas.example.test/games", SECRET)
    assert store.keyed_get("netinstall", "smb://nas.example.test/games") == SECRET
    assert store.keyed_get("netinstall", "smb://other.example.test/games") == ""
    store.keyed_set("netinstall", "smb://nas.example.test/games", None)
    assert store.keyed_get("netinstall", "smb://nas.example.test/games") == ""


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="file modes need POSIX")
def test_backend_files_are_private(tmp_path):
    CredentialStore(str(tmp_path)).save("steamgriddb", {"apiKey": KEY})
    assert stat.S_IMODE(os.stat(tmp_path / "steamgriddb.json").st_mode) == 0o600
