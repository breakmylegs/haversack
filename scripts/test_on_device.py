"""Run backend tests on a development device over SSH (ADR-0004).

There is no CI and WSL is unavailable, so the device is the Linux test run.
Tests that need a real Linux ``/proc``, POSIX signals, symlinks or file modes
are marked ``posix`` and only run here.

    python scripts/test_on_device.py                      # the posix-marked tests
    python scripts/test_on_device.py tests/test_freeze.py # named tests

The script streams py_modules, tests and scripts to a fresh temporary folder
under ``~/.cache`` on the device, runs pytest with the device's ``python3`` in a
reusable venv at ``~/.cache/keepsake-test-venv`` (pytest and Hypothesis only),
and deletes the run folder afterwards, pass or fail. It never touches the
installed plugin or Decky. Uses ``deploy.local.json`` like scripts/deploy.py.
"""

from __future__ import annotations

import io
import os
import shlex
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import device

ROOT = device.ROOT
FILES = ("pyproject.toml", "requirements-test.txt")
TREES = ("py_modules", "tests", "scripts")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".hypothesis"}
DEFAULT_ARGS = ("-m", "posix")

REMOTE_SCRIPT = r"""set -eu
mkdir -p "$HOME/.cache"
run=$(mktemp -d "$HOME/.cache/keepsake-test-run.XXXXXX")
trap 'rm -rf "$run"' EXIT
tar -xzf - -C "$run"
venv="$HOME/.cache/keepsake-test-venv"
if [ ! -x "$venv/bin/python" ]; then python3 -m venv "$venv"; fi
"$venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$run/requirements-test.txt"
cd "$run"
"$venv/bin/python" --version
"$venv/bin/python" -m pytest -q -p no:cacheprovider "$@"
"""


ONEDRIVE_TOKEN = "$HOME/homebrew/settings/Haversack/onedrive-token.json"  # noqa: S105 - a path, not a secret


def git_ignored(root: str = ROOT) -> set[str]:
    """Files git ignores (local scratch, generated files): never sent to the device."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard", *TREES],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def build_archive(root: str = ROOT, ignored: set[str] | None = None) -> bytes:
    """Return a gzipped tar of the files the tests need, with POSIX names."""
    ignored = git_ignored(root) if ignored is None else ignored
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in FILES:
            archive.add(os.path.join(root, name), arcname=name)
        for tree in TREES:
            for folder, dirs, files in os.walk(os.path.join(root, tree)):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS)
                for name in sorted(files):
                    if name.endswith((".pyc", ".pyo")):
                        continue
                    src = os.path.join(folder, name)
                    rel = os.path.relpath(src, root).replace(os.sep, "/")
                    if rel not in ignored:
                        archive.add(src, arcname=rel)
    return buffer.getvalue()


def remote_command(pytest_args: list[str], onedrive: bool = False) -> str:
    args = pytest_args or (["-m", "onedrive", "-s"] if onedrive else list(DEFAULT_ARGS))
    command = ["sh", "-c", shlex.quote(REMOTE_SCRIPT), "keepsake-test", *(shlex.quote(a) for a in args)]
    if onedrive:
        # Uses the token Haversack's own sign-in stored on the device; it never leaves the device.
        command.insert(0, f'KEEPSAKE_ONEDRIVE_TOKEN_FILE="{ONEDRIVE_TOKEN}"')
    return " ".join(command)


def main(argv: list[str]) -> int:
    onedrive = "--onedrive" in argv
    args = [a for a in argv if a != "--onedrive"]
    host, port = device.load_target()
    result = subprocess.run(
        ["ssh", "-p", port, host, remote_command(args, onedrive)], input=build_archive(), check=False
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
