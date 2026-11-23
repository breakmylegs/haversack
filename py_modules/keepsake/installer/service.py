"""Installer jobs (v2 spec 8.3, slices 21 and 22, ADR-0026 and ADR-0027).

The established community method, automated: a temporary shortcut ``Install:
<Title>`` runs the installer in its own prefix with the chosen compatibility
tool (and ``STEAM_COMPAT_MOUNTS`` for a mounted ISO or a source outside the home
folder); the user installs to the suggested folder and quits; Keepsake lists the
new executables, the user picks the game's, and the same shortcut is retargeted
to it, so the prefix is kept.

States: ``choose-installer``, ``creating-shortcut``, ``run-installer``,
``choose-game``, ``retargeting``, then ``done``, ``failed`` or ``cancelled``.
Every Steam change is a Steam Operations Executor operation created from a user
action (P15). The Installer writes only the CD drive links and drive type in
the new shortcut's own prefix (slice 22) and staged artwork; the installer
program writes the game, inside the prefix and the chosen library folder. Jobs
live in the ``installer_jobs`` table.
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
from . import cdrom, files, inplace, udisks
from .artwork import ArtworkError, SteamGridDB

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
FINAL = ("done", "failed", "cancelled")
_TITLE = re.compile(r'^[^/\\:*?"<>|\x00-\x1f]{1,80}$')
# Wine's own files, not the game's: never offered as the game's executable.
PREFIX_SKIP = ("windows/", "users/", "programdata/", "program files/common files/", "program files (x86)/common files/")
_ROW = ("id", "title", "state", "created", "updated")


class InstallerError(ValueError):
    pass


class InPlaceFailed(InstallerError):
    """An ISO on a network share could not be opened where it is: copy it to staging first (ADR-0067)."""

    def __init__(self, source: str, fstype: str, reason: str) -> None:
        super().__init__(f"the ISO could not be opened on the share ({fstype}): {reason}")
        self.source, self.fstype = source, fstype


def windows_path(linux_path: str) -> str:
    """How the installer sees a Linux folder: drive Z: is the root (for example Z:\\home\\deck\\Games\\Title)."""
    return "Z:" + linux_path.replace("/", "\\")


STALE_DISC_SECONDS = 12 * 3600
STALE_OP_SECONDS = 15 * 60


def health_checks(jobs: list[dict[str, Any]], ops: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Discs left attached, installer shortcuts left behind and Steam changes still waiting (v2 module doc)."""
    discs = [
        j["title"]
        for j in jobs
        if j.get("device")
        and not j.get("unmounted")
        and (j["state"] in FINAL or now - float(j["updated"]) > STALE_DISC_SECONDS)
    ]
    leftovers = [
        j["title"]
        for j in jobs
        if j["state"] in ("failed", "cancelled")
        and j.get("appid")
        and not j.get("gameExe")
        and not j.get("shortcutRemoved")
    ]
    waiting = [
        o["kind"]
        for o in ops
        if o["module"] == "installer" and o["state"] in ("pending", "claimed") and now - o["created"] > STALE_OP_SECONDS
    ]

    def check(check_id: str, label: str, items: list[str], ok: str, warn: str) -> dict[str, Any]:
        return {
            "id": check_id,
            "label": label,
            "status": "warn" if items else "ok",
            "detail": warn if items else ok,
            "items": items,
        }

    return [
        check(
            "installer-discs",
            "Discs",
            discs,
            "No disc left mounted.",
            "A disc is still mounted from an earlier install. Cancel that install to release it.",
        ),
        check(
            "installer-shortcuts",
            "Installer shortcuts",
            leftovers,
            "No installer shortcut left behind.",
            "An install stopped and left its Install: shortcut in Steam. Remove it from the Install page.",
        ),
        check(
            "installer-steam-ops",
            "Steam changes",
            waiting,
            "No Steam change waiting.",
            "Steam changes are waiting. They are applied when Gaming Mode is open.",
        ),
    ]


def _data(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k not in _ROW}


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
        *,
        home: Callable[[], str] = lambda: os.path.expanduser("~"),
        running: Callable[[int, str | None], bool] = lambda appid, prefix: True,  # unknown means running
        work_dir: str = "",
        art: SteamGridDB | None = None,
        symlink: Callable[[str, str], None] = os.symlink,
    ) -> None:
        self.db = db
        self.ops = ops
        self.library_root = library_root
        self.prefix_for = prefix_for
        self.runner = runner
        self.has_udisks = has_udisks
        self.clock = clock
        self.home = home
        self.running = running
        self.work_dir = work_dir
        self.art = art
        self.symlink = symlink
        self.mounts_file = "/proc/self/mounts"
        # Called with a job's data when its disc is released: the app closes a network ISO's mount (ADR-0067).
        self.on_released: Callable[[dict[str, Any]], None] = lambda data: None
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

    def _staging(self) -> str:
        if not self.work_dir:
            raise InstallerError("the Installer has no working folder")
        folder = os.path.join(self.work_dir, "staging")
        os.makedirs(folder, exist_ok=True)
        return folder

    def staged_file(self, op: dict[str, Any]) -> str:
        """The staged image for a claimed ``set-artwork`` operation this module queued."""
        if op.get("module") != "installer" or op.get("kind") != "set-artwork" or op.get("state") != "claimed":
            raise InstallerError("that operation has no staged file")
        path = os.path.join(self._staging(), str(op["payload"]["file"]))
        if os.path.dirname(os.path.realpath(path)) != os.path.realpath(self._staging()):
            raise InstallerError("that operation has no staged file")
        return path

    # Steps

    def downloads_dir(self) -> str:
        """Where network downloads are staged (ADR-0033); everything in it belongs to Keepsake."""
        folder = os.path.join(self._staging(), "net")
        os.makedirs(folder, exist_ok=True)
        return folder

    def clean_downloads(self) -> list[str]:
        """Delete staged downloads no active install uses, and any partial file. Returns the names removed."""
        folder = self.downloads_dir()
        in_use = {os.path.realpath(j["staged"]) for j in self.jobs() if j["state"] in ACTIVE and j.get("staged")}
        removed = []
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and not os.path.islink(path) and os.path.realpath(path) not in in_use:
                os.unlink(path)
                removed.append(name)
        return removed

    def _drop_staged(self, data: dict[str, Any]) -> None:
        staged = data.get("staged")
        if staged and os.path.dirname(os.path.realpath(staged)) == os.path.realpath(self.downloads_dir()):
            try:
                os.unlink(staged)
            except FileNotFoundError:
                pass
            data["stagedRemoved"] = True

    def start(
        self, source: str, title: str, staged: bool = False, queue: bool = False, net_mount: str | None = None
    ) -> dict[str, Any]:
        """Prepare an install from an ISO or a folder; mounts an ISO read-only.

        ``staged`` marks a downloaded ISO in :meth:`downloads_dir`, deleted when the install ends.
        ``queue`` (ADR-0053) adds it to the install queue instead: it starts by itself when no other
        install is active, and the queue survives a restart. ``net_mount`` names Keepsake's own mount of
        a network ISO (ADR-0067), released with the disc.
        """
        if queue:
            return self._enqueue(source, title, staged)
        try:
            return self._start(source, title, staged, net_mount=net_mount)
        except Exception:
            if staged:
                self._drop_staged({"staged": source})
            raise

    def _enqueue(self, source: str, title: str, staged: bool) -> dict[str, Any]:
        title = " ".join(str(title).split())
        if not _TITLE.match(title):
            raise InstallerError('the title is 1 to 80 characters without / \\ : * ? " < > |')
        source = os.path.realpath(str(source)).replace(os.sep, "/")
        if not (os.path.isdir(source) or (os.path.isfile(source) and source.lower().endswith(".iso"))):
            raise InstallerError("choose an .iso file or a folder")
        data = {"source": source, "ops": {}, "queuedStaged": bool(staged)}
        now = self.clock()
        self.db.execute(
            "INSERT INTO installer_jobs (title, state, data, created, updated) VALUES (?, 'queued', ?, ?, ?)",
            (title, json.dumps(data, sort_keys=True), now, now),
        )
        job_id = int(self.db.execute("SELECT max(id) FROM installer_jobs")[0][0])
        self.promote()
        return self.get(job_id)

    def promote(self) -> dict[str, Any] | None:
        """Start the oldest queued install when none is active. A queued install that cannot start fails, and
        the next one is tried."""
        while not any(j["state"] in ACTIVE for j in self.jobs()):
            rows = self.db.execute("SELECT id FROM installer_jobs WHERE state = 'queued' ORDER BY id LIMIT 1")
            if not rows:
                return None
            job = self.get(int(rows[0][0]))
            try:
                return self._start(job["source"], job["title"], bool(job.get("queuedStaged")), job_id=job["id"])
            except (InstallerError, udisks.UdisksError, OSError) as exc:
                data = _data(job)
                data["error"] = str(exc)
                self._save(job["id"], "failed", data)
        return None

    def _start(
        self, source: str, title: str, staged: bool, job_id: int | None = None, net_mount: str | None = None
    ) -> dict[str, Any]:
        title = " ".join(str(title).split())
        if not _TITLE.match(title):
            raise InstallerError('the title is 1 to 80 characters without / \\ : * ? " < > |')
        source = os.path.realpath(str(source)).replace(os.sep, "/")
        data: dict[str, Any] = {"source": source, "ops": {}}
        if staged:
            data["staged"] = source
        target = posixpath.join(self.library_root(), title)
        if os.path.isfile(source) and source.lower().endswith(".iso"):
            if not self.has_udisks():
                raise InstallerError(
                    "udisksctl is not available on this system, so ISO files cannot be opened; use a folder"
                )
            fstype = inplace.network_filesystem(source, self.mounts_file)
            try:
                device, mount = udisks.mount_iso(source, self.runner)
            except udisks.UdisksError as exc:
                if fstype and not net_mount:
                    raise InPlaceFailed(source, fstype, str(exc)) from exc  # option A: copy, then try again
                raise
            data.update(kind="iso", device=device, mount=mount, contents=mount)
            if fstype:
                data["inPlace"] = fstype  # opened on the share, not copied (ADR-0067)
            if net_mount:
                data["netMount"] = net_mount
            # A set of discs (ADR-0053): the other ISOs beside this one can be swapped in later.
            data["otherDiscs"] = [] if staged or net_mount else files.sibling_discs(source)
        elif os.path.isdir(source):
            data.update(kind="folder", contents=source)
        else:
            raise InstallerError("choose an .iso file or a folder")
        try:
            # The Steam runtime container only sees the home folder; anything else is passed in.
            # For a disc, the folder discs are mounted under, so a disc swapped in later is visible too (ADR-0053).
            visible = posixpath.dirname(data["mount"]) if data.get("kind") == "iso" else data["contents"]
            data["compatMounts"] = files.compat_mounts([visible, target], self.home().replace(os.sep, "/"))
        except ValueError as exc:
            if data.get("device"):
                udisks.detach(data["device"], self.runner)
                self.on_released(data)
            raise InstallerError(str(exc)) from exc
        data.update(
            target=target,
            windowsTarget=windows_path(target),
            installers=files.find_installers(data["contents"])[:20],
            before=files.file_list(target),
        )
        now = self.clock()
        if job_id is not None:  # a queued install starting
            self._save(job_id, "choose-installer", data)
            return self.get(job_id)
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
        mounts = job.get("compatMounts", "")
        options = f'STEAM_COMPAT_MOUNTS="{mounts}" %command%' if mounts else ""
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
        data = _data(job)
        data["ops"][str(op_id)] = "add"
        data["installerExe"] = exe
        self._save(job_id, "creating-shortcut", data)
        return self.get(job_id)

    def op_finished(self, op_id: int, ok: bool, result: dict[str, Any]) -> dict[str, Any] | None:
        """Record an executor result; returns the job it belonged to, as it is now."""
        for job in self.jobs():
            role = job["ops"].get(str(op_id))
            if role is None:
                continue
            data = _data(job)
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
            elif role == "remove":
                data["shortcutRemoved"] = bool(ok)
                self._save(job["id"], job["state"], data)
            elif role.startswith("artwork:"):
                staged = role.split(":", 1)[1]
                data.setdefault("artwork", {})[staged] = bool(ok)
                path = os.path.join(self._staging(), staged)
                if os.path.exists(path):
                    os.unlink(path)
                self._save(job["id"], job["state"], data)
            return self.get(job["id"])
        return None

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
        data = _data(job)
        data["candidates"] = files.rank_game_exes(candidates, job["title"])[:15]
        # Runtime installers shipped with the game or on the disc (ADR-0053): guidance only, nothing is run.
        data["runtimes"] = files.find_runtimes(after, files.file_list(job["contents"]) if job.get("contents") else {})
        self._save(job["id"], "choose-game", data)
        return self.get(job["id"])

    def retarget(self, job_id: int, exe: str) -> dict[str, Any]:
        """User action: point the same shortcut at the game, keeping its prefix."""
        job = self.get(job_id)
        if job["state"] != "choose-game" or exe not in [c["path"] for c in job.get("candidates", [])]:
            raise InstallerError("choose one of the programs found")
        appid = int(job["appid"])
        data = _data(job)
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
        if job["state"] == "queued":
            self._save(job_id, "cancelled", _data(job))  # nothing was mounted yet
            return self.get(job_id)
        if job["state"] not in ACTIVE:
            raise InstallerError("that install has already finished")
        self._finish(job_id, _data(job), "cancelled")
        return self.get(job_id)

    # Slice 22

    def add_cd_drive(self, job_id: int) -> dict[str, Any]:
        """User action: make the mounted disc a CD drive in the installer shortcut's prefix."""
        job = self.get(job_id)
        if job.get("kind") != "iso" or job["state"] != "run-installer":
            raise InstallerError("a disc drive can only be added while an ISO install is waiting for the installer")
        if job.get("cdDrive"):
            return job
        prefix = self.prefix_for(int(job["appid"]))
        if not prefix:
            raise InstallerError("start the installer shortcut once and quit it, so Proton creates its prefix first")
        if self.running(int(job["appid"]), prefix):
            raise InstallerError("quit the installer first; Haversack never changes a prefix while it runs")
        try:
            made = cdrom.add_drive(
                prefix, job["mount"], job["device"], os.path.join(self.work_dir, "registry-backups"), self.symlink
            )
        except cdrom.CdromError as exc:
            raise InstallerError(str(exc)) from exc
        data = _data(job)
        links = [str(link) for link in made["links"]]
        targets = {link: (job["device"] if link.endswith("::") else job["mount"]) for link in links}
        data["cdDrive"] = {"letter": made["letter"], "links": links, "targets": targets}
        self._save(job_id, job["state"], data)
        return self.get(job_id)

    def swap_disc(self, job_id: int, disc: str) -> dict[str, Any]:
        """User action, while the installer asks for the next disc: put another ISO of the set in the drive.

        The drive's links are repointed in one step each (a new link renamed over the old one), the way a
        real disc swap changes what is in the drive. This is the one change made to a prefix while its
        installer runs; nothing else in the prefix is touched (ADR-0053).
        """
        job = self.get(job_id)
        drive = job.get("cdDrive") or {}
        if job.get("kind") != "iso" or job["state"] != "run-installer" or not drive.get("links"):
            raise InstallerError("add the disc drive first; discs can be swapped while the installer runs")
        if disc not in job.get("otherDiscs", []):
            raise InstallerError("choose one of the other discs in the same folder")
        new_source = posixpath.join(posixpath.dirname(job["source"]), disc)
        device, mount = udisks.mount_iso(new_source, self.runner)
        targets = dict(drive.get("targets", {}))
        try:
            targets.update(
                cdrom.repoint(
                    list(drive["links"]),
                    targets,
                    lambda link: device if link.endswith("::") else mount,
                    self.symlink,
                )
            )
        except (cdrom.CdromError, OSError) as exc:
            udisks.detach(device, self.runner)
            raise InstallerError(str(exc)) from exc
        old_device = job.get("device")
        data = _data(job)
        data["otherDiscs"] = [d for d in job["otherDiscs"] if d != disc] + [posixpath.basename(job["source"])]
        data.setdefault("discs", []).append(posixpath.basename(job["source"]))
        data.update(source=new_source, device=device, mount=mount, contents=mount)
        data["cdDrive"] = {**drive, "targets": targets}
        self._save(job_id, job["state"], data)
        if old_device:
            udisks.detach(old_device, self.runner)  # the installer asked for the next disc, so the old one is done
        return self.get(job_id)

    def resume(self) -> list[dict[str, Any]]:
        """After a restart: mount the discs of active installs again, then start the next queued install.

        If a disc comes back at a different place after its installer shortcut was made, the shortcut
        would point at a folder that no longer exists, so that install fails with a plain reason.
        """
        resumed = []
        for job in self.jobs():
            if job["state"] not in ACTIVE or job.get("kind") != "iso" or os.path.isdir(job.get("mount") or ""):
                continue
            data = _data(job)
            try:
                device, mount = udisks.mount_iso(job["source"], self.runner)
            except (udisks.UdisksError, OSError) as exc:
                data["error"] = f"the disc could not be opened again after a restart: {exc}"
                self._finish(job["id"], data, "failed")
                continue
            if mount != job["mount"] and job["state"] != "choose-installer":
                data["error"] = "the disc came back at a different place after a restart; start this install again"
                data["device"] = device
                self._finish(job["id"], data, "failed")
                continue
            data.update(device=device, mount=mount, contents=mount)
            self._save(job["id"], job["state"], data)
            resumed.append(self.get(job["id"]))
        self.promote()
        return resumed

    def forget_appid(self, appid: int) -> int:
        """Forget finished installs of a game that was uninstalled (ADR-0065). Active ones are kept."""
        forgotten = 0
        for job in self.jobs():
            if job.get("appid") == int(appid) and job["state"] in FINAL:
                self.db.execute("DELETE FROM installer_jobs WHERE id = ?", (int(job["id"]),))
                forgotten += 1
        return forgotten

    def remove_shortcut(self, job_id: int) -> dict[str, Any]:
        """User action: remove the ``Install:`` shortcut a failed or cancelled install left in Steam."""
        job = self.get(job_id)
        if job["state"] not in ("failed", "cancelled") or not job.get("appid") or job.get("shortcutRemoved"):
            raise InstallerError("there is no installer shortcut to remove for this install")
        if job.get("gameExe"):
            raise InstallerError("this shortcut was already pointed at the game; remove it in Steam if you mean to")
        data = _data(job)
        data["ops"][str(self.ops.enqueue("installer", "remove-shortcut", {"appid": int(job["appid"])}))] = "remove"
        self._save(job_id, job["state"], data)
        return self.get(job_id)

    def search_artwork(self, job_id: int) -> list[dict[str, Any]]:
        job = self.get(job_id)
        if self.art is None:
            raise InstallerError("SteamGridDB artwork is not available")
        try:
            return self.art.search(job["title"])
        except ArtworkError as exc:
            raise InstallerError(str(exc)) from exc

    def queue_artwork(self, job_id: int, game_id: int) -> dict[str, Any]:
        """User action: stage SteamGridDB's top images and queue them for the finished shortcut."""
        job = self.get(job_id)
        if job["state"] != "done" or not job.get("appid"):
            raise InstallerError("artwork is added once the shortcut starts the game")
        if self.art is None:
            raise InstallerError("SteamGridDB artwork is not available")
        data = _data(job)
        queued = 0
        try:
            for item in self.art.choose(int(game_id)):
                name = f"job{job_id}-{item['label']}"
                path = os.path.join(self._staging(), name)
                kind = self.art.download(item["url"], path)
                staged = f"{name}.{kind}"
                os.replace(path, os.path.join(self._staging(), staged))
                payload = {"appid": int(job["appid"]), "assetType": item["assetType"], "imageType": kind}
                op_id = self.ops.enqueue("installer", "set-artwork", {**payload, "file": staged})
                data["ops"][str(op_id)] = f"artwork:{staged}"
                queued += 1
        except ArtworkError as exc:
            self._save(job_id, job["state"], data)
            raise InstallerError(str(exc)) from exc
        if not queued:
            raise InstallerError("SteamGridDB has no artwork for that game")
        self._save(job_id, job["state"], data)
        return self.get(job_id)

    def queue_stream_art(self, appid: int, game_id: int) -> int:
        """User action (R18, ADR-0081): SteamGridDB's top images for a streaming tile, queued for Steam.

        Same route as an installed game's artwork: staged here, set by Steam's own artwork call
        (P15), only after the user chose the game on SteamGridDB. Returns how many were queued.
        """
        if self.art is None:
            raise InstallerError("SteamGridDB artwork is not available")
        if not 2**31 <= int(appid) < 2**32:
            raise InstallerError("only a non-Steam game's streaming tile needs artwork")
        queued = 0
        try:
            for item in self.art.choose(int(game_id)):
                name = f"stream{int(appid)}-{item['label']}"
                path = os.path.join(self._staging(), name)
                kind = self.art.download(item["url"], path)
                staged = f"{name}.{kind}"
                os.replace(path, os.path.join(self._staging(), staged))
                payload = {"appid": int(appid), "assetType": item["assetType"], "imageType": kind, "file": staged}
                self.ops.enqueue("installer", "set-artwork", payload)
                queued += 1
        except ArtworkError as exc:
            raise InstallerError(str(exc)) from exc
        if not queued:
            raise InstallerError("SteamGridDB has no artwork for that game")
        return queued

    def search_titles(self, title: str) -> list[dict[str, Any]]:
        if self.art is None:
            raise InstallerError("SteamGridDB artwork is not available")
        try:
            return self.art.search(title)
        except ArtworkError as exc:
            raise InstallerError(str(exc)) from exc

    def _finish(self, job_id: int, data: dict[str, Any], state: str) -> None:
        drive = data.get("cdDrive")
        if drive and drive.get("links"):
            cdrom.remove_links(drive["links"], drive.get("targets", {}))
            drive["links"] = []
        if data.get("device"):
            udisks.detach(data["device"], self.runner)
            data["unmounted"] = True
            self.on_released(data)
        self._drop_staged(data)
        self._save(job_id, state, data)
        self.promote()  # the next queued install, if any (ADR-0053)
