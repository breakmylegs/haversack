"""Separate SPL, SPPT and FPPT through the Keepsake Helper (R24, ADR-0084). A fake sysfs tree stands in
for the firmware attributes; a fake steamos-manager for the mode."""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "helper", "py_modules"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from keepsake.device import performance as perf  # noqa: E402
from keepsake.device import powerlimits, steamos  # noqa: E402
from keepsake.device.helper import HelperError  # noqa: E402
from keepsake_helper import power, server  # noqa: E402
from test_device_performance import APPID, FakeManager  # noqa: E402

RANGES = {"spl": (8, 30, 15), "sppt": (8, 32, 17), "fppt": (8, 41, 20)}


def firmware(tmp_path: Any, profile: str = "custom", step: int = 1) -> tuple[str, str]:
    """A firmware-attributes tree and a platform profile; returns (attributes root, profile glob)."""
    attrs = tmp_path / "sys" / "class" / "firmware-attributes" / "lenovo-wmi-other-0" / "attributes"
    for key, (low, high, current) in RANGES.items():
        folder = attrs / power.KEYS[key]
        folder.mkdir(parents=True)
        (folder / "current_value").write_text(f"{current}\n")
        (folder / "min_value").write_text(f"{low}\n")
        (folder / "max_value").write_text(f"{high}\n")
        (folder / "scalar_increment").write_text(f"{step}\n")
    prof = tmp_path / "sys" / "class" / "platform-profile" / "platform-profile-0"
    prof.mkdir(parents=True)
    (prof / "name").write_text("lenovo-wmi-gamezone\n")
    (prof / "profile").write_text(f"{profile}\n")
    return str(tmp_path / "sys" / "class" / "firmware-attributes"), str(prof.parent / "platform-profile-*")


def currents(root: str) -> dict[str, int]:
    return {k: v["current"] for k, v in power.read(root).items()}


# The helper's job


def test_helper_applies_reads_back_and_refuses_outside_custom(tmp_path: Any) -> None:
    root, prof = firmware(tmp_path)
    assert power.apply({"spl": 25, "sppt": 28, "fppt": 35}, root, prof) == {"spl": 25, "sppt": 28, "fppt": 35}
    assert currents(root) == {"spl": 25, "sppt": 28, "fppt": 35}
    root2, prof2 = firmware(tmp_path / "b", profile="balanced")
    with pytest.raises(power.PowerError, match="Custom"):
        power.apply({"spl": 25, "sppt": 28, "fppt": 35}, root2, prof2)
    assert currents(root2) == {"spl": 15, "sppt": 17, "fppt": 20}


@pytest.mark.parametrize(
    "values",
    [
        {"spl": 31, "sppt": 31, "fppt": 35},  # SPL above its maximum
        {"spl": 7, "sppt": 17, "fppt": 20},  # below the minimum
        {"spl": 20, "sppt": 18, "fppt": 25},  # not rising
        {"spl": 15, "sppt": 17},  # one missing
        {"spl": 15.5, "sppt": 17, "fppt": 20},  # not whole watts
        {"spl": True, "sppt": 17, "fppt": 20},
        {"spl": 15, "sppt": 17, "fppt": 20, "extra": 1},
    ],
)
def test_helper_refuses_bad_values(tmp_path: Any, values: dict[str, Any]) -> None:
    root, prof = firmware(tmp_path)
    with pytest.raises(power.PowerError):
        power.apply(values, root, prof)
    assert currents(root) == {"spl": 15, "sppt": 17, "fppt": 20}


def test_helper_honours_the_step(tmp_path: Any) -> None:
    root, prof = firmware(tmp_path, step=2)
    with pytest.raises(power.PowerError):
        power.apply({"spl": 15, "sppt": 18, "fppt": 22}, root, prof)  # 15 is off the 8, 10, 12 step
    assert power.apply({"spl": 16, "sppt": 18, "fppt": 22}, root, prof)["spl"] == 16


@pytest.mark.parametrize(
    ("current", "wanted"),
    [
        ({"spl": 15, "sppt": 17, "fppt": 20}, {"spl": 25, "sppt": 28, "fppt": 35}),  # all up
        ({"spl": 25, "sppt": 28, "fppt": 35}, {"spl": 10, "sppt": 12, "fppt": 14}),  # all down
        ({"spl": 15, "sppt": 17, "fppt": 20}, {"spl": 18, "sppt": 18, "fppt": 18}),
    ],
)
def test_write_order_never_crosses(current: dict[str, int], wanted: dict[str, int]) -> None:
    state = dict(current)
    for key in power.order(current, wanted):
        state[key] = wanted[key]
        assert state["spl"] <= state["sppt"] <= state["fppt"], state
    assert state == wanted


def test_helper_jobs_through_the_interface(tmp_path: Any) -> None:
    root, prof = firmware(tmp_path)
    helper = server.Helper("0.43.0", 1000, str(tmp_path / "state.json"), None, power_root=root, profile_glob=prof)

    def req(job: str, **args: Any) -> dict[str, Any]:
        return helper.handle({"token": helper.token, "version": "0.43.0", "job": job, "args": args})

    found = req("power.read")
    assert found["profile"] == "custom" and found["limits"]["fppt"]["max"] == 41
    assert req("power.set", values={"spl": 20, "sppt": 22, "fppt": 30})["limits"] == {"spl": 20, "sppt": 22, "fppt": 30}
    assert req("power.set", values={"spl": 99, "sppt": 99, "fppt": 99})["ok"] is False


# Keepsake's side


class FakeHelper:
    def __init__(self, root: str, prof: str, fail: bool = False) -> None:
        self.root, self.prof, self.fail = root, prof, fail
        self.calls: list[dict[str, int]] = []

    def status(self) -> dict[str, Any]:
        return {"ready": True}

    def call(self, job: str, **args: Any) -> dict[str, Any]:
        assert job == "power.set"
        if self.fail:
            raise HelperError("switch the performance mode to Custom first")
        self.calls.append(dict(args["values"]))
        return {"limits": power.apply(args["values"], self.root, self.prof)}


def test_keepsake_reads_and_clamps_before_asking_the_helper(tmp_path: Any) -> None:
    root, prof = firmware(tmp_path)
    fake = FakeHelper(root, prof)
    limits = powerlimits.PowerLimits(fake, str(tmp_path / "sys"))  # type: ignore[arg-type]
    assert limits.current() == {"spl": 15, "sppt": 17, "fppt": 20}
    assert limits.set({"spl": 40, "sppt": 45, "fppt": 50}) == {"spl": 30, "sppt": 32, "fppt": 41}
    assert fake.calls == [{"spl": 30, "sppt": 32, "fppt": 41}]
    with pytest.raises(powerlimits.LimitsError):
        limits.set({"spl": 30, "sppt": 20, "fppt": 41})
    failing = powerlimits.PowerLimits(FakeHelper(root, prof, fail=True), str(tmp_path / "sys"))  # type: ignore[arg-type]
    with pytest.raises(powerlimits.LimitsError, match="Custom"):
        failing.set({"spl": 20, "sppt": 22, "fppt": 30})


def test_no_firmware_attributes_means_unavailable(tmp_path: Any) -> None:
    assert powerlimits.read(str(tmp_path)) is None


def make(tmp_path: Any) -> tuple[perf.Performance, FakeManager, perf.ProfileStore, str]:
    root, prof = firmware(tmp_path)
    manager = FakeManager()
    store = perf.ProfileStore(str(tmp_path / "device-profiles.json"))
    limits = powerlimits.PowerLimits(FakeHelper(root, prof), str(tmp_path / "sys"))  # type: ignore[arg-type]
    p = perf.Performance(
        store, steamos.SteamOSManager(manager.connect), lambda: [], lambda: {"min": 5, "max": 30}, limits
    )
    return p, manager, store, root


def test_a_profile_with_limits_sets_custom_then_the_limits_and_restores(tmp_path: Any) -> None:
    p, manager, store, root = make(tmp_path)
    store.set(APPID, {"limits": {"spl": 25, "sppt": 28, "fppt": 35}})
    applied = p.game_started(APPID)
    assert applied == {"mode": "custom", "limits": {"spl": 25, "sppt": 28, "fppt": 35}}
    assert manager.sets[0] == ("PerformanceProfile", "custom")
    assert currents(root) == {"spl": 25, "sppt": 28, "fppt": 35}
    assert p.game_exited() == ["limits", "mode"]  # the limits first, the mode last
    assert currents(root) == {"spl": 15, "sppt": 17, "fppt": 20}


def test_a_change_by_someone_else_stops_keepsake(tmp_path: Any) -> None:
    p, _manager, store, root = make(tmp_path)
    store.set(APPID, {"limits": {"spl": 25, "sppt": 28, "fppt": 35}})
    p.game_started(APPID)
    path = os.path.join(root, "lenovo-wmi-other-0", "attributes", "ppt_pl1_spl", "current_value")
    with open(path, "w") as handle:
        handle.write("20")
    assert p.watch()
    assert "limits" not in p.applied
    assert p.game_exited() == ["mode"]  # the limits someone else set are left alone


def test_profiles_check_limits(tmp_path: Any) -> None:
    assert perf.clean_profile({"limits": {"spl": 10, "sppt": 12, "fppt": 14}})["limits"]["fppt"] == 14
    for bad in ({"spl": 10}, {"spl": 20, "sppt": 12, "fppt": 14}, {"spl": 0, "sppt": 12, "fppt": 14}, "15"):
        with pytest.raises(perf.ProfileError):
            perf.clean_profile({"limits": bad})


def test_status_reports_ranges_and_readiness(tmp_path: Any) -> None:
    p, *_ = make(tmp_path)
    found = p.status()["powerLimits"]
    assert found["available"] and found["ready"] and found["ranges"]["sppt"]["max"] == 32


def test_helper_reports_limits_the_firmware_did_not_keep(tmp_path: Any, monkeypatch: Any) -> None:
    root, prof = firmware(tmp_path)
    real = power.read
    reads = {"n": 0}

    def stale(r: str = power.ROOT) -> dict[str, dict[str, int]]:
        reads["n"] += 1
        found = real(r)
        if reads["n"] > 1:  # after the writes: the firmware quietly kept its old SPL
            found["spl"]["current"] = 15
        return found

    monkeypatch.setattr(power, "read", stale)
    with pytest.raises(power.PowerError, match="did not keep"):
        power.apply({"spl": 25, "sppt": 28, "fppt": 35}, root, prof)
