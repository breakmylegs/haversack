"""Build the plugin zip in the layout Decky Loader expects.

    out/Haversack-v<version>.zip
      Haversack/
        dist/index.js
        main.py
        py_modules/keepsake/...
        package.json
        plugin.json
        LICENSE
        README.md

The zip is deterministic: sorted entries, fixed timestamps and explicit Unix
modes, so the same source always gives the same SHA-256.

Run ``pnpm build`` first.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FILES = ("main.py", "package.json", "plugin.json", "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md")
TREES = ("dist", "py_modules")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


# Never shipped. The cloud sign-in that used it was removed in the strip (ADR-0098); a copy left in a
# development checkout must not reach the zip.
NEVER_SHIP = {"client_secrets.json"}


def plugin_name() -> str:
    with open(os.path.join(ROOT, "plugin.json"), encoding="utf-8") as handle:
        return str(json.load(handle)["name"])


def version() -> str:
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as handle:
        return str(json.load(handle)["version"])


def collect() -> list[tuple[str, str, int]]:
    """Return (source path, archive path, mode) for every file to ship."""
    entries: list[tuple[str, str, int]] = []
    for name in FILES:
        entries.append((os.path.join(ROOT, name), name, 0o644))
    for tree in TREES:
        base = os.path.join(ROOT, tree)
        if not os.path.isdir(base):
            continue
        for folder, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS)
            for name in files:
                if name.endswith((".pyc", ".pyo")) or name in NEVER_SHIP:
                    continue
                src = os.path.join(folder, name)
                entries.append((src, os.path.relpath(src, ROOT).replace(os.sep, "/"), 0o644))
    return sorted(entries, key=lambda e: e[1])


def build(out_dir: str) -> str:
    if not os.path.isfile(os.path.join(ROOT, "dist", "index.js")):
        sys.exit("dist/index.js is missing. Run pnpm build first.")
    name = plugin_name()
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, f"{name}-v{version()}.zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for src, rel, mode in collect():
            info = zipfile.ZipInfo(f"{name}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, so external_attr carries the mode
            info.external_attr = (0o100000 | mode) << 16
            with open(src, "rb") as handle:
                archive.writestr(info, handle.read())
    return target


def main() -> None:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out")
    target = build(out_dir)
    with open(target, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    print(f"{digest}  {os.path.basename(target)}")


if __name__ == "__main__":
    main()
