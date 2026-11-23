"""The PC host updates itself (ADR-0043): signed checksums, a checked download, a safe unpack, a rollback.

Everything happens in tmp folders with a fake GitHub and a synthetic signing key.
"""

import asyncio
import hashlib
import io
import json
import os
import sys
import zipfile

import pytest

from keepsake import host as host_module
from keepsake import launcher, pcinstall, pcupdate
from keepsake.net import HttpResponse
from keepsake.update import RELEASES_URL, Updater
from test_signatures import public_text, signature_text


def package_zip(version="0.27.0", extra=None, version_text=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Keepsake-desktop/VERSION", (version_text or version) + "\n")
        archive.writestr("Keepsake-desktop/install.pyw", "installer")
        archive.writestr("Keepsake-desktop/py_modules/keepsake/__init__.py", "")
        archive.writestr("Keepsake-desktop/desktop/dist/main.js", "export {};")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def release_payload(version="0.27.0", desktop=True, signed=True):
    tag = f"v{version}"
    assets = [
        {"name": f"Keepsake-v{version}.zip", "browser_download_url": f"https://github.com/r/{tag}/zip"},
        {"name": "SHA256SUMS", "browser_download_url": f"https://github.com/r/{tag}/sums"},
    ]
    if desktop:
        assets.append(
            {"name": f"Haversack-desktop-v{version}.zip", "browser_download_url": f"https://github.com/r/{tag}/desktop"}
        )
    if signed:
        assets.append({"name": "SHA256SUMS.minisig", "browser_download_url": f"https://github.com/r/{tag}/sig"})
    return [
        {"tag_name": tag, "prerelease": False, "published_at": "2026-11-17T10:00:00Z", "body": "", "assets": assets}
    ]


class FakeGitHub:
    def __init__(self, payload, sums, signature):
        self.payload, self.sums, self.signature = payload, sums, signature

    def __call__(self, url, headers=None):
        if url == RELEASES_URL:
            return HttpResponse(status=200, headers={}, body=json.dumps(self.payload).encode())
        if url.endswith("/sums"):
            return HttpResponse(status=200, body=self.sums)
        if url.endswith("/sig"):
            return HttpResponse(status=200, body=self.signature.encode())
        return HttpResponse(status=404)


def ready_updater(tmp_path, data, payload=None, sums=None, signature=None, key=None):
    sums = sums if sums is not None else f"{hashlib.sha256(data).hexdigest()}  Haversack-desktop-v0.27.0.zip\n".encode()
    gh = FakeGitHub(payload or release_payload(), sums, signature or signature_text(sums))
    updater = Updater(str(tmp_path / "runtime"), "0.26.0", gh, public_key=key or public_text())
    os.makedirs(tmp_path / "runtime", exist_ok=True)
    updater.check("stable", force=True)
    return updater


def serve_bytes(data):
    def fetch(url, dest):
        with open(dest, "wb") as handle:
            handle.write(data)

    return fetch


def installed_env(tmp_path, version="0.26.0"):
    """A Linux PC with ``version`` installed by the real installer, start-up entries off."""
    env = {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    source = tmp_path / f"src-{version}"
    (source / "py_modules" / "keepsake").mkdir(parents=True)
    (source / "VERSION").write_text(version + "\n")
    pcinstall.install(str(source), "linux-desktop", env, python="python3", autostart=False)
    os.unlink(tmp_path / "data" / "applications" / "keepsake.desktop")  # so a stray rewrite would show
    return env


# Verifying the release


def test_the_pc_package_is_approved_only_under_a_valid_signature(tmp_path):
    data = package_zip()
    prepared = ready_updater(tmp_path, data).prepare_desktop("v0.27.0")
    assert prepared == {
        "ok": True,
        "signed": True,
        "url": "https://github.com/r/v0.27.0/desktop",
        "name": "Haversack-desktop-v0.27.0.zip",
        "version": "0.27.0",
        "sha256": hashlib.sha256(data).hexdigest(),
    }


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("unsigned", "unsigned-release"),
        ("forged", "bad-signature"),
        ("no-desktop-asset", "no-pc-package"),
        ("sums-without-desktop", "sums-missing-zip"),
        ("unknown-tag", "unknown-release"),
    ],
)
def test_the_pc_package_is_refused_without_proof(tmp_path, case, reason):
    data = package_zip()
    sums = f"{hashlib.sha256(data).hexdigest()}  Haversack-desktop-v0.27.0.zip\n".encode()
    kwargs = {}
    if case == "unsigned":
        kwargs["payload"] = release_payload(signed=False)
    elif case == "forged":
        kwargs["signature"] = signature_text(sums, seed=bytes(32))  # another key's signature
    elif case == "no-desktop-asset":
        kwargs["payload"] = release_payload(desktop=False)
    elif case == "sums-without-desktop":
        kwargs["sums"] = b"ab" * 32 + b"  Haversack-v0.27.0.zip\n"
    updater = ready_updater(tmp_path, data, **kwargs)
    tag = "v9.9.9" if case == "unknown-tag" else "v0.27.0"
    result = updater.prepare_desktop(tag)
    assert result["ok"] is False and result["reason"] == reason


# Installing it


def test_a_verified_update_installs_beside_the_running_version_and_keeps_it_for_rollback(tmp_path):
    env = installed_env(tmp_path)
    data = package_zip()
    prepared = ready_updater(tmp_path, data).prepare_desktop("v0.27.0")
    assert pcupdate.apply(prepared, "linux-desktop", serve_bytes(data), env) == {
        "ok": True,
        "version": "0.27.0",
        "restart": True,
    }
    root = pcinstall.app_root("linux-desktop", env)
    assert pcinstall.installed("linux-desktop", env) == {"version": "0.27.0", "previous": "0.26.0"}
    assert os.path.isfile(os.path.join(root, "0.27.0", "desktop", "dist", "main.js"))
    assert os.path.isfile(os.path.join(root, "0.26.0", "VERSION"))  # the running version is untouched
    assert not os.path.exists(os.path.join(root, "0.27.0", "install.pyw"))
    # Start-up and menu entries stay as the user set them.
    assert not os.path.exists(tmp_path / "data" / "applications" / "keepsake.desktop")
    assert not os.path.exists(tmp_path / "config" / "autostart")

    assert pcupdate.rollback("linux-desktop", env) == {"ok": True, "version": "0.26.0", "restart": True}
    assert pcinstall.installed("linux-desktop", env) == {"version": "0.26.0", "previous": "0.27.0"}


def test_a_download_that_does_not_match_the_signed_checksum_installs_nothing(tmp_path):
    env = installed_env(tmp_path)
    prepared = ready_updater(tmp_path, package_zip()).prepare_desktop("v0.27.0")
    with pytest.raises(pcupdate.UpdateError, match="signed checksum"):
        pcupdate.apply(prepared, "linux-desktop", serve_bytes(package_zip(extra={"Keepsake-desktop/x": "y"})), env)
    assert pcinstall.installed("linux-desktop", env)["version"] == "0.26.0"
    assert not os.path.exists(os.path.join(pcinstall.app_root("linux-desktop", env), "0.27.0"))


def test_a_package_whose_version_differs_from_the_signed_release_is_refused(tmp_path):
    env = installed_env(tmp_path)
    data = package_zip(version_text="0.99.0")
    prepared = ready_updater(tmp_path, data).prepare_desktop("v0.27.0")
    with pytest.raises(pcupdate.UpdateError, match="version"):
        pcupdate.apply(prepared, "linux-desktop", serve_bytes(data), env)
    assert pcinstall.installed("linux-desktop", env)["version"] == "0.26.0"


def test_an_unverified_preparation_is_never_downloaded():
    fetched = []
    with pytest.raises(pcupdate.UpdateError, match="unsigned-release"):
        pcupdate.apply({"ok": False, "reason": "unsigned-release"}, "linux-desktop", lambda u, d: fetched.append(u))
    assert fetched == []


@pytest.mark.parametrize(
    "name",
    [
        "Keepsake-desktop/../escape.txt",
        "../escape.txt",
        "other/file.txt",
        "/abs/file.txt",
        "Keepsake-desktop/C:/file.txt",
        "Keepsake-desktop\\..\\escape.txt",
        "Keepsake-desktop/sub\\..\\..\\escape.txt",  # a path on Windows, a plain name elsewhere
        "Keepsake-desktop/./file.txt",
        "Keepsake-desktopx/file.txt",
    ],
)
def test_a_member_outside_the_package_folder_is_refused_before_anything_is_written(tmp_path, name):
    zip_path = tmp_path / "p.zip"
    zip_path.write_bytes(package_zip(extra={name: "bad"}))
    dest = tmp_path / "out"
    with pytest.raises(pcupdate.UpdateError, match="outside"):
        pcupdate.unpack(str(zip_path), str(dest))
    assert not dest.exists() and not (tmp_path / "escape.txt").exists()


def test_size_and_count_limits(tmp_path, monkeypatch):
    zip_path = tmp_path / "p.zip"
    zip_path.write_bytes(package_zip(extra={"Keepsake-desktop/big.bin": "x" * 5000}))
    monkeypatch.setattr(pcupdate, "MAX_UNPACKED", 4000)
    with pytest.raises(pcupdate.UpdateError, match="larger"):
        pcupdate.unpack(str(zip_path), str(tmp_path / "a"))
    monkeypatch.setattr(pcupdate, "MAX_UNPACKED", 10**9)
    monkeypatch.setattr(pcupdate, "MAX_MEMBERS", 3)
    with pytest.raises(pcupdate.UpdateError, match="too many"):
        pcupdate.unpack(str(zip_path), str(tmp_path / "b"))


def test_a_broken_zip_is_an_update_error(tmp_path):
    env = installed_env(tmp_path)
    data = b"not a zip"
    prepared = {"ok": True, "url": "https://github.com/r/x", "sha256": hashlib.sha256(data).hexdigest(), "version": "1"}
    with pytest.raises(pcupdate.UpdateError, match="unpacked"):
        pcupdate.apply(prepared, "linux-desktop", serve_bytes(data), env)


def test_rollback_needs_a_previous_version_on_disk(tmp_path):
    env = installed_env(tmp_path)
    with pytest.raises(pcupdate.UpdateError, match="no previous"):
        pcupdate.rollback("linux-desktop", env)
    root = pcinstall.app_root("linux-desktop", env)
    with open(os.path.join(root, "current.json"), "w") as handle:
        json.dump({"version": "0.26.0", "previous": "0.25.0"}, handle)  # named, but pruned away
    with pytest.raises(pcupdate.UpdateError, match="no previous"):
        pcupdate.rollback("linux-desktop", env)


# The host-only calls


class FakeJobs:
    def __init__(self):
        self.reason = None

    def busy_reason(self):
        return self.reason


class FakeApp:
    def __init__(self, updater, version="0.26.0"):
        self.updater, self.version, self.jobs = updater, version, FakeJobs()


def control(tmp_path, env, updater=None, data=b""):
    stopped, spawned = [], []
    pc = host_module.PcControl(
        FakeApp(updater),
        "linux-desktop",
        lambda: stopped.append(True),
        env=env,
        spawn=spawned.append,
        fetch=serve_bytes(data),
    )
    return pc, stopped, spawned


def test_the_host_installs_a_verified_update_and_restarts_through_the_launcher(tmp_path, monkeypatch):
    monkeypatch.setattr(host_module, "RESTART_DELAY", 0.01)
    env = installed_env(tmp_path)
    data = package_zip()
    pc, stopped, spawned = control(tmp_path, env, ready_updater(tmp_path, data), data)

    async def scenario():
        assert (await pc.pc_update_status())["current"] == "0.26.0"
        assert await pc.pc_update_apply("v0.27.0") == {"ok": True, "version": "0.27.0", "restart": True}
        status = await pc.pc_update_status()
        assert (status["current"], status["previous"], status["running"]) == ("0.27.0", "0.26.0", "0.26.0")
        pc.app.jobs.reason = "syncing"
        assert (await pc.pc_restart())["reason"] == "busy" and spawned == []
        pc.app.jobs.reason = None
        assert await pc.pc_restart() == {"ok": True}
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    launcher_path = os.path.join(pcinstall.app_root("linux-desktop", env), "keepsake.pyw")
    assert spawned == [[pcinstall.pythonw(sys.executable), launcher_path, "--restart"]]
    assert stopped == [True]


def test_the_host_refuses_updates_it_cannot_prove_or_install(tmp_path):
    data = package_zip()
    env = {"XDG_DATA_HOME": str(tmp_path / "none")}
    pc, _, spawned = control(tmp_path, env, ready_updater(tmp_path, data), data)

    async def not_installed():
        assert (await pc.pc_update_apply("v0.27.0"))["reason"] == "not-installed"
        assert (await pc.pc_restart())["reason"] == "not-installed"
        assert (await pc.pc_rollback())["reason"] == "no-previous"

    asyncio.run(not_installed())
    assert spawned == []

    env = installed_env(tmp_path / "b")
    unsigned = ready_updater(tmp_path / "b", data, payload=release_payload(signed=False))
    pc, _, _ = control(tmp_path, env, unsigned, data)
    assert asyncio.run(pc.pc_update_apply("v0.27.0"))["reason"] == "unsigned-release"
    pc, _, _ = control(tmp_path, env, ready_updater(tmp_path / "b", data), b"tampered")
    result = asyncio.run(pc.pc_update_apply("v0.27.0"))
    assert result["reason"] == "install-failed" and "checksum" in result["detail"]
    assert pcinstall.installed("linux-desktop", env)["version"] == "0.26.0"


def test_the_launcher_waits_for_the_old_host_before_starting_the_new_one():
    answers = ["link", "link", None]
    slept = []
    assert launcher.wait_for_exit("rt", check=lambda _: answers.pop(0), sleep=slept.append) is True
    assert slept == [0.5, 0.5]
    slept.clear()
    assert launcher.wait_for_exit("rt", check=lambda _: "link", sleep=slept.append, timeout=2.0) is False
    assert len(slept) == 4


def test_host_calls_are_separate_from_the_plugin_calls():
    assert not host_module.HOST_CALLABLES & host_module.CALLABLES
