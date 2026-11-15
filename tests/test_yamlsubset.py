import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from keepsake.yamlsubset import YamlSubsetError, iter_entries, parse_scalar, split_key


def entries(text):
    return list(iter_entries(text.splitlines(keepends=True)))


def ok(text):
    out = {}
    for key, value in entries(text):
        assert not isinstance(value, YamlSubsetError), (key, value)
        out[key] = value
    return out


MANIFEST_SAMPLE = """---
"Example Game: Deluxe":
  files:
    "<winLocalAppData>/Example/Saves":
      tags:
        - save
      when:
        - os: windows
          store: steam
        - os: linux
    <base>/settings.ini:
      tags:
        - config
  installDir:
    ExampleGame: {}
  steam:
    id: 12345
  id:
    steamExtra:
      - 1
      - 2
  notes:
    - message: "Quote \\"inside\\" and unicode \\u00e9"
Plain Key With = !Bang;:
  alias: "Example Game: Deluxe"
Empty One:
  steam:
    id: 99
"""


def test_manifest_shape():
    data = ok(MANIFEST_SAMPLE)
    game = data["Example Game: Deluxe"]
    files = game["files"]
    assert files["<winLocalAppData>/Example/Saves"] == {
        "tags": ["save"],
        "when": [{"os": "windows", "store": "steam"}, {"os": "linux"}],
    }
    assert files["<base>/settings.ini"] == {"tags": ["config"]}
    assert game["installDir"] == {"ExampleGame": {}}
    assert game["steam"] == {"id": 12345}
    assert game["id"]["steamExtra"] == [1, 2]
    assert game["notes"][0]["message"] == 'Quote "inside" and unicode \u00e9'
    assert data["Plain Key With = !Bang;"] == {"alias": "Example Game: Deluxe"}
    assert data["Empty One"] == {"steam": {"id": 99}}


@pytest.mark.parametrize(
    "bad",
    [
        "  files: &anchor\n    a: 1\n",
        "  files: *alias\n",
        "  notes: |\n    multi\n    line\n",
        "  list: [1, 2]\n",
        "  map: {a: 1}\n",
        "  tagged: !custom x\n",
        "  key: value # comment\n",
        "  a: 1\n    b: 2\n",  # unexpected indentation
        '  "unterminated: 1\n',
        '  bad: "\\q"\n',
        "  just text\n",
    ],
)
def test_unsupported_construct_fails_only_that_entry(bad):
    text = "Before:\n  steam:\n    id: 1\nBroken:\n" + bad + "After:\n  steam:\n    id: 2\n"
    result = dict(entries(text))
    assert result["Before"] == {"steam": {"id": 1}}
    assert result["After"] == {"steam": {"id": 2}}
    assert isinstance(result["Broken"], YamlSubsetError)


def test_tab_indentation_fails_entry():
    result = dict(entries("Tabbed:\n\tsteam: 1\nNext:\n  steam:\n    id: 3\n"))
    assert isinstance(result["Tabbed"], YamlSubsetError)
    assert result["Next"] == {"steam": {"id": 3}}


def test_sequence_at_same_indent_as_key():
    assert ok("G:\n  tags:\n  - save\n  - config\n  other: 1\n") == {"G": {"tags": ["save", "config"], "other": 1}}


def test_scalars():
    assert parse_scalar("12") == 12
    assert parse_scalar("-3") == -3
    assert parse_scalar("012") == "012"
    assert parse_scalar("true") is True and parse_scalar("false") is False
    assert parse_scalar("~") is None
    assert parse_scalar("'it''s'") == "it's"
    assert parse_scalar('"a\\tb"') == "a\tb"
    assert parse_scalar("<base>/x y") == "<base>/x y"


def test_split_key():
    assert split_key('"a: b": 1') == ("a: b", "1")
    assert split_key("plain: value: more") == ("plain", "value: more")
    assert split_key("trailing:") == ("trailing", "")
    assert split_key("- item") is None
    assert split_key("no colon") is None


def test_crlf_and_comments_and_blank_lines():
    text = "# comment\r\n\r\nG:\r\n  steam:\r\n    id: 5\r\n"
    assert ok(text) == {"G": {"steam": {"id": 5}}}


def test_deep_nesting_is_an_error_not_a_crash():
    depth = 60
    lines = ["G:"] + [("  " * (i + 1)) + f"k{i}:" for i in range(depth)] + [("  " * (depth + 1)) + "v: 1"]
    result = dict(entries("\n".join(lines) + "\n"))
    assert isinstance(result["G"], YamlSubsetError)


# Property: anything serde-style block YAML can express round-trips.

ALPHABET = 'abcXYZ019 _-./<>:é"\\'


def emit(value, indent):
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            k = json.dumps(key, ensure_ascii=False)
            if isinstance(item, dict) and item:
                lines.append(f"{pad}{k}:")
                lines.extend(emit(item, indent + 1))
            elif isinstance(item, list) and item:
                lines.append(f"{pad}{k}:")
                lines.extend(emit(item, indent + 1))
            else:
                lines.append(f"{pad}{k}: {scalar(item)}")
    else:
        for item in value:
            if isinstance(item, dict) and item:
                sub = emit(item, indent + 1)
                first = sub[0].lstrip(" ")
                lines.append(f"{pad}- {first}")
                lines.extend(sub[1:])
            elif isinstance(item, list) and item:
                lines.append(f"{pad}-")
                lines.extend(emit(item, indent + 1))
            else:
                lines.append(f"{pad}- {scalar(item)}")
    return lines


def scalar(value):
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, list):
        return "[]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


keys = st.text(alphabet=ALPHABET, min_size=1, max_size=8)
leaves = st.one_of(st.integers(-1000, 10**9), st.booleans(), st.text(alphabet=ALPHABET, max_size=10))
trees = st.recursive(
    leaves,
    lambda children: st.one_of(st.lists(children, max_size=3), st.dictionaries(keys, children, max_size=3)),
    max_leaves=10,
)


@settings(suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large], deadline=None)
@given(st.dictionaries(keys, st.dictionaries(keys, trees, min_size=1, max_size=3), min_size=1, max_size=3))
def test_round_trip_property(document):
    text = "\n".join(emit(document, 0)) + "\n"
    assert ok(text) == document
