"""Verify minisign signatures over a release's ``SHA256SUMS`` (build prompt section 12, threat model T10).

A minisign public key is a base64 line holding ``Ed``, an 8-byte key ID and the
32-byte Ed25519 key. A signature file has four lines: an untrusted comment,
base64 of the algorithm (``Ed`` signs the file, ``ED`` signs its BLAKE2b-512
hash, minisign's default), the key ID and the 64-byte signature, then a trusted
comment and a global signature over the signature and the trusted comment.
Both signatures must verify with the pinned key.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from . import ed25519

MAX_SIGNATURE_BYTES = 4096


class MinisignError(ValueError):
    pass


def _b64(text: str, size: int, what: str) -> bytes:
    try:
        data = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MinisignError(f"{what} is not valid base64") from exc
    if len(data) != size:
        raise MinisignError(f"{what} has the wrong length")
    return data


def parse_public_key(text: str) -> tuple[bytes, bytes]:
    """``(key_id, key)`` from a minisign public key (with or without its comment line)."""
    lines = [line for line in text.strip().splitlines() if line.strip() and not line.startswith("untrusted comment:")]
    if len(lines) != 1:
        raise MinisignError("the public key must be one base64 line")
    data = _b64(lines[0], 42, "the public key")
    if data[:2] != b"Ed":
        raise MinisignError("not an Ed25519 minisign public key")
    return data[2:10], data[10:]


def verify(public_key_text: str, signature_text: str, data: bytes) -> str:
    """Return the trusted comment if ``signature_text`` is a valid signature of ``data``; raise otherwise."""
    if len(signature_text) > MAX_SIGNATURE_BYTES:
        raise MinisignError("the signature file is too large")
    key_id, key = parse_public_key(public_key_text)
    lines = signature_text.strip().splitlines()
    if len(lines) != 4 or not lines[0].startswith("untrusted comment:") or not lines[2].startswith("trusted comment: "):
        raise MinisignError("the signature file is not in minisign format")
    blob = _b64(lines[1], 74, "the signature")
    algorithm, sig_key_id, signature = blob[:2], blob[2:10], blob[10:]
    if sig_key_id != key_id:
        raise MinisignError("the release was signed with a different key")
    if algorithm == b"ED":
        message = hashlib.blake2b(data, digest_size=64).digest()
    elif algorithm == b"Ed":
        message = data
    else:
        raise MinisignError("unknown signature algorithm")
    if not ed25519.verify(key, message, signature):
        raise MinisignError("the signature does not match")
    trusted = lines[2][len("trusted comment: ") :]
    global_signature = _b64(lines[3], 64, "the global signature")
    if not ed25519.verify(key, signature + trusted.encode("utf-8"), global_signature):
        raise MinisignError("the trusted comment has been changed")
    return trusted
