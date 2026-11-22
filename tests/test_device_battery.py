"""R21 stage 4 (ADR-0077): the 80 percent charge limit through steamos-manager only. Synthetic trees (P12)."""

import asyncio

import pytest

from keepsake import devicechecks
from keepsake.device import battery, steamos
from test_device_performance import FakeManager


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def with_charge(manager, level=-1):
    manager.props[steamos.CHARGE] = {"MaxChargeLevel": ("i", level), "SuggestedMinimumLimit": ("i", 50)}
    return manager


def legion_battery(root, types="[Standard] Long_Life"):
    put(root / "class/power_supply/BAT0/type", "Battery")
    put(root / "class/power_supply/BAT0/charge_types", types)
    put(root / "class/power_supply/hid-ctrl/type", "Battery")
    put(root / "class/power_supply/hid-ctrl/scope", "Device")
    return str(root)


def test_the_kernel_state_is_read_from_the_system_battery(tmp_path):
    root = legion_battery(tmp_path)
    put(tmp_path / "class/power_supply/A-controller/type", "Battery")  # listed first, but a controller's
    put(tmp_path / "class/power_supply/A-controller/scope", "Device")
    put(tmp_path / "class/power_supply/A-controller/charge_types", "Standard [Long_Life]")
    assert battery.firmware_state(root)["limited"] is False
    put(tmp_path / "class/power_supply/BAT0/charge_types", "Standard [Long_Life]")
    state = battery.firmware_state(root)
    assert state["limited"] is True and state["battery"] == "BAT0"


def test_a_threshold_counts_too(tmp_path):
    put(tmp_path / "class/power_supply/BAT1/type", "Battery")
    put(tmp_path / "class/power_supply/BAT1/charge_control_end_threshold", "80")
    assert battery.firmware_state(str(tmp_path)) == {
        "battery": "BAT1",
        "chargeTypes": None,
        "threshold": 80,
        "limited": True,
    }
    assert battery.firmware_state(str(tmp_path / "none"))["limited"] is None


def test_steamos_manager_sets_the_limit_and_reads_it_back(tmp_path):
    manager = with_charge(FakeManager())
    sm = steamos.SteamOSManager(manager.connect)
    root = legion_battery(tmp_path)
    assert battery.status(sm, root)["control"] == "steamos-manager" and battery.status(sm, root)["limited"] is False
    on = battery.set_limit(sm, True, root)
    assert on["limited"] is True and on["level"] == 80 and manager.sets[-1] == ("MaxChargeLevel", 80)
    off = battery.set_limit(sm, False, root)
    assert off["limited"] is False and manager.sets[-1] == ("MaxChargeLevel", -1)


def test_without_steamos_manager_it_only_shows_and_says_where(tmp_path):
    manager = FakeManager()  # no BatteryChargeLimit1: Valve's Legion file does not enable it yet
    sm = steamos.SteamOSManager(manager.connect)
    root = legion_battery(tmp_path, "Standard [Long_Life]")
    shown = battery.status(sm, root)
    assert shown["control"] is None and shown["limited"] is True and "Steam's settings" in shown["where"]
    with pytest.raises(steamos.ManagerError, match="does not offer the charge limit"):
        battery.set_limit(sm, False, root)
    assert manager.sets == []


def test_a_read_back_that_differs_is_an_error():
    manager = with_charge(FakeManager())
    manager.drift = {"MaxChargeLevel": 100}
    with pytest.raises(steamos.ManagerError, match="reads back"):
        steamos.SteamOSManager(manager.connect).set_charge_limit(80)


@pytest.mark.parametrize(
    ("found", "status"),
    [
        ({"control": "steamos-manager", "limited": True, "level": 80, "firmware": {}}, "pass"),
        (
            {
                "control": None,
                "limited": False,
                "level": None,
                "firmware": {"chargeTypes": "[Standard] Long_Life"},
                "where": "x",
            },
            "warn",
        ),
        ({"control": None, "limited": None, "level": None, "firmware": {"chargeTypes": None}, "where": "x"}, "fail"),
    ],
)
def test_device_check(found, status):
    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"charge-limit": probe})
    outcome = asyncio.run(devicechecks.run("charge-limit", ctx))
    assert outcome["status"] == status and outcome["title"] == "Battery charge limit"


def test_the_app_sets_the_limit_through_steamos_manager(tmp_path, monkeypatch):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    manager = with_charge(FakeManager())
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.35.0", home=str(tmp_path))
    app.sys_root = legion_battery(tmp_path / "sys")
    monkeypatch.setattr(app, "_steamos", lambda: steamos.SteamOSManager(manager.connect))

    async def go():
        await app.start()
        try:
            on = await app.device_set_charge_limit(True)
            await app.set_module_enabled("device", False)
            with pytest.raises(ValueError, match="Device controls are off"):
                await app.device_set_charge_limit(False)
            return on
        finally:
            await app.stop()

    on = asyncio.run(go())
    assert on["limited"] is True and manager.value(steamos.CHARGE, "MaxChargeLevel") == 80
