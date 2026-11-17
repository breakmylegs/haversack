"""The network mount probe (ADR-0033) prints no paths and always deletes the loop device it made."""

import importlib.util
import pathlib
import subprocess

SPEC = importlib.util.spec_from_file_location(
    "network_mount_probe", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "network_mount_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def fake_run(answers, calls):
    def run(command, **kw):
        calls.append(command[1])
        code, out, err = answers[command[1]]
        return subprocess.CompletedProcess(command, code, out, err)

    return run


def test_loop_test_sets_up_and_deletes_and_hides_paths(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        fake_run(
            {"loop-setup": (0, "Mapped file /x/secret-share/a.iso as /dev/loop9.\n", ""), "loop-delete": (0, "", "")},
            calls,
        ),
    )
    result = probe.loop_test(str(tmp_path / "a.iso"))
    assert result["loopSetup"] == "ok" and result["loopDelete"] == "ok" and calls == ["loop-setup", "loop-delete"]
    assert "secret-share" not in repr(result)


def test_loop_test_failure_is_reported_without_paths(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        fake_run(
            {"loop-setup": (1, "", "Error opening /run/user/1000/gvfs/smb-share:server=nas/a.iso: denied")}, calls
        ),
    )
    result = probe.loop_test(str(tmp_path / "a.iso"))
    assert result["loopSetup"] == "failed (exit 1)" and calls == ["loop-setup"]
    assert "nas" not in result["loopSetupError"] and "<path>" in result["loopSetupError"]
