"""BIOS check (R21 stage 6, ADR-0079): known Legion Go BIOS problems, from the version DMI shows. Read-only.

The Legion Go's BIOS version reads ``N3CNxxWW``. Known from Lenovo and the research
(``docs/research/legion-control.md``):
- N3CN42WW bricked units; Lenovo withdrew it and rolled support back to N3CN40WW.
- Before v28 there are no custom fan curves; before v29 there is no 80% charge limit.
- On v29 a custom fan curve and custom TDP could not be used together (fixed in v29.1).
Keepsake never updates a BIOS; it only says what it knows.
"""

from __future__ import annotations

import os
import re
from typing import Any

LEGION_GO = re.compile(r"^N3CN(\d{2})WW$")


def _text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(128).strip()
    except OSError:
        return None


def check(sys_root: str = "/sys") -> dict[str, Any]:
    dmi = os.path.join(sys_root, "class", "dmi", "id")
    version = _text(os.path.join(dmi, "bios_version"))
    product = _text(os.path.join(dmi, "product_name"))
    out: dict[str, Any] = {
        "version": version,
        "date": _text(os.path.join(dmi, "bios_date")),
        "notes": [],
        "level": "ok",
    }
    match = LEGION_GO.match(version or "")
    if not match:
        out["known"] = False
        return out
    number = int(match.group(1))
    out.update(known=True, model="Legion Go", number=number)
    notes: list[str] = []
    if number == 42:
        notes.append(
            "This BIOS (N3CN42WW) bricked some units and Lenovo withdrew it. Lenovo supports N3CN40WW; "
            "contact Lenovo if anything misbehaves."
        )
        out["level"] = "fail"
    if number < 28:
        notes.append("This BIOS has no custom fan curves; v28 or later adds them.")
    if number < 29:
        notes.append("This BIOS has no 80% charge limit; v29 or later adds it.")
        out["level"] = "warn" if out["level"] == "ok" else out["level"]
    if number == 29:
        notes.append("On v29 a custom fan curve and custom TDP cannot be used together; v29.1 or later fixes it.")
        out["level"] = "warn" if out["level"] == "ok" else out["level"]
    out["notes"] = notes
    if product and product != "83E1":
        out["product"] = product
    return out
