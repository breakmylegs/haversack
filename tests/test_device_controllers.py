"""R21 stage 5 (ADR-0078): the Legion controllers, read-only, from what the kernel shows. Synthetic trees (P12).

HID device folders are named like ``0003:17EF:61EB.0004``. Windows cannot make that name, so the
test that needs it runs on POSIX only (the device run).
"""

import asyncio
import os

import pytest

from keepsake import devicechecks
from keepsake.device import controllers


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def legion_tree(root):
    sys = root / "sys"
    put(sys / "class/power_supply/BAT0/type", "Battery")  # the system battery: not a controller
    put(sys / "class/power_supply/BAT0/capacity", "70")
    put(sys / "class/power_supply/hid-left/type", "Battery")
    put(sys / "class/power_supply/hid-left/scope", "Device")
    put(sys / "class/power_supply/hid-left/capacity", "55")
    put(sys / "class/power_supply/hid-left/status", "Discharging")
    put(sys / "class/power_supply/hid-left/model_name", "Legion Controller L")
    ring = sys / "class/leds/go:rgb:joystick_rings" if os.name != "nt" else sys / "class/leds/go_rgb_joystick_rings"
    put(ring / "effect", "rainbow")
    put(ring / "brightness", "120")
    proc = root / "proc"
    put(proc / "900/comm", "inputplumber")
    put(proc / "901/comm", "bash")
    return str(sys), str(proc)


def test_batteries_lights_and_tools_are_read(tmp_path, monkeypatch):
    sys, proc = legion_tree(tmp_path)
    if os.name == "nt":
        monkeypatch.setattr(controllers.glob, "glob", _windows_glob(controllers.glob.glob))
    status = controllers.status(sys, proc)
    assert status["batteries"] == [
        {"name": "Legion Controller L", "percent": 55, "level": None, "status": "Discharging"}
    ]
    assert status["rings"]["effect"] == "rainbow" and status["rings"]["brightness"] == "120"
    assert status["tools"] == ["InputPlumber"]
    assert status["controllers"] == []


def _windows_glob(real):
    # Windows cannot name the LED folder "go:rgb:joystick_rings": the synthetic tree uses "_" there.
    def glob(pattern, *args, **kwargs):
        return real(pattern.replace("*:rgb:joystick_rings", "*_rgb_joystick_rings"), *args, **kwargs)

    return glob


def test_an_older_kernel_shows_nothing(tmp_path):
    status = controllers.status(str(tmp_path / "sys"), str(tmp_path / "proc"))
    assert status == {"batteries": [], "controllers": [], "rings": None, "tools": []}


@pytest.mark.posix
@pytest.mark.skipif(os.name == "nt", reason="HID device names need POSIX")
def test_the_legion_controller_settings_are_read(tmp_path):
    sys, proc = legion_tree(tmp_path)
    pad = tmp_path / "sys/bus/hid/devices/0003:17EF:61EB.0004"
    put(pad / "mode", "standard")
    put(pad / "rumble_intensity", "medium")
    put(pad / "left_handle/imu_enabled", "true")
    put(pad / "left_handle/auto_sleep_time", "10")
    put(pad / "touchpad/enabled", "true")
    put(tmp_path / "sys/bus/hid/devices/0003:046D:C52B.0001/mode", "x")  # a mouse: not a Legion controller
    (found,) = controllers.status(sys, proc)["controllers"]
    assert found["id"] == "0003:17EF:61EB" and found["settings"] == {"mode": "standard", "rumble_intensity": "medium"}
    assert found["left"] == {"imu_enabled": "true", "auto_sleep_time": "10"} and found["touchpad"] == {
        "enabled": "true"
    }


@pytest.mark.parametrize("empty", [False, True])
def test_device_check(tmp_path, monkeypatch, empty):
    sys, proc = legion_tree(tmp_path)
    if os.name == "nt":
        monkeypatch.setattr(controllers.glob, "glob", _windows_glob(controllers.glob.glob))
    found = (
        controllers.status(str(tmp_path / "none"), str(tmp_path / "none")) if empty else controllers.status(sys, proc)
    )

    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"controllers": probe})
    outcome = asyncio.run(devicechecks.run("controllers", ctx))
    assert outcome["status"] == ("warn" if empty else "pass") and outcome["title"] == "Controllers"
