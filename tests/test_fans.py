"""Fan control (R24, ADR-0085): curves, the controller, the helper's EC access and lease, and the
service's profiles and loop. A fake EC models the 0x4E/0x4F index protocol byte by byte."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "helper", "py_modules"))

from keepsake.device import fancurve, fans  # noqa: E402
from keepsake.device.helper import HelperError  # noqa: E402
from keepsake_helper import fan  # noqa: E402

# Curves


def test_presets_are_valid_and_clean_checks_shape() -> None:
    for points in fancurve.PRESETS.values():
        assert fancurve.clean([list(p) for p in points]) == points
    bad = [
        [(50, 2000)],  # one point
        [(50, 2000), (40, 3000)],  # temperatures fall
        [(40, 3000), (50, 2000)],  # speeds fall
        [(40, 1000), (90, 3000)],  # below the floor
        [(40, 2000), (90, 5000)],  # above 4800 while locked
        [(40, 1500), (90, 1800)],  # hottest point under 2000
        [(10, 2000), (90, 3000)],  # temperature out of range
        [(40, 2000.5), (90, 3000)],  # not whole
        [(40, True), (90, 3000)],
        [(t, 3000) for t in range(20, 100, 8)],  # more than 8 points
    ]
    for points in bad:
        with pytest.raises(fancurve.CurveError):
            fancurve.clean(points)
    assert fancurve.clean([(40, 2000), (90, 5200)], unlocked=True)[-1] == (90, 5200)
    with pytest.raises(fancurve.CurveError):
        fancurve.clean([(40, 2000), (90, 5300)], unlocked=True)


def test_target_stepped_smooth_and_failsafe() -> None:
    curve = [(40, 1500), (60, 2500), (80, 3500)]
    assert fancurve.target(curve, 30) == 1500
    assert fancurve.target(curve, 50) == 2000
    assert fancurve.target(curve, 50, smooth=False) == 1500
    assert fancurve.target(curve, 90) == 3500
    assert fancurve.target(curve, 101) == 4800  # the failsafe beats the curve
    assert fancurve.target([(40, 2000), (90, 5200)], 101) == 5200


def test_controller_rises_at_once_and_falls_slowly() -> None:
    c = fancurve.Controller([(40, 1500), (60, 2500), (80, 3500)], smooth=False)
    assert c.update(80, 0) == 3500
    assert c.update(79, 1) == 3500  # inside the hysteresis
    assert c.update(60, 2) == 3500  # a real drop, but the dwell has not passed
    assert c.update(60, 6) == 3500
    assert c.update(60, 7.5) == 3200  # one step down after the dwell
    assert c.update(60, 8) == 3200  # the next step waits again
    assert c.update(85, 9) == 3500  # hotter: up at once
    assert c.update(101, 10) == 4800


def test_controller_is_within_the_perf_budget() -> None:
    c = fancurve.Controller(list(fancurve.DEFAULT))
    start = time.perf_counter()
    for i in range(10000):
        c.update(40 + (i % 60), i * 2.0)
    assert time.perf_counter() - start < 0.5  # a 2 s loop spends microseconds here


# The helper: a fake EC behind /dev/port


class FakeEC:
    def __init__(self, bios_ec: tuple[int, int] = (1, 16), rpm: int = 1800, follows: bool = True) -> None:
        self.mem = {0xC300: bios_ec[0], 0xC301: bios_ec[1], 0xC683: 177, 0xC6C8: 0, 0xC6C9: 0}
        self.set_rpm(rpm)
        self.index = 0
        self.selector = 0
        self.regs = {0x10: 0, 0x11: 0}
        self.follows = follows
        self.writes: list[tuple[int, int]] = []

    def set_rpm(self, rpm: int) -> None:
        self.mem[0xC6C0], self.mem[0xC6C1] = rpm & 0xFF, rpm >> 8
        self.mem[0xC664], self.mem[0xC665] = rpm & 0xFF, rpm >> 8

    def address(self) -> int:
        return (self.regs[0x11] << 8) | self.regs[0x10]

    def out(self, port: int, value: int) -> None:
        if port == fan.INDEX:
            self.index = value
        elif self.index == 0x2E:
            self.selector = value
        elif self.selector in self.regs:
            self.regs[self.selector] = value
        elif self.selector == 0x12:
            self.mem[self.address()] = value
            self.writes.append((self.address(), value))
            override = self.mem[0xC6C8] | (self.mem[0xC6C9] << 8)
            if self.follows and override >= fan.MIN_RPM:
                self.set_rpm(override)

    def inb(self, port: int) -> int:
        if self.selector in self.regs:
            return self.regs[self.selector]
        return self.mem.get(self.address(), 0)

    def close(self) -> None:
        pass


def dmi(
    tmp_path: Any,
    product: str = "83N0",
    version: str = "Legion Go 8ASP2",
    board: str = "LNVNB161216",
    bios: str = "RRCN16WW",
) -> str:
    folder = tmp_path / "dmi"
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in {
        "sys_vendor": "LENOVO",
        "product_name": product,
        "product_version": version,
        "board_name": board,
        "bios_version": bios,
    }.items():
        (folder / name).write_text(value + "\n")
    return str(folder)


def hwmon(tmp_path: Any, cpu: int = 55000, gpu: int = 60000) -> str:
    for i, (name, value) in enumerate((("k10temp", cpu), ("amdgpu", gpu))):
        folder = tmp_path / "hwmon" / f"hwmon{i}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "name").write_text(name + "\n")
        (folder / "temp1_input").write_text(f"{value}\n")
    return str(tmp_path / "hwmon")


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def helper_fans(tmp_path: Any, ec: FakeEC | None = None, **kwargs: Any) -> tuple[fan.Fans, FakeEC, Clock]:
    ec = ec or FakeEC()
    clock = Clock()
    proc = tmp_path / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "modules").write_text(kwargs.pop("modules", "hid_playstation 1 0 - Live\n"))
    (proc / "ioports").write_text(kwargs.pop("ioports", "0000-001f : dma1\n0060-0060 : keyboard\n"))
    f = fan.Fans(
        opener=lambda: ec,
        dmi=kwargs.pop("dmi", None) or dmi(tmp_path),
        proc=str(proc),
        hwmon=kwargs.pop("hwmon", None) or hwmon(tmp_path),
        attrs=str(tmp_path / "attrs"),
        clock=clock,
        sleep=clock.sleep,
        **kwargs,
    )
    return f, ec, clock


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, "go2"),
        ({"version": "Legion Go 8AHP2", "product": "83N1", "bios": "RQCN10WW"}, "go2-beta"),
        ({"product": "83E1"}, "go1"),
        ({"board": "OTHER"}, None),
        ({"product": "82XX"}, None),
    ],
)
def test_model_from_exact_dmi(tmp_path: Any, fields: dict[str, str], expected: str | None) -> None:
    assert fan.model(dmi(tmp_path, **fields)) == expected


def test_ec_reads_and_writes_only_allowed_addresses(tmp_path: Any) -> None:
    ec = fan.EC(FakeEC())
    assert ec.word(fan.RPM) == 1800
    with pytest.raises(fan.FanError):
        ec.read(0xC000)
    with pytest.raises(fan.FanError):
        ec.write(fan.MODE, 179)
    assert ec.set_override(3000) == 3000
    assert ec.set_override(0) == 0
    with pytest.raises(fan.FanError):
        ec.set_override(1000)


def test_ec_notices_a_selector_that_did_not_stick() -> None:
    class Deaf(FakeEC):
        def inb(self, port: int) -> int:
            return 0xAA if self.selector in self.regs else super().inb(port)

    with pytest.raises(fan.FanError, match="address"):
        fan.EC(Deaf()).word(fan.RPM)


def test_set_rpm_needs_validated_firmware_a_lease_and_range(tmp_path: Any) -> None:
    f, _ec, _clock = helper_fans(tmp_path)
    assert f.set_rpm(3000, 10)["override"] == 3000 and f.controlling
    with pytest.raises(fan.FanError, match="lease"):
        f.set_rpm(3000, 0)
    with pytest.raises(fan.FanError, match="lease"):
        f.set_rpm(3000, 120)
    with pytest.raises(fan.FanError):
        f.set_rpm(1200, 10)
    unchecked, _, _ = helper_fans(tmp_path / "b", ec=FakeEC(bios_ec=(1, 15)))
    with pytest.raises(fan.FanError, match="fan test"):
        unchecked.set_rpm(3000, 10)


def test_set_rpm_refuses_other_fan_drivers_and_port_owners(tmp_path: Any) -> None:
    f, _, _ = helper_fans(tmp_path, modules="legion_laptop 1 0 - Live\n")
    with pytest.raises(fan.FanError, match="legion_laptop"):
        f.set_rpm(3000, 10)
    g, _, _ = helper_fans(tmp_path / "b", ioports="004e-004f : some_driver\n")
    with pytest.raises(fan.FanError, match="EC ports"):
        g.set_rpm(3000, 10)


def test_failsafe_and_lease_expiry(tmp_path: Any) -> None:
    f, ec, clock = helper_fans(tmp_path)
    f.set_rpm(2000, 10)
    assert f.tick() is None
    hot = tmp_path / "hwmon" / "hwmon1" / "temp1_input"
    hot.write_text("101500\n")
    assert f.tick() == "failsafe"
    assert ec.mem[0xC6C8] | (ec.mem[0xC6C9] << 8) == 4800
    assert f.set_rpm(2000, 10)["override"] == 4800  # still hot: never below the ceiling
    hot.write_text("60000\n")
    clock.now += 11
    assert f.tick() == "lease expired"
    assert ec.mem[0xC6C8] | (ec.mem[0xC6C9] << 8) == 0 and not f.controlling


def test_renew_keeps_control(tmp_path: Any) -> None:
    f, _, clock = helper_fans(tmp_path)
    f.set_rpm(2500, 10)
    clock.now += 8
    f.renew(10)
    clock.now += 8
    assert f.tick() is None and f.controlling


def test_selftest_passes_records_and_hands_back(tmp_path: Any) -> None:
    recorded: list[tuple[str, str]] = []
    f, ec, _ = helper_fans(tmp_path, ec=FakeEC(bios_ec=(1, 15)), record_pass=recorded.append)
    found = f.selftest()
    assert found["passed"] and recorded == [("RRCN16WW", "1.15")]
    assert ec.mem[0xC6C8] == 0 and ec.mem[0xC6C9] == 0 and not f.controlling


def test_selftest_fails_when_the_fan_does_not_follow(tmp_path: Any) -> None:
    recorded: list[tuple[str, str]] = []
    f, ec, _ = helper_fans(tmp_path, ec=FakeEC(bios_ec=(1, 15), follows=False), record_pass=recorded.append)
    assert f.selftest()["passed"] is False and recorded == []
    assert ec.mem[0xC6C8] | (ec.mem[0xC6C9] << 8) == 0


def test_go1_full_speed_through_the_firmware_attribute(tmp_path: Any) -> None:
    attr = tmp_path / "attrs" / "lenovo-wmi-other-0" / "attributes" / "fan_full_speed"
    attr.mkdir(parents=True)
    (attr / "current_value").write_text("0\n")
    f, _, clock = helper_fans(tmp_path, dmi=dmi(tmp_path, product="83E1"))
    assert f.full_speed(True, 10) == {"fullSpeed": True}
    assert (attr / "current_value").read_text().strip() == "1"
    with pytest.raises(fan.FanError):
        f.set_rpm(3000, 10)  # no RPM override on the Go 1
    clock.now += 11
    assert f.tick() == "lease expired"
    assert (attr / "current_value").read_text().strip() == "0"


def test_status_reports_firmware_and_readings(tmp_path: Any) -> None:
    f, _, _ = helper_fans(tmp_path)
    found = f.status()
    assert found["model"] == "go2" and found["validated"] and found["rpm"] == 1800
    assert found["firmware"] == {"bios": "RRCN16WW", "ec": "1.16"} and found["mode"] == "balanced"
    assert found["temperature"] == 60.0


# The service


class FakeHelper:
    def __init__(self, model: str = "go2", fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.model = model
        self.fail = fail

    def status(self) -> dict[str, Any]:
        return {"installed": True, "ready": True}

    def call(self, job: str, timeout: float = 20.0, **args: Any) -> dict[str, Any]:
        self.calls.append((job, args))
        if self.fail and job == "fan.set":
            raise HelperError("this BIOS and EC have not been checked: run the fan test first")
        if job == "fan.status":
            return {"model": self.model}
        return {}


def sysfs(tmp_path: Any, temp: int = 55000, mode: str = "balanced") -> str:
    root = tmp_path / "sys"
    folder = root / "class" / "hwmon" / "hwmon0"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "name").write_text("k10temp\n")
    (folder / "temp1_input").write_text(f"{temp}\n")
    prof = root / "class" / "platform-profile" / "platform-profile-0"
    prof.mkdir(parents=True, exist_ok=True)
    (prof / "profile").write_text(mode + "\n")
    return str(root)


def service(
    tmp_path: Any, helper: FakeHelper | None = None, tools: list[str] | None = None
) -> tuple[fans.Fans, FakeHelper, Clock]:
    helper = helper or FakeHelper()
    clock = Clock()
    walls = {"t": 1_800_000_000.0}

    def wall() -> float:
        return walls["t"] + (clock.now - 100.0)

    s = fans.Fans(
        fans.FanStore(str(tmp_path / "fan-profiles.json")),
        helper,
        lambda: list(tools or []),
        sysfs(tmp_path),
        clock=clock,
        wall=wall,
    )  # type: ignore[arg-type]
    s.walls = walls  # type: ignore[attr-defined]
    return s, helper, clock


def test_store_defaults_and_profile_edits(tmp_path: Any) -> None:
    s, _, _ = service(tmp_path)
    data = s.settings()
    assert (
        set(data["profiles"]) == {"Balanced", "Quiet", "Cool"} and data["default"] == "Balanced" and not data["enabled"]
    )
    s.save_profile("Mine", [[40, 1600], [90, 3000]], make_default=True)
    s.assign("mode", "performance", "Cool")
    s.assign("game", "4000123", "Quiet")
    data = s.settings()
    assert (
        data["default"] == "Mine" and data["modes"] == {"performance": "Cool"} and data["games"] == {"4000123": "Quiet"}
    )
    s.delete_profile("Quiet")
    assert "4000123" not in s.settings()["games"]
    with pytest.raises(fans.FanSettingsError):
        s.save_profile("Bad", [[40, 1000], [90, 3000]])
    with pytest.raises(fans.FanSettingsError):
        s.assign("mode", "turbo", "Cool")


def test_choose_game_then_mode_then_default(tmp_path: Any) -> None:
    s, _, _ = service(tmp_path)
    s.assign("mode", "balanced", "Cool")
    s.assign("game", "4000123", "Quiet")
    assert s.choose(s.settings()) == "Cool"
    s.game = 4000123
    assert s.choose(s.settings()) == "Quiet"
    s.game = 4000456
    assert s.choose(s.settings()) == "Cool"


def test_tick_sends_on_change_renews_otherwise_and_respects_off(tmp_path: Any) -> None:
    s, helper, clock = service(tmp_path)
    assert s.tick() is None and helper.calls == []  # off by default: nothing at all
    s.set_options(enabled=True)
    rpm = s.tick()
    assert helper.calls[-1] == ("fan.set", {"rpm": rpm, "lease": fans.LEASE})
    clock.now += 2
    s.tick()
    assert helper.calls[-1] == ("fan.renew", {"lease": fans.LEASE})


def test_tick_resends_after_sleep(tmp_path: Any) -> None:
    s, helper, clock = service(tmp_path)
    s.set_options(enabled=True)
    s.tick()
    clock.now += 2
    s.walls["t"] += 600  # type: ignore[attr-defined]  # the wall clock jumped: the device slept
    s.tick()
    assert helper.calls[-1][0] == "fan.set"


def test_another_fan_tool_means_read_only(tmp_path: Any) -> None:
    s, helper, _ = service(tmp_path, tools=["Handheld Daemon"])
    s.set_options(enabled=True)
    assert s.tick() is None
    assert [c for c in helper.calls if c[0] != "fan.status"] == []
    assert "Handheld Daemon" in (s.problem or "")


def test_helper_refusal_is_shown_not_raised(tmp_path: Any) -> None:
    s, _, _ = service(tmp_path, helper=FakeHelper(fail=True))
    s.set_options(enabled=True)
    assert s.tick() is None and "fan test" in (s.problem or "")


def test_stop_hands_back(tmp_path: Any) -> None:
    s, helper, _ = service(tmp_path)
    s.set_options(enabled=True)
    s.tick()
    s.stop()
    assert helper.calls[-1][0] == "fan.release"


def test_go1_full_speed_is_held_by_the_lease(tmp_path: Any) -> None:
    s, helper, clock = service(tmp_path, helper=FakeHelper(model="go1"))
    s.set_options(full_speed=True)
    s.tick()
    assert ("fan.full", {"on": True, "lease": fans.LEASE}) in helper.calls
    clock.now += 2
    s.tick()
    assert helper.calls[-1] == ("fan.renew", {"lease": fans.LEASE})
    s.set_options(full_speed=False)
    s.tick()
    assert helper.calls[-1][0] == "fan.release"


def test_relocking_brings_curves_back_inside_the_limits(tmp_path: Any) -> None:
    s, _, _ = service(tmp_path)
    s.set_options(unlocked=True)
    s.save_profile("Loud", [[40, 2000], [90, 5200]])
    s.set_options(unlocked=False)
    assert s.settings()["profiles"]["Loud"][-1] == (90, 4800)


def test_an_override_the_ec_ignores_is_an_error() -> None:
    class Stubborn(FakeEC):
        def out(self, port: int, value: int) -> None:
            if port == fan.DATA and self.index == 0x2F and self.selector == 0x12:
                return  # the EC drops the write
            super().out(port, value)

    with pytest.raises(fan.FanError, match="did not keep"):
        fan.EC(Stubborn()).set_override(3000)
