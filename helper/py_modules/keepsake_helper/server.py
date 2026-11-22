"""Keepsake Helper's interface: one Unix socket, a short list of jobs, nothing else (ADR-0083).

- **The socket** is ``/run/keepsake-helper/helper.sock``, owned by the Decky user, mode 0600, in a
  root-owned folder.
- **A caller must pass three checks:**
  - its user ID (``SO_PEERCRED``) is the Decky user;
  - its executable is the same as the helper's own, Decky's plugin loader;
  - it sends the per-boot token, which only that user can read.
- **Version lock.** Every request carries Keepsake's version, and the helper refuses any other
  version than its own: they ship together.
- **Framing.** One request per connection: a 4-byte length, then JSON. Requests are at most 64 KB.
- **The SSP lease.** Turning SSP off needs a lease of at most 5 minutes, which Keepsake renews.
  When the lease runs out (Keepsake stopped, crashed or was removed), and when the helper
  unloads, SSP goes back on.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import socket
import struct
import threading
import time
from collections.abc import Callable
from typing import Any

from . import bluetooth, hid, mgmt, power

RUN_DIR = "/run/keepsake-helper"
MAX_REQUEST = 64 * 1024
MAX_LEASE = 300.0
JOBS = (
    "ping",
    "hid.get",
    "hid.set",
    "bt.state",
    "bt.install",
    "bt.restore",
    "ssp.set",
    "ssp.renew",
    "ssp.release",
    "hci.capture",
    "power.read",
    "power.set",
)
log = logging.getLogger("keepsake-helper")


class Refused(Exception):
    pass


def _hex(value: Any, length: int) -> bytes:
    try:
        raw = bytes.fromhex(str(value))
    except ValueError as exc:
        raise Refused("bad bytes") from exc
    if len(raw) != length:
        raise Refused("bad length")
    return raw


def _index(value: Any) -> int:
    if not isinstance(value, int) or not 0 <= value < 16:
        raise Refused("bad adapter index")
    return value


class Helper:
    def __init__(
        self,
        version: str,
        uid: int,
        state_path: str,
        systemd: Any,
        opener: mgmt.Opener = mgmt.open_channel,
        bt_root: str = bluetooth.ROOT,
        sys_root: str = "/sys",
        ioctl: hid.Ioctl | None = None,
        clock: Callable[[], float] = time.monotonic,
        power_root: str = power.ROOT,
        profile_glob: str = power.PROFILE_GLOB,
    ) -> None:
        self.power_root = power_root
        self.profile_glob = profile_glob
        self.version = version
        self.uid = uid
        self.token = secrets.token_hex(32)
        self.state_path = state_path
        self.systemd = systemd
        self.opener = opener
        self.bt_root = bt_root
        self.sys_root = sys_root
        self.ioctl = ioctl
        self.clock = clock
        self.lease_until = 0.0
        self.lock = threading.Lock()

    # The SSP gate's state survives a helper restart, so SSP is never left off by accident.

    def _off(self) -> list[int]:
        try:
            with open(self.state_path, encoding="utf-8") as handle:
                return [int(i) for i in json.load(handle).get("sspOff", [])]
        except (OSError, ValueError):
            return []

    def _save_off(self, indexes: list[int]) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        temp = f"{self.state_path}.tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump({"sspOff": sorted(set(indexes))}, handle)
        os.replace(temp, self.state_path)

    def restore_ssp(self, reason: str) -> None:
        """SSP back on for every adapter the helper turned it off on."""
        with self.lock:
            off = self._off()
            left = []
            for index in off:
                try:
                    mgmt.set_ssp(index, True, self.opener)
                except (OSError, mgmt.MgmtError) as exc:
                    log.warning("SSP could not be restored on hci%d (%s)", index, exc)
                    left.append(index)
            self._save_off(left)
            self.lease_until = 0.0
        if off:
            log.info("SSP restored (%s)", reason)

    def tick(self) -> None:
        """Called every few seconds: an expired lease puts SSP back on."""
        if self._off() and self.clock() > self.lease_until:
            self.restore_ssp("lease expired")

    # Requests

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict) or not secrets.compare_digest(str(request.get("token", "")), self.token):
            raise Refused("not authorised")
        if request.get("version") != self.version:
            return {"ok": False, "error": "version", "helper": self.version}
        job, args = request.get("job"), request.get("args") or {}
        if job not in JOBS or not isinstance(args, dict):
            raise Refused("unknown job")
        try:
            return {"ok": True, **self._run(str(job), args)}
        except (
            bluetooth.BluetoothError,
            hid.HidError,
            mgmt.MgmtError,
            power.PowerError,
            Refused,
            ValueError,
            OSError,
        ) as exc:
            return {"ok": False, "error": str(exc)[:200]}

    def _run(self, job: str, args: dict[str, Any]) -> dict[str, Any]:
        extra: dict[str, Any] = {} if self.ioctl is None else {"ioctl": self.ioctl}
        if job == "ping":
            return {"version": self.version, "sspOff": self._off()}
        if job == "hid.get":
            data = hid.get_feature(args.get("node"), args.get("report"), self.sys_root, **extra)
            return {"data": data.hex()}
        if job == "hid.set":
            raw = bytes.fromhex(str(args.get("data", "")))
            hid.set_feature(args.get("node"), raw, self.sys_root, **extra)
            return {}
        if job == "bt.state":
            return bluetooth.state(args.get("adapter"), args.get("device"), self.bt_root)  # type: ignore[arg-type]
        if job == "bt.install":
            key = _hex(args.get("key"), 16)
            key_type = args.get("type")
            if not isinstance(key_type, int):
                raise Refused("bad key type")
            return bluetooth.install(args.get("adapter"), args.get("device"), key, key_type, self.systemd, self.bt_root)  # type: ignore[arg-type]
        if job == "bt.restore":
            return bluetooth.restore(args.get("adapter"), args.get("device"), self.systemd, self.bt_root)  # type: ignore[arg-type]
        if job == "ssp.set":
            index, on = _index(args.get("index")), bool(args.get("on"))
            if not on:
                lease = float(args.get("lease") or 0)
                if not 0 < lease <= MAX_LEASE:
                    raise Refused("turning SSP off needs a lease of up to 5 minutes")
            with self.lock:
                result = mgmt.set_ssp(index, on, self.opener, power_cycle=bool(args.get("powerCycle")))
                off = set(self._off())
                if result.get("ok") and not on:
                    off.add(index)
                    self.lease_until = self.clock() + float(args["lease"])
                elif result.get("ok"):
                    off.discard(index)
                self._save_off(sorted(off))
            return result
        if job == "ssp.renew":
            lease = float(args.get("lease") or 0)
            if not 0 < lease <= MAX_LEASE:
                raise Refused("a lease is up to 5 minutes")
            self.lease_until = self.clock() + lease
            return {"sspOff": self._off()}
        if job == "ssp.release":
            self.restore_ssp("released by Keepsake")
            return {}
        if job == "power.read":
            return {"limits": power.read(self.power_root), "profile": power.profile(self.profile_glob)}
        if job == "power.set":
            return {"limits": power.apply(args.get("values"), self.power_root, self.profile_glob)}
        if job == "hci.capture":
            data = mgmt.capture(float(args.get("seconds") or 40), self.opener)
            return {"btsnoop": base64.b64encode(data).decode("ascii")}
        raise Refused("unknown job")


# The socket


def peer_allowed(sock: Any, uid: int, proc_root: str = "/proc") -> bool:
    """SO_PEERCRED: the Decky user, running the same executable as the helper (the plugin loader)."""
    creds = sock.getsockopt(socket.SOL_SOCKET, getattr(socket, "SO_PEERCRED", 17), struct.calcsize("3i"))
    pid, peer_uid, _gid = struct.unpack("3i", creds)
    if peer_uid != uid:
        return False
    try:
        return os.path.realpath(f"{proc_root}/{pid}/exe") == os.path.realpath(f"{proc_root}/self/exe")
    except OSError:
        return False


def _read(conn: Any) -> bytes:
    head = b""
    while len(head) < 4:
        chunk = conn.recv(4 - len(head))
        if not chunk:
            raise Refused("short request")
        head += chunk
    (length,) = struct.unpack(">I", head)
    if length > MAX_REQUEST:
        raise Refused("request too large")
    body = b""
    while len(body) < length:
        chunk = conn.recv(min(65536, length - len(body)))
        if not chunk:
            raise Refused("short request")
        body += chunk
    return body


def _reply(conn: Any, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    conn.sendall(struct.pack(">I", len(data)) + data)


def serve_one(helper: Helper, conn: Any, check_peer: Callable[[Any], bool]) -> None:
    try:
        conn.settimeout(90.0)
        if not check_peer(conn):
            _reply(conn, {"ok": False, "error": "not authorised"})
            return
        request = json.loads(_read(conn).decode("utf-8"))
        _reply(conn, helper.handle(request))
    except (Refused, ValueError) as exc:
        try:
            _reply(conn, {"ok": False, "error": str(exc)[:120]})
        except OSError:
            pass
    except OSError:
        pass
    finally:
        conn.close()


def publish(helper: Helper, run_dir: str = RUN_DIR) -> Any:
    """Create the folder, the token file and the listening socket, with their owners and modes."""
    os.makedirs(run_dir, mode=0o755, exist_ok=True)
    os.chmod(run_dir, 0o755)  # noqa: S103 - root-owned; the user must reach the 0600 socket inside
    token_path = os.path.join(run_dir, "token")
    fd = os.open(token_path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, helper.token.encode("ascii"))
        os.fchown(fd, helper.uid, -1)  # type: ignore[attr-defined, unused-ignore]
    finally:
        os.close(fd)
    os.replace(token_path + ".tmp", token_path)
    path = os.path.join(run_dir, "helper.sock")
    if os.path.exists(path):
        os.remove(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
    server.bind(path)
    os.chown(path, helper.uid, -1)  # type: ignore[attr-defined, unused-ignore]
    os.chmod(path, 0o600)
    server.listen(4)
    return server
