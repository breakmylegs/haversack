"""Build Keepsake's ProtonDB index from a monthly ODbL dump, and publish it (ADR-0035).

Runs on the laptop only (ADR-0004: nothing runs on GitHub). Ported from Tuning
Advisor's tools/protondb_index.py (ADR-0013).

Source: https://github.com/bdefore/protondb-data, reports/reports_<mon><n>_<year>.tar.gz,
one JSON array in reports_piiremoved.json. Licence: ODbL 1.0 for the database,
DbCL 1.0 for its contents. The index is a derived database, so it is published
under the ODbL too, with attribution, and this script is how to rebuild it.

Steps:
  survey   print the dump's shape (record keys, handheld share)
  build    stream the dump (never extracted) and write out/protondb-index.json.gz
  publish  upload that file to the rolling release protondb-index (never "latest")

Index format, gzipped UTF-8 text, so Advisor finds one app by reading lines
without holding the index in memory:
  line 1:   {"schema": 1, "dump": "oct1_2026", "licence": ..., ...}
  then:     <appid><TAB>{"n": .., "works": .., "handheld": .., "title": .., "reports": [...]}
  sorted by app ID as text. Only apps with reports from handheld chips are kept.

Usage:
  python -I scripts/protondb_index.py survey <dump.tar.gz>
  python -I scripts/protondb_index.py build <dump.tar.gz> [--out out/]
  python scripts/protondb_index.py publish out/protondb-index.json.gz
"""

from __future__ import annotations

import collections
import gzip
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterator
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBER = "reports_piiremoved.json"
INDEX_NAME = "protondb-index.json.gz"
RELEASE_TAG = "protondb-index"  # not a v* tag: the updater and the install link ignore it
WHITESPACE = " \t\r\n"
SCHEMA = 1
ATTRIBUTION = "Contains information from ProtonDB, made available under the ODbL."
MAX_INDEX_BYTES = 30 * 1024 * 1024  # Advisor refuses anything larger

# Handheld chips, matched in a report's CPU or GPU string: (pattern, device label, chip).
# The chip matches the "apu" of Keepsake's device profiles, so Advisor can say "same chip".
HANDHELD_CHIPS = [
    (re.compile(r"custom (?:apu|gpu) 0405|aerith", re.I), "Steam Deck LCD", "AMD Aerith (Van Gogh)"),
    (re.compile(r"custom (?:apu|gpu) 0932|sephiroth", re.I), "Steam Deck OLED", "AMD Sephiroth"),
    (re.compile(r"z2 extreme", re.I), "Handheld with Ryzen Z2 Extreme", "AMD Ryzen Z2 Extreme"),
    (re.compile(r"z1 extreme", re.I), "Handheld with Ryzen Z1 Extreme", "AMD Ryzen Z1 Extreme"),
    (re.compile(r"z2 go", re.I), "Handheld with Ryzen Z2 Go", "AMD Ryzen Z2 Go"),
    (re.compile(r"\bz2 a\b", re.I), "Handheld with Ryzen Z2 A", "AMD Ryzen Z2 A"),
    (re.compile(r"\bryzen z2\b(?! (?:extreme|go|a)\b)", re.I), "Handheld with Ryzen Z2", "AMD Ryzen Z2"),
    (re.compile(r"\bryzen z1\b(?! extreme)", re.I), "Handheld with Ryzen Z1", "AMD Ryzen Z1"),
]
MAX_REPORTS_PER_APP = 5
MAX_TEXT = 240


def records(text: io.TextIOBase, chunk: int = 1 << 22) -> Iterator[dict[str, Any]]:
    """Yield objects from a top-level JSON array without loading it all.

    Reads text, so multi-byte characters never split across chunks, and trims
    the buffer only when a new chunk is read, so it stays linear.
    """
    decoder = json.JSONDecoder()
    buf = ""
    pos = 0
    eof = False
    opened = False
    while True:
        if not eof and len(buf) - pos < chunk:
            data = text.read(chunk)
            if data:
                buf = buf[pos:] + data
                pos = 0
            else:
                eof = True
        while pos < len(buf) and buf[pos] in WHITESPACE:
            pos += 1
        if not opened and pos < len(buf):
            if buf[pos] != "[":
                raise ValueError("the dump is not a JSON array")
            pos += 1
            opened = True
            continue
        while pos < len(buf) and buf[pos] in WHITESPACE + ",":
            pos += 1
        if pos >= len(buf):
            if eof:
                # A cut-off download must not quietly give a smaller index.
                raise ValueError("the dump ends before its closing bracket" if opened else "the dump is empty")
            continue
        if buf[pos] == "]":
            return
        try:
            obj, end = decoder.raw_decode(buf, pos)
        except ValueError:
            if eof:
                raise ValueError("the dump ends part way through a record") from None
            data = text.read(chunk)
            if not data:
                eof = True
            else:
                buf = buf[pos:] + data
                pos = 0
            continue
        if isinstance(obj, dict):
            yield obj
        pos = end


def open_dump(path: str) -> io.TextIOBase:
    tar = tarfile.open(path)  # one named member is streamed; nothing is extracted to disk
    member = tar.extractfile(MEMBER)
    if member is None:
        raise SystemExit(f"{MEMBER} not found in {path}")
    return io.TextIOWrapper(member, encoding="utf-8", errors="replace")


def dump_name(path: str) -> str:
    match = re.search(r"reports_([a-z]{3}\d+_\d{4})", os.path.basename(path))
    if not match:
        raise SystemExit("Name the dump as downloaded, for example reports_oct1_2026.tar.gz")
    return match.group(1)


def handheld(record: dict[str, Any]) -> tuple[str, str] | None:
    """(device label, chip) for reports from handheld chips, else None."""
    info = record.get("systemInfo") or {}
    info = info if isinstance(info, dict) else {}
    text = f"{info.get('cpu') or ''} {info.get('gpu') or ''}"
    for pattern, label, chip in HANDHELD_CHIPS:
        if pattern.search(text):
            return label, chip
    return None


def _text(value: Any) -> str:
    """Single-line text with home folders and links removed, capped."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"/(?:var/)?home/[^/\s\"']+", "~", text)
    # Removable media and Windows profiles can carry a user name or card label too.
    text = re.sub(r"/run/media/(?:[^/\s\"']+/){1,2}", "/run/media/.../", text)
    text = re.sub(r"(?i)\b([a-z]):[\\/]+users[\\/]+[^\\/\s\"']+", r"\1:/Users/...", text)
    text = re.sub(r"https?://\S+", "[link]", text)
    return text[:MAX_TEXT]


def summarise(record: dict[str, Any]) -> dict[str, Any] | None:
    resp = record.get("responses") or {}
    resp = resp if isinstance(resp, dict) else {}
    if resp.get("type") not in (None, "steamPlay"):
        return None
    found = handheld(record)
    if found is None:
        return None
    notes = resp.get("notes") or {}
    if isinstance(notes, str):
        notes = {"verdict": notes}
    notes = notes if isinstance(notes, dict) else {}
    info = record.get("systemInfo") or {}
    info = info if isinstance(info, dict) else {}
    return {
        "t": int(record.get("timestamp") or 0),
        "device": found[0],
        "apu": found[1],
        "os": _text(info.get("os"))[:60],
        "verdict": resp.get("verdict"),
        "variant": resp.get("variant"),
        "proton": _text(resp.get("customProtonVersion") or resp.get("protonVersion"))[:40] or None,
        "battery": resp.get("batteryPerformance"),
        "launch": _text(resp.get("launchOptions"))[:200] or None,
        "notes": _text(notes.get("verdict") or notes.get("extra") or resp.get("concludingNotes") or "") or None,
        "tinker": bool(resp.get("tinkerOverride") or resp.get("launchOptions")),
    }


def survey(path: str) -> None:
    count = 0
    keys: collections.Counter[str] = collections.Counter()
    devices: collections.Counter[str] = collections.Counter()
    latest = 0
    apps = set()
    for rec in records(open_dump(path)):
        count += 1
        resp = rec.get("responses") or {}
        keys.update(resp.keys() if isinstance(resp, dict) else [])
        latest = max(latest, int(rec.get("timestamp") or 0))
        apps.add(str(((rec.get("app") or {}).get("steam") or {}).get("appId")))
        found = handheld(rec)
        devices[found[0] if found else "other"] += 1
    print(
        json.dumps(
            {
                "records": count,
                "apps": len(apps),
                "latest": latest,
                "response_keys": keys.most_common(),
                "handheld": devices.most_common(),
            },
            indent=1,
        )
    )


def build(path: str, out_dir: str) -> str:
    name = dump_name(path)
    per_app: dict[str, dict[str, Any]] = {}
    total = 0
    for rec in records(open_dump(path)):
        total += 1
        app_info = rec.get("app") or {}
        app_info = app_info if isinstance(app_info, dict) else {}
        app = str((app_info.get("steam") or {}).get("appId") or "")
        if not app.isdigit():
            continue
        entry = per_app.setdefault(app, {"n": 0, "works": 0, "handheld": 0, "title": "", "reports": []})
        entry["n"] += 1
        resp = rec.get("responses") or {}
        if isinstance(resp, dict) and resp.get("verdict") == "yes":
            entry["works"] += 1
        if app_info.get("title") and not entry["title"]:
            entry["title"] = _text(app_info["title"])[:80]
        summary = summarise(rec)
        if summary:
            entry["handheld"] += 1
            entry["reports"].append(summary)
    for entry in per_app.values():
        entry["reports"].sort(key=lambda r: r["t"], reverse=True)
        entry["reports"] = entry["reports"][:MAX_REPORTS_PER_APP]
    kept = {app: e for app, e in per_app.items() if e["reports"]}
    header = {
        "schema": SCHEMA,
        "dump": name,
        "source": "https://github.com/bdefore/protondb-data",
        "licence": "ODbL 1.0 (database), DbCL 1.0 (contents). Derived from ProtonDB data.",
        "attribution": ATTRIBUTION,
        "builder": "https://github.com/breakmylegs/keepsake/blob/main/scripts/protondb_index.py",
        "records_read": total,
        "apps": len(kept),
    }
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, INDEX_NAME)
    with gzip.open(target, "wt", encoding="utf-8", compresslevel=9, newline="\n") as handle:
        handle.write(json.dumps(header, separators=(",", ":")) + "\n")
        for app in sorted(kept):
            handle.write(f"{app}\t{json.dumps(kept[app], separators=(',', ':'), ensure_ascii=False)}\n")
    size = os.path.getsize(target)
    if size > MAX_INDEX_BYTES:
        raise SystemExit(f"{target} is {size} bytes, over Advisor's {MAX_INDEX_BYTES} byte limit")
    print(
        f"{target}: dump {name}, {total} records, {len(per_app)} apps, {len(kept)} with handheld reports, "
        f"{size // 1024} KB"
    )
    return target


def publish(target: str) -> None:
    """Upload to the one rolling release, so Advisor's address never changes. Never marked latest."""
    if os.path.basename(target) != INDEX_NAME:
        raise SystemExit(f"Pass the {INDEX_NAME} made by the build step")
    with gzip.open(target, "rt", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
    notes = (
        f"ProtonDB index for Keepsake's Advisor, built locally from {header['source']} "
        f"reports_{header['dump']}.tar.gz by scripts/protondb_index.py. "
        f"{header['apps']} apps with handheld reports.\n\n"
        "Contains information from ProtonDB, made available under the Open Database License (ODbL) 1.0. "
        "Contents under the Database Contents License (DbCL) 1.0. This derived index is shared under the ODbL.\n\n"
        "This is a data release, not a Keepsake version: install Keepsake from the latest release."
    )
    title = f"ProtonDB index ({header['dump']})"
    exists = subprocess.run(
        ["gh", "release", "view", RELEASE_TAG], cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL
    )
    if exists.returncode == 0:
        subprocess.run(
            ["gh", "release", "upload", RELEASE_TAG, target, "--clobber"],
            cwd=ROOT,
            check=True,
            stdin=subprocess.DEVNULL,
        )
        subprocess.run(
            ["gh", "release", "edit", RELEASE_TAG, "--title", title, "--notes", notes, "--latest=false"],
            cwd=ROOT,
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
        )
    else:
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                RELEASE_TAG,
                target,
                "--title",
                title,
                "--notes",
                notes,
                "--latest=false",
                "--target",
                "main",
            ],
            cwd=ROOT,
            check=True,
            stdin=subprocess.DEVNULL,
        )
    print(f"published {RELEASE_TAG} with dump {header['dump']}")


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in ("survey", "build", "publish"):
        print(__doc__, file=sys.stderr)
        return 2
    if sys.argv[1] == "survey":
        survey(sys.argv[2])
    elif sys.argv[1] == "build":
        out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ROOT, "out")
        build(sys.argv[2], out)
    else:
        publish(sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
