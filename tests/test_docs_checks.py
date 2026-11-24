"""The user guide checks and the screenshot harness (ADR-0046)."""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import check_docs


def png(chunks=()):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    body = b"".join(chunk(kind, data) for kind, data in chunks)
    return b"\x89PNG\r\n\x1a\n" + header + body + chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")


def make_docs(root, page, images=()):
    user = root / "docs" / "user"
    (user / "images").mkdir(parents=True)
    (root / "README.md").write_text("[guide](docs/user/README.md)\n", encoding="utf-8")
    (user / "README.md").write_text(page, encoding="utf-8")
    for name, data in images:
        (user / "images" / name).write_bytes(data)
    return root


def test_the_real_guide_is_clean():
    assert check_docs.check() == []


def test_missing_links_and_images_are_found(tmp_path):
    root = make_docs(tmp_path, "[a](missing.md) ![b](images/gone.png) [web](https://example.com) [here](#top)\n")
    problems = check_docs.check(str(root))
    assert problems == ["docs/user/README.md: missing missing.md", "docs/user/README.md: missing images/gone.png"]


def test_unused_screenshots_and_png_text_are_found(tmp_path):
    root = make_docs(
        tmp_path,
        "![shot](images/used.png)\n",
        [("used.png", png([(b"tEXt", b"Comment\x00C:/somewhere")])), ("stale.png", png())],
    )
    assert check_docs.check(str(root)) == [
        "docs/user/images/stale.png: not used by any page",
        "docs/user/images/used.png: tEXt",
    ]
    assert check_docs.png_text_chunks(b"GIF89a") == ["not a PNG"]
    assert check_docs.png_text_chunks(png()) == []


def test_mermaid_blocks_must_name_a_diagram(tmp_path):
    root = make_docs(tmp_path, "```mermaid\nflowchart LR\n  A --> B\n```\n\n```mermaid\nnonsense\n```\n")
    assert check_docs.check(str(root)) == ["docs/user/README.md: unknown Mermaid diagram 'nonsense'"]


def test_sample_data_must_use_synthetic_app_ids():
    assert check_docs.sample_problems('"steam:1999999104" "shortcut:7:3000000101"') == []
    assert check_docs.sample_problems('"steam:440" "shortcut:7:12345"') == [
        "sample data: steam:440 is not a synthetic app ID",
        "sample data: shortcut:7:12345 is not a synthetic app ID",
    ]
