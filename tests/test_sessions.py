"""Advisor play sessions (ADR-0069): readings, summaries, frame rate sources, storage, advice. Synthetic data."""

from __future__ import annotations

import asyncio
import base64
import os
import struct

import pytest

from keepsake import devicechecks
from keepsake.advisor import sessions


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def gpu_metrics_v2(socket_mw=15000, cpu_mw=6000, gfx_mw=8000, temp=7100, throttle=0, busy=97, gfx_mhz=1600):
    data = bytearray(120)
    struct.pack_into("<HBB", data, 0, 120, 2, 1)
    struct.pack_into("<HH", data, 4, temp, 6500)
    struct.pack_into("<H", data, 28, busy)
    struct.pack_into("<HHHH", data, 40, socket_mw, cpu_mw, 3000, gfx_mw)
    struct.pack_into("<H", data, 64, gfx_mhz)
    struct.pack_into("<I", data, 108, throttle)
    return bytes(data)


def fake_device(root, *, mains=False, metrics=None, hwmon_power=15_000_000):
    write(os.path.join(root, "class", "drm", "card0", "device", "vendor"), "0x8086")  # not the AMD GPU
    write(os.path.join(root, "class", "drm", "card0", "device", "gpu_busy_percent"), "5")
    gpu = os.path.join(root, "class", "drm", "card1", "device")
    write(os.path.join(gpu, "vendor"), "0x1002")
    write(os.path.join(gpu, "gpu_busy_percent"), "96")
    write(os.path.join(gpu, "mem_info_vram_used"), str(3 * 1024**3))
    if hwmon_power is not None:
        write(os.path.join(gpu, "hwmon", "hwmon3", "power1_average"), str(hwmon_power))
    write(os.path.join(gpu, "hwmon", "hwmon3", "temp1_input"), "72000")
    write(os.path.join(gpu, "hwmon", "hwmon3", "freq1_input"), "1600000000")
    if metrics is not None:
        with open(os.path.join(gpu, "gpu_metrics"), "wb") as handle:
            handle.write(metrics)
    write(os.path.join(root, "class", "hwmon", "hwmon1", "name"), "k10temp")
    write(os.path.join(root, "class", "hwmon", "hwmon1", "temp1_input"), "68000")
    write(os.path.join(root, "class", "power_supply", "BAT0", "type"), "Battery")
    write(os.path.join(root, "class", "power_supply", "BAT0", "capacity"), "77")
    write(os.path.join(root, "class", "power_supply", "BAT0", "power_now"), "17000000")
    write(os.path.join(root, "class", "power_supply", "BAT0", "energy_now"), "40000000")
    write(os.path.join(root, "class", "power_supply", "BAT0", "status"), "Discharging")
    write(os.path.join(root, "class", "power_supply", "ACAD", "type"), "Mains")
    write(os.path.join(root, "class", "power_supply", "ACAD", "online"), "1" if mains else "0")
    for cpu in range(8):
        write(os.path.join(root, "devices", "system", "cpu", f"cpu{cpu}", "cpufreq", "scaling_cur_freq"), "3000000")
    write(os.path.join(root, "meminfo"), "MemTotal: 16000000 kB\nMemAvailable: 6000000 kB\n")
    write(os.path.join(root, "stat"), "cpu  100 0 100 800 0 0 0 0 0 0\n")


# Readings


def test_gpu_metrics_v2_and_other_versions():
    found = sessions.parse_gpu_metrics(gpu_metrics_v2(throttle=4))
    assert found == {
        "gpuTempC": 71.0,
        "socTempC": 65.0,
        "socketW": 15.0,
        "cpuW": 6.0,
        "gpuW": 8.0,
        "gpuBusy": 97.0,
        "gpuMhz": 1600.0,
        "throttled": 1.0,
    }
    v3 = bytearray(gpu_metrics_v2())
    v3[2] = 3
    assert sessions.parse_gpu_metrics(bytes(v3)) is None  # Strix Point's layout: hwmon only (A212)
    assert sessions.parse_gpu_metrics(b"\x00" * 10) is None
    unsupported = sessions.parse_gpu_metrics(gpu_metrics_v2(cpu_mw=0xFFFF))
    assert "cpuW" not in unsupported  # 0xFFFF means "not supported"


def test_a_reading_of_everything(tmp_path):
    fake_device(str(tmp_path), metrics=gpu_metrics_v2())
    sample = sessions.Sensors(str(tmp_path), str(tmp_path)).read()
    assert sample["socketW"] == 15.0 and sample["gpuTempC"] == 72.0 and sample["gpuMhz"] == 1600.0  # hwmon first
    assert sample["cpuW"] == 6.0 and sample["gpuW"] == 8.0  # from gpu_metrics
    assert sample["gpuBusy"] == 96.0 and sample["vramMiB"] == 3072.0 and sample["cpuTempC"] == 68.0
    assert sample["cpuMhz"] == 3000.0 and sample["ramMiB"] == pytest.approx(9765.6, abs=0.1)
    assert sample["battery_percent"] == 77.0 and sample["battery_watts"] == 17.0 and sample["mains"] == 0.0
    assert sessions.read_sample(str(tmp_path), str(tmp_path)) == sample
    assert sessions.sources(sample, False) == {
        "frameRate": False,
        "socketPower": True,
        "cpuPower": True,
        "gpuPower": True,
        "battery": True,
        "temperatures": True,
        "load": True,
    }
    assert sessions.read_sample(str(tmp_path / "nothing"), str(tmp_path / "nothing")) == {}


def test_battery_power_from_current_and_voltage(tmp_path):
    root = str(tmp_path)
    write(os.path.join(root, "class", "power_supply", "BAT1", "type"), "Battery")
    write(os.path.join(root, "class", "power_supply", "BAT1", "current_now"), "2000000")
    write(os.path.join(root, "class", "power_supply", "BAT1", "voltage_now"), "8000000")
    write(os.path.join(root, "class", "power_supply", "0-pad", "type"), "Battery")  # sorts first
    write(os.path.join(root, "class", "power_supply", "0-pad", "scope"), "Device")  # a controller's battery
    write(os.path.join(root, "class", "power_supply", "0-pad", "power_now"), "1000000")
    assert sessions.read_sample(root, root)["battery_watts"] == 16.0


def test_cpu_times(tmp_path):
    write(str(tmp_path / "stat"), "cpu  10 5 15 60 10 0 0 0\ncpu0 1 1 1 1\n")
    assert sessions.cpu_times(str(tmp_path)) == (30, 100)
    write(str(tmp_path / "stat"), "nonsense\n")
    assert sessions.cpu_times(str(tmp_path)) is None


# A session's summary


def test_summary_of_a_session():
    acc = sessions.Accumulator(1000.0)
    for second in range(600):
        temp = 96.0 if second >= 300 else 70.0
        sample = {"socketW": 14 + second % 3, "gpuBusy": 98.0, "gpuTempC": temp, "battery_percent": 80 - second / 60}
        sample["battery_watts"] = 16.0
        acc.add(sample, 1000.0 + second, (second * 30, second * 100))
        acc.add_fps(60.0 if second % 10 else 30.0)
    s = acc.summary(extra={"settings": {"tdp": 15}})
    assert s["seconds"] == 599 and s["power"] == "on battery"
    assert s["fps"]["source"] == "steam" and s["fps"]["avg"] == 57.0 and s["fps"]["min5s"] == 54.0
    assert s["watts"]["socketAvg"] == 15.0 and s["watts"]["socketPeak"] == 16.0
    assert s["cpu"]["busyAvg"] == 30.0 and s["gpu"]["tempPeak"] == 96.0
    assert s["throttle"] == {"seen": True, "afterMinutes": 5.0}
    assert s["battery"]["percentPerHour"] == pytest.approx(60.1, abs=0.2) and s["battery"]["drainW"] == 16.0
    assert s["battery"]["lifeHours"] == pytest.approx(1.7, abs=0.1)
    assert s["settings"] == {"tdp": 15}


def test_plugged_in_and_mixed_sessions_and_no_frame_rate():
    acc = sessions.Accumulator(0.0)
    acc.add({"mains": 1.0, "battery_percent": 90.0}, 1.0)
    acc.add({"mains": 1.0, "battery_percent": 95.0}, 3600.0)  # charging: not a drain
    assert acc.summary()["power"] == "plugged in" and acc.summary()["fps"] == {"source": None}
    assert acc.summary()["battery"] == {}
    acc.add({"mains": 0.0, "battery_percent": 50.0}, 2.0)
    assert acc.summary()["power"] == "mixed"
    acc2 = sessions.Accumulator(0.0)
    acc2.add({"throttled": 1.0}, 120.0)
    assert acc2.summary()["throttle"] == {"seen": True, "afterMinutes": 2.0}


def test_lows_from_frame_times():
    times = [16.0] * 990 + [40.0] * 5 + [50.0] * 5
    found = sessions.lows(times)
    assert found["avg"] == pytest.approx(61.4, abs=0.1) and found["low1"] == 22.2 and found["low01"] == 20.0
    assert sessions.lows([16.0] * 99) == {}
    acc = sessions.Accumulator(0.0)
    acc.add({}, 100.0)
    assert acc.summary(mangohud=times)["fps"]["source"] == "mangohud"
    for _ in range(200):
        acc.add_fps(60.0, 16.6)
    assert acc.summary()["fps"]["source"] == "steam" and "low1" in acc.summary()["fps"]


# Frame rate from Steam and MangoHud


def pb_field(number, payload):
    return bytes([(number << 3) | 2, len(payload)]) + payload


def test_steam_diagnostic_entries():
    entry = lambda name, value: pb_field(1, pb_field(1, name.encode()) + pb_field(2, value.encode()))  # noqa: E731
    data = entry("GPU Clock", "1600 MHz") + entry("FPS", "58.3") + entry("Frame Time", "17.1 ms") + bytes([0x18, 0x2A])
    assert sessions.steam_fps(data) == (58.3, 17.1)
    assert sessions.steam_fps(entry("FPS", "9999")) == (None, None)  # out of range
    assert sessions.steam_fps(b"\xff\xff\xff") == (None, None)
    assert sessions.steam_fps(entry("Battery", "80%")) == (None, None)
    assert sessions.protobuf_strings(pb_field(1, b"\x00\x01")) == []


def test_mangohud_logs_written_during_the_session(tmp_path):
    home = tmp_path / "home"
    logs = home / "logs"
    write(str(home / ".config" / "MangoHud" / "MangoHud.conf"), "fps_limit=60\noutput_folder=~/logs\n")
    rows = "os,cpu,gpu\nSteamOS,Z1,780M\nfps,frametime,cpu_load\n" + "".join(
        f"60,{16.6 if i % 50 else 33.3},40\n" for i in range(500)
    )
    write(str(logs / "Game_2026-11-21_10-00-00.csv"), rows)
    os.utime(logs / "Game_2026-11-21_10-00-00.csv", (1000, 1000))
    write(str(logs / "Old.csv"), rows)
    os.utime(logs / "Old.csv", (10, 10))
    folders = sessions.mangohud_folders(str(home))
    assert folders[0] == str(home) + "/logs"
    times = sessions.mangohud_frametimes(folders, 900, 990)
    assert len(times) == 500 and max(times) == 33.3
    assert sessions.mangohud_frametimes(folders, 5000, 6000) == []


# Storage and the recorder


def test_store_keeps_the_last_twenty_and_a_running_summary(tmp_path):
    store = sessions.SessionStore(str(tmp_path))
    for i in range(25):
        store.add(7, {"seconds": 60, "fps": {"avg": 50.0 + i}})
    data = store.load(7)
    assert len(data["sessions"]) == 20 and data["sessions"][0]["fps"]["avg"] == 55.0
    assert data["total"]["sessions"] == 25 and data["total"]["seconds"] == 1500 and data["total"]["fpsAvg"] == 62.0
    assert store.load(8) == {"sessions": [], "total": {"sessions": 0, "seconds": 0}}


def test_recorder_samples_pauses_and_keeps_only_long_enough_sessions(tmp_path):
    fake_device(str(tmp_path / "sys"))
    clock = [0.0]
    store = sessions.SessionStore(str(tmp_path / "store"))
    rec = sessions.Recorder(store, str(tmp_path / "sys"), str(tmp_path / "sys"), clock=lambda: clock[0], interval=3600)
    rec.start(42, {"settings": {"tdp": 12}})
    for second in range(1, 121):
        clock[0] = float(second)
        rec.sample_once()
        rec.feed_fps(55.0, None)
    rec.paused.set()
    rec.feed_fps(1.0, None)  # ignored while asleep
    rec.paused.clear()
    assert rec.finish(41) is None  # another game's exit
    rec.start(42, {})
    clock[0] = 130.0
    rec.sample_once()
    clock[0] = 140.0
    assert rec.finish(42) is None  # ten seconds: not kept
    rec.start(42, {"settings": {"tdp": 12}})
    for second in range(141, 260):
        clock[0] = float(second)
        rec.sample_once()
        rec.feed_fps(55.0, None)
        if second == 200:
            rec.paused.set()
            rec.feed_fps(1.0, None)  # asleep: not counted
            rec.paused.clear()
    summary = rec.finish(42, lambda since, until: [])
    assert summary["fps"]["avg"] == 55.0 and summary["settings"] == {"tdp": 12} and summary["seconds"] == 119
    assert len(store.load(42)["sessions"]) == 1 and rec.fps_seen


# Advice and AI numbers


def session(fps=55.0, low=None, tdp=15, cap=None, gpu=98.0, cpu=40.0, throttle=None, seconds=1800):
    return {
        "seconds": seconds,
        "power": "on battery",
        "fps": {"source": "steam", "avg": fps, "min5s": low},
        "watts": {"socketAvg": tdp + 2.0},
        "cpu": {"busyAvg": cpu},
        "gpu": {"busyAvg": gpu, "tempPeak": 80.0},
        "throttle": {"seen": throttle is not None, "afterMinutes": throttle},
        "settings": {
            "tdp": tdp,
            "frameCap": cap,
            "launchOptions": "/home/someone/secret %command%",
            "protonVersion": "GE-Proton9-27",
        },
    }


def test_advice_measured_here():
    found = {a["id"]: a for a in sessions.advice([session(fps=45, low=32, cap=45, throttle=20.0)])}
    assert set(found) == {"cap", "gpu-bound", "throttle"}
    assert "lower the cap to 30" in found["cap"]["text"] and "at 15 W" in found["cap"]["text"]
    assert found["gpu-bound"]["text"].startswith("The GPU was at 98% and the CPU at 40%")
    assert found["throttle"]["text"] == "It throttled after 20 minutes: a lower TDP or frame cap keeps it cooler."
    assert all(a["source"] == "Measured on this device, 1 session" and a["measured"] for a in found.values())
    same = sessions.advice([session(fps=60, tdp=18, gpu=50), session(fps=59, tdp=12, gpu=50)])
    assert [a["id"] for a in same] == ["save-battery"] and "at 12 W (59 fps) as at 18 W (60 fps)" in same[0]["text"]
    assert same[0]["source"] == "Measured on this device, 2 sessions"
    assert sessions.advice([session(fps=60, tdp=18, gpu=50), session(fps=40, tdp=12, gpu=50)]) == []
    assert sessions.advice([]) == []
    assert sessions.advice([session(low=44, cap=45, gpu=50)]) == []  # within 15% of the cap: fine
    assert sessions.advice([session(gpu=98, cpu=80)]) == []  # both busy: not GPU-bound


def test_ai_gets_plain_numbers_only():
    numbers = sessions.ai_numbers([session(throttle=12.0)] * 7)
    assert len(numbers) == 5
    flat = str(numbers)
    assert "secret" not in flat and "command" not in flat and "/home" not in flat and "Proton" not in flat
    assert numbers[0] == {
        "minutes": 30,
        "power": "on battery",
        "fpsAvg": 55.0,
        "fpsLow1": None,
        "socketW": 17.0,
        "cpuBusy": 40.0,
        "gpuBusy": 98.0,
        "gpuTempPeak": 80.0,
        "throttledAfterMinutes": 12.0,
        "tdpW": 15,
        "frameCap": None,
    }


# The app and the device check


def test_app_feeds_frame_rate_pauses_on_sleep_and_records_on_exit(tmp_path):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    fake_device(str(tmp_path / "sys"))
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "sys"), version="0.28.0", home=str(tmp_path))
    app.sys_root = str(tmp_path / "sys")
    entry = pb_field(1, pb_field(1, b"FPS") + pb_field(2, b"61"))

    class FakeAdvisor:
        def __init__(self):
            self.device = {"vendor": "Example", "model": "Handheld", "display": {"refresh_hz": 144}}
            self.detected = {"tools": []}
            self.decky_home = self.user_home = str(tmp_path)

        def selected(self):
            return {}

    async def go():
        await app._session_start(FakeAdvisor(), 4242)
        fed = await app.advisor_perf_sample(base64.b64encode(entry).decode())
        bad = await app.advisor_perf_sample("not base64!")
        await app.on_suspend()
        paused = app.session_recorder.paused.is_set()
        await app.on_resume()
        resumed = not app.session_recorder.paused.is_set()
        app.session_recorder.acc.started -= 120  # as if two minutes had passed
        app.session_recorder.sample_once()
        await app._session_finish(4242)
        return fed, bad, paused, resumed

    fed, bad, paused, resumed = asyncio.run(go())
    assert fed == {"ok": True, "fps": 61.0} and bad == {"ok": False} and paused and resumed
    stored = app.session_recorder.store.load(4242)["sessions"]
    assert len(stored) == 1 and stored[0]["fps"]["avg"] == 61.0
    assert stored[0]["device"] == "Example Handheld" and stored[0]["display"] == {"refresh_hz": 144}


@pytest.mark.parametrize(
    ("found", "status"),
    [
        ({"frameRate": True, "socketPower": True, "battery": True}, "pass"),
        ({"frameRate": False, "socketPower": True, "battery": True, "mangohudConfig": True}, "warn"),
        ({"frameRate": False, "socketPower": False, "battery": False}, "fail"),
    ],
)
def test_device_check(found, status):
    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"session-sources": probe})
    outcome = asyncio.run(devicechecks.run("session-sources", ctx))
    assert outcome["status"] == status and outcome["title"] == "Session stats sources"
    if status == "warn":
        assert "MangoHud" in outcome["found"] and "play a game for a minute" in outcome["found"]
    assert (
        asyncio.run(devicechecks.run("session-sources", devicechecks.Context("", "", "", "", {}, "")))["status"]
        == "skip"
    )
