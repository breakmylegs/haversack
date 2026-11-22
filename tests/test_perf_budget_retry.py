"""The performance budget measures twice before failing, so one stalled measurement on a busy laptop does not
stop a release, while a slowdown seen twice still does."""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import perf_budget

NAME = "match 500 games"


def runs(monkeypatch: Any, *values: float) -> list[int]:
    calls = []
    seq = iter(values)

    def fake_run() -> dict[str, float]:
        calls.append(1)
        return {NAME: next(seq)}

    monkeypatch.setattr(perf_budget, "run", fake_run)
    monkeypatch.setattr(perf_budget, "BUDGETS", {NAME: 0.5})
    return calls


def test_a_one_off_spike_passes(monkeypatch: Any) -> None:
    calls = runs(monkeypatch, 2.0, 0.1)
    assert perf_budget.main() == 0 and len(calls) == 2


def test_a_slowdown_seen_twice_fails(monkeypatch: Any) -> None:
    calls = runs(monkeypatch, 2.0, 1.5)
    assert perf_budget.main() == 1 and len(calls) == 2


def test_within_budget_measures_once(monkeypatch: Any) -> None:
    calls = runs(monkeypatch, 0.1)
    assert perf_budget.main() == 0 and len(calls) == 1
