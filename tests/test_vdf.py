import struct

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpers import dumps_binary_vdf, shortcut_entry
from keepsake.vdf import VdfError, loads_binary, loads_text


def test_binary_round_trip_shortcuts():
    data = {"shortcuts": {"0": shortcut_entry(-123456789, "Example Game", "/games/example.exe")}}
    parsed = loads_binary(dumps_binary_vdf(data))
    entry = parsed["shortcuts"]["0"]
    assert entry["appid"] == -123456789
    assert entry["AppName"] == "Example Game"
    assert entry["tags"] == {}


def test_binary_uint64_and_float():
    raw = b"\x07big\x00" + struct.pack("<Q", 2**40) + b"\x03f\x00" + struct.pack("<f", 1.5) + b"\x08"
    parsed = loads_binary(raw)
    assert parsed == {"big": 2**40, "f": 1.5}


@pytest.mark.parametrize(
    "raw",
    [
        b"\x01key",  # unterminated key
        b"\x02key\x00\x01",  # truncated int
        b"\x00a\x00\x01b\x00c\x00",  # missing end of nested map
        b"\x09key\x00",  # unknown type
        b"\x08junk",  # trailing data
    ],
)
def test_binary_malformed(raw):
    with pytest.raises(VdfError):
        loads_binary(raw)


def test_binary_depth_limit():
    raw = b"".join(b"\x00k\x00" for _ in range(40)) + b"\x08" * 41
    with pytest.raises(VdfError):
        loads_binary(raw)


ALPHABET = "abcXYZ019 _-./:é漢"
keys = st.text(alphabet=ALPHABET, min_size=1, max_size=8)
leaves = st.one_of(
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.text(alphabet=ALPHABET, max_size=12),
)
trees = st.recursive(leaves, lambda children: st.dictionaries(keys, children, max_size=3), max_leaves=6)


@settings(suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large], deadline=None)
@given(st.dictionaries(keys, trees, max_size=3))
def test_binary_property_round_trip(tree):
    assert loads_binary(dumps_binary_vdf(tree)) == tree


@given(st.binary(max_size=200))
def test_binary_never_crashes_unexpectedly(raw):
    try:
        loads_binary(raw)
    except VdfError:
        pass


LIBRARYFOLDERS = r"""
"libraryfolders"
{
    // comment
    "0"
    {
        "path"      "/home/deck/.local/share/Steam"
        "label"     ""
        "apps"
        {
            "228980"        "123"
        }
    }
    "1"
    {
        "path"      "/run/media/card\"x"
    }
}
"""


def test_text_libraryfolders():
    parsed = loads_text(LIBRARYFOLDERS)
    folders = parsed["libraryfolders"]
    assert folders["0"]["path"] == "/home/deck/.local/share/Steam"
    assert folders["0"]["apps"]["228980"] == "123"
    assert folders["1"]["path"] == '/run/media/card"x'


def test_text_unquoted_and_conditionals():
    parsed = loads_text('AppState { appid 10 name "Game" [$WIN32] }')
    assert parsed == {"AppState": {"appid": "10", "name": "Game"}}


@pytest.mark.parametrize("text", ['"a" {', '"a" }', '"a"', '"a" "b" }', '"unterminated'])
def test_text_malformed(text):
    with pytest.raises(VdfError):
        loads_text(text)
