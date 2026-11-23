"""Keepsake starts on a Decky build whose frozen Python leaves out stdlib modules (ADR-0030).

Decky Loader builds its Python with PyInstaller (``backend/pyinstaller.spec``),
which bundles only the stdlib modules the loader itself imports plus a short
``hiddenimports`` list. ``xml`` is not among them, and a top-level ``import
xml.etree.ElementTree`` once stopped the whole backend from loading on a
Legion Go 2. This runs ``main.py`` in a fresh interpreter (pytest itself
imports ``xml``) with those modules blocked through a ``sys.meta_path`` finder.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Modules Keepsake uses that Decky's frozen Python is not proven to bundle: the transitive closure of the
# loader's own imports and hiddenimports does not contain them (ADR-0030).
NOT_BUNDLED = ("xml", "tomllib", "resource")

SCRIPT = r"""
import asyncio, importlib.abc, json, os, sys, types

BLOCKED = tuple(sys.argv[1].split(","))


class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r} (blocked like Decky's frozen Python)", name=name)
        return None


sys.meta_path.insert(0, Block())
for name in list(sys.modules):
    if name.split(".")[0] in BLOCKED:
        del sys.modules[name]
sys.path[:0] = [sys.argv[2], os.path.join(sys.argv[2], "py_modules")]

decky = types.ModuleType("decky")


async def emit(event, *args):
    return None


decky.emit = emit
sys.modules["decky"] = decky

from keepsake import net  # noqa: E402


def refuse(*args, **kwargs):
    raise net.NetError("no network in this test")


net.fetch = net.fetch_to_file = net.request = refuse  # before keepsake.app binds them as defaults

import main  # noqa: E402  (the bug: this import failed with "No module named 'xml.etree'")
from keepsake import diagnostics  # noqa: E402
from keepsake.store import StoreError  # noqa: E402


async def go():
    plugin = main.Plugin()
    await plugin._main()
    app = plugin.app
    status = await app.get_status()
    checks = {c["id"]: c for c in await app._health(False)}
    modules = diagnostics.environment()["modules"]
    try:
        app._webdav()
        webdav = "no error"
    except StoreError as exc:
        webdav = str(exc)
    await plugin._unload()
    return {
        "version": status.get("version"),
        "pythonModules": checks["python-modules"],
        "xml": modules["xml"]["available"],
        "tomllib": modules["tomllib"]["available"],
        "webdav": webdav,
        "store": app.settings.get("snapshotStore"),
    }


print("RESULT " + json.dumps(asyncio.run(go())))
"""


def run_blocked(tmp_path, blocked=NOT_BUNDLED):
    home = tmp_path / "home"
    env = {
        **os.environ,
        "DECKY_USER_HOME": str(home),
        "DECKY_PLUGIN_SETTINGS_DIR": str(home / "homebrew/settings/Haversack"),
        "DECKY_PLUGIN_RUNTIME_DIR": str(home / "homebrew/data/Haversack"),
        "DECKY_PLUGIN_LOG_DIR": str(home / "homebrew/logs/Haversack"),
        "DECKY_PLUGIN_DIR": ROOT,
        "HOME": str(home),
    }
    for path in (
        env["DECKY_PLUGIN_SETTINGS_DIR"],
        env["DECKY_PLUGIN_RUNTIME_DIR"],
        env["DECKY_PLUGIN_LOG_DIR"],
    ):
        os.makedirs(path, exist_ok=True)
    script = tmp_path / "frozen_start.py"
    script.write_text(SCRIPT, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), ",".join(blocked), ROOT], capture_output=True, text=True, env=env, timeout=300
    )


def test_the_backend_starts_without_xml_tomllib_or_resource(tmp_path):
    import json

    result = run_blocked(tmp_path)
    assert result.returncode == 0, result.stderr[-3000:]
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    found = json.loads(line[len("RESULT ") :])
    assert found["xml"] is False and found["tomllib"] is False  # diagnostics report them in plain terms
    assert found["pythonModules"]["status"] == "warn"
    assert found["pythonModules"]["items"] == ["xml (needed for WebDAV and S3)"]
    assert "WebDAV and S3 are not supported by this Decky build" in found["webdav"]
    assert found["store"] == "local"  # save sync with the local store, OneDrive or Google Drive is unaffected


def test_webdav_and_s3_listing_fail_clearly_without_xml(monkeypatch):
    import builtins

    from keepsake.store import StoreError, httpcall

    real_import = builtins.__import__

    def no_xml(name, *args, **kwargs):
        if name.startswith("xml"):
            raise ModuleNotFoundError("No module named 'xml'", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_xml)
    try:
        httpcall.parse_xml(b"<a/>", "WebDAV server")
    except StoreError as exc:
        assert str(exc) == httpcall.XML_MISSING
    else:
        raise AssertionError("parse_xml must raise StoreError without xml")
