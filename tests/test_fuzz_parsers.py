"""Parser fuzzing (v2 slice 25): every parser of outside input either returns or raises its own error.

Deterministic: fixed seeds, so a failure reproduces. Each case mutates
synthetic valid inputs (bit flips, byte and token insertions, truncation,
splicing) and checks the parser's contract. Round-trip properties check that
generated valid inputs parse back to what was written. Iterations default to a
quick run; set ``KEEPSAKE_FUZZ_ITERATIONS`` for a longer one.
"""

import os
import random
import struct

import pytest

from keepsake import manifest, registry, update, vdf, yamlsubset

ITERATIONS = int(os.environ.get("KEEPSAKE_FUZZ_ITERATIONS", "1500"))


def mutate_bytes(rng, data, specials):
    data = bytearray(data)
    for _ in range(rng.randint(1, 4)):
        op = rng.randrange(5)
        pos = rng.randrange(len(data) + 1)
        if op == 0 and data:
            data[min(pos, len(data) - 1)] ^= 1 << rng.randrange(8)
        elif op == 1:
            data[pos:pos] = bytes([rng.randrange(256)])
        elif op == 2:
            data[pos:pos] = rng.choice(specials)
        elif op == 3:
            del data[pos : pos + rng.randint(1, 8)]
        else:
            data = data[:pos]
    return bytes(data)


def mutate_text(rng, text, specials):
    out = list(text)
    for _ in range(rng.randint(1, 4)):
        op = rng.randrange(4)
        pos = rng.randrange(len(out) + 1)
        if op == 0:
            out[pos:pos] = list(rng.choice(specials))
        elif op == 1:
            del out[pos : pos + rng.randint(1, 6)]
        elif op == 2:
            out[pos:pos] = [chr(rng.choice([0, 9, 10, 13, 32, 34, 92, 0xFEFF, 0x1F600, rng.randrange(0x20, 0x7F)]))]
        else:
            out = out[:pos]
    return "".join(out)


# Binary VDF (shortcuts.vdf)


def encode_binary(tree):
    out = bytearray()
    for key, value in tree.items():
        k = key.encode() + b"\x00"
        if isinstance(value, dict):
            out += b"\x00" + k + encode_binary(value) + b"\x08"
        elif isinstance(value, str):
            out += b"\x01" + k + value.encode() + b"\x00"
        else:
            out += b"\x02" + k + struct.pack("<i", value)
    return bytes(out)


def random_tree(rng, depth=0, text=False):
    tree = {}
    for i in range(rng.randint(0, 5)):
        key = rng.choice(["appname", "exe", "StartDir", "LaunchOptions", "tags", "k"]) + str(i)
        roll = rng.random()
        if roll < 0.25 and depth < 4:
            tree[key] = random_tree(rng, depth + 1, text)
        elif roll < 0.6 or text:
            tree[key] = "".join(rng.choice('ab "\\/{}C:é') for _ in range(rng.randint(0, 12)))
        else:
            tree[key] = rng.randint(-(2**31), 2**31 - 1)
    return tree


SHORTCUT = (
    encode_binary(
        {
            "shortcuts": {
                "0": {"appid": -123456789, "AppName": "Example Quest", "Exe": '"/g/game.exe"', "tags": {"0": "x"}}
            }
        }
    )
    + b"\x08\x08"
)


def test_binary_vdf_fuzz():
    rng = random.Random(2201)
    specials = [b"\x00", b"\x08", b"\x0b", b"\x05", b"\x07", b"\x0a", b"\x00" * 40, b"\x00\x00\x00" * 12]
    for _ in range(ITERATIONS):
        data = mutate_bytes(rng, SHORTCUT, specials)
        try:
            assert isinstance(vdf.loads_binary(data), dict)
        except vdf.VdfError:
            pass


def test_binary_vdf_deep_nesting_is_refused():
    deep = b"".join(b"\x00k\x00" for _ in range(5000))
    with pytest.raises(vdf.VdfError):
        vdf.loads_binary(deep)


def test_binary_vdf_round_trip():
    rng = random.Random(2202)
    for _ in range(300):
        tree = random_tree(rng)
        assert vdf.loads_binary(encode_binary(tree) + b"\x08") == tree


# Text VDF (libraryfolders.vdf, appmanifest_*.acf, config.vdf)


def encode_text(tree, indent=0):
    pad = "\t" * indent
    lines = []
    for key, value in tree.items():
        quoted = '"' + key.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(value, dict):
            lines.append(f"{pad}{quoted}\n{pad}{{\n{encode_text(value, indent + 1)}{pad}}}\n")
        else:
            lines.append(
                f'{pad}{quoted}\t\t"{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"\n'
            )
    return "".join(lines)


LIBRARY = encode_text({"libraryfolders": {"0": {"path": "/home/deck/.local/share/Steam", "apps": {"3000000001": "1"}}}})


def test_text_vdf_fuzz():
    rng = random.Random(2203)
    specials = ["{", "}", '"', "\\", "//", "[$WIN32]", "[", "\n", '"\\', "{" * 40, "}" * 3]
    for _ in range(ITERATIONS):
        text = mutate_text(rng, LIBRARY, specials)
        try:
            assert isinstance(vdf.loads_text(text), dict)
        except vdf.VdfError:
            pass


def test_text_vdf_deep_nesting_is_refused():
    with pytest.raises(vdf.VdfError):
        vdf.loads_text('"k" {' * 5000)


def test_text_vdf_round_trip():
    rng = random.Random(2204)
    for _ in range(300):
        tree = random_tree(rng, text=True)
        assert vdf.loads_text(encode_text(tree)) == tree


# Ludusavi manifest (YAML subset) and the compact index

MANIFEST = """\
Example Quest:
  files:
    <winAppData>/ExampleQuest:
      tags:
        - save
      when:
        - os: windows
          store: steam
  installDir:
    ExampleQuest: {}
  launch:
    <base>/ExampleQuest.exe:
      - when:
          - os: windows
  steam:
    id: 3000000001
  id:
    steamExtra:
      - 3000000002
  cloud:
    steam: true
Other Game:
  alias: Example Quest
"""


def test_manifest_fuzz():
    rng = random.Random(2205)
    specials = [
        ":",
        ": ",
        "- ",
        "-",
        '"',
        "'",
        "\\x4",
        "\\u12",
        "{}",
        "[]",
        "[a]",
        "{a: b}",
        "&a",
        "*a",
        "|",
        "\t",
        "\n  ",
        "\n    - ",
        " #",
        "---\n",
        "\n",
        "  " * 40 + "- x\n",
    ]
    for _ in range(ITERATIONS):
        text = mutate_text(rng, MANIFEST, specials)
        for _title, entry in yamlsubset.iter_entries(text.splitlines(keepends=True)):
            assert not isinstance(entry, Exception) or isinstance(entry, yamlsubset.YamlSubsetError)
        index = manifest.build_index(text.splitlines(keepends=True))
        assert index["entries"] >= len(index["games"])


def test_manifest_index_survives_odd_but_valid_yaml():
    odd = "Odd Game:\n  files:\n    <base>/x:\n      tags:\n        - - save\n        - k: v\n  steam: 5\n"
    index = manifest.build_index(odd.splitlines(keepends=True))
    assert "Odd Game" not in index["games"] and index["skipped"] == 0  # no save paths, nothing guessed


def test_manifest_deep_nesting_is_an_entry_error():
    deep = "Deep:\n" + "".join("  " * (i + 1) + f"k{i}:\n" for i in range(200)) + "  " * 201 + "v: 1\n"
    entries = list(yamlsubset.iter_entries(deep.splitlines(keepends=True)))
    assert entries[0][0] == "Deep" and isinstance(entries[0][1], yamlsubset.YamlSubsetError)


# Wine registry files

USER_REG = """WINE REGISTRY Version 2
;; All keys relative to \\\\User\\\\S-1-5-21-0-0-0-1000

#arch=win64

[Software\\\\Example\\\\Quest] 1700000000
#time=1d9a0b0c0d0e0f0
"Volume"=dword:00000050
"Name"="Player \\"One\\""
"Blob"=hex:01,02,03,\\
  04,05

[Software\\\\Other] 1700000001
@="default"
"""


def test_registry_fuzz():
    rng = random.Random(2206)
    specials = ["[", "]", "\\", '"', "=", "\n", "\\\n", "\r\n", "hex:", "dword:", "#", ";;", "[Software\\\\X] 1\n"]
    managed = ["Software\\Example\\Quest"]
    for _ in range(ITERATIONS):
        text = mutate_text(rng, USER_REG, specials)
        try:
            registry.parse(text)
        except registry.RegistryError:
            continue
        try:
            fragment = registry.export(text, managed)
            merged = registry.merge(text, fragment, managed, 1_800_000_000)
            registry.verify_merge(text, merged, fragment, managed)
        except registry.RegistryError:
            pass


# Update metadata (from GitHub, untrusted until verified)


def test_update_parsers_fuzz():
    rng = random.Random(2207)
    sums = "0" * 64 + "  Keepsake-v1.2.3.zip\n" + "f" * 64 + " *Keepsake.zip\n"
    specials = [" ", "*", "\n", "\x00", "v", ".", "-rc.1", "+", "=", "==", "RW"]
    for _ in range(ITERATIONS):
        for parser, seed, errors in (
            (update.parse_sums, sums, (ValueError,)),
            (update.parse_version, "v1.2.3-rc.1", (ValueError,)),
        ):
            try:
                parser(mutate_text(rng, seed, specials))
            except errors:
                pass
    for payload in (None, 5, "x", [None], [{"tag_name": 5}], [{"tag_name": "v1.0.0", "assets": "x"}], {"a": 1}):
        try:
            update.parse_releases(payload)
        except ValueError:
            pass


def test_manifest_steam_ids_are_positive_integers_never_booleans():
    text = (
        "True Game:\n  files:\n    <base>/s:\n      tags:\n        - save\n  steam:\n    id: true\n"
        "  id:\n    steamExtra:\n      - false\n      - 3000000009\n      - -4\n"
    )
    record = manifest.build_index(text.splitlines(keepends=True))["games"]["True Game"]
    assert "s" not in record and record["se"] == [3000000009]
