"""Release signing key on this laptop (ADR-0036). Windows only.

The minisign secret key is encrypted with a long random passphrase (minisign's
own scrypt encryption). The passphrase is sealed with Windows DPAPI for the
current user, so `release.py publish` can sign without anyone typing it, and a
copy of the key file alone is useless. Both files sit in
``%LOCALAPPDATA%\\Keepsake\\signing`` (not roamed, not synced to OneDrive), in a
folder whose access list is limited to the current user.

    python scripts/signing.py setup              once: create the key (the owner runs this)
    python scripts/signing.py status             public key and checks; prints nothing secret
    python scripts/signing.py backup <folder>    copy the encrypted key and public key for an offline backup
    python scripts/signing.py show-passphrase    the owner writes it down for the backup; asks first
    python scripts/signing.py restore <folder>   on a new laptop: re-seal a backed-up key with DPAPI

Nothing here prints, logs or commits the secret key, and only show-passphrase
ever shows the passphrase, after the owner confirms.
"""

from __future__ import annotations

import getpass
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "py_modules"))

from keepsake import minisign  # noqa: E402

FOLDER = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Keepsake", "signing")
SECRET_NAME = "keepsake-release.key"  # noqa: S105 - a file name, not a secret
PUBLIC_NAME = "keepsake-release.pub"
SEALED_NAME = "passphrase.dpapi"
ENTROPY = b"Keepsake release signing (ADR-0036)"
CRYPTPROTECT_UI_FORBIDDEN = 0x1

Runner = Callable[..., subprocess.CompletedProcess]


class SigningError(Exception):
    pass


def paths(folder: str = FOLDER) -> tuple[str, str, str]:
    return (os.path.join(folder, SECRET_NAME), os.path.join(folder, PUBLIC_NAME), os.path.join(folder, SEALED_NAME))


def is_set_up(folder: str = FOLDER) -> bool:
    return all(os.path.isfile(p) for p in paths(folder))


# DPAPI (CryptProtectData), current user, through ctypes: stdlib only.


def _dpapi(data: bytes, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise SigningError("release signing uses Windows DPAPI; run it on the Windows laptop")
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]  # noqa: RUF012

    def blob(raw: bytes) -> tuple[Blob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    func.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p if not protect else wintypes.LPCWSTR,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    func.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    source, keep_source = blob(data)
    entropy, keep_entropy = blob(ENTROPY)
    out = Blob()
    description = "Keepsake release signing" if protect else None
    if not func(
        ctypes.byref(source),
        description,
        ctypes.byref(entropy),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    ):
        raise SigningError(
            f"Windows could not {'seal' if protect else 'unseal'} the passphrase (error {ctypes.GetLastError()})"
        )
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)
        del keep_source, keep_entropy


def seal(secret: bytes) -> bytes:
    return _dpapi(secret, protect=True)


def unseal(sealed: bytes) -> bytes:
    return _dpapi(sealed, protect=False)


# The folder


def current_user() -> str:
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    if not os.environ.get("USERNAME"):
        raise SigningError("could not tell who the current user is")
    return user


def lock_folder(folder: str, runner: Runner = subprocess.run) -> None:
    """Only the current user may open the folder: inherited permissions removed, one grant."""
    user = current_user()
    result = runner(
        ["icacls", folder, "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SigningError("could not restrict the folder to your account")


def acl_principals(icacls_output: str, folder: str) -> list[str]:
    """Who ``icacls <folder>`` lists. Its first line starts with the folder path; a blank line ends the list."""
    names = []
    for index, line in enumerate(icacls_output.splitlines()):
        if not line.strip():
            break
        entry = line[len(folder) :] if index == 0 and line.startswith(folder) else line
        entry = entry.strip()
        if ":(" in entry:
            names.append(entry.split(":(", 1)[0].strip())
    return names


def folder_is_private(folder: str, runner: Runner = subprocess.run) -> bool:
    result = runner(["icacls", folder], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False
    names = acl_principals(result.stdout, folder)
    return bool(names) and all(n.casefold() == current_user().casefold() for n in names)


# minisign


def _minisign(args: Sequence[str], passphrase: str, runner: Runner) -> subprocess.CompletedProcess:
    if not shutil.which("minisign"):
        raise SigningError("minisign is not on PATH: winget install jedisct1.minisign")
    # minisign reads the password with fgets(stdin), so a pipe works (ADR-0036).
    return runner(
        ["minisign", *args], input=passphrase + "\n" + passphrase + "\n", capture_output=True, text=True, check=False
    )


def public_key(folder: str = FOLDER) -> str:
    """The base64 line of the public key (the line pinned in release_key.py)."""
    with open(paths(folder)[1], encoding="utf-8") as handle:
        text = handle.read()
    minisign.parse_public_key(text)
    return next(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("untrusted"))


def setup(folder: str = FOLDER, runner: Runner = subprocess.run) -> str:
    secret_path, public_path, sealed_path = paths(folder)
    if any(os.path.exists(p) for p in paths(folder)):
        raise SigningError(f"a signing key already exists in {folder}; never replace a pinned key")
    os.makedirs(folder, exist_ok=True)
    lock_folder(folder, runner)
    passphrase = secrets.token_urlsafe(48)
    with open(sealed_path, "wb") as handle:
        handle.write(seal(passphrase.encode("utf-8")))
    made = _minisign(
        ["-G", "-p", public_path, "-s", secret_path, "-c", "Keepsake release signing key"], passphrase, runner
    )
    if made.returncode != 0 or not os.path.isfile(secret_path):
        raise SigningError("minisign could not create the key")
    sign_check(folder, runner)
    return public_key(folder)


def passphrase_of(folder: str = FOLDER) -> str:
    with open(paths(folder)[2], "rb") as handle:
        return unseal(handle.read()).decode("utf-8")


def sign(file_path: str, trusted_comment: str, folder: str = FOLDER, runner: Runner = subprocess.run) -> str:
    """Sign ``file_path``; return the signature path. Checked with the plugin's own verifier before returning."""
    if not is_set_up(folder):
        raise SigningError("no signing key on this laptop; the owner runs: python scripts/signing.py setup")
    secret_path = paths(folder)[0]
    signature_path = file_path + ".minisig"
    done = _minisign(
        ["-S", "-s", secret_path, "-m", file_path, "-x", signature_path, "-t", trusted_comment],
        passphrase_of(folder),
        runner,
    )
    if done.returncode != 0 or not os.path.isfile(signature_path):
        raise SigningError("minisign could not sign (was the passphrase changed?)")
    with open(file_path, "rb") as data, open(signature_path, encoding="utf-8") as sig:
        minisign.verify(public_key(folder), sig.read(), data.read())  # raises if the plugin would refuse it
    return signature_path


def sign_check(folder: str = FOLDER, runner: Runner = subprocess.run) -> None:
    """Sign a throwaway file and verify it with the plugin's verifier: the key, passphrase and verifier agree."""
    with tempfile.TemporaryDirectory() as scratch:
        probe = os.path.join(scratch, "probe.txt")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("Keepsake signing check\n")
        sign(probe, "Keepsake signing check", folder, runner)


def backup(target: str, folder: str = FOLDER) -> None:
    """Copy the encrypted secret key and the public key (never the DPAPI file, which only works here)."""
    if not is_set_up(folder):
        raise SigningError("nothing to back up yet")
    os.makedirs(target, exist_ok=True)
    secret_path, public_path, _sealed = paths(folder)
    shutil.copy2(secret_path, os.path.join(target, SECRET_NAME))
    shutil.copy2(public_path, os.path.join(target, PUBLIC_NAME))


def restore(
    source: str, folder: str = FOLDER, ask: Callable[[str], str] = getpass.getpass, runner: Runner = subprocess.run
) -> str:
    """Re-seal a backed-up key on this laptop; the owner types the passphrase once."""
    if any(os.path.exists(p) for p in paths(folder)):
        raise SigningError(f"a signing key already exists in {folder}")
    os.makedirs(folder, exist_ok=True)
    lock_folder(folder, runner)
    shutil.copy2(os.path.join(source, SECRET_NAME), paths(folder)[0])
    shutil.copy2(os.path.join(source, PUBLIC_NAME), paths(folder)[1])
    typed = ask("Passphrase from your backup: ")
    with open(paths(folder)[2], "wb") as handle:
        handle.write(seal(typed.encode("utf-8")))
    sign_check(folder, runner)
    return public_key(folder)


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    try:
        if command == "setup":
            key = setup()
            print("Signing key created. Public key (not secret; pin it in py_modules/keepsake/release_key.py):")
            print(key)
            print("Now back it up: see docs/releasing.md, 'Back up the signing key'.")
        elif command == "status":
            if not is_set_up():
                print("No signing key on this laptop.")
                return 1
            sign_check()
            print(f"Public key: {public_key()}")
            private = "yes" if folder_is_private(FOLDER) else "NO: run setup again or fix it with icacls"
            print(f"Folder limited to your account: {private}")
            print("Sign check with the plugin's verifier: passed")
        elif command == "backup" and len(argv) == 2:
            backup(argv[1])
            print(f"Copied the encrypted key and the public key to {argv[1]}.")
            print("Write down the passphrase too: python scripts/signing.py show-passphrase")
        elif command == "show-passphrase":
            if input("This shows the passphrase on screen. Type SHOW to continue: ").strip() != "SHOW":
                return 1
            print(passphrase_of())
        elif command == "restore" and len(argv) == 2:
            print(f"Restored. Public key: {restore(argv[1])}")
        else:
            print(__doc__)
            return 2
    except (SigningError, minisign.MinisignError, OSError) as exc:
        print(f"signing: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
