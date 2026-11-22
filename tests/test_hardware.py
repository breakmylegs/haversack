"""R21 stage 1 (ADR-0074): live readings from world-readable sysfs files only. Synthetic trees (P12)."""

import asyncio

import pytest

from keepsake import devicechecks, hardware


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def legion_like(root):
    sys = root / "sys"
    put(sys / "class/hwmon/hwmon0/name", "k10temp")
    put(sys / "class/hwmon/hwmon0/temp1_input", "61250")
    put(sys / "class/hwmon/hwmon0/temp1_label", "Tctl")
    put(sys / "class/hwmon/hwmon1/name", "amdgpu")
    put(sys / "class/hwmon/hwmon1/temp1_input", "55000")
    put(sys / "class/hwmon/hwmon1/power1_input", "9500000")
    put(sys / "class/hwmon/hwmon2/name", "lenovo_wmi_other")
    put(sys / "class/hwmon/hwmon2/fan1_input", "3100")
    put(sys / "class/hwmon/hwmon3/name", "nvme")  # no readings: left out
    put(sys / "class/power_supply/BAT0/type", "Battery")
    put(sys / "class/power_supply/BAT0/capacity", "72")
    put(sys / "class/power_supply/BAT0/status", "Discharging")
    put(sys / "class/power_supply/BAT0/power_now", "14200000")
    put(sys / "class/power_supply/BAT0/charge_control_end_threshold", "80")
    put(sys / "class/power_supply/BAT1/type", "Battery")  # a second battery: the first one counts
    put(sys / "class/power_supply/BAT1/capacity", "10")
    put(sys / "class/power_supply/hid-ctrl-battery/type", "Battery")  # a controller's battery
    put(sys / "class/power_supply/hid-ctrl-battery/scope", "Device")
    put(sys / "class/power_supply/hid-ctrl-battery/capacity", "30")
    put(sys / "class/power_supply/ADP0/type", "Mains")
    put(sys / "class/power_supply/ADP0/online", "0")
    put(sys / "class/dmi/id/bios_version", "N3CN99WW")
    put(sys / "class/dmi/id/bios_date", "01/02/2026")
    put(sys / "class/dmi/id/product_serial", "NEVER-READ")
    put(sys / "class/platform-profile/platform-profile-0/profile", "balanced")
    put(sys / "class/platform-profile/platform-profile-0/choices", "low-power balanced performance custom")
    put(sys / "devices/system/cpu/cpufreq/boost", "1")
    put(sys / "devices/system/cpu/smt/control", "on")
    put(sys / "devices/system/cpu/online", "0-15")
    return str(sys)


def test_a_legion_like_device_reads_everything(tmp_path):
    status = hardware.read_status(legion_like(tmp_path))
    assert [c["name"] for c in status["chips"]] == ["k10temp", "amdgpu", "lenovo_wmi_other"]
    assert status["chips"][0]["temps"] == [{"label": "Tctl", "value": 61.2}]
    assert status["chips"][2]["fans"] == [{"label": "fan1", "value": 3100.0}]
    assert status["gpuWatts"] == 9.5
    assert status["battery"] == {
        "mains": False,
        "percent": 72,
        "status": "Discharging",
        "watts": 14.2,
        "chargeLimit": 80,
    }
    assert status["bios"] == {"version": "N3CN99WW", "date": "01/02/2026"}
    assert status["profile"] == {
        "current": "balanced",
        "choices": ["low-power", "balanced", "performance", "custom"],
        "words": "Balanced",
    }
    assert status["cpu"] == {"boost": True, "smt": "on", "online": 16}
    assert "NEVER-READ" not in str(status)


def test_the_older_profile_file_and_missing_files(tmp_path):
    sys = tmp_path / "sys"
    put(sys / "firmware/acpi/platform_profile", "low-power")
    put(sys / "firmware/acpi/platform_profile_choices", "low-power balanced performance")
    put(sys / "devices/system/cpu/cpufreq/policy0/boost", "0")
    put(sys / "devices/system/cpu/online", "0-3,6,8-9")
    status = hardware.read_status(str(sys))
    assert status["profile"]["words"] == "Quiet" and status["chips"] == [] and status["battery"] == {}
    assert status["cpu"] == {"boost": False, "smt": None, "online": 7}
    assert status["bios"] == {"version": None, "date": None}


def test_a_broken_reading_is_left_out(tmp_path):
    sys = tmp_path / "sys"
    put(sys / "class/hwmon/hwmon0/name", "k10temp")
    put(sys / "class/hwmon/hwmon0/temp1_input", "not a number")
    put(sys / "class/hwmon/hwmon0/temp2_input", "40000")
    assert hardware.chips(str(sys))[0]["temps"] == [{"label": "temp2", "value": 40.0}]


@pytest.mark.parametrize(
    ("found", "status"),
    [
        ("full", "pass"),
        ("nofan", "warn"),
        ("none", "fail"),
    ],
)
def test_device_check(tmp_path, found, status):
    sys = legion_like(tmp_path)
    readings = hardware.read_status(sys)
    if found == "nofan":
        readings["chips"] = [c for c in readings["chips"] if not c["fans"]]
    if found == "none":
        readings["chips"] = []

    async def probe():
        return readings

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"device-readings": probe})
    outcome = asyncio.run(devicechecks.run("device-readings", ctx))
    assert outcome["status"] == status and outcome["title"] == "Device readings"


def test_the_app_serves_readings(tmp_path):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.33.0", home=str(tmp_path))
    app.sys_root = legion_like(tmp_path / "dev")
    readings = asyncio.run(app.device_readings())
    assert readings["bios"]["version"] == "N3CN99WW"
    app._disk.shutdown(wait=False)
