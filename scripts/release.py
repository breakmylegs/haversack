"""Local release helper (build prompt section 13, ADR-0004, ADR-0005).

There is no CI and ``main`` only accepts pull requests, so a release has two
steps:

    pnpm release prepare 0.2.1
        Checks you are on an up-to-date, clean main and that CHANGELOG.md has a
        "## [0.2.1]" section, then bumps package.json on a release/v0.2.1
        branch, pushes it and opens a pull request.

    pnpm release publish --device-tested [--dry-run]
        After that pull request is merged: on an up-to-date, clean main, runs
        scripts/check.py, builds the deterministic zip, writes SHA256SUMS,
        signs it with minisign when KEEPSAKE_MINISIGN_KEY points at your secret
        key, tags v<version>, pushes the tag and creates the GitHub Release
        with that version's CHANGELOG section as notes. -beta.N versions are
        marked as pre-releases. --device-tested confirms you ran
        `pnpm run test:device` on this commit; --accept-untested publishes
        without them and says so in the release notes. --dry-run builds the assets into
        out/release/ and stops before any git or GitHub change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import package
import signing
from keepsake import minisign

ROOT = package.ROOT
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-beta\.\d+)?$")
SUMS_NAME = "SHA256SUMS"

Runner = Callable[[Sequence[str]], str]


class ReleaseError(Exception):
    pass


def run(command: Sequence[str]) -> str:
    result = subprocess.run(list(command), cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ReleaseError(f"{' '.join(command)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def version_key(version: str) -> tuple[int, int, int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$", version)
    if not match:
        raise ReleaseError(f"{version!r} is not X.Y.Z or X.Y.Z-beta.N")
    major, minor, patch, beta = match.groups()
    return (int(major), int(minor), int(patch), 0 if beta else 1, int(beta or 0))


def is_prerelease(version: str) -> bool:
    return "-beta." in version


def extract_notes(changelog: str, version: str) -> str:
    """Return the body of the ``## [version]`` section, without its heading."""
    pattern = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(changelog)
    if not match or not match.group(1).strip():
        raise ReleaseError(f"CHANGELOG.md has no notes under '## [{version}]'")
    return match.group(1).strip() + "\n"


def bump_package_json(text: str, version: str) -> str:
    new, count = re.subn(r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1)
    if count != 1:
        raise ReleaseError("could not find the version field in package.json")
    return new


def read_version() -> str:
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as handle:
        return str(json.load(handle)["version"])


def read_changelog() -> str:
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as handle:
        return handle.read()


def ensure_clean_main(runner: Runner) -> None:
    if runner(["git", "status", "--porcelain"]).strip():
        raise ReleaseError("working tree is not clean")
    if runner(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip() != "main":
        raise ReleaseError("switch to main first")
    runner(["git", "fetch", "origin", "--tags"])
    if runner(["git", "rev-parse", "HEAD"]).strip() != runner(["git", "rev-parse", "origin/main"]).strip():
        raise ReleaseError("main is not the same as origin/main; pull first")


def stable_zip_name() -> str:
    """The unversioned asset behind the fixed URL .../releases/latest/download/Keepsake.zip."""
    return f"{package.plugin_name()}.zip"


def build_assets(out_dir: str, version: str, notes: str) -> list[str]:
    """Build the zips, SHA256SUMS and notes; return the files to upload, SHA256SUMS last.

    Two zips with the same bytes are published: ``Keepsake-v<version>.zip``,
    which the in-plugin updater and the reproducible-build check use, and
    ``Keepsake.zip``, so a first install can always use the same URL.
    ``SHA256SUMS`` lists both, so its signature covers both names.
    """
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    zip_path = package.build(out_dir)
    expected = f"{package.plugin_name()}-v{version}.zip"
    if os.path.basename(zip_path) != expected:
        raise ReleaseError(f"zip is {os.path.basename(zip_path)}, expected {expected}")
    stable_path = os.path.join(out_dir, stable_zip_name())
    shutil.copyfile(zip_path, stable_path)
    with open(zip_path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    # The PC package (ADR-0038, P5): the same core and the desktop interface, under the same signature.
    desktop_path = package.build_desktop(out_dir)
    with open(desktop_path, "rb") as handle:
        desktop_digest = hashlib.sha256(handle.read()).hexdigest()
    sums_path = os.path.join(out_dir, SUMS_NAME)
    with open(sums_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"{digest}  {expected}\n{digest}  {stable_zip_name()}\n{desktop_digest}  {os.path.basename(desktop_path)}\n"
        )
    with open(os.path.join(out_dir, "notes.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(notes)
    return [zip_path, stable_path, desktop_path, sums_path]


def pinned_key() -> str:
    """The public key the plugin being released will trust (``release_key.PUBLIC_KEY``)."""
    from keepsake import release_key

    return release_key.PUBLIC_KEY.strip()


def sign(
    sums_path: str,
    version: str,
    runner: Runner,
    signer: Callable[[str, str], str] | None = None,
) -> str | None:
    """Sign SHA256SUMS: with the laptop's sealed key (ADR-0036), else an interactive KEEPSAKE_MINISIGN_KEY.

    The signature is then checked with the plugin's own verifier against the pinned key, so a release
    that installed devices would refuse is never published (and the verifier is re-proved against the
    real minisign tool every release).
    """
    comment = f"Keepsake v{version}"
    signature: str | None = None
    if signing.is_set_up():
        try:
            signature = (signer or signing.sign)(sums_path, comment)
        except signing.SigningError as exc:
            raise ReleaseError(str(exc)) from exc
    elif os.environ.get("KEEPSAKE_MINISIGN_KEY"):
        if not shutil.which("minisign"):
            raise ReleaseError("KEEPSAKE_MINISIGN_KEY is set but minisign is not on PATH")
        runner(["minisign", "-S", "-s", os.environ["KEEPSAKE_MINISIGN_KEY"], "-m", sums_path, "-t", comment])
        signature = sums_path + ".minisig"
    pinned = pinned_key()
    if signature is None:
        if pinned:
            raise ReleaseError(
                "the release key is pinned, so devices refuse unsigned releases; "
                "set up the signing key first (python scripts/signing.py status)"
            )
        print("warning: no signing key; SHA256SUMS will not be signed", file=sys.stderr)
        return None
    if pinned:
        with open(sums_path, "rb") as data, open(signature, encoding="utf-8") as sig:
            try:
                minisign.verify(pinned, sig.read(), data.read())
            except minisign.MinisignError as exc:
                raise ReleaseError(f"the signature does not verify with the pinned key: {exc}") from exc
    return signature


def prepare(version: str, runner: Runner = run) -> None:
    current = read_version()
    if version_key(version) <= version_key(current):
        raise ReleaseError(f"{version} is not newer than the current {current}")
    extract_notes(read_changelog(), version)
    ensure_clean_main(runner)
    branch = f"release/v{version}"
    runner(["git", "switch", "-c", branch])
    path = os.path.join(ROOT, "package.json")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(bump_package_json(text, version))
    runner(["git", "commit", "-am", f"chore(release): v{version}"])
    runner(["git", "push", "-u", "origin", branch])
    runner(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            f"Release v{version}",
            "--body",
            f"Bump version to {version}. After merge: `pnpm release publish --device-tested`.",
        ]
    )
    print(f"Opened the release pull request for v{version}. Merge it, then run publish on main.")


UNTESTED_NOTE = (
    "\n> Device tests (`pnpm run test:device`) were not run for this release. "
    "The owner accepted publishing it untested.\n"
)


def publish(
    device_tested: bool,
    dry_run: bool,
    runner: Runner = run,
    check: Callable[[], int] | None = None,
    accept_untested: bool = False,
) -> str:
    version = read_version()
    version_key(version)
    tag = f"v{version}"
    notes = extract_notes(read_changelog(), version)
    if device_tested and accept_untested:
        raise ReleaseError("pass either --device-tested or --accept-untested, not both")
    if accept_untested:
        # Say so in the release notes rather than pretend the tests ran.
        notes += UNTESTED_NOTE
    if not dry_run:
        if not (device_tested or accept_untested):
            raise ReleaseError(
                "run `pnpm run test:device` on this commit, then pass --device-tested "
                "(or --accept-untested to publish without them, noted in the release)"
            )
        ensure_clean_main(runner)
        if (
            runner(["git", "tag", "--list", tag]).strip()
            or runner(["git", "ls-remote", "--tags", "origin", tag]).strip()
        ):
            raise ReleaseError(f"tag {tag} already exists")
    if check is not None and check() != 0:
        raise ReleaseError("scripts/check.py failed")
    out_dir = os.path.join(ROOT, "out", "release", tag)
    files = build_assets(out_dir, version, notes)
    signature = sign(os.path.join(out_dir, SUMS_NAME), version, runner)
    if signature:
        files.append(signature)
    if dry_run:
        print(f"Dry run: assets for {tag} are in {out_dir}. No tag or release was created.")
        return out_dir
    runner(["git", "tag", "-a", tag, "-m", f"Keepsake {tag}"])
    runner(["git", "push", "origin", tag])
    command = [
        "gh",
        "release",
        "create",
        tag,
        *files,
        "--verify-tag",
        "--title",
        f"Keepsake {tag}",
        "--notes-file",
        os.path.join(out_dir, "notes.md"),
    ]
    if is_prerelease(version):
        command.append("--prerelease")
    runner(command)
    print(f"Published {tag}.")
    return out_dir


def run_checks() -> int:
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check.py")], cwd=ROOT, check=False).returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pnpm release")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="open the version bump pull request")
    prep.add_argument("version")
    pub = sub.add_parser("publish", help="tag and publish the version on main")
    pub.add_argument("--device-tested", action="store_true", help="you ran pnpm run test:device on this commit")
    pub.add_argument(
        "--accept-untested", action="store_true", help="publish without device tests; stated in the release notes"
    )
    pub.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if not SEMVER.match(args.version):
                raise ReleaseError(f"{args.version!r} is not X.Y.Z or X.Y.Z-beta.N")
            prepare(args.version)
        else:
            publish(args.device_tested, args.dry_run, check=run_checks, accept_untested=args.accept_untested)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
