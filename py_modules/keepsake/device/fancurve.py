"""Fan curves for the Legion Go 2, and the controller that follows them (R24, ADR-0085). Pure: no I/O.

A curve is 2 to 8 points of (temperature °C, fan RPM), rising in both. The controller turns the
temperature into an RPM target the way the careful tools do: up at once when it gets hotter, down
only after the temperature has dropped by the hysteresis and stayed down for the dwell, and then
in small steps. At the failsafe temperature it goes straight to the ceiling, whatever the curve.

Limits (from the research, `docs/research/fan-control.md`):
- every point is 1500 to 4800 RPM (handing the fan back to the firmware is a separate action);
- the point at the highest temperature is at least 2000 RPM;
- the "unlock" lets the user go below the safe defaults' shape (down to the 1500 floor) and above
  4800 up to 5200, off by default; it never lifts the failsafe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

MIN_RPM, MAX_RPM, UNLOCKED_MAX = 1500, 4800, 5200
LAST_POINT_MIN = 2000
FAILSAFE_C = 101.0
MAX_POINTS = 8
DEFAULT = [(40, 1500), (55, 1800), (65, 2200), (75, 2800), (85, 3600), (95, 4800)]
QUIET = [(45, 1500), (60, 1700), (70, 2000), (80, 2600), (90, 3600), (95, 4800)]
COOL = [(35, 1800), (50, 2200), (60, 2800), (70, 3400), (80, 4200), (90, 4800)]
PRESETS = {"balanced": DEFAULT, "quiet": QUIET, "cool": COOL}


class CurveError(ValueError):
    pass


def clean(points: Any, unlocked: bool = False) -> list[tuple[int, int]]:
    """A curve from the page or the file, checked: rising, within the limits, at most 8 points."""
    if not isinstance(points, list) or not 2 <= len(points) <= MAX_POINTS:
        raise CurveError(f"a curve has 2 to {MAX_POINTS} points")
    top = UNLOCKED_MAX if unlocked else MAX_RPM
    out: list[tuple[int, int]] = []
    for item in points:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise CurveError("each point is a temperature and a speed")
        temp, rpm = item
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (temp, rpm)):
            raise CurveError("temperatures and speeds are whole numbers")
        if not 20 <= temp <= 100:
            raise CurveError("temperatures are 20 to 100 °C")
        if not MIN_RPM <= rpm <= top:
            raise CurveError(f"speeds are {MIN_RPM} to {top} RPM")
        out.append((temp, rpm))
    temps = [t for t, _ in out]
    speeds = [r for _, r in out]
    if temps != sorted(set(temps)):
        raise CurveError("temperatures must rise from point to point")
    if any(b < a for a, b in pairwise(speeds)):
        raise CurveError("speeds must not fall as the temperature rises")
    if speeds[-1] < LAST_POINT_MIN:
        raise CurveError(f"the hottest point must be at least {LAST_POINT_MIN} RPM")
    return out


def target(points: list[tuple[int, int]], temp: float, smooth: bool = True) -> int:
    """The curve's RPM at ``temp``: stepped (the point at or below) or smooth (straight lines)."""
    if temp >= FAILSAFE_C:
        return max(MAX_RPM, points[-1][1])
    if temp <= points[0][0]:
        return points[0][1]
    for (t0, r0), (t1, r1) in pairwise(points):
        if t0 <= temp < t1:
            if not smooth:
                return r0
            return round(r0 + (r1 - r0) * (temp - t0) / (t1 - t0))
    return points[-1][1]


@dataclass
class Controller:
    """Follows a curve with hysteresis: up at once, down after a drop of ``hysteresis`` °C held for
    ``dwell`` seconds, by at most ``step_down`` RPM per update."""

    points: list[tuple[int, int]]
    smooth: bool = True
    hysteresis: float = 2.0
    dwell: float = 5.0
    step_down: int = 300
    step_every: float = 2.0
    current: int | None = None
    last_step: float | None = None
    peak: float = field(default=-1000.0)  # the temperature the current speed was set for
    low_since: float | None = None

    def update(self, temp: float, now: float) -> int:
        wanted = target(self.points, temp, self.smooth)
        if temp >= FAILSAFE_C or self.current is None or wanted >= self.current:
            if self.current is None or wanted > self.current:
                self.peak = temp
            self.current = wanted
            self.low_since = self.last_step = None
            return wanted
        # Cooler: wait for a real drop that lasts, then come down a step at a time.
        if temp > self.peak - self.hysteresis:
            self.low_since = self.last_step = None
            return self.current
        if self.low_since is None:
            self.low_since = now
        if now - self.low_since < self.dwell:
            return self.current
        if self.last_step is not None and now - self.last_step < self.step_every:
            return self.current
        self.current = max(wanted, self.current - self.step_down)
        self.last_step = now
        if self.current == wanted:
            self.peak, self.low_since, self.last_step = temp, None, None
        return self.current
