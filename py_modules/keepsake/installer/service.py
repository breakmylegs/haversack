"""Installer jobs (v2 spec 8.3, slice 21, ADR-0026).

The established community method, automated: a temporary shortcut ``Install:
<Title>`` runs the installer in its own prefix with the chosen compatibility
tool (and ``STEAM_COMPAT_MOUNTS`` for a mounted ISO); the user installs to the
suggested folder and quits; Keepsake lists the new executables, the user picks
the game's, and the same shortcut is retargeted to it, so the prefix is kept.

States: ``choose-installer``, ``creating-shortcut``, ``run-installer``,
``choose-game``, ``retargeting``, then ``done``, ``failed`` or ``cancelled``.
Every Steam change is a Steam Operations Executor operation created from a user
action (P15). The Installer writes no files itself: the installer program does,
inside the prefix and the chosen library folder. Jobs live in the
``installer_jobs`` table.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import time
from collections.abc import Callable
from typing import Any

from ..statedb import StateDB
from ..steamops import SteamOps
from . import files, udisks

MIGRATIONS = [
    """
    CREATE TABLE installer_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        state TEXT NOT NULL,
        data TEXT NOT NULL,
        created REAL NOT NULL,
        updated REAL NOT NULL
    )
    """,
]
ACTIVE = ("choose-installer", "creating-shortcut", "run-installer", "choose-game", "retargeting")
_TITLE = re.compile(r'^[^/\\:*?"<>|\x00-\x1f]{1,80}$')
# Wine's own files, not the game's: never offered as the game's executable.
PREFIX_SKIP = ("windows/", "users/", "programdata/", "program files/common files/", "program files (x86)/common files/")


class InstallerError(ValueError):
    pass


def windows_path(linux_path: str) -> str:
    """How the installer sees a Linux folder: drive Z: is the root (for example Z:\\home\\deck\\Games\\Title)."""
    return "Z:" + linux_path.replace("/", "\\")


class Installer:
    def __init__(
        self,
        db: StateDB,
        ops: SteamOps,
        library_root: Callable[[], str],
        prefix_for: Callable[[int], str | None],
        runner: udisks.Runner = udisks.run,
        has_udisks: Callable[[], bool] = udisks.available,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.ops = ops
        self.library_root = library_root
        self.prefix_for = prefix_for
        self.runner = runner
        self.has_udisks = has_udisks
        self.clock = clock
        db.migrate("installer", MIGRATIONS)

    # Storage

    def _save(self, job_id: int, state: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE installer_jobs SET state = ?, data = ?, updated = ? WHERE id = ?",
            (state, json.dumps(data, sort_keys=True), self.clock(), job_id),
        )

    def get(self, job_id: int) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT id, title, state, data, created, updated FROM installer_jobs WHERE id = ?", (int(job_id),)
        )
        if not rows:
            raise InstallerError("no such install")
        r = rows[0]
        return {"id": r[0], "title": r[1], "state": r[2], **json.loads(r[3]), "created": r[4], "updated": r[5]}

    def jobs(self) -> list[dict[str, Any]]:
        ids = [r[0] for r in self.db.execute("SELECT id FROM installer_jobs ORDER BY id DESC LIMIT 20")]
        return [self.get(i) for i in ids]

    # Steps

    def start(self, source: str, title: str) -> dict[str, Any]:
        """Prepare an install from an ISO or a folder; mounts an ISO read-only."""
        title = " ".join(str(title).split())
        if not _TITLE.match(title):
            raise InstallerError('the title is 1 to 80 characters without / \\ : * ? " < > |')
        source = os.path.realpath(str(source))
        data: dict[str, Any] = {"source": source, "ops": {}}
        if os.path.isfile(source) and source.lower().endswith(".iso"):
            if not self.has_udisks():
                raise InstallerError(
                    "udisksctl is not available on this system, so ISO files cannot be opened; use a folder"
                )
            device, mount = udisks.mount_iso(source, self.runner)
            data.update(kind="iso", device=device, mount=mount, contents=mount)
        elif os.path.isdir(source):
            data.update(kind="folder", contents=source)
        else:
            raise InstallerError("choose an .iso file or a folder")
        target = posixpath.join(self.library_root(), title)
        data.update(
            target=target,
            windowsTarget=windows_path(target),
            installers=files.find_installers(data["contents"])[:20],
            before=files.file_list(target),
        )
        now = self.clock()
        self.db.execute(
            "INSERT INTO installer_jobs (title, state, data, created, updated) VALUES (?, 'choose-installer', ?, ?, ?)",
            (title, json.dumps(data, sort_keys=True), now, now),
        )
        return self.get(int(self.db.execute("SELECT max(id) FROM installer_jobs")[0][0]))

    def create_shortcut(self, job_id: int, installer_rel: str) -> dict[str, Any]:
        """User action: queue the temporary installer shortcut."""
        job = self.get(job_id)
        if job["state"] != "choose-installer" or installer_rel not in job["installers"]:
            raise InstallerError("choose one of the installers found")
        exe = posixpath.join(job["contents"], installer_rel)
        options = f'STEAM_COMPAT_MOUNTS="{job["mount"]}" %command%' if job["kind"] == "iso" else ""
        op_id = self.ops.enqueue(
            "installer",
            "add-shortcut",
            {
                "name": f"Install: {job['title']}",
                "exe": exe,
                "startDir": posixpath.dirname(exe),
                "launchOptions": options,
            },
        )
        data = {k: v for k, v in job.items() if k not in ("id", "title", "state", "created", "updated")}
        data["ops"][str(op_id)] = "add"
        data["installerExe"] = exe
        self._save(job_id, "creating-shortcut", data)
        return self.get(job_id)

    def op_finished(self, op_id: int, ok: bool, result: dict[str, Any]) -> None:
        for job in self.jobs():
            role = job["ops"].get(str(op_id))
            if role is None:
                continue
            data = {k: v for k, v in job.items() if k not in ("id", "title", "state", "created", "updated")}
            if role == "add":
                if ok and isinstance(result.get("appid"), int):
                    data["appid"] = result["appid"]
                    self._save(job["id"], "run-installer", data)
                else:
                    data["error"] = str(result.get("error") or "the shortcut could not be created")
                    self._finish(job["id"], data, "failed")
            elif role == "retarget":
                data.setdefault("retargetResults", {})[str(op_id)] = {"ok": ok, **result}
                pending = [o for o, r in data["ops"].items() if r == "retarget" and o not in data["retargetResults"]]
                if not ok:
                    data["error"] = "Steam did not accept a change to the shortcut; check it in the game's properties"
                    self._finish(job["id"], data, "failed")
                elif not pending:
                    self._finish(job["id"], data, "done")
                else:
                    self._save(job["id"], "retargeting", data)
            return

    def installer_exited(self, appid: int) -> dict[str, Any] | None:
        """The installer shortcut was closed: list the executables the install created."""
        job = next((j for j in self.jobs() if j["state"] == "run-installer" and j.get("appid") == int(appid)), None)
        if job is None:
            return None
        candidates: list[tuple[str, int]] = []
        after = files.file_list(job["target"])
        for rel in files.new_files(job["before"], after):
            candidates.append((posixpath.join(job["target"], rel), after[rel][0]))
        prefix = self.prefix_for(int(appid))
        if prefix:
            drive_c = os.path.join(prefix, "pfx", "drive_c")
            listing = files.file_list(drive_c)
            for rel, (size, _mtime) in listing.items():
                if not rel.lower().startswith(PREFIX_SKIP):
                    candidates.append((posixpath.join(drive_c.replace(os.sep, "/"), rel), size))
        data = {k: v for k, v in job.items() if k not in ("id", "title", "state", "created", "updated")}
        data["candidates"] = files.rank_game_exes(candidates, job["title"])[:15]
        self._save(job["id"], "choose-game", data)
        return self.get(job["id"])

    def retarget(self, job_id: int, exe: str) -> dict[str, Any]:
        """User action: point the same shortcut at the game, keeping its prefix."""
        job = self.get(job_id)
        if job["state"] != "choose-game" or exe not in [c["path"] for c in job.get("candidates", [])]:
            raise InstallerError("choose one of the programs found")
        appid = int(job["appid"])
        data = {k: v for k, v in job.items() if k not in ("id", "title", "state", "created", "updated")}
        for kind, value in (
            ("set-shortcut-name", job["title"]),
            ("set-shortcut-exe", exe),  # never pre-quoted (research 2.1)
            ("set-shortcut-start-dir", posixpath.dirname(exe)),
            ("set-launch-options", ""),  # the installer-only STEAM_COMPAT_MOUNTS goes
        ):
            data["ops"][str(self.ops.enqueue("installer", kind, {"appid": appid, "value": value}))] = "retarget"
        data["gameExe"] = exe
        self._save(job_id, "retargeting", data)
        return self.get(job_id)

    def cancel(self, job_id: int) -> dict[str, Any]:
        job = self.get(job_id)
        if job["state"] not in ACTIVE:
            raise InstallerError("that install has already finished")
        data = {k: v for k, v in job.items() if k not in ("id", "title", "state", "created", "updated")}
        self._finish(job_id, data, "cancelled")
        return self.get(job_id)

    def _finish(self, job_id: int, data: dict[str, Any], state: str) -> None:
        if data.get("device"):
            udisks.detach(data["device"], self.runner)
            data["unmounted"] = True
        self._save(job_id, state, data)
