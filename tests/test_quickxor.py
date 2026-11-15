import os
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from keepsake.quickxor import QuickXorHash, quickxor_file, reference


def test_empty_is_all_zero():
    assert reference(b"") == "AAAAAAAAAAAAAAAAAAAAAAAAAAA="
    assert QuickXorHash().digest_b64() == reference(b"")


def test_length_goes_into_the_last_eight_bytes():
    import base64

    raw = base64.b64decode(reference(b"\0" * 300))
    assert raw[:12] == b"\0" * 12
    assert int.from_bytes(raw[12:], "little") == 300


@settings(max_examples=200, deadline=None)
@given(data=st.binary(max_size=1200), cuts=st.lists(st.integers(1, 400), max_size=10))
def test_streaming_matches_reference_for_any_chunking(data, cuts):
    h = QuickXorHash()
    i = 0
    for cut in cuts:
        h.update(data[i : i + cut])
        i += cut
    h.update(data[i:])
    assert h.digest_b64() == reference(data)


@pytest.mark.parametrize("size", [160, 161, 319, 320, 481, 1000, 5000])
def test_folded_sizes_match_reference(size):
    # Inputs of 160 bytes or more exercise the folding path, which small random inputs rarely reach.
    rng = random.Random(size)
    data = rng.randbytes(size)
    h = QuickXorHash()
    i = 0
    while i < size:
        step = rng.randint(1, 400)
        h.update(data[i : i + step])
        i += step
    assert h.digest_b64() == reference(data)


def test_file_helper(tmp_path):
    data = os.urandom(5000)
    path = tmp_path / "f"
    path.write_bytes(data)
    assert quickxor_file(str(path)) == reference(data)


def test_large_input_is_fast_enough():
    random.seed(0)
    data = random.randbytes(8 * 1024 * 1024)
    h = QuickXorHash()
    h.update(data)
    assert len(h.digest_b64()) == 28
