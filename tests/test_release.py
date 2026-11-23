import hashlib
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import package
import release
from test_scripts import make_repo

CHANGELOG = """# Changelog

## [0.2.1]

### Fixed

- Something.

## [0.2.0]

First release.
"""


class FakeRunner:
    """Records commands and answers git queries like a clean, up-to-date main."""

    def __init__(self, branch="main", dirty="", head="abc", origin="abc", tags=""):
        self.calls = []
        self.answers = {
            ("git", "status", "--porcelain"): dirty,
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): branch + "\n",
            ("git", "rev-parse", "HEAD"): head,
            ("git", "rev-parse", "origin/main"): origin,
        }
        self.tags = tags

    def __call__(self, command):
        command = tuple(command)
        self.calls.append(command)
        if command[:3] == ("git", "tag", "--list") or command[:3] == ("git", "ls-remote", "--tags"):
            return self.tags
        return self.answers.get(command, "")

    def commands(self, prefix):
        return [c for c in self.calls if c[: len(prefix)] == prefix]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    make_repo(root, version="0.2.1", changelog=CHANGELOG)
    (root / "package.json").write_text('{\n  "name": "keepsake",\n  "version": "0.2.1",\n  "x": 1\n}\n')
    # Synthetic stand-ins for the built-in Google secrets (ADR-0055), too short to look like real ones.
    secrets = {"googleClientSecret": "GOCSPX-test-tv", "googleDesktopClientSecret": "GOCSPX-test-desk"}
    (root / "py_modules" / "keepsake" / "client_secrets.json").write_text(json.dumps(secrets))
    monkeypatch.setattr(package, "ROOT", str(root))
    monkeypatch.setattr(release, "ROOT", str(root))
    monkeypatch.delenv("KEEPSAKE_MINISIGN_KEY", raising=False)
    # Never the laptop's real signing key or pinned key: each test sets what it needs.
    monkeypatch.setattr(release.signing, "is_set_up", lambda *a: False)
    monkeypatch.setattr(release, "pinned_key", lambda: "")
    return root


def signed_by_test_key(monkeypatch, pin=True):
    """Sign with a throwaway Ed25519 key from test_signatures, pinning its public key."""
    from test_signatures import public_text, signature_text

    def fake_sign(path, comment):
        with open(path, "rb") as handle:
            data = handle.read()
        with open(path + ".minisig", "w", encoding="utf-8") as handle:
            handle.write(signature_text(data))
        return path + ".minisig"

    monkeypatch.setattr(release.signing, "is_set_up", lambda *a: True)
    monkeypatch.setattr(release.signing, "sign", fake_sign)
    if pin:
        monkeypatch.setattr(release, "pinned_key", lambda: public_text())


def test_the_sealed_key_signs_and_the_signature_is_checked_against_the_pin(repo, monkeypatch):
    signed_by_test_key(monkeypatch)
    runner = FakeRunner()
    release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    (create,) = runner.commands(("gh", "release", "create"))
    assert any(arg.endswith("SHA256SUMS.minisig") for arg in create)


def test_a_pinned_key_refuses_to_publish_unsigned(repo, monkeypatch):
    monkeypatch.setattr(release, "pinned_key", lambda: "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3")
    runner = FakeRunner()
    with pytest.raises(release.ReleaseError, match="refuse unsigned releases"):
        release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    assert not runner.commands(("git", "tag", "-a"))


def test_a_signature_from_another_key_is_refused_before_tagging(repo, monkeypatch):
    signed_by_test_key(monkeypatch, pin=False)
    monkeypatch.setattr(release, "pinned_key", lambda: "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3")
    runner = FakeRunner()
    with pytest.raises(release.ReleaseError, match="does not verify with the pinned key"):
        release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    assert not runner.commands(("git", "tag", "-a"))


def test_extract_notes():
    assert release.extract_notes(CHANGELOG, "0.2.1") == "### Fixed\n\n- Something.\n"
    assert release.extract_notes(CHANGELOG, "0.2.0") == "First release.\n"
    with pytest.raises(release.ReleaseError):
        release.extract_notes(CHANGELOG, "9.9.9")
    with pytest.raises(release.ReleaseError):
        release.extract_notes("## [1.0.0]\n\n## [0.9.0]\nx\n", "1.0.0")


def test_bump_package_json_keeps_formatting():
    text = '{\n  "name": "k",\n  "version": "0.1.0",\n  "deps": {"version": "keep"}\n}\n'
    assert release.bump_package_json(text, "0.2.0") == text.replace('"0.1.0"', '"0.2.0"')


def test_version_order_and_prerelease():
    assert release.version_key("0.2.1") > release.version_key("0.2.1-beta.3") > release.version_key("0.2.0")
    assert release.is_prerelease("1.0.0-beta.1") and not release.is_prerelease("1.0.0")
    with pytest.raises(release.ReleaseError):
        release.version_key("1.0")


def test_publish_dry_run_builds_assets_without_git_changes(repo):
    runner = FakeRunner()
    out_dir = release.publish(device_tested=False, dry_run=True, runner=runner, check=lambda: 0)
    zip_path = os.path.join(out_dir, "Haversack-v0.2.1.zip")
    with open(zip_path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    with open(os.path.join(out_dir, "Haversack-desktop-v0.2.1.zip"), "rb") as handle:
        desktop = hashlib.sha256(handle.read()).hexdigest()
    with open(os.path.join(out_dir, "Haversack-helper-v0.2.1.zip"), "rb") as handle:
        helper = hashlib.sha256(handle.read()).hexdigest()
    with open(os.path.join(out_dir, "Haversack-v0.2.1.sbom.cdx.json"), "rb") as handle:
        sbom_bytes = handle.read()
    with open(os.path.join(out_dir, "SHA256SUMS"), encoding="utf-8") as handle:
        assert handle.read() == (
            f"{digest}  Haversack-v0.2.1.zip\n{digest}  Haversack.zip\n{desktop}  Haversack-desktop-v0.2.1.zip\n"
            f"{helper}  Haversack-helper-v0.2.1.zip\n"
            f"{hashlib.sha256(sbom_bytes).hexdigest()}  Haversack-v0.2.1.sbom.cdx.json\n"
            # The same bytes under Keepsake's names, so installed Keepsakes update (ADR-0089).
            f"{digest}  Keepsake-v0.2.1.zip\n{digest}  Keepsake.zip\n{desktop}  Keepsake-desktop-v0.2.1.zip\n"
        )
    sbom = json.loads(sbom_bytes)
    assert sbom["metadata"]["component"]["version"] == "0.2.1"
    assert [c["name"] for c in sbom["components"]] == ["examplelib"]
    with open(os.path.join(out_dir, "notes.md"), encoding="utf-8") as handle:
        assert "Something." in handle.read()
    assert runner.calls == []


def test_stable_zip_is_a_byte_identical_copy(repo):
    out_dir = release.publish(device_tested=False, dry_run=True, runner=FakeRunner(), check=lambda: 0)
    with (
        open(os.path.join(out_dir, "Haversack-v0.2.1.zip"), "rb") as versioned,
        open(os.path.join(out_dir, "Haversack.zip"), "rb") as stable,
    ):
        assert versioned.read() == stable.read()


def test_signature_covers_both_names(repo, monkeypatch):
    monkeypatch.setenv("KEEPSAKE_MINISIGN_KEY", str(repo / "secret.key"))
    monkeypatch.setattr(release.shutil, "which", lambda name: "/usr/bin/minisign")
    runner = FakeRunner()
    out_dir = release.publish(device_tested=False, dry_run=True, runner=runner, check=lambda: 0)
    (signed,) = runner.commands(("minisign",))
    assert signed[signed.index("-m") + 1] == os.path.join(out_dir, "SHA256SUMS")


def test_accept_untested_publishes_and_says_so_in_notes(repo):
    runner = FakeRunner()
    out_dir = release.publish(device_tested=False, dry_run=False, runner=runner, check=lambda: 0, accept_untested=True)
    assert runner.commands(("gh", "release", "create"))
    with open(os.path.join(out_dir, "notes.md"), encoding="utf-8") as handle:
        notes = handle.read()
    assert "Something." in notes and "were not run for this release" in notes


def test_device_tested_notes_have_no_untested_line(repo):
    out_dir = release.publish(device_tested=True, dry_run=False, runner=FakeRunner(), check=lambda: 0)
    with open(os.path.join(out_dir, "notes.md"), encoding="utf-8") as handle:
        assert "not run" not in handle.read()


def test_both_test_flags_rejected(repo):
    with pytest.raises(release.ReleaseError, match="not both"):
        release.publish(device_tested=True, dry_run=False, runner=FakeRunner(), check=lambda: 0, accept_untested=True)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "is missing"),
        ("not json", "not valid JSON"),
        ('{"googleClientSecret": "GOCSPX-test-tv"}', "googleDesktopClientSecret"),
        ('{"googleClientSecret": "x", "googleDesktopClientSecret": "GOCSPX-test-desk"}', "googleClientSecret"),
    ],
)
def test_publish_refuses_without_the_google_client_secrets(repo, content, message, capsys):
    path = repo / "py_modules" / "keepsake" / "client_secrets.json"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    runner = FakeRunner()
    with pytest.raises(release.ReleaseError, match=message):
        release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    assert not runner.commands(("git", "tag", "-a"))
    release.publish(device_tested=False, dry_run=True, runner=FakeRunner(), check=lambda: 0)  # a dry run warns
    assert message in capsys.readouterr().err


def test_the_secrets_file_ships_in_both_packages(repo):
    out_dir = release.publish(device_tested=False, dry_run=True, runner=FakeRunner(), check=lambda: 0)
    for name, inner in (
        ("Haversack-v0.2.1.zip", "Haversack/py_modules/keepsake/client_secrets.json"),
        ("Haversack-desktop-v0.2.1.zip", "Keepsake-desktop/py_modules/keepsake/client_secrets.json"),
    ):
        with zipfile.ZipFile(os.path.join(out_dir, name)) as archive:
            assert json.loads(archive.read(inner))["googleDesktopClientSecret"] == "GOCSPX-test-desk"


def test_publish_requires_device_tests(repo):
    with pytest.raises(release.ReleaseError, match="test:device"):
        release.publish(device_tested=False, dry_run=False, runner=FakeRunner(), check=lambda: 0)


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        (FakeRunner(dirty=" M x"), "not clean"),
        (FakeRunner(branch="slice/02"), "main"),
        (FakeRunner(origin="def"), "origin/main"),
        (FakeRunner(tags="v0.2.1\n"), "already exists"),
    ],
)
def test_publish_guards(repo, runner, message):
    with pytest.raises(release.ReleaseError, match=message):
        release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    assert not runner.commands(("git", "tag", "-a"))


def test_publish_stops_when_checks_fail(repo):
    runner = FakeRunner()
    with pytest.raises(release.ReleaseError, match=r"check\.py"):
        release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 1)
    assert not runner.commands(("git", "tag", "-a"))


def test_publish_tags_pushes_and_creates_release(repo):
    runner = FakeRunner()
    release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    assert runner.commands(("git", "tag", "-a", "v0.2.1"))
    assert runner.commands(("git", "push", "origin", "v0.2.1"))
    (create,) = runner.commands(("gh", "release", "create"))
    assert "--prerelease" not in create
    assert any(arg.endswith("Haversack-v0.2.1.zip") for arg in create)
    assert any(os.path.basename(arg) == "Haversack.zip" for arg in create)  # the stable "latest" asset
    assert any(os.path.basename(arg) == "Haversack-desktop-v0.2.1.zip" for arg in create)  # the PC package
    # Installed Keepsakes (v0.25.0's updater included) find their usual names (ADR-0089).
    for old in ("Keepsake-v0.2.1.zip", "Keepsake.zip", "Keepsake-desktop-v0.2.1.zip"):
        assert any(os.path.basename(arg) == old for arg in create)
    assert any(arg.endswith("SHA256SUMS") for arg in create)
    # Tag before release, release last.
    assert runner.calls.index(create) == len(runner.calls) - 1


def test_beta_is_marked_prerelease(repo):
    (repo / "package.json").write_text('{"version": "0.3.0-beta.1"}')
    (repo / "CHANGELOG.md").write_text("## [0.3.0-beta.1]\n\nBeta.\n")
    runner = FakeRunner()
    release.publish(device_tested=True, dry_run=False, runner=runner, check=lambda: 0)
    (create,) = runner.commands(("gh", "release", "create"))
    assert "--prerelease" in create


def test_signing_key_without_minisign_fails(repo, monkeypatch):
    monkeypatch.setenv("KEEPSAKE_MINISIGN_KEY", str(repo / "missing.key"))
    monkeypatch.setattr(release.shutil, "which", lambda _name: None)
    with pytest.raises(release.ReleaseError, match="minisign"):
        release.publish(device_tested=False, dry_run=True, runner=FakeRunner(), check=lambda: 0)


def test_prepare_bumps_on_a_branch_and_opens_pr(repo):
    (repo / "CHANGELOG.md").write_text("## [0.2.2]\n\nNext.\n" + CHANGELOG)
    runner = FakeRunner()
    release.prepare("0.2.2", runner=runner)
    assert json.loads((repo / "package.json").read_text())["version"] == "0.2.2"
    assert runner.commands(("git", "switch", "-c", "release/v0.2.2"))
    assert runner.commands(("gh", "pr", "create"))


@pytest.mark.parametrize(("version", "message"), [("0.2.1", "not newer"), ("0.3.0", "no notes")])
def test_prepare_refusals(repo, version, message):
    runner = FakeRunner()
    with pytest.raises(release.ReleaseError, match=message):
        release.prepare(version, runner=runner)
    assert not runner.commands(("git", "switch"))
