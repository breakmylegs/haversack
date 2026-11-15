"""Backend-specific rules for the WebDAV, S3 and Google Drive stores (slice 10)."""

import hashlib

import pytest

from fake_clouds import FakeDrive, FakeGoogleTokens, FakeS3, FakeWebDav
from fake_graph import http_transport
from keepsake import net
from keepsake.store import AlreadyExistsError, NotFoundError, StoreError, sigv4
from keepsake.store.gdrive import GoogleDriveStore
from keepsake.store.httpcall import parse_xml
from keepsake.store.s3 import S3Store
from keepsake.store.webdav import WebDavStore

NO_SLEEP = {"sleep": lambda s: None}
# AWS's documented example credentials, assembled so the file holds no key-shaped literal.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY"
AWS_EXAMPLE_TIME = 1369353600  # 2013-05-24T00:00:00Z


@pytest.fixture
def webdav():
    fake = FakeWebDav()
    yield fake, WebDavStore(fake.base_url, "user", "secret", transport=http_transport, **NO_SLEEP)
    fake.close()


@pytest.fixture
def s3():
    fake = FakeS3()
    yield (
        fake,
        S3Store(fake.endpoint, "eu-west-2", FakeS3.BUCKET, "AKIDEXAMPLE", "x", transport=http_transport, **NO_SLEEP),
    )
    fake.close()


@pytest.fixture
def drive():
    fake = FakeDrive()
    yield (
        fake,
        GoogleDriveStore(FakeGoogleTokens(), transport=http_transport, api=fake.api, upload=fake.upload, **NO_SLEEP),
    )
    fake.close()


# SigV4


def test_sigv4_matches_the_aws_get_object_example():
    headers = sigv4.sign(
        "GET",
        "https://examplebucket.s3.amazonaws.com/test.txt",
        {"Range": "bytes=0-9"},
        sigv4.EMPTY_SHA256,
        AWS_KEY,
        AWS_SECRET,
        "us-east-1",
        now=AWS_EXAMPLE_TIME,
    )
    assert headers["Authorization"] == (
        f"AWS4-HMAC-SHA256 Credential={AWS_KEY}/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )
    assert headers["x-amz-date"] == "20130524T000000Z"


def test_sigv4_matches_the_aws_list_objects_example():
    headers = sigv4.sign(
        "GET",
        "https://examplebucket.s3.amazonaws.com/?max-keys=2&prefix=J",
        {},
        sigv4.EMPTY_SHA256,
        AWS_KEY,
        AWS_SECRET,
        "us-east-1",
        now=AWS_EXAMPLE_TIME,
    )
    assert headers["Authorization"].endswith(
        "Signature=34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"
    )


# Create-only proof before use (fail closed)


def test_webdav_check_accepts_a_create_only_server_and_refuses_one_that_ignores_it(webdav):
    fake, store = webdav
    assert store.check("device-1") == {"ok": True}
    assert "registry/probe/device-1.json" in fake.files
    fake.ignore_create_only = True
    with pytest.raises(StoreError, match="ignores create-only"):
        store.check("device-2")


def test_s3_check_accepts_conditional_writes_and_refuses_a_service_without_them(s3):
    fake, store = s3
    assert store.check("device-1") == {"ok": True}
    fake.ignore_create_only = True
    with pytest.raises(StoreError, match="ignores conditional writes"):
        store.check("device-2")


def test_webdav_wrong_password_is_a_clear_error(webdav):
    fake, _ = webdav
    store = WebDavStore(fake.base_url, "user", "wrong", transport=http_transport, **NO_SLEEP)
    with pytest.raises(StoreError, match="user name or password"):
        store.get("a/b.json")


def test_s3_keys_live_under_the_prefix_and_delete_of_a_missing_key_is_not_found(s3):
    fake, store = s3
    store.put_new("games/g/x.json", b"{}")
    assert list(fake.files) == ["keepsake/games/g/x.json"]
    with pytest.raises(NotFoundError):
        store.delete("games/g/missing.json")  # S3 itself answers 204 here


def test_s3_upload_corrupted_in_transit_is_refused(s3):
    fake, store = s3

    def corrupting(method, url, headers=None, body=None, **kw):
        return http_transport(method, url, headers, body[:-1] + b"!" if body else body, **kw)

    store.transport = corrupting
    with pytest.raises(StoreError, match="upload failed"):
        store.put_new("a/b.bin", b"payload")  # the signed hash no longer matches the body
    assert fake.files == {}


# Google Drive


def test_drive_duplicate_names_resolve_to_the_oldest_copy(drive):
    fake, store = drive
    store.put_new("games/g/pins/1.json", b"first")
    # Another device's upload that slipped past the name check lands later: it must lose.
    fake.meta["99"] = {"name": "games/g/pins/2.json", "created": 0}
    fake.files["99"] = b"older"
    with pytest.raises(AlreadyExistsError):
        store.put_new("games/g/pins/2.json", b"newer")
    assert fake.names() == ["games/g/pins/1.json", "games/g/pins/2.json"]  # its own losing copy is gone
    assert store.get("games/g/pins/2.json") == b"older"


def test_drive_writer_that_loses_a_race_deletes_only_its_own_copy(drive):
    fake, store = drive

    def other_device_lands_first(name):
        fake.meta["50"] = {"name": name, "created": 0}  # older than anything this upload gets
        fake.files["50"] = b"theirs"

    fake.before_create = other_device_lands_first
    with pytest.raises(AlreadyExistsError):
        store.put_new("games/g/pins/3.json", b"mine")
    assert fake.names() == ["games/g/pins/3.json"]  # one copy left, and it is theirs
    assert store.get("games/g/pins/3.json") == b"theirs"


def test_drive_does_not_upload_when_the_name_is_taken(drive):
    fake, store = drive
    store.put_new("a/b.json", b"first")
    uploads = sum(1 for method, path in fake.log if method == "POST")
    with pytest.raises(AlreadyExistsError):
        store.put_new("a/b.json", b"second")
    assert sum(1 for method, path in fake.log if method == "POST") == uploads


def test_sigv4_canonical_query_is_sorted_and_encoded():
    assert sigv4.canonical_query("prefix=J&max-keys=2") == "max-keys=2&prefix=J"
    assert sigv4.canonical_query("prefix=games/g/&continuation-token=a+b") == (
        "continuation-token=a%20b&prefix=games%2Fg%2F"
    )


def test_drive_readers_and_retention_agree_on_duplicates(drive):
    fake, store = drive
    for created, data in ((5, b"later"), (2, b"earliest")):
        file_id = str(100 + created)
        fake.meta[file_id] = {"name": "k/x.json", "created": created}
        fake.files[file_id] = data
    assert store.get("k/x.json") == b"earliest"
    assert [o.key for o in store.list("k/")] == ["k/x.json"]
    store.delete("k/x.json")
    assert fake.names() == []


def test_drive_refuses_a_redirected_download(drive):
    fake, store = drive
    store.put_new("a/b.json", b"{}")
    fake.redirect_downloads = True
    with pytest.raises(StoreError):
        store.get("a/b.json")


def test_drive_upload_reports_the_verified_hash(drive):
    _, store = drive
    info = store.put_new("a/b.bin", b"data")
    assert info.sha256 == hashlib.sha256(b"data").hexdigest()


# Transport and parsing safety


def test_endpoint_transport_is_https_only_and_single_host():
    with pytest.raises(net.DisallowedHost):
        net.endpoint_transport("http://dav.example.test/remote.php/dav/")
    transport = net.endpoint_transport("https://dav.example.test/remote.php/dav/")
    with pytest.raises(net.DisallowedHost):
        transport("GET", "https://other.example.test/x")


def test_google_transport_only_reaches_google_hosts():
    with pytest.raises(net.DisallowedHost):
        net.google_request("GET", "https://graph.microsoft.com/v1.0/me")


def test_xml_with_a_dtd_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    with pytest.raises(StoreError, match="document type"):
        parse_xml(bomb, "WebDAV server")
    with pytest.raises(StoreError, match="unreadable"):
        parse_xml(b"<not closed", "WebDAV server")
