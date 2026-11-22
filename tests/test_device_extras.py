"""R21 stage 6 (ADR-0079): Wi-Fi power saving through steamos-manager, and the BIOS check. Synthetic (P12)."""

import asyncio

import pytest

from keepsake import devicechecks
from keepsake.device import bios, steamos
from test_device_performance import FakeManager


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def dmi(root, version, product="83E1"):
    put(root / "class/dmi/id/bios_version", version)
    put(root / "class/dmi/id/product_name", product)
    put(root / "class/dmi/id/bios_date", "01/02/2026")
    return str(root)


@pytest.mark.parametrize(
    ("version", "level", "says"),
    [
        ("N3CN42WW", "fail", "bricked"),
        ("N3CN27WW", "warn", "no custom fan curves"),
        ("N3CN28WW", "warn", "no 80% charge limit"),
        ("N3CN29WW", "warn", "v29.1"),
        ("N3CN40WW", "ok", ""),
    ],
)
def test_known_legion_go_bios_versions(tmp_path, version, level, says):
    found = bios.check(dmi(tmp_path, version))
    assert found["level"] == level and found["known"] is True
    assert (says in " ".join(found["notes"])) if says else found["notes"] == []
    if version == "N3CN28WW":
        assert "fan curves" not in " ".join(found["notes"])  # v28 has them


def test_another_model_has_no_notes(tmp_path):
    found = bios.check(dmi(tmp_path, "QCCN12WW", "83N0"))
    assert found["known"] is False and found["notes"] == [] and found["level"] == "ok"


def test_wifi_power_saving_through_steamos_manager():
    manager = FakeManager()
    manager.props[steamos.WIFI] = {"WifiPowerManagementState": ("u", 1)}
    sm = steamos.SteamOSManager(manager.connect)
    assert sm.read()["wifiPowerSaving"] is True
    assert sm.set_wifi_power_saving(False) is False and manager.sets[-1] == ("WifiPowerManagementState", 0)
    manager.drift = {"WifiPowerManagementState": 1}
    with pytest.raises(steamos.ManagerError, match="did not change"):
        sm.set_wifi_power_saving(False)


def test_no_wifi_interface_reads_as_none():
    assert steamos.SteamOSManager(FakeManager().connect).read()["wifiPowerSaving"] is None


@pytest.mark.parametrize(
    ("version", "status"),
    [("N3CN42WW", "fail"), ("N3CN29WW", "warn"), ("N3CN40WW", "pass"), ("QCCN12WW", "pass"), (None, "warn")],
)
def test_device_check(tmp_path, version, status):
    found = bios.check(dmi(tmp_path, version) if version else str(tmp_path / "none"))

    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"bios": probe})
    outcome = asyncio.run(devicechecks.run("bios", ctx))
    assert outcome["status"] == status and outcome["title"] == "BIOS check"


def test_the_app_changes_wifi_power_saving(tmp_path, monkeypatch):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    manager = FakeManager()
    manager.props[steamos.WIFI] = {"WifiPowerManagementState": ("u", 1)}
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.37.0", home=str(tmp_path))
    app.sys_root = dmi(tmp_path / "sys", "N3CN40WW")
    monkeypatch.setattr(app, "_steamos", lambda: steamos.SteamOSManager(manager.connect))

    async def go():
        await app.start()
        try:
            return await app.device_set_wifi_power_saving(False)
        finally:
            await app.stop()

    extras = asyncio.run(go())
    assert extras["wifiPowerSaving"] is False and extras["bios"]["version"] == "N3CN40WW"
