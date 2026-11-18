"""Build the plugin zip in the layout Decky Loader expects.

    out/Keepsake-v<version>.zip
      Keepsake/
        dist/index.js
        main.py
        py_modules/keepsake/...
        bin/...            (executable bits preserved)
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
TREES = ("dist", "py_modules", "bin")
EXECUTABLE_TREES = ("bin",)
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


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
                if name.endswith((".pyc", ".pyo")):
                    continue
                src = os.path.join(folder, name)
                rel = os.path.relpath(src, ROOT).replace(os.sep, "/")
                mode = 0o755 if tree in EXECUTABLE_TREES else 0o644
                entries.append((src, rel, mode))
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
                data = handle.read()
            if rel.startswith("bin/"):
                # Shell scripts must have LF line endings or "#!/bin/sh" fails on the device.
                data = data.replace(b"\r\n", b"\n")
            archive.writestr(info, data)
    return target


DESKTOP_FILES = (  # (source in the repository, path in the PC package)
    ("desktop/index.html", "desktop/index.html"),
    ("desktop/app.css", "desktop/app.css"),
    ("desktop/install.pyw", "install.pyw"),
    ("LICENSE", "LICENSE"),
    ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    ("CHANGELOG.md", "CHANGELOG.md"),  # "What's new" after an update (ADR-0049)
    ("docs/pc-host.md", "README-PC.md"),
)


def desktop_name() -> str:
    return f"{plugin_name()}-desktop-v{version()}.zip"


def collect_desktop() -> list[tuple[str, str]]:
    """(source path, archive path) for the PC package (ADR-0038, P5): the same core, the built desktop UI."""
    entries = [(os.path.join(ROOT, *src.split("/")), dst) for src, dst in DESKTOP_FILES]
    dist = os.path.join(ROOT, "desktop", "dist")
    scripts = sorted(n for n in os.listdir(dist) if n.endswith(".js")) if os.path.isdir(dist) else []
    if "main.js" not in scripts:
        sys.exit("desktop/dist/main.js is missing. Run pnpm run build:desktop first.")
    entries += [(os.path.join(dist, n), f"desktop/dist/{n}") for n in scripts]
    base = os.path.join(ROOT, "py_modules")
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS)
        for name in files:
            if not name.endswith((".pyc", ".pyo")):
                src = os.path.join(folder, name)
                entries.append((src, os.path.relpath(src, ROOT).replace(os.sep, "/")))
    return sorted(entries, key=lambda e: e[1])


def build_desktop(out_dir: str) -> str:
    """Build ``Keepsake-desktop-v<version>.zip``, deterministic like the plugin zip."""
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, desktop_name())
    folder = f"{plugin_name()}-desktop"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for src, rel in collect_desktop():
            info = zipfile.ZipInfo(f"{folder}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100000 | 0o644) << 16
            with open(src, "rb") as handle:
                archive.writestr(info, handle.read())
        info = zipfile.ZipInfo(f"{folder}/VERSION", date_time=FIXED_TIME)
        info.create_system = 3
        info.external_attr = (0o100000 | 0o644) << 16
        archive.writestr(info, version() + "\n")  # read by install.pyw and the self-update
    return target


def main() -> None:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out")
    for target in (build(out_dir), build_desktop(out_dir)):
        with open(target, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        print(f"{digest}  {os.path.basename(target)}")


if __name__ == "__main__":
    main()
