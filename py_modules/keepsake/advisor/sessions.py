"""How each game actually ran on this device: play sessions, measured and summarised (ADR-0069).

Read-only, about once a second while a game runs, from files the kernel already exposes to the user:

- **Power and heat:** the amdgpu ``hwmon`` (socket power, edge temperature, GPU clock), ``gpu_metrics``
  version 2 (CPU and GPU power, throttle status, temperatures), ``k10temp`` for the CPU.
- **Load:** ``/proc/stat`` (CPU use), ``gpu_busy_percent``, ``/proc/meminfo``, ``mem_info_vram_used``,
  ``scaling_cur_freq``.
- **Battery:** the battery's ``power_now`` (or current times voltage), ``capacity``, ``energy_now`` and
  whether mains power is connected.
- **Frame rate, never by changing the game (P16):** what Steam's own performance overlay reports
  (``SteamClient.System.Perf`` diagnostic entries, forwarded by the frontend), or MangoHud's own
  logs when the user already logs with MangoHud. Otherwise the session says "frame rate not available".

Only a summary of each session is kept, never the samples: the last 20 per game and a running
summary, in Keepsake's own runtime folder, never the cloud. Numbers sent to an AI provider carry no
paths or names (P18).
"""

from __future__ import annotations

import csv
import glob
import itertools
import math
import os
import re
import struct
import threading
import time
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json

KEEP = 20
SAMPLE_SECONDS = 1.0
WINDOW_SECONDS = 5
MIN_SESSION_SECONDS = 60  # shorter sessions (a crash, a quick check) are not kept
THROTTLE_TEMP_C = 95.0
MAX_MANGOHUD_BYTES = 64 * 1024 * 1024
FPS_NAME = re.compile(r"\b(fps|frame ?rate|framerate)\b", re.IGNORECASE)
FRAMETIME_NAME = re.compile(r"frame ?time", re.IGNORECASE)


# Readings


def _text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(4096).strip()
    except OSError:
        return None


def _int(path: str) -> int | None:
    text = _text(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def parse_gpu_metrics(data: bytes) -> dict[str, float] | None:
    """APU ``gpu_metrics`` version 2.x (Van Gogh, Rembrandt, Phoenix): power in mW, temperatures in
    centi-degrees. Version 3 (Strix Point) has another layout and is left to ``hwmon`` (A212)."""
    if len(data) < 112:
        return None
    size, revision, _content = struct.unpack_from("<HBB", data, 0)
    if revision != 2 or size < 112:
        return None
    temps = struct.unpack_from("<HH", data, 4)
    gfx_busy = struct.unpack_from("<H", data, 28)[0]
    socket_mw, cpu_mw, _soc_mw, gfx_mw = struct.unpack_from("<HHHH", data, 40)
    gfx_mhz = struct.unpack_from("<H", data, 64)[0]
    (throttle,) = struct.unpack_from("<I", data, 108)
    out = {
        "gpuTempC": temps[0] / 100,
        "socTempC": temps[1] / 100,
        "socketW": socket_mw / 1000,
        "cpuW": cpu_mw / 1000,
        "gpuW": gfx_mw / 1000,
        "gpuBusy": float(gfx_busy),
        "gpuMhz": float(gfx_mhz),
        "throttled": 1.0 if throttle else 0.0,
    }
    return {k: v for k, v in out.items() if v not in (0xFFFF / 1000, 0xFFFF / 100, float(0xFFFF))}


def _amdgpu(sys_root: str) -> str | None:
    for device in sorted(glob.glob(os.path.join(sys_root, "class", "drm", "card*", "device"))):
        if _text(os.path.join(device, "vendor")) == "0x1002":
            return device
    return None


def _hwmon(sys_root: str, name: str) -> str | None:
    for folder in sorted(glob.glob(os.path.join(sys_root, "class", "hwmon", "hwmon*"))):
        if _text(os.path.join(folder, "name")) == name:
            return folder
    return None


class Sensors:
    """The files one device exposes, found once per session; each reading then only opens those (ADR-0069)."""

    def __init__(self, sys_root: str = "/sys", proc_root: str = "/proc") -> None:
        self.proc_root = proc_root
        gpu = _amdgpu(sys_root)
        self.hwmon = sorted(glob.glob(os.path.join(gpu, "hwmon", "hwmon*"))) if gpu else []
        self.gpu = gpu
        k10 = _hwmon(sys_root, "k10temp")
        self.cpu_temp = os.path.join(k10, "temp1_input") if k10 else None
        pattern = os.path.join(sys_root, "devices", "system", "cpu", "cpu[0-9]*", "cpufreq", "scaling_cur_freq")
        found = sorted(glob.glob(pattern), key=lambda p: int(re.sub(r"\D", "", p.split("cpufreq")[0][-4:]) or 0))
        self.cpu_freqs = found[:: max(1, len(found) // 4)][:4]  # four cores across the CPU: enough for an average
        self.batteries: list[str] = []
        self.mains: list[str] = []
        for supply in sorted(glob.glob(os.path.join(sys_root, "class", "power_supply", "*"))):
            kind = _text(os.path.join(supply, "type"))
            if kind == "Mains":
                self.mains.append(supply)
            elif kind == "Battery" and _text(os.path.join(supply, "scope")) != "Device":
                self.batteries.append(supply)

    def _battery(self) -> tuple[dict[str, float], bool | None]:
        out: dict[str, float] = {}
        mains = any(_int(os.path.join(m, "online")) == 1 for m in self.mains) if self.mains else None
        for supply in self.batteries[:1]:
            capacity = _int(os.path.join(supply, "capacity"))
            power = _int(os.path.join(supply, "power_now"))
            if power is None:
                current, voltage = _int(os.path.join(supply, "current_now")), _int(os.path.join(supply, "voltage_now"))
                power = current * voltage // 1_000_000 if current is not None and voltage is not None else None
            energy = _int(os.path.join(supply, "energy_now"))
            status = _text(os.path.join(supply, "status")) or ""
            if capacity is not None:
                out["percent"] = float(capacity)
            if power is not None:
                out["watts"] = abs(power) / 1_000_000
            if energy is not None:
                out["energyWh"] = energy / 1_000_000
            out["discharging"] = 1.0 if status == "Discharging" else 0.0
        return out, mains

    def read(self) -> dict[str, float]:
        """One reading. Missing readings are simply absent."""
        sample: dict[str, float] = {}
        for folder in self.hwmon:
            power = _int(os.path.join(folder, "power1_average")) or _int(os.path.join(folder, "power1_input"))
            temp = _int(os.path.join(folder, "temp1_input"))
            freq = _int(os.path.join(folder, "freq1_input"))
            if power is not None:
                sample["socketW"] = power / 1_000_000
            if temp is not None:
                sample["gpuTempC"] = temp / 1000
            if freq is not None:
                sample["gpuMhz"] = freq / 1_000_000
        if self.gpu:
            busy = _int(os.path.join(self.gpu, "gpu_busy_percent"))
            if busy is not None:
                sample["gpuBusy"] = float(busy)
            vram = _int(os.path.join(self.gpu, "mem_info_vram_used"))
            if vram is not None:
                sample["vramMiB"] = vram / 1024 / 1024
            try:
                with open(os.path.join(self.gpu, "gpu_metrics"), "rb") as handle:
                    metrics = parse_gpu_metrics(handle.read(1024))
            except OSError:
                metrics = None
            for key, value in (metrics or {}).items():
                sample.setdefault(key, value)  # hwmon first where both report
        cpu_temp = _int(self.cpu_temp) if self.cpu_temp else None
        if cpu_temp is not None:
            sample["cpuTempC"] = cpu_temp / 1000
        freqs = [f for f in (_int(p) for p in self.cpu_freqs) if f]
        if freqs:
            sample["cpuMhz"] = sum(freqs) / len(freqs) / 1000
        meminfo = _text(os.path.join(self.proc_root, "meminfo")) or ""
        values = {
            k: int(v.split()[0])
            for k, v in (line.split(":", 1) for line in meminfo.splitlines() if ":" in line)
            if v.split()
        }
        if "MemTotal" in values and "MemAvailable" in values:
            sample["ramMiB"] = (values["MemTotal"] - values["MemAvailable"]) / 1024
        battery, mains = self._battery()
        for key, value in battery.items():
            sample[f"battery_{key}"] = value
        if mains is not None:
            sample["mains"] = 1.0 if mains else 0.0
        return sample


def cpu_times(proc_root: str) -> tuple[int, int] | None:
    """``(busy, total)`` jiffies from the first line of ``/proc/stat``."""
    line = (_text(os.path.join(proc_root, "stat")) or "").splitlines()[:1]
    parts = line[0].split() if line else []
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    numbers = [int(p) for p in parts[1:9] if p.isdigit()]
    idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
    return sum(numbers) - idle, sum(numbers)


def read_sample(sys_root: str = "/sys", proc_root: str = "/proc") -> dict[str, float]:
    """One reading, finding the files first (for one-off checks; a session keeps its ``Sensors``)."""
    return Sensors(sys_root, proc_root).read()


def sources(sample: dict[str, float], fps_seen: bool) -> dict[str, bool]:
    """Which readings this device gives (for the Device check)."""
    return {
        "frameRate": fps_seen,
        "socketPower": "socketW" in sample,
        "cpuPower": "cpuW" in sample,
        "gpuPower": "gpuW" in sample,
        "battery": "battery_watts" in sample or "battery_percent" in sample,
        "temperatures": "gpuTempC" in sample or "cpuTempC" in sample,
        "load": "gpuBusy" in sample,
    }


# Frame rate: Steam's diagnostic entries, MangoHud's own logs


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value, shift = 0, 0
    while True:
        if at >= len(data) or shift > 63:
            raise ValueError("bad varint")
        byte = data[at]
        value |= (byte & 0x7F) << shift
        at += 1
        if not byte & 0x80:
            return value, at
        shift += 7


def protobuf_strings(data: bytes, depth: int = 0) -> list[list[str]]:
    """Every message's string fields, in order, from raw protobuf of unknown schema."""
    found: list[list[str]] = []
    strings: list[str] = []
    at = 0
    try:
        while at < len(data):
            key, at = _varint(data, at)
            wire = key & 7
            if wire == 0:
                _, at = _varint(data, at)
            elif wire == 1:
                at += 8
            elif wire == 5:
                at += 4
            elif wire == 2:
                length, at = _varint(data, at)
                chunk = data[at : at + length]
                if len(chunk) != length:
                    raise ValueError("truncated")
                at += length
                inner = protobuf_strings(chunk, depth + 1) if depth < 4 else []
                text = None
                try:
                    text = chunk.decode("utf-8")
                except UnicodeDecodeError:
                    pass
                if inner and not (text and text.isprintable()):
                    found += inner
                elif text is not None and text.isprintable():
                    strings.append(text)
            else:
                raise ValueError("unknown wire type")
    except ValueError:
        return found
    if strings:
        found.append(strings)
    return found


def steam_fps(diagnostic: bytes) -> tuple[float | None, float | None]:
    """``(fps, frame time ms)`` from Steam's performance diagnostic entries, by their names (A211)."""
    fps = frametime = None
    for fields in protobuf_strings(diagnostic):
        for name, value in itertools.pairwise(fields):
            number = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", value)
            if not number:
                continue
            if fps is None and FPS_NAME.search(name):
                fps = float(number.group(1))
            elif frametime is None and FRAMETIME_NAME.search(name):
                frametime = float(number.group(1))
    if fps is not None and not 1 <= fps <= 1000:
        fps = None
    if frametime is not None and not 0.5 <= frametime <= 1000:
        frametime = None
    return fps, frametime


def mangohud_folders(user_home: str) -> list[str]:
    """Where the user's MangoHud writes its logs: ``output_folder`` in its config, else its defaults."""
    folders = []
    config = os.path.join(user_home, ".config", "MangoHud", "MangoHud.conf")
    text = _text(config) or ""
    for line in text.splitlines():
        if line.strip().startswith("output_folder"):
            folder = line.split("=", 1)[-1].strip().strip('"')
            folders.append(user_home + folder[1:] if folder.startswith("~") else folder)  # the Decky user's home
    return [*folders, user_home, os.path.join(user_home, "mangologs")]


def mangohud_frametimes(folders: list[str], since: float, until: float) -> list[float]:
    """Frame times (ms) from MangoHud CSV logs written during the session, if the user logs with MangoHud."""
    times: list[float] = []
    for folder in folders:
        for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
            try:
                info = os.stat(path)
            except OSError:
                continue
            if not since - 5 <= info.st_mtime <= until + 120 or info.st_size > MAX_MANGOHUD_BYTES:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace", newline="") as handle:
                    rows = csv.reader(handle)
                    header = None
                    for row in rows:
                        if header is None:
                            lowered = [c.strip().lower() for c in row]
                            if "frametime" in lowered:
                                header = lowered.index("frametime")
                            continue
                        if header < len(row):
                            try:
                                value = float(row[header])
                            except ValueError:
                                continue
                            if 0.5 <= value <= 1000:
                                times.append(value)
            except OSError:
                continue
        if times:
            return times
    return times


def lows(frametimes: list[float]) -> dict[str, float]:
    """Average frame rate and the 1% and 0.1% lows (the frame rate of the slowest frames)."""
    if len(frametimes) < 100:
        return {}
    ordered = sorted(frametimes, reverse=True)

    def low(share: float) -> float:
        worst = ordered[: max(1, math.ceil(len(ordered) * share))]
        return round(1000 / (sum(worst) / len(worst)), 1)

    return {"avg": round(1000 * len(frametimes) / sum(frametimes), 1), "low1": low(0.01), "low01": low(0.001)}


# A session


class Accumulator:
    """Running totals of one session: no sample is kept, only what the summary needs."""

    def __init__(self, started: float) -> None:
        self.started = started
        self.ended = started
        self.sums: dict[str, float] = {}
        self.counts: dict[str, int] = {}
        self.peaks: dict[str, float] = {}
        self.samples = 0
        self.on_mains = 0
        self.fps: list[float] = []  # the current 5-second window only
        self.fps_sum = 0.0
        self.fps_count = 0
        self.fps_min_window: float | None = None
        self.frametimes_steam: list[float] = []
        self.battery_first: tuple[float, float] | None = None
        self.battery_last: tuple[float, float] | None = None
        self.throttle_at: float | None = None
        self.busy_seconds = 0.0
        self.cpu_last: tuple[int, int] | None = None

    def add(self, sample: dict[str, float], now: float, cpu: tuple[int, int] | None = None) -> None:
        self.samples += 1
        self.ended = now
        if cpu is not None and self.cpu_last is not None and cpu[1] > self.cpu_last[1]:
            sample = {**sample, "cpuBusy": 100 * (cpu[0] - self.cpu_last[0]) / (cpu[1] - self.cpu_last[1])}
        if cpu is not None:
            self.cpu_last = cpu
        for key, value in sample.items():
            self.sums[key] = self.sums.get(key, 0.0) + value
            self.counts[key] = self.counts.get(key, 0) + 1
            self.peaks[key] = max(self.peaks.get(key, value), value)
        if sample.get("mains"):
            self.on_mains += 1
        if "battery_percent" in sample and not sample.get("mains"):
            point = (now, sample["battery_percent"])
            self.battery_first = self.battery_first or point
            self.battery_last = point
        hot = max(sample.get("gpuTempC", 0), sample.get("cpuTempC", 0)) >= THROTTLE_TEMP_C
        if self.throttle_at is None and (sample.get("throttled") or hot):
            self.throttle_at = now

    def add_fps(self, fps: float, frametime: float | None = None) -> None:
        self.fps_sum += fps
        self.fps_count += 1
        self.fps.append(fps)
        if frametime is not None and len(self.frametimes_steam) < 100_000:
            self.frametimes_steam.append(frametime)
        if len(self.fps) >= WINDOW_SECONDS:
            window = sum(self.fps) / len(self.fps)
            self.fps_min_window = window if self.fps_min_window is None else min(self.fps_min_window, window)
            self.fps.clear()

    def avg(self, key: str) -> float | None:
        return round(self.sums[key] / self.counts[key], 1) if self.counts.get(key) else None

    def peak(self, key: str) -> float | None:
        return round(self.peaks[key], 1) if key in self.peaks else None

    def summary(self, mangohud: list[float] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        seconds = max(0.0, self.ended - self.started)
        fps: dict[str, Any] = {"source": None}
        detailed = lows(mangohud or []) or lows(self.frametimes_steam)
        if detailed:
            fps = {"source": "mangohud" if mangohud and lows(mangohud) else "steam", **detailed}
        elif self.fps_count:
            fps = {"source": "steam", "avg": round(self.fps_sum / self.fps_count, 1), "min5s": self.fps_min_window}
        battery: dict[str, Any] = {}
        if self.battery_first and self.battery_last and self.battery_last[0] > self.battery_first[0]:
            hours = (self.battery_last[0] - self.battery_first[0]) / 3600
            per_hour = (self.battery_first[1] - self.battery_last[1]) / hours if hours else 0
            battery["percentPerHour"] = round(per_hour, 1)
            if per_hour > 0:
                battery["lifeHours"] = round(100 / per_hour, 1)
        if self.avg("battery_watts") is not None and self.on_mains < self.samples:
            battery["drainW"] = self.avg("battery_watts")
        plugged = "plugged in" if self.on_mains == self.samples else "on battery" if not self.on_mains else "mixed"
        return {
            "start": round(self.started),
            "end": round(self.ended),
            "seconds": round(seconds),
            "power": plugged,
            "fps": fps,
            "watts": {
                "socketAvg": self.avg("socketW"),
                "socketPeak": self.peak("socketW"),
                "cpuAvg": self.avg("cpuW"),
                "cpuPeak": self.peak("cpuW"),
                "gpuAvg": self.avg("gpuW"),
                "gpuPeak": self.peak("gpuW"),
            },
            "battery": battery,
            "cpu": {
                "busyAvg": self.avg("cpuBusy"),
                "mhzAvg": self.avg("cpuMhz"),
                "tempAvg": self.avg("cpuTempC"),
                "tempPeak": self.peak("cpuTempC"),
            },
            "gpu": {
                "busyAvg": self.avg("gpuBusy"),
                "mhzAvg": self.avg("gpuMhz"),
                "tempAvg": self.avg("gpuTempC"),
                "tempPeak": self.peak("gpuTempC"),
            },
            "memory": {"ramPeakMiB": self.peak("ramMiB"), "vramPeakMiB": self.peak("vramMiB")},
            "throttle": {
                "seen": self.throttle_at is not None,
                "afterMinutes": round((self.throttle_at - self.started) / 60, 1) if self.throttle_at else None,
            },
            **(extra or {}),
        }


class SessionStore:
    """The last 20 sessions of each game, and a running summary, in Keepsake's own runtime folder."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    def _path(self, appid: int) -> str:
        return os.path.join(self.folder, f"{int(appid)}.json")

    def load(self, appid: int) -> dict[str, Any]:
        data = read_json(self._path(appid), default={})
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
            return {"sessions": [], "total": {"sessions": 0, "seconds": 0}}
        return data

    def add(self, appid: int, summary: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self.load(appid)
            data["sessions"] = [*data["sessions"], summary][-KEEP:]
            total = data.get("total") or {"sessions": 0, "seconds": 0}
            total["sessions"] = int(total.get("sessions", 0)) + 1
            total["seconds"] = int(total.get("seconds", 0)) + int(summary.get("seconds", 0))
            fps = (summary.get("fps") or {}).get("avg")
            if fps is not None:
                count = int(total.get("fpsSessions", 0))
                total["fpsAvg"] = round((float(total.get("fpsAvg", 0)) * count + fps) / (count + 1), 1)
                total["fpsSessions"] = count + 1
            data["total"] = total
            os.makedirs(self.folder, exist_ok=True)
            atomic_write_json(self._path(appid), data)
            return data


class Recorder:
    """Samples the running game once a second in a background thread; pauses while the device sleeps."""

    def __init__(
        self,
        store: SessionStore,
        sys_root: str = "/sys",
        proc_root: str = "/proc",
        clock: Callable[[], float] = time.time,
        interval: float = SAMPLE_SECONDS,
    ) -> None:
        self.store, self.sys_root, self.proc_root, self.clock, self.interval = (
            store,
            sys_root,
            proc_root,
            clock,
            interval,
        )
        self.appid: int | None = None
        self.acc: Accumulator | None = None
        self.extra: dict[str, Any] = {}
        self.paused = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.fps_seen = False
        self.sensors: Sensors | None = None

    def start(self, appid: int, extra: dict[str, Any]) -> None:
        self.stop_sampling()
        with self._lock:
            self.appid, self.extra = int(appid), dict(extra)
            self.acc = Accumulator(self.clock())
            self.sensors = Sensors(self.sys_root, self.proc_root)
            self._stop.clear()
            self.paused.clear()
            self._thread = threading.Thread(target=self._run, name="keepsake-sessions", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            if self.paused.is_set():
                continue
            self.sample_once()

    def sample_once(self) -> None:
        sensors = self.sensors or Sensors(self.sys_root, self.proc_root)
        sample = sensors.read()
        cpu = cpu_times(self.proc_root)
        with self._lock:
            if self.acc is not None:
                self.acc.add(sample, self.clock(), cpu)

    def feed_fps(self, fps: float | None, frametime: float | None) -> None:
        with self._lock:
            if self.acc is not None and fps is not None and not self.paused.is_set():
                self.fps_seen = True
                self.acc.add_fps(fps, frametime)

    def stop_sampling(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def finish(
        self, appid: int, mangohud: Callable[[float, float], list[float]] | None = None
    ) -> dict[str, Any] | None:
        """Stop and keep the session's summary, if it is this game's and long enough."""
        self.stop_sampling()
        with self._lock:
            acc, extra, current = self.acc, self.extra, self.appid
            self.acc, self.appid = None, None
        if acc is None or current != int(appid) or acc.ended - acc.started < MIN_SESSION_SECONDS:
            return None
        frames = mangohud(acc.started, acc.ended) if mangohud else None
        summary = acc.summary(frames, extra)
        self.store.add(int(appid), summary)
        return summary


# Advice from measurements


def ai_numbers(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The last sessions as plain numbers for the AI explanation: no paths, names or launch options (P18)."""
    out = []
    for s in sessions[-5:]:
        settings = s.get("settings") or {}
        out.append(
            {
                "minutes": round(s.get("seconds", 0) / 60),
                "power": s.get("power"),
                "fpsAvg": (s.get("fps") or {}).get("avg"),
                "fpsLow1": (s.get("fps") or {}).get("low1") or (s.get("fps") or {}).get("min5s"),
                "socketW": (s.get("watts") or {}).get("socketAvg"),
                "cpuBusy": (s.get("cpu") or {}).get("busyAvg"),
                "gpuBusy": (s.get("gpu") or {}).get("busyAvg"),
                "gpuTempPeak": (s.get("gpu") or {}).get("tempPeak"),
                "throttledAfterMinutes": (s.get("throttle") or {}).get("afterMinutes"),
                "tdpW": settings.get("tdp"),
                "frameCap": settings.get("frameCap"),
            }
        )
    return out


def advice(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Advice measured on this device, weighted above community reports when they disagree."""
    if not sessions:
        return []
    source = f"Measured on this device, {len(sessions)} {'session' if len(sessions) == 1 else 'sessions'}"
    last = sessions[-1]
    fps = last.get("fps") or {}
    settings = last.get("settings") or {}
    out: list[dict[str, Any]] = []

    def item(kind: str, text: str) -> None:
        out.append({"id": kind, "text": text, "source": source, "measured": True})

    low = fps.get("low1") or fps.get("min5s")
    cap, tdp = settings.get("frameCap"), settings.get("tdp")
    if low and cap and low < 0.85 * cap:
        target = max(30, int(low // 5 * 5))
        at = f" at {tdp} W" if tdp else ""
        item(
            "cap",
            f"The 1% lows were {low:.0f} fps, well under your {cap} fps cap{at}: "
            f"lower the cap to {target} or raise the TDP.",
        )
    gpu, cpu = (last.get("gpu") or {}).get("busyAvg"), (last.get("cpu") or {}).get("busyAvg")
    if gpu is not None and cpu is not None and gpu >= 95 and cpu <= 50:
        item(
            "gpu-bound",
            f"The GPU was at {gpu:.0f}% and the CPU at {cpu:.0f}%, so it is GPU-bound: "
            "lower the resolution or use FSR.",
        )
    by_tdp: dict[float, list[float]] = {}
    for s in sessions:
        t, f = (s.get("settings") or {}).get("tdp"), (s.get("fps") or {}).get("avg")
        if t and f:
            by_tdp.setdefault(float(t), []).append(float(f))
    if len(by_tdp) >= 2:
        means = {t: sum(v) / len(v) for t, v in by_tdp.items()}
        low_tdp, high_tdp = min(means), max(means)
        if means[low_tdp] >= 0.95 * means[high_tdp]:
            item(
                "save-battery",
                f"You get the same frame rate at {low_tdp:.0f} W ({means[low_tdp]:.0f} fps) as at {high_tdp:.0f} W "
                f"({means[high_tdp]:.0f} fps), so {low_tdp:.0f} W saves battery.",
            )
    after = (last.get("throttle") or {}).get("afterMinutes")
    if after is not None:
        item("throttle", f"It throttled after {after:.0f} minutes: a lower TDP or frame cap keeps it cooler.")
    return out
