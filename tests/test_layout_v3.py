"""Layout v3 (ADR-0073): Device, Status reads this handheld's profile and battery, read-only.

Synthetic DMI and power-supply files only; no serial number is ever read.
"""

import asyncio

from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths


def app_at(tmp_path):
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.32.0", home=str(tmp_path))
    app.power_root = str(tmp_path / "root")
    return app


def dmi(root, **fields):
    folder = root / "sys" / "class" / "dmi" / "id"
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in fields.items():
        (folder / name).write_text(value + "\n")


def battery(root, percent=None, mains=None):
    supply = root / "sys" / "class" / "power_supply"
    if percent is not None:
        (supply / "BAT0").mkdir(parents=True, exist_ok=True)
        (supply / "BAT0" / "type").write_text("Battery\n")
        (supply / "BAT0" / "capacity").write_text(f"{percent}\n")
        (supply / "BAT0" / "status").write_text("Discharging\n")
    if mains is not None:
        (supply / "AC0").mkdir(parents=True, exist_ok=True)
        (supply / "AC0" / "type").write_text("Mains\n")
        (supply / "AC0" / "online").write_text("1\n" if mains else "0\n")


def test_a_known_handheld_on_battery(tmp_path):
    app = app_at(tmp_path)
    root = tmp_path / "root"
    dmi(root, sys_vendor="Valve", product_name="Jupiter", product_serial="SHOULD-NOT-BE-READ")
    battery(root, percent=64, mains=False)
    status = asyncio.run(app.device_status())
    assert (
        status["model"] == "Steam Deck LCD"
        and status["profile"] == "valve-steam-deck-lcd"
        and status["how"] == "detected"
    )
    assert status["tdp"]["min"] == 4 and status["tdp"]["max"] == 15
    assert status["battery"] == {"percent": 64, "mains": False, "present": True}
    assert "SHOULD-NOT-BE-READ" not in str(status)  # serial numbers are never read
    app._disk.shutdown(wait=False)


def test_an_unknown_device_gets_safe_generic_limits(tmp_path):
    app = app_at(tmp_path)
    root = tmp_path / "root"
    dmi(root, sys_vendor="Example Maker", product_name="Box 1")
    battery(root, mains=True)
    status = asyncio.run(app.device_status())
    assert status["how"] == "generic" and status["profile"] == "generic"
    assert status["tdp"] == {"min": 5, "max": 25}
    assert status["battery"]["present"] is False  # a mains-only device
    app._disk.shutdown(wait=False)
