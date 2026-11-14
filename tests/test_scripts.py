import hashlib
import io
import json
import os
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import check_versions
import device
import package
import secret_scan
import test_on_device


def make_repo(root, version="1.2.3", changelog=None, plugin_extra=None):
    (root / "dist").mkdir()
    (root / "dist" / "index.js").write_text("x")
    (root / "py_modules" / "keepsake" / "__pycache__").mkdir(parents=True)
    (root / "py_modules" / "keepsake" / "__init__.py").write_text("")
    (root / "py_modules" / "keepsake" / "__pycache__" / "a.pyc").write_text("")
    (root / "bin").mkdir()
    (root / "bin" / "keepsake-gate").write_text("#!/bin/sh\n")
    for name in ("main.py", "LICENSE", "README.md"):
        (root / name).write_text(name)
    (root / "package.json").write_text(json.dumps({"version": version}))
    (root / "plugin.json").write_text(json.dumps({"name": "Keepsake", **(plugin_extra or {})}))
    (root / "CHANGELOG.md").write_text(changelog if changelog is not None else f"# Changelog\n\n## [{version}]\n")


def test_package_layout_modes_and_determinism(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo)
    monkeypatch.setattr(package, "ROOT", str(repo))
    first = package.build(str(tmp_path / "out1"))
    second = package.build(str(tmp_path / "out2"))
    assert os.path.basename(first) == "Keepsake-v1.2.3.zip"
    with open(first, "rb") as a, open(second, "rb") as b:
        assert hashlib.sha256(a.read()).hexdigest() == hashlib.sha256(b.read()).hexdigest()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert "Keepsake/plugin.json" in names
        assert "Keepsake/dist/index.js" in names
        assert "Keepsake/py_modules/keepsake/__init__.py" in names
        assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
        assert all(n.startswith("Keepsake/") for n in names)
        # Decky finds the plugin by a plugin.json exactly one folder deep.
        assert [n for n in names if n.endswith("/plugin.json") and n.count("/") == 1] == ["Keepsake/plugin.json"]
        gate = archive.getinfo("Keepsake/bin/keepsake-gate")
        assert (gate.external_attr >> 16) & 0o777 == 0o755
        assert (archive.getinfo("Keepsake/main.py").external_attr >> 16) & 0o777 == 0o644


def test_package_requires_build(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo)
    os.remove(repo / "dist" / "index.js")
    monkeypatch.setattr(package, "ROOT", str(repo))
    with pytest.raises(SystemExit):
        package.build(str(tmp_path / "out"))


def test_check_versions_ok_and_failures(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REF_TYPE", raising=False)
    repo = tmp_path / "ok"
    repo.mkdir()
    make_repo(repo)
    monkeypatch.setattr(check_versions, "ROOT", str(repo))
    assert check_versions.main() == 0

    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF_NAME", "v9.9.9")
    assert check_versions.main() == 1
    monkeypatch.setenv("GITHUB_REF_NAME", "v1.2.3")
    assert check_versions.main() == 0
    monkeypatch.delenv("GITHUB_REF_TYPE")

    bad = tmp_path / "bad"
    bad.mkdir()
    make_repo(bad, changelog="# Changelog\n", plugin_extra={"version": "1.2.3"})
    monkeypatch.setattr(check_versions, "ROOT", str(bad))
    assert check_versions.main() == 1


def test_secret_scan_patterns():
    # Fixtures are assembled at runtime so this file never contains a
    # secret-shaped literal that would trip the scanner it tests.
    text = "\n".join(
        [
            "token = " + "gh" + "p_" + "a" * 36,
            "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----",
            "client_" + 'secret = "abcdefghijklmnop"',
            "contact someone" + "@" + "company.test",
            "noreply 1+x@users.noreply.github.com and dev@example.com",
            "plain line",
        ]
    )
    findings = secret_scan.scan_text("f.txt", text, [])
    assert findings == [
        "f.txt:1: GitHub token",
        "f.txt:2: private key",
        "f.txt:3: assigned secret",
        "f.txt:4: email address",
    ]


def test_device_archive_contents(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo)
    (repo / "pyproject.toml").write_text("")
    (repo / "requirements-test.txt").write_text("pytest\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "package.py").write_text("")
    with tarfile.open(fileobj=io.BytesIO(test_on_device.build_archive(str(repo))), mode="r:gz") as archive:
        names = set(archive.getnames())
    assert {"pyproject.toml", "requirements-test.txt", "tests/test_x.py", "scripts/package.py"} <= names
    assert "py_modules/keepsake/__init__.py" in names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert not any(n.startswith(("dist/", "bin/")) or n == "main.py" for n in names)


def test_device_remote_command_quotes_arguments():
    default = test_on_device.remote_command([])
    assert default.endswith("keepsake-test -m posix")
    named = test_on_device.remote_command(["tests/test_freeze.py", "-k", "a b; rm -rf /"])
    assert named.endswith("keepsake-test tests/test_freeze.py -k 'a b; rm -rf /'")
    assert "trap 'rm -rf \"$run\"' EXIT" in test_on_device.REMOTE_SCRIPT


def test_device_config_missing_exits(tmp_path):
    with pytest.raises(SystemExit):
        device.load_target(str(tmp_path / "missing.json"))
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"host": "h", "port": 2222}))
    assert device.load_target(str(path)) == ("deck@h", "2222")


def test_secret_scan_denylist_and_exemption():
    assert secret_scan.scan_text("src/a.ts", "My Secret Game", ["secret game"]) == ["src/a.ts:1: denylisted string"]
    assert secret_scan.scan_text("docs/build-prompt.md", "My Secret Game", ["secret game"]) == []
