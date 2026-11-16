"""Signature fuzzing (v2 slice 25): a corrupted key or signature file never verifies, and never crashes.

Release signatures and keys are untrusted input until verified (T10). For any
mutation, ``minisign.verify`` either raises :class:`minisign.MinisignError` or,
if it still verifies, the mutation touched only the untrusted comment, which
minisign does not sign. ``ed25519.verify`` on arbitrary bytes returns a bool.
Deterministic seeds; Ed25519 in pure Python is slow, so the default run is short
(``KEEPSAKE_FUZZ_ITERATIONS`` scales it).
"""

import os
import random

from keepsake import ed25519, minisign
from test_signatures import SUMS, public_text, signature_text

ITERATIONS = max(50, int(os.environ.get("KEEPSAKE_FUZZ_ITERATIONS", "1500")) // 5)


def signed_lines(text):
    """The lines minisign signs or checks: everything except the untrusted comment."""
    lines = text.strip().splitlines()
    return [line.strip() for line in lines[1:]] if len(lines) == 4 else None


def mutate(rng, text):
    out = list(text)
    for _ in range(rng.randint(1, 3)):
        pos = rng.randrange(len(out) + 1)
        op = rng.randrange(4)
        if op == 0 and out:
            i = min(pos, len(out) - 1)
            out[i] = chr(ord(out[i]) ^ (1 << rng.randrange(7)))
        elif op == 1:
            out[pos:pos] = list(rng.choice(["\n", "=", "A", "/", "+", " ", "trusted comment: ", "\x00", "é"]))
        elif op == 2:
            del out[pos : pos + rng.randint(1, 5)]
        else:
            out = out[:pos]
    return "".join(out)


def test_minisign_signature_fuzz_never_accepts_a_signed_change():
    rng = random.Random(2501)
    key = public_text()
    good = signature_text(SUMS)
    for _ in range(ITERATIONS):
        text = mutate(rng, good)
        try:
            minisign.verify(key, text, SUMS)
        except minisign.MinisignError:
            continue
        assert signed_lines(text) == signed_lines(good), "a changed signature verified"


def test_minisign_public_key_fuzz():
    rng = random.Random(2502)
    good = public_text()
    for _ in range(ITERATIONS * 4):
        text = mutate(rng, good)
        try:
            key_id, key = minisign.parse_public_key(text)
        except minisign.MinisignError:
            continue
        assert len(key_id) == 8 and len(key) == 32


def test_ed25519_verify_on_arbitrary_bytes_returns_a_bool():
    rng = random.Random(2503)
    public = ed25519.public_key(bytes(range(32)))
    signature = ed25519.sign(bytes(range(32)), SUMS)
    for _ in range(ITERATIONS):
        key = bytes(rng.randrange(256) for _ in range(rng.choice([31, 32, 32, 33])))
        sig = bytearray(signature)
        sig[rng.randrange(64)] ^= 1 << rng.randrange(8)
        for k, s in ((key, signature), (public, bytes(sig)), (key, bytes(rng.randrange(256) for _ in range(64)))):
            assert ed25519.verify(k, SUMS, s) in (True, False)
            assert not ed25519.verify(k, SUMS, s) or (k == public and s == signature)
    # Points that are not on the curve, the all-ones encoding and a small-order point.
    for bad in (b"\xff" * 32, b"\x00" * 32, (1).to_bytes(32, "little"), (2**255 - 20).to_bytes(32, "little")):
        assert ed25519.verify(bad, SUMS, signature) is False
        assert ed25519.verify(public, SUMS, bad + signature[32:]) is False
