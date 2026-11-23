"""Installing Keepsake on a PC and launching it (ADR-0038, P5). Everything in tmp folders; a fake registry."""

import contextlib
import json
import os

import pytest

from keepsake import launcher, pcinstall


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    @contextlib.contextmanager
    def CreateKey(self, hive, path):
        yield (hive, path)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[(key, name)] = value

    def DeleteValue(self, key, name):
        if (key, name) not in self.values:
            raise FileNotFoundError(name)
        del self.values[(key, name)]


def package(tmp_path, version):
    root = tmp_path / f"pkg-{version}"
    (root / "py_modules" / "keepsake" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (root / "py_modules" / "keepsake" / "__init__.py").write_text("")
    (root / "py_modules" / "keepsake" / "__pycache__" / "x.pyc").write_text("")
    (root / "desktop" / "dist").mkdir(parents=True, exist_ok=True)
    (root / "desktop" / "dist" / "main.js").write_text("export {};")
    (root / "install.pyw").write_text("installer")
    (root / "VERSION").write_text(version + "\n")
    return str(root)


def test_windows_install_switches_versions_keeps_one_previous_and_registers_start_up(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    registry = FakeRegistry()
    python = str(tmp_path / "Python" / "python.exe")
    os.makedirs(os.path.dirname(python))
    open(os.path.join(os.path.dirname(python), "pythonw.exe"), "w").close()
    for version in ("0.26.0", "0.27.0", "0.28.0"):
        result = pcinstall.install(package(tmp_path, version), "windows", env, python=python, registry=registry)
    root = pcinstall.app_root("windows", env)
    assert result["version"] == "0.28.0" and sorted(os.listdir(root)) == [
        "0.27.0",
        "0.28.0",
        "current.json",
        "keepsake.pyw",
    ]
    assert json.loads(open(os.path.join(root, "current.json")).read()) == {"version": "0.28.0", "previous": "0.27.0"}
    assert os.path.isfile(os.path.join(root, "0.28.0", "desktop", "dist", "main.js"))
    assert not os.path.exists(os.path.join(root, "0.28.0", "install.pyw"))  # the installer stays in the download
    assert not os.path.exists(os.path.join(root, "0.28.0", "py_modules", "keepsake", "__pycache__"))
    (command,) = registry.values.values()
    assert command.startswith(f'"{os.path.join(os.path.dirname(python), "pythonw.exe")}"') and command.endswith(
        'keepsake.pyw" --background'
    )
    assert pcinstall.installed("windows", env)["version"] == "0.28.0"


def test_reinstalling_the_same_version_replaces_it_cleanly(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    registry = FakeRegistry()
    pcinstall.install(package(tmp_path, "0.26.0"), "windows", env, registry=registry)
    stale = os.path.join(pcinstall.app_root("windows", env), "0.26.0", "stale.txt")
    open(stale, "w").close()
    pcinstall.install(package(tmp_path, "0.26.0"), "windows", env, registry=registry)
    assert not os.path.exists(stale)
    assert pcinstall.installed("windows", env) == {"version": "0.26.0", "previous": None}


def test_linux_install_writes_menu_and_autostart_entries(tmp_path):
    env = {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    result = pcinstall.install(package(tmp_path, "0.26.0"), "linux-desktop", env, python="/usr/bin/python3")
    menu = tmp_path / "data" / "applications" / "keepsake.desktop"
    start = tmp_path / "config" / "autostart" / "keepsake.desktop"
    assert menu.is_file() and start.is_file()
    assert "--background" in start.read_text() and "--background" not in menu.read_text()
    assert result["launcher"] in menu.read_text()


def test_uninstall_removes_the_program_and_start_up_but_never_settings(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    registry = FakeRegistry()
    settings = tmp_path / "Local" / "Keepsake" / "runtime" / "state.db"
    settings.parent.mkdir(parents=True)
    settings.write_text("keep me")
    pcinstall.install(package(tmp_path, "0.26.0"), "windows", env, registry=registry)
    pcinstall.uninstall("windows", env, registry=registry)
    assert registry.values == {} and not os.path.exists(pcinstall.app_root("windows", env))
    assert settings.read_text() == "keep me"


def test_bad_packages_and_decky_are_refused(tmp_path):
    with pytest.raises(pcinstall.InstallError, match="not a Haversack package"):
        pcinstall.install(str(tmp_path), "windows", {"LOCALAPPDATA": str(tmp_path / "L")}, registry=FakeRegistry())
    bad = tmp_path / "bad"
    bad.mkdir()
    for text in ("../evil", "1.0/../x", "", "a" * 50):
        (bad / "VERSION").write_text(text)
        with pytest.raises(pcinstall.InstallError):
            pcinstall.package_version(str(bad))
    with pytest.raises(pcinstall.InstallError, match="through Decky"):
        pcinstall.install(package(tmp_path, "0.26.0"), "decky")


class Answer:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n):
        return self.body


def test_the_launcher_trusts_host_json_only_when_the_host_answers(tmp_path):
    assert launcher.running_host(str(tmp_path)) is None  # no file
    (tmp_path / "host.json").write_text(json.dumps({"port": 47120, "token": "synthetic-token"}))
    seen = []

    def alive(request, timeout):
        seen.append((request.full_url, request.get_header("X-keepsake-token")))
        return Answer(b'{"ok": true, "result": {}}')

    assert launcher.running_host(str(tmp_path), alive) == "http://127.0.0.1:47120/#token=synthetic-token"
    assert seen == [("http://127.0.0.1:47120/api/call/get_status", "synthetic-token")]

    def gone(request, timeout):
        raise ConnectionRefusedError("nothing listens")

    assert launcher.running_host(str(tmp_path), gone) is None  # a stopped host's file
    assert launcher.running_host(str(tmp_path), lambda r, timeout: Answer(b'{"ok": false}')) is None  # refused
    assert launcher.running_host(str(tmp_path), lambda r, timeout: Answer(b"<html>other program</html>")) is None
    (tmp_path / "host.json").write_text(json.dumps({"port": 99999, "token": "t"}))
    assert launcher.running_host(str(tmp_path), alive) is None
