"""The in-plugin verifier against a signature made by the real minisign tool (A123, ADR-0036).

The fixture is minisign's own signed source release (ISC licence), checked with
``minisign -V`` before it was committed. It is data only and never unpacked.
"""

import pathlib

import pytest

from keepsake import minisign

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "minisign"
DATA = (FIXTURE / "minisign-0.12.tar.gz").read_bytes()
SIGNATURE = (FIXTURE / "minisign-0.12.tar.gz.minisig").read_text(encoding="utf-8")
# Published in minisign's README for verifying its releases.
MINISIGN_PUBLIC_KEY = "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3"
OTHER_KEY = "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO4"


def test_a_real_minisign_signature_is_accepted():
    comment = minisign.verify(MINISIGN_PUBLIC_KEY, SIGNATURE, DATA)
    assert comment == "timestamp:1736977639\tfile:minisign-0.12.tar.gz\thashed"


def test_one_changed_byte_is_refused():
    changed = bytearray(DATA)
    changed[len(changed) // 2] ^= 1
    with pytest.raises(minisign.MinisignError):
        minisign.verify(MINISIGN_PUBLIC_KEY, SIGNATURE, bytes(changed))


def test_a_changed_signature_or_trusted_comment_is_refused():
    lines = SIGNATURE.splitlines()
    sig = lines[1]
    flipped = sig[:-6] + ("A" if sig[-6] != "A" else "B") + sig[-5:]
    with pytest.raises(minisign.MinisignError):
        minisign.verify(MINISIGN_PUBLIC_KEY, "\n".join([lines[0], flipped, *lines[2:]]), DATA)
    with pytest.raises(minisign.MinisignError):  # the global signature covers the trusted comment
        minisign.verify(MINISIGN_PUBLIC_KEY, "\n".join([*lines[:2], lines[2] + "x", lines[3]]), DATA)


@pytest.mark.parametrize("signature", ["", "untrusted comment: x\n", "garbage\n" * 4])
def test_a_missing_or_broken_signature_is_refused(signature):
    with pytest.raises(minisign.MinisignError):
        minisign.verify(MINISIGN_PUBLIC_KEY, signature, DATA)


def test_another_key_is_refused():
    with pytest.raises(minisign.MinisignError):
        minisign.verify(OTHER_KEY, SIGNATURE, DATA)
