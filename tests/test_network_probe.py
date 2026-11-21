"""The network mount probe (ADR-0033) prints no paths. Its loop test moved to a Device check (ADR-0067)."""

import importlib.util
import pathlib

SPEC = importlib.util.spec_from_file_location(
    "network_mount_probe", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "network_mount_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_mounts_are_reported_by_type_and_depth_only(monkeypatch, tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text(
        "//nas/secret-share /run/user/1000/smb cifs rw 0 0\n"
        "/dev/sda1 / ext4 rw 0 0\n"
        "portal /run/user/1000/doc fuse.portal rw 0 0\n"
    )
    real_open = open
    monkeypatch.setattr(
        "builtins.open", lambda path, *a, **k: real_open(mounts if path == "/proc/self/mounts" else path, *a, **k)
    )
    found = probe.mounts()
    assert found == [
        {"fstype": "cifs", "depth": 4, "underRunUser": True},
        {"fstype": "fuse.portal", "depth": 4, "underRunUser": True},
    ]
    assert "secret" not in str(found)


def test_the_ssh_loop_test_is_gone():
    assert not hasattr(probe, "loop_test")
