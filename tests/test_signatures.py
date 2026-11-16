"""Release signatures (slice 12, threat model T10): Ed25519, minisign and the updater's check."""

import base64
import hashlib
import json

import pytest

from keepsake import ed25519, minisign
from keepsake.net import HttpResponse
from keepsake.update import RELEASES_URL, Updater

# RFC 8032 section 7.1, tests 1 and 2.
RFC_VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
]


@pytest.mark.parametrize(("secret", "public", "message", "signature"), RFC_VECTORS)
def test_rfc8032_vectors(secret, public, message, signature):
    secret, public, message, signature = map(bytes.fromhex, (secret, public, message, signature))
    assert ed25519.public_key(secret) == public
    assert ed25519.sign(secret, message) == signature
    assert ed25519.verify(public, message, signature)


def test_ed25519_rejects_tampering():
    _secret, public, _, signature = map(bytes.fromhex, RFC_VECTORS[1])
    message = bytes.fromhex("72")
    assert not ed25519.verify(public, b"\x73", signature)
    assert not ed25519.verify(public, message, signature[:-1] + bytes([signature[-1] ^ 1]))
    assert not ed25519.verify(bytes.fromhex(RFC_VECTORS[0][1]), message, signature)
    # s + L also satisfies the equation (L*B is the identity); RFC 8032 requires rejecting s >= L.
    s = int.from_bytes(signature[32:], "little")
    assert not ed25519.verify(public, message, signature[:32] + (s + ed25519.L).to_bytes(32, "little"))
    assert not ed25519.verify(public[:31], message, signature)


SEED = bytes(range(32))
KEY_ID = bytes.fromhex("0102030405060708")


def b64(data):
    return base64.b64encode(data).decode()


def public_text(seed=SEED, key_id=KEY_ID):
    return f"untrusted comment: minisign public key {key_id.hex()}\n{b64(b'Ed' + key_id + ed25519.public_key(seed))}\n"


def signature_text(data, seed=SEED, key_id=KEY_ID, prehash=True, trusted="timestamp:1700000000\tfile:SHA256SUMS"):
    message = hashlib.blake2b(data, digest_size=64).digest() if prehash else data
    sig = ed25519.sign(seed, message)
    blob = (b"ED" if prehash else b"Ed") + key_id + sig
    global_sig = ed25519.sign(seed, sig + trusted.encode())
    return (
        f"untrusted comment: signature from minisign secret key\n{b64(blob)}\n"
        f"trusted comment: {trusted}\n{b64(global_sig)}\n"
    )


SUMS = b"ab" * 32 + b"  Keepsake-v1.0.0.zip\n"


@pytest.mark.parametrize("prehash", [True, False])
def test_minisign_verifies_both_algorithms(prehash):
    assert minisign.verify(public_text(), signature_text(SUMS, prehash=prehash), SUMS).startswith("timestamp:")


def test_minisign_refuses_changed_data_key_or_comment():
    good = signature_text(SUMS)
    with pytest.raises(minisign.MinisignError, match="does not match"):
        minisign.verify(public_text(), good, SUMS + b"evil  Keepsake-v9.zip\n")
    with pytest.raises(minisign.MinisignError, match="different key"):
        minisign.verify(public_text(key_id=b"\x09" * 8), good, SUMS)
    other_seed = bytes(range(1, 33))
    with pytest.raises(minisign.MinisignError, match="does not match"):
        minisign.verify(public_text(seed=other_seed), good, SUMS)
    lines = good.splitlines()
    lines[2] = "trusted comment: timestamp:1\tfile:other"
    with pytest.raises(minisign.MinisignError, match="trusted comment"):
        minisign.verify(public_text(), "\n".join(lines), SUMS)
    with pytest.raises(minisign.MinisignError, match="format"):
        minisign.verify(public_text(), "not a signature", SUMS)
    with pytest.raises(minisign.MinisignError):
        minisign.parse_public_key("untrusted comment: x\nnot base64!!\n")


# The updater


def release_payload(signed=True):
    assets = [
        {"name": "Keepsake-v1.0.0.zip", "browser_download_url": "https://github.com/r/v1.0.0/zip"},
        {"name": "SHA256SUMS", "browser_download_url": "https://github.com/r/v1.0.0/sums"},
    ]
    if signed:
        assets.append({"name": "SHA256SUMS.minisig", "browser_download_url": "https://github.com/r/v1.0.0/sig"})
    return [{"tag_name": "v1.0.0", "draft": False, "prerelease": False, "body": "", "assets": assets}]


def fetcher(payload, sig_text):
    def fetch(url, headers=None):
        if url == RELEASES_URL:
            return HttpResponse(status=200, body=json.dumps(payload).encode())
        if url.endswith("/sums"):
            return HttpResponse(status=200, body=SUMS)
        if url.endswith("/sig"):
            return HttpResponse(status=200, body=sig_text.encode())
        return HttpResponse(status=404)

    return fetch


def prepared(tmp_path, payload, sig_text, key):
    updater = Updater(str(tmp_path), "0.11.0", fetcher(payload, sig_text), public_key=key)
    updater.check("stable")
    return updater.prepare("v1.0.0", busy_reason=None)


def test_without_a_pinned_key_updates_are_unsigned_but_allowed(tmp_path):
    result = prepared(tmp_path, release_payload(signed=False), "", "")
    assert result["ok"] is True and result["signed"] is False and result["sha256"] == "ab" * 32


def test_with_a_pinned_key_a_valid_signature_is_required(tmp_path):
    ok = prepared(tmp_path / "a", release_payload(), signature_text(SUMS), public_text())
    assert ok["ok"] is True and ok["signed"] is True
    unsigned = prepared(tmp_path / "b", release_payload(signed=False), "", public_text())
    assert unsigned == {"ok": False, "reason": "unsigned-release"}
    forged = prepared(tmp_path / "c", release_payload(), signature_text(SUMS, seed=bytes(range(1, 33))), public_text())
    assert forged["ok"] is False and forged["reason"] == "bad-signature"
    other_file = prepared(tmp_path / "d", release_payload(), signature_text(b"other file"), public_text())
    assert other_file["reason"] == "bad-signature"
