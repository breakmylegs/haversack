"""Performance budget (ADR-0050): the hot paths at 500 games and 10,000 snapshots, against time limits.

    python scripts/perf_budget.py

Part of ``scripts/check.py``. All data is synthetic and built in memory, so it needs no
network and no files. The limits are about four times what this laptop measures, so a
slow day passes but a real regression (an accidental quadratic loop) fails.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "py_modules"))

from keepsake import manifest, ordering, retention  # noqa: E402
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
}


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
