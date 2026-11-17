"""The vendored libraries are exactly what scripts/vendor.py wrote (ADR-0034)."""

import hashlib
import json
import pathlib

VENDOR = pathlib.Path(__file__).resolve().parent.parent / "py_modules" / "keepsake" / "_vendor"
MANIFEST = json.loads((VENDOR / "MANIFEST.json").read_text(encoding="utf-8"))
OWN = {"__init__.py", "MANIFEST.json"}


def test_every_vendored_file_matches_the_manifest_and_nothing_was_added():
    on_disk = {
        p.relative_to(VENDOR).as_posix()
        for p in VENDOR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.relative_to(VENDOR).as_posix() not in OWN
    }
    assert on_disk == set(MANIFEST["files"])
    changed = [
        rel for rel, sha in MANIFEST["files"].items() if hashlib.sha256((VENDOR / rel).read_bytes()).hexdigest() != sha
    ]
    assert changed == []


def test_pins_licences_and_patches():
    libraries = {lib["name"]: lib for lib in MANIFEST["libraries"]}
    assert {n: lib["version"] for n, lib in libraries.items()} == {"pysmb": "1.2.15", "pyasn1": "0.6.5"}
    assert {n: lib["licence"] for n, lib in libraries.items()} == {"pysmb": "zlib/libpng", "pyasn1": "BSD-2-Clause"}
    assert all(
        len(lib["sha256"]) == 64 and lib["url"].startswith("https://files.pythonhosted.org/")
        for lib in libraries.values()
    )
    assert sorted(p.name for p in (VENDOR / "LICENSES").iterdir()) == ["pyasn1-LICENSE.rst", "pysmb-LICENSE"]
    for rel in libraries["pysmb"]["patched"]:
        text = (VENDOR / rel).read_text(encoding="utf-8")
        assert "from tqdm import" not in text and "Keepsake patch (ADR-0034)" in text


def test_no_vendored_file_needs_something_that_is_not_shipped():
    banned = ("import tqdm", "from tqdm", "import twisted", "from twisted", "import cryptography", "from cryptography")
    offenders = [
        rel
        for rel in MANIFEST["files"]
        if rel.endswith(".py") and any(b in (VENDOR / rel).read_text(encoding="utf-8") for b in banned)
    ]
    assert offenders == []
    assert not [p for p in VENDOR.rglob("*") if p.suffix in (".so", ".pyd", ".dll", ".exe")]  # pure Python only (P9)
