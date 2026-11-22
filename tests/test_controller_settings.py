"""The Legion controllers' own settings and stick lights (R24, ADR-0086), against a fake hid-lenovo-go tree."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "helper", "py_modules"))

from keepsake.device import controller_settings as cs  # noqa: E402
from keepsake.device.helper import HelperError  # noqa: E402
from keepsake_helper import controller  # noqa: E402

HID_NAME = "0003_17EF_61EB.0001" if sys.platform == "win32" else "0003:17EF:61EB.0001"
VALUES = {
    "mode": "xinput",
    "os_mode": "linux",
    "rumble_intensity": "medium",
    "fps_mode_dpi": "800",
    "left_handle/auto_sleep_time": "10",
    "right_handle/auto_sleep_time": "10",
    "left_handle/imu_enabled": "true",
    "left_handle/rumble_mode": "standard",
    "right_handle/rumble_mode": "standard",
    "touchpad/enabled": "true",
    "touchpad/vibration_enabled": "true",
    "touchpad/vibration_intensity": "low",
}
LED_NAME = "go_rgb_joystick_rings" if sys.platform == "win32" else controller.LED_NAME


@pytest.fixture(autouse=True)
def windows_names(monkeypatch: Any) -> None:
    monkeypatch.setattr(controller, "LED_NAME", LED_NAME)
    monkeypatch.setattr(cs, "LED", LED_NAME)


LED = {
    "enabled": "true",
    "mode": "custom",
    "effect": "monocolor",
    "profile": "1",
    "speed": "50",
    "brightness": "80",
    "multi_intensity": "100 0 0",
}


def tree(tmp_path: Any) -> str:
    root = tmp_path / "sys"
    hid = root / "bus" / "hid" / "devices" / HID_NAME
    for key, value in VALUES.items():
        path = hid / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n")
    (hid / "reset_mcu").write_text("")
    led = root / "class" / "leds" / LED_NAME
    led.mkdir(parents=True)
    for key, value in LED.items():
        (led / key).write_text(value + "\n")
    return str(root)


def read_file(root: str, key: str) -> str:
    base = controller.device_dir(root)
    assert base is not None
    with open(controller.path_for(base, root, key), encoding="ascii") as handle:
        return handle.read().strip()


# The helper's job


def test_values_are_checked_against_the_driver() -> None:
    assert controller.normal("led/multi_intensity", [100, 50, 0]) == "100 50 0"
    assert controller.normal("left_handle/imu_enabled", True) == "true"
    assert controller.normal("led/speed", "75") == "75"
    for key, value in [
        ("reset_mcu", "1"),  # destructive: never offered
        ("right_handle/reset", "1"),
        ("right_handle/imu_enabled", "true"),  # a driver bug makes it the bypass
        ("left_handle/calibrate_gyro", "start"),
        ("led/mode", "dynamic"),
        ("led/multi_intensity", [101, 0, 0]),
        ("led/multi_intensity", [1, 2]),
        ("led/speed", 101),
        ("led/profile", 0),
        ("fps_mode_dpi", "1000"),
        ("mode", "steam"),
        ("left_handle/auto_sleep_time", 256),
        ("led/brightness", True),
    ]:
        with pytest.raises(controller.ControllerError):
            controller.normal(key, value)


def test_apply_writes_reads_back_and_keeps_the_light_order(tmp_path: Any, monkeypatch: Any) -> None:
    root = tree(tmp_path)
    order: list[str] = []
    real_read = controller._read

    def spy(path: str) -> str:
        order.append("read:" + os.path.basename(path))
        return real_read(path)

    monkeypatch.setattr(controller, "_read", spy)
    done = controller.apply(
        {"led/speed": 20, "led/effect": "breathe", "led/multi_intensity": [0, 0, 100], "rumble_intensity": "high"},
        root,
        sleep=lambda s: None,
    )
    assert done["settings"] == {
        "led/speed": "20",
        "led/effect": "breathe",
        "led/multi_intensity": "0 0 100",
        "rumble_intensity": "high",
    }
    assert order[0] == "read:profile"  # the driver must know the profile before any light write
    writes = [o for o in order if o.startswith("read:") and o != "read:profile"]
    assert writes[-1] == "read:speed"  # the speed is written (and read back) last
    assert read_file(root, "led/multi_intensity") == "0 0 100" and read_file(root, "rumble_intensity") == "high"


def test_nothing_is_written_when_one_value_is_bad(tmp_path: Any) -> None:
    root = tree(tmp_path)
    with pytest.raises(controller.ControllerError):
        controller.apply({"rumble_intensity": "high", "reset_mcu": "1"}, root)
    assert read_file(root, "rumble_intensity") == "medium"


def test_a_value_the_controller_does_not_keep_is_an_error(tmp_path: Any, monkeypatch: Any) -> None:
    root = tree(tmp_path)
    monkeypatch.setattr(controller, "_read", lambda path: "low")  # the controller never takes it
    with pytest.raises(controller.ControllerError, match="did not keep"):
        controller.apply({"rumble_intensity": "high"}, root, sleep=lambda s: None)


def test_no_driver_means_no_settings(tmp_path: Any) -> None:
    with pytest.raises(controller.ControllerError):
        controller.read(str(tmp_path))
    assert cs.read(str(tmp_path)) is None


# Keepsake's side


class FakeHelper:
    def __init__(self, root: str, fail: bool = False) -> None:
        self.root, self.fail = root, fail
        self.calls: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        return {"ready": True}

    def call(self, job: str, **args: Any) -> dict[str, Any]:
        assert job == "ctrl.set"
        self.calls.append(dict(args["values"]))
        if self.fail:
            raise HelperError("the controller did not keep rumble_intensity")
        return controller.apply(args["values"], self.root, sleep=lambda s: None)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.jump = 0.0

    def mono(self) -> float:
        return self.now

    def wall(self) -> float:
        return 1_800_000_000.0 + self.now + self.jump


def make(
    tmp_path: Any, tools: dict[str, bool] | None = None, fail: bool = False
) -> tuple[cs.ControllerSettings, FakeHelper, Clock, str]:
    root = tree(tmp_path)
    helper = FakeHelper(root, fail)
    clock = Clock()
    s = cs.ControllerSettings(
        str(tmp_path / "controller-settings.json"), helper, lambda: dict(tools or {}), root, clock.mono, clock.wall
    )  # type: ignore[arg-type]
    return s, helper, clock, root


def test_keepsake_reads_without_root_and_reports_status(tmp_path: Any) -> None:
    s, _, _, _ = make(tmp_path)
    found = s.status()
    assert (
        found["present"] and found["current"]["led/effect"] == "monocolor" and found["current"]["fps_mode_dpi"] == "800"
    )
    assert set(found["allowed"]) == set(cs.KEYS)


def test_other_tools_limit_what_is_offered(tmp_path: Any) -> None:
    s, helper, _, _ = make(tmp_path, tools={"hhd": True})
    assert s.allowed() == []
    with pytest.raises(cs.SettingsError, match="Handheld Daemon"):
        s.set({"rumble_intensity": "high"}, keep=False)
    assert helper.calls == []
    t, helper2, _, _ = make(tmp_path / "b", tools={"inputplumber": True})
    assert "os_mode" not in t.allowed() and "touchpad/vibration_enabled" not in t.allowed()
    with pytest.raises(cs.SettingsError, match="another tool"):
        t.set({"os_mode": "windows"}, keep=False)
    assert helper2.calls == []


def test_kept_settings_come_back_after_a_reconnect_and_after_sleep(tmp_path: Any) -> None:
    s, helper, clock, root = make(tmp_path)
    s.set({"rumble_intensity": "high"}, keep=True)
    assert s.kept() == {"rumble_intensity": "high"}
    helper.calls.clear()
    assert s.tick() is True  # first sight of the controller
    assert helper.calls == [{"rumble_intensity": "high"}]
    clock.now += 10
    assert s.tick() is False  # still there, nothing to do
    clock.now += 10
    clock.jump += 600  # the device slept
    assert s.tick() is True
    hid = os.path.join(root, "bus", "hid", "devices", HID_NAME)
    os.rename(hid, hid + ".gone")
    os.rename(os.path.join(root, "class", "leds"), os.path.join(root, "class", "leds.gone"))
    clock.now += 10
    assert s.tick() is False  # unplugged
    os.rename(hid + ".gone", hid)
    os.rename(os.path.join(root, "class", "leds.gone"), os.path.join(root, "class", "leds"))
    clock.now += 10
    assert s.tick() is True  # back again


def test_unkept_changes_are_not_reapplied_and_forget_clears(tmp_path: Any) -> None:
    s, helper, _, _ = make(tmp_path)
    s.set({"rumble_intensity": "high"}, keep=False)
    assert s.kept() == {}
    helper.calls.clear()
    assert s.tick() is False and helper.calls == []
    s.set({"led/brightness": 40}, keep=True)
    s.forget()
    assert s.kept() == {}


def test_a_failing_reapply_is_shown_not_raised(tmp_path: Any) -> None:
    s, _, _, _ = make(tmp_path)
    s.set({"rumble_intensity": "high"}, keep=True)
    s.helper.fail = True  # type: ignore[attr-defined]
    s.present = False
    assert s.tick() is False and "did not keep" in (s.problem or "")


def test_the_watch_interval_is_cheap(tmp_path: Any) -> None:
    s, _, _, _ = make(tmp_path)
    start = time.perf_counter()
    for _ in range(200):
        s.tick()
    assert time.perf_counter() - start < 2.0
