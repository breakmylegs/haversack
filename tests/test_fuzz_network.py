"""Fuzzing the network install parsers (ADR-0033): hostile listing pages and addresses never escape or crash."""

import random
from urllib.parse import urlsplit

import pytest

from keepsake.installer import remote

BASE = "https://nas.example/games/"
PIECES = [
    '<a href="',
    "'",
    '"',
    ">",
    "</a>",
    "../",
    "./",
    "/",
    "//evil.example/",
    "http://nas.example/",
    "https://nas.example/",
    "games/",
    "Sub/",
    "a.iso",
    "A.ISO",
    "%2F",
    "%2e%2e/",
    "?x=1",
    "#f",
    "&amp;",
    "javascript:",
    "mailto:",
    "\x00",
    "\n",
    " ",
    "x" * 300,
    "é",
    "%00",
    "\\",
    "<a  HREF=",
    "b.iso/",
    "%20",
    ":",
    "*",
]


@pytest.mark.parametrize("seed", range(300))
def test_listing_entries_stay_one_level_under_the_folder(seed):
    rng = random.Random(seed)
    page = "".join(rng.choice(PIECES) for _ in range(rng.randint(0, 80)))
    for entry in remote.parse_listing(page, BASE):
        parts = urlsplit(entry["url"])
        assert (parts.scheme, parts.netloc) == ("https", "nas.example")
        assert parts.path.startswith("/games/") and not parts.query and not parts.fragment
        rest = parts.path[len("/games/") :].rstrip("/")
        assert rest and "/" not in rest
        assert entry["kind"] in ("folder", "iso") and "/" not in entry["name"] and "\x00" not in entry["name"]
        assert entry["name"] not in (".", "..")
        if entry["kind"] == "iso":
            assert remote.file_name(entry["url"]) == entry["name"]


@pytest.mark.parametrize("seed", range(300))
def test_addresses_are_accepted_only_when_clean(seed):
    rng = random.Random(seed)
    text = "".join(
        rng.choice(
            [
                "https://",
                "http://",
                "ftp://",
                "nas",
                ".example",
                ":",
                "@",
                "/",
                "?",
                "#",
                "\x01",
                "%",
                "99999",
                "80",
                "[::1]",
                " ",
            ]
        )
        for _ in range(rng.randint(0, 12))
    )
    try:
        url = remote.check_location(text)
    except remote.RemoteError:
        return
    parts = urlsplit(url)
    assert parts.scheme in ("http", "https") and parts.hostname
    assert not parts.username and not parts.password and not parts.query and not parts.fragment


def test_a_huge_listing_is_capped():
    page = "".join(f'<a href="d{i}.iso">x</a>' for i in range(remote.LISTING_ENTRIES + 500))
    assert len(remote.parse_listing(page, BASE)) == remote.LISTING_ENTRIES
