"""ProtonDB reports from Keepsake's own index (c0-report Q4 option a, ADR-0035).

The index is built on the owner's laptop from ProtonDB's monthly ODbL dump by
``scripts/protondb_index.py`` and published as the rolling release
``protondb-index`` of the Keepsake repository. Advisor downloads it once when
the source is turned on (off by default), refreshes it after 31 days, and finds
one game by reading the gzipped lines; nothing stays in memory, and no game is
ever named to anyone. ``www.protondb.com`` is never called.

ProtonDB has no TDP or frame-rate fields, so its reports feed the compatibility
section (Proton version, launch options) and notes, not power settings.
Ported from Tuning Advisor (ADR-0013).
"""

from __future__ import annotations

import gzip
import io
import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .. import net
from ..fsutil import atomic_write_bytes

INDEX_FILE = "protondb-index.json.gz"
RELEASE_TAG = "protondb-index"
URL = f"https://github.com/breakmylegs/haversack/releases/download/{RELEASE_TAG}/{INDEX_FILE}"
REFRESH_AFTER = 31 * 24 * 60 * 60
RETRY_AFTER = 60 * 60
MAX_BYTES = 30 * 1024 * 1024
SCHEMA = 1
SOURCE = "protondb"
ATTRIBUTION = "Contains information from ProtonDB, made available under the ODbL."
MAX_REPORTS = 5
_GE = re.compile(r"ge[- ]?proton\s*(\d+[-.]\d+)", re.I)


class ProtonDbError(Exception):
    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint


Downloader = Callable[[str], bytes]


def download(url: str) -> bytes:
    """Blocking. GitHub redirects release downloads to its file host (both allowlisted). Held in memory, capped."""
    try:
        response = net.fetch(url, headers={"Accept": "application/octet-stream"}, timeout=60.0, max_bytes=MAX_BYTES)
    except net.NetError as exc:
        raise ProtonDbError("Could not download the ProtonDB index. It is tried again in an hour.") from exc
    if response.status != 200:
        raise ProtonDbError(f"The ProtonDB index answered HTTP {response.status}.")
    return response.body


def _header(handle: Any) -> dict[str, Any] | None:
    try:
        data = json.loads(handle.readline(65536))
    except (OSError, ValueError, EOFError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == SCHEMA else None


class ProtonDbIndex:
    """The index file in the Advisor's own cache folder. Its only write is ``atomic_write_bytes`` (P16)."""

    def __init__(
        self,
        cache_dir: str,
        url: str = URL,
        fetch: Downloader = download,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.path = os.path.join(cache_dir, INDEX_FILE)
        self.url = url
        self._fetch = fetch
        self._now = now
        self._failed_at: float | None = None

    def header(self) -> dict[str, Any] | None:
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as handle:
                return _header(handle)
        except (OSError, EOFError):
            return None

    def age(self) -> float | None:
        try:
            return self._now() - os.path.getmtime(self.path)
        except OSError:
            return None

    def ensure(self, force: bool = False) -> dict[str, Any]:
        """Blocking. Download when missing, unreadable or a month old. A failed refresh keeps the old copy."""
        header = self.header()
        age = self.age()
        if header and age is not None and age < REFRESH_AFTER and not force:
            return header
        if not force and self._failed_at is not None and self._now() - self._failed_at < RETRY_AFTER:
            if header:
                return header
            raise ProtonDbError("Could not download the ProtonDB index. Press Refresh to try again.")
        try:
            data = self._fetch(self.url)
            # Checked in memory, so a bad download never replaces the old copy.
            with gzip.open(io.BytesIO(data), "rt", encoding="utf-8") as handle:
                fresh = _header(handle)
            if fresh is None or len(data) > MAX_BYTES:
                raise ProtonDbError("The downloaded ProtonDB index was not valid. Try again later.")
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            atomic_write_bytes(self.path, data)
        except (ProtonDbError, OSError, EOFError) as exc:
            self._failed_at = self._now()
            if header is not None:
                return header
            if isinstance(exc, ProtonDbError):
                raise
            raise ProtonDbError("The downloaded ProtonDB index was not valid. Try again later.") from exc
        self._failed_at = None
        return fresh

    def lookup(self, appid: int) -> dict[str, Any] | None:
        """The index entry for one Steam app ID, or None. Reads line by line."""
        prefix = f"{int(appid)}\t"
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as handle:
                handle.readline()
                for line in handle:
                    if line.startswith(prefix):
                        entry = json.loads(line[len(prefix) :])
                        return entry if isinstance(entry, dict) else None
        except (OSError, ValueError, EOFError, UnicodeDecodeError):
            return None
        return None

    def clear(self) -> None:
        """Free the space when the source is turned off: the file is emptied, never deleted (P16)."""
        if os.path.exists(self.path):
            atomic_write_bytes(self.path, b"")


def _text(value: Any, limit: int) -> str:
    text = " ".join(str(value).split()) if isinstance(value, (str, int, float)) else ""
    return text[:limit]


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value and abs(value) < 1e15:  # not NaN or huge
        return int(value)
    return 0


def compat_fields(variant: Any, proton: Any) -> tuple[str | None, str | None]:
    """ProtonDB's variant and version as the tool and version ``compat.proton_name`` reads."""
    text = _text(proton, 40)
    ge = _GE.search(text)
    if variant == "ge" or ge:
        return "Glorious Eggroll Proton (GE)", ge.group(1) if ge else "latest"
    if variant == "native":
        return "Native Linux", ""
    if variant == "experimental":
        return "Steam Proton", "experimental"
    if text:
        return "Steam Proton", re.sub(r"(?i)^\s*proton\s*", "", text) or "default"
    if variant == "official":
        return "Steam Proton", "default"
    return None, None


def normalise(entry: dict[str, Any], appid: int) -> list[dict[str, Any]]:
    """Index reports in the shape the Advisor's ranking reads (the Deck Verified one)."""
    reports = entry.get("reports")
    out: list[dict[str, Any]] = []
    for report in reports if isinstance(reports, list) else []:
        if not isinstance(report, dict):
            continue
        ts = _int(report.get("t"))
        works = report.get("verdict") == "yes"
        tool, version = compat_fields(report.get("variant"), report.get("proton"))
        launch = _text(report.get("launch"), 200) or None
        frame_gen = (
            "lsfg-vk" if launch and "lsfg" in launch else ("optiscaler" if launch and "fgmod" in launch else None)
        )
        notes = _text(report.get("notes"), 240)
        try:
            date = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if 0 < ts < 4102444800 else ""
        except (OverflowError, OSError, ValueError):
            date = ""
        out.append(
            {
                "source": SOURCE,
                "source_url": f"https://www.protondb.com/app/{int(appid)}",
                "report_title": "Works" if works else "Reported not working",
                "report_date": date,
                "votes": 0,
                "device_reported": _text(report.get("device"), 80),
                "apu_reported": _text(report.get("apu"), 80),
                "device_match": "other_handheld",
                "confidence": "low",
                "works": works,
                "power": {"tdp_w": None, "gpu_clock_mhz": None},
                "display": {"refresh_hz": None, "fps_cap": None, "vrr": None},
                "scaling": {"steam_filter": None, "scaling_mode": None, "game_resolution": None},
                "upscaler": {"name": None, "mode": None},
                "frame_gen": {"tool": frame_gen, "mode": None},
                "in_game": {"preset": None, "settings": []},
                "compat": {
                    "proton": _text(report.get("proton"), 40) or None,
                    "tool": tool,
                    "tool_version": version,
                    "launch_options": launch,
                },
                "notes": notes if works else f"Reported not working. {notes}".strip(),
            }
        )
        if len(out) >= MAX_REPORTS:
            break
    return out


def summary(entry: dict[str, Any] | None, header: dict[str, Any] | None, appid: int) -> dict[str, Any] | None:
    if not entry:
        return None
    n = max(_int(entry.get("n")), 0)
    works = min(max(_int(entry.get("works")), 0), n)
    return {
        "reports": n,
        "works": works,
        "handheld": max(_int(entry.get("handheld")), 0),
        "share": round(100 * works / n) if n else None,
        "dump": _text((header or {}).get("dump"), 30),
        "url": f"https://www.protondb.com/app/{int(appid)}",
        "attribution": ATTRIBUTION,
    }
