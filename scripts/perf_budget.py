"""Performance budget (ADR-0050): the hot paths at 500 games and 10,000 snapshots, against time limits.

    python scripts/perf_budget.py

Part of ``scripts/check.py``. All data is synthetic and built in memory, so it needs no
network and no files. The limits are about four times what this laptop measures, so a
slow day passes but a real regression (an accidental quadratic loop) fails.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Callable
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "py_modules"))

from keepsake import manifest, ordering, retention  # noqa: E402
from keepsake.advisor import sessions  # noqa: E402
from keepsake.snapshot import FileEntry, content_hash  # noqa: E402

GAMES = 500
TITLES = 5000
SNAPSHOTS = 10_000
FILES = 10_000

# Seconds. Measured on the development laptop, then about four times that.
BUDGETS = {
    "manifest index of 5,000 titles": 4.0,
    "match 500 games": 0.5,
    "order 500 games": 0.25,
    "retention plan over 10,000 snapshots": 1.0,
    "content hash of 10,000 files": 0.25,
    # Advisor sessions (ADR-0069): sampling runs once a second while a game plays, so it must stay tiny.
    "100 session readings": 1.5,  # about 3.4 ms a reading on the laptop (far less on sysfs): once a second
    "an hour of session samples summarised": 0.25,
}


def fake_sys(root: str) -> None:
    """A handheld's sysfs files as the session sampler reads them."""
    gpu = os.path.join(root, "class", "drm", "card0", "device")
    files = {
        os.path.join(gpu, "vendor"): "0x1002",
        os.path.join(gpu, "gpu_busy_percent"): "97",
        os.path.join(gpu, "mem_info_vram_used"): str(2 * 1024**3),
        os.path.join(gpu, "hwmon", "hwmon3", "power1_average"): "15000000",
        os.path.join(gpu, "hwmon", "hwmon3", "temp1_input"): "71000",
        os.path.join(root, "class", "hwmon", "hwmon1", "name"): "k10temp",
        os.path.join(root, "class", "hwmon", "hwmon1", "temp1_input"): "68000",
        os.path.join(root, "class", "power_supply", "BAT0", "type"): "Battery",
        os.path.join(root, "class", "power_supply", "BAT0", "capacity"): "77",
        os.path.join(root, "class", "power_supply", "BAT0", "power_now"): "17000000",
        os.path.join(root, "class", "power_supply", "BAT0", "status"): "Discharging",
    }
    for cpu in range(16):
        files[os.path.join(root, "devices", "system", "cpu", f"cpu{cpu}", "cpufreq", "scaling_cur_freq")] = "2800000"
    for path, text in files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


def manifest_lines(titles: int) -> list[str]:
    lines = ["---"]
    for n in range(titles):
        lines += [
            f"Synthetic Title {n:05d}:",
            "  files:",
            f'    "<winLocalAppData>/SyntheticTitle{n:05d}":',
            "      tags:",
            "        - save",
            "  steam:",
            f"    id: {1999990000 + n}",
        ]
    return lines


def games(count: int) -> list[dict[str, Any]]:
    return [
        {
            "key": f"shortcut:7:{3000000000 + n}",
            "kind": "shortcut",
            "appid": 3000000000 + n,
            "name": f"Synthetic Title {n * 7 % TITLES:05d}",
        }
        for n in range(count)
    ]


def metas(count: int) -> list[dict[str, Any]]:
    out = []
    parent: list[str] = []
    for n in range(count):
        snap_id = f"{n:06d}-aaaaaa-{n:08x}"
        day, rest = divmod(n, 24)
        out.append(
            {
                "snapId": snap_id,
                "parents": parent,
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(1_700_000_000 + day * 86400 + rest * 3600)),
                "kind": "auto-exit",
                "flags": [],
                "deviceId": "aaaaaaaa",
            }
        )
        parent = [snap_id]
    return out


def measure(work: Callable[[], Any]) -> float:
    start = time.perf_counter()
    work()
    return time.perf_counter() - start


def run() -> dict[str, float]:
    lines = manifest_lines(TITLES)
    index: dict[str, Any] = {}

    def build() -> None:
        index.update(manifest.build_index(lines))

    results = {"manifest index of 5,000 titles": measure(build)}
    library = games(GAMES)
    matched: list[dict[str, Any]] = []

    def match() -> None:
        for game in library:
            found = manifest.match_game(index, game, {})
            matched.append({"key": game["key"], "name": game["name"], "enabled": True, "sync": "synced", **found})

    results["match 500 games"] = measure(match)
    results["order 500 games"] = measure(lambda: ordering.order(matched, set()))
    history = metas(SNAPSHOTS)
    results["retention plan over 10,000 snapshots"] = measure(
        lambda: retention.plan(history, set(), set(), set(), 1_700_000_000 + SNAPSHOTS * 3600)
    )
    entries = [FileEntry("winLocalAppData", f"Game/save{n:05d}.sav", n, f"{n:064x}") for n in range(FILES)]
    results["content hash of 10,000 files"] = measure(lambda: content_hash(entries))
    with tempfile.TemporaryDirectory() as root:
        fake_sys(root)
        sensors = sessions.Sensors(root, root)  # found once per session, as the recorder does
        results["100 session readings"] = measure(lambda: [sensors.read() for _ in range(100)])
        sample = sensors.read()

    def an_hour() -> None:
        acc = sessions.Accumulator(0.0)
        for second in range(3600):
            acc.add(sample, float(second), (second * 50, second * 100))
            acc.add_fps(55.0 + second % 7, 18.0)
        acc.summary()

    results["an hour of session samples summarised"] = measure(an_hour)
    if len(matched) != GAMES or not all(m.get("title") for m in matched):
        raise SystemExit("perf budget: the synthetic games did not all match; the benchmark is broken")
    return results


def main() -> int:
    results = run()
    failed = []
    for name, seconds in results.items():
        limit = BUDGETS[name]
        mark = "ok" if seconds <= limit else "OVER"
        print(f"{mark:4}  {seconds:7.3f} s of {limit:4.1f} s  {name}")
        if seconds > limit:
            failed.append(name)
    print("perf: within budget" if not failed else f"perf: over budget: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
