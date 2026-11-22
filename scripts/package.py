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


CLIENT_SECRETS = ("py_modules", "keepsake", "client_secrets.json")
CLIENT_SECRET_KEYS = ("googleClientSecret", "googleDesktopClientSecret")


def client_secrets_problem() -> str | None:
    """Why the built-in Google clients would ship without their secrets, or None (ADR-0055).

    The file is git-ignored; the walk over ``py_modules`` puts it in both packages.
    """
    path = os.path.join(ROOT, *CLIENT_SECRETS)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return f"{'/'.join(CLIENT_SECRETS)} is missing: the built-in Google sign-in needs it (docs/releasing.md)"
    except (OSError, ValueError):
        return f"{'/'.join(CLIENT_SECRETS)} is not valid JSON"
    missing = [k for k in CLIENT_SECRET_KEYS if not str((data or {}).get(k, "")).startswith("GOCSPX-")]
    if missing:
        return f"{'/'.join(CLIENT_SECRETS)} has no {', '.join(missing)}"
    return None


def plugin_name() -> str:
    with open(os.path.join(ROOT, "plugin.json"), encoding="utf-8") as handle:
        return str(json.load(handle)["name"])


def version() -> str:
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as handle:
        return str(json.load(handle)["version"])


# The desktop interface the plugin serves in Desktop Mode, and the tray's icon (ADR-0068).
PLUGIN_DESKTOP = ("desktop/index.html", "desktop/app.css", "assets/icons/hicolor/256x256/apps/keepsake-tray.png")


def collect() -> list[tuple[str, str, int]]:
    """Return (source path, archive path, mode) for every file to ship."""
    entries: list[tuple[str, str, int]] = []
    for name in FILES + PLUGIN_DESKTOP:
        entries.append((os.path.join(ROOT, name), name, 0o644))
    dist = os.path.join(ROOT, "desktop", "dist")
    for name in sorted(os.listdir(dist)) if os.path.isdir(dist) else []:
        if name.endswith(".js"):
            entries.append((os.path.join(dist, name), f"desktop/dist/{name}", 0o644))
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
    if not os.path.isfile(os.path.join(ROOT, "desktop", "dist", "main.js")):
        sys.exit("desktop/dist/main.js is missing. Run pnpm run build:desktop first (ADR-0068).")
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


# The root helper (ADR-0083): a separate plugin, version-locked to Keepsake, under the same signature.
HELPER = os.path.join(ROOT, "helper")
HELPER_FOLDER = "keepsake-helper"


def helper_name() -> str:
    return f"{plugin_name()}-helper-v{version()}.zip"


def collect_helper() -> list[tuple[str, str]]:
    """(source path, archive path) for the helper: its own files, a copy of the licence, no tests."""
    entries = [(os.path.join(HELPER, n), n) for n in ("main.py", "plugin.json")]
    # Hand-written against Decky's globals, so it is kept in the repository (dist/ is ignored).
    entries.append((os.path.join(HELPER, "frontend", "index.js"), "dist/index.js"))
    entries.append((os.path.join(ROOT, "LICENSE"), "LICENSE"))
    base = os.path.join(HELPER, "py_modules")
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS)
        for name in files:
            if name.endswith(".py"):
                src = os.path.join(folder, name)
                entries.append((src, os.path.relpath(src, HELPER).replace(os.sep, "/")))
    return sorted(entries, key=lambda e: e[1])


def build_helper(out_dir: str) -> str:
    """Build ``Keepsake-helper-v<version>.zip``, deterministic, with its version stamped in."""
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, helper_name())
    with open(os.path.join(HELPER, "package.json"), encoding="utf-8") as handle:
        meta = json.load(handle)
    meta["version"] = version()
    extra = {"VERSION": version() + "\n", "package.json": json.dumps(meta, indent=2) + "\n"}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        items = [(rel, open(src, "rb").read()) for src, rel in collect_helper()]
        items += [(rel, text.encode("utf-8")) for rel, text in extra.items()]
        for rel, data in sorted(items):
            info = zipfile.ZipInfo(f"{HELPER_FOLDER}/{rel}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100000 | 0o644) << 16
            archive.writestr(info, data)
    return target


def main() -> None:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out")
    for target in (build(out_dir), build_desktop(out_dir), build_helper(out_dir)):
        with open(target, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        print(f"{digest}  {os.path.basename(target)}")


if __name__ == "__main__":
    main()
