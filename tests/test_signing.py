"""The laptop's release signing helper (ADR-0036). A throwaway Ed25519 key stands in for minisign's."""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import signing
from test_signatures import public_text, signature_text

windows = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")


@windows
def test_dpapi_round_trip_and_tamper():
    sealed = signing.seal(b"synthetic passphrase")
    assert sealed != b"synthetic passphrase" and b"synthetic" not in sealed
    assert signing.unseal(sealed) == b"synthetic passphrase"
    broken = bytearray(sealed)
    broken[-5] ^= 0xFF
    with pytest.raises(signing.SigningError):
        signing.unseal(bytes(broken))


def test_acl_parsing(monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "CORP")
    monkeypatch.setenv("USERNAME", "someone")
    folder = r"C:\x\signing"
    mine = f"{folder} CORP\\someone:(OI)(CI)(F)\n\nSuccessfully processed 1 files; Failed processing 0 files\n"
    shared = (
        f"{folder} CORP\\someone:(OI)(CI)(F)\n             BUILTIN\\Users:(I)(RX)\n\nSuccessfully processed 1 files\n"
    )
    assert signing.acl_principals(mine, folder) == ["CORP\\someone"]
    assert signing.acl_principals(shared, folder) == ["CORP\\someone", "BUILTIN\\Users"]

    def runner(output):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, output, "")

    assert signing.folder_is_private(folder, runner(mine)) is True
    assert signing.folder_is_private(folder, runner(shared)) is False


class FakeMinisign:
    """Answers like minisign: -G writes the key pair, -S writes a signature. Checks the piped passphrase."""

    def __init__(self, passphrase=None):
        self.passphrase, self.calls = passphrase, []

    def __call__(self, command, input=None, **kw):
        self.calls.append(command[1] if command[0] == "minisign" else command[0])
        if command[0] == "icacls":
            return subprocess.CompletedProcess(command, 0, "", "")
        typed = (input or "").splitlines()[0]
        if command[1] == "-G":
            self.passphrase = typed
            args = dict(zip(command[2::2], command[3::2], strict=False))
            with open(args["-p"], "w", encoding="utf-8") as handle:
                handle.write(public_text())
            with open(args["-s"], "w", encoding="utf-8") as handle:
                handle.write("encrypted synthetic key\n")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "-S":
            if typed != self.passphrase:
                return subprocess.CompletedProcess(command, 1, "", "Wrong password for that key")
            args = dict(zip(command[2::2], command[3::2], strict=False))
            with open(args["-m"], "rb") as handle:
                data = handle.read()
            with open(args["-x"], "w", encoding="utf-8") as handle:
                handle.write(signature_text(data))
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)


@windows
def test_setup_then_sign_with_the_sealed_passphrase(tmp_path, monkeypatch):
    monkeypatch.setattr(signing.shutil, "which", lambda name: "minisign")
    fake = FakeMinisign()
    folder = str(tmp_path / "signing")
    key = signing.setup(folder, fake)
    assert key == public_text().splitlines()[1]
    assert fake.calls[:3] == ["icacls", "-G", "-S"]  # locked first, then a sign check
    assert len(fake.passphrase) >= 60 and fake.passphrase.encode() not in open(signing.paths(folder)[2], "rb").read()
    target = tmp_path / "SHA256SUMS"
    target.write_bytes(b"ab" * 32 + b"  Keepsake-v9.9.9.zip\n")
    assert signing.sign(str(target), "Keepsake v9.9.9", folder, fake).endswith(".minisig")
    with pytest.raises(signing.SigningError, match="never replace"):
        signing.setup(folder, fake)


@windows
def test_a_wrong_passphrase_or_a_bad_signature_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(signing.shutil, "which", lambda name: "minisign")
    fake = FakeMinisign()
    folder = str(tmp_path / "signing")
    signing.setup(folder, fake)
    target = tmp_path / "SHA256SUMS"
    target.write_bytes(b"x")
    fake.passphrase = "changed"
    with pytest.raises(signing.SigningError, match="could not sign"):
        signing.sign(str(target), "c", folder, fake)
    fake.passphrase = signing.passphrase_of(folder)
    with open(signing.paths(folder)[1], "w", encoding="utf-8") as handle:
        handle.write(public_text(seed=bytes(range(1, 33))))  # the pinned half no longer matches
    with pytest.raises(signing.minisign.MinisignError):
        signing.sign(str(target), "c", folder, fake)


@windows
def test_backup_has_the_encrypted_key_but_never_the_sealed_passphrase(tmp_path, monkeypatch):
    monkeypatch.setattr(signing.shutil, "which", lambda name: "minisign")
    fake = FakeMinisign()
    folder = str(tmp_path / "signing")
    signing.setup(folder, fake)
    signing.backup(str(tmp_path / "usb"), folder)
    assert sorted(os.listdir(tmp_path / "usb")) == [signing.SECRET_NAME, signing.PUBLIC_NAME]
    restored = str(tmp_path / "new-laptop")
    key = signing.restore(str(tmp_path / "usb"), restored, ask=lambda prompt: fake.passphrase, runner=fake)
    assert key == signing.public_key(folder)


def test_without_a_key_signing_says_what_to_do(tmp_path):
    with pytest.raises(signing.SigningError, match=r"signing\.py setup"):
        signing.sign(str(tmp_path / "f"), "c", str(tmp_path / "none"))
