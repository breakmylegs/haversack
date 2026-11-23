"""Keepsake's side of the root helper (ADR-0075 tier 1, ADR-0083).

Keepsake never runs as root. The separate "Keepsake Helper" plugin does a short list of root jobs,
on request, over a Unix socket in ``/run/keepsake-helper``. This client reads the per-boot token,
sends one request per connection with Keepsake's version (the helper refuses any other), and
turns refusals into plain errors. Every call has a timeout and runs off the event loop.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
from collections.abc import Callable
from typing import Any

RUN_DIR = "/run/keepsake-helper"
MAX_REPLY = 16 * 1024 * 1024
TIMEOUT = 20.0
CAPTURE_TIMEOUT = 90.0


class HelperError(Exception):
    pass


class HelperMissing(HelperError):
    pass


class HelperVersion(HelperError):
    def __init__(self, helper: str) -> None:
        super().__init__(f"the helper is version {helper}; update it to match Haversack")
        self.helper = helper


def _unix_connect(path: str, timeout: float) -> Any:
    if not hasattr(socket, "AF_UNIX"):
        raise HelperMissing("this system has no Unix sockets")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
    sock.settimeout(timeout)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    return sock


class HelperClient:
    def __init__(
        self,
        version: str,
        run_dir: str = RUN_DIR,
        connect: Callable[[str, float], Any] = _unix_connect,
    ) -> None:
        self.version = version
        self.run_dir = run_dir
        self.connect = connect

    def installed(self) -> bool:
        return os.path.exists(os.path.join(self.run_dir, "helper.sock"))

    def _token(self) -> str:
        try:
            with open(os.path.join(self.run_dir, "token"), encoding="ascii") as handle:
                return handle.read(128).strip()
        except OSError as exc:
            raise HelperMissing("the Haversack Helper is not running") from exc

    def call(self, job: str, timeout: float = TIMEOUT, **args: Any) -> dict[str, Any]:
        request = json.dumps({"token": self._token(), "version": self.version, "job": job, "args": args}).encode()
        try:
            sock = self.connect(os.path.join(self.run_dir, "helper.sock"), timeout)
        except OSError as exc:
            raise HelperMissing("the Haversack Helper is not running") from exc
        try:
            sock.sendall(struct.pack(">I", len(request)) + request)
            head = self._exact(sock, 4)
            (length,) = struct.unpack(">I", head)
            if length > MAX_REPLY:
                raise HelperError("the helper's reply is too large")
            reply = json.loads(self._exact(sock, length).decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise HelperError(f"the helper did not answer ({type(exc).__name__})") from exc
        finally:
            sock.close()
        if not isinstance(reply, dict):
            raise HelperError("the helper's reply has the wrong shape")
        if reply.get("error") == "version":
            raise HelperVersion(str(reply.get("helper")))
        if not reply.get("ok"):
            raise HelperError(str(reply.get("error") or "the helper refused")[:200])
        return reply

    @staticmethod
    def _exact(sock: Any, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = sock.recv(min(65536, size - len(data)))
            if not chunk:
                raise HelperError("the helper closed the connection")
            data += chunk
        return data

    def status(self) -> dict[str, Any]:
        """For the screen: installed, reachable, version-matched, and the SSP gate's adapters."""
        if not self.installed():
            return {"installed": False, "ready": False, "problem": "not installed"}
        try:
            found = self.call("ping", timeout=3.0)
        except HelperVersion as exc:
            return {"installed": True, "ready": False, "problem": "version", "helper": exc.helper}
        except HelperError as exc:
            return {"installed": True, "ready": False, "problem": str(exc)}
        return {"installed": True, "ready": True, "version": found.get("version"), "sspOff": found.get("sspOff", [])}

    # The jobs, as Keepsake uses them

    def get_feature(self, node: str, report: int, length: int) -> bytes:
        data = bytes.fromhex(str(self.call("hid.get", node=node, report=report)["data"]))
        if len(data) != length:
            raise HelperError("the controller's report has the wrong length")
        return data

    def set_feature(self, node: str, data: bytes) -> None:
        self.call("hid.set", node=node, data=data.hex())

    def bt_state(self, adapter: str, device: str) -> dict[str, Any]:
        return self.call("bt.state", adapter=adapter, device=device)

    def bt_install(self, adapter: str, device: str, key: bytes, key_type: int) -> dict[str, Any]:
        return self.call("bt.install", timeout=60.0, adapter=adapter, device=device, key=key.hex(), type=key_type)

    def bt_restore(self, adapter: str, device: str) -> dict[str, Any]:
        return self.call("bt.restore", timeout=60.0, adapter=adapter, device=device)

    def ssp_set(self, index: int, on: bool, lease: float = 0.0, power_cycle: bool = False) -> dict[str, Any]:
        return self.call("ssp.set", index=index, on=on, lease=lease, powerCycle=power_cycle)

    def ssp_renew(self, lease: float) -> dict[str, Any]:
        return self.call("ssp.renew", lease=lease)

    def ssp_release(self) -> dict[str, Any]:
        return self.call("ssp.release")

    def power_set(self, values: dict[str, int]) -> dict[str, Any]:
        return self.call("power.set", values=values)

    def capture(self, seconds: float) -> bytes:
        found = self.call("hci.capture", timeout=CAPTURE_TIMEOUT, seconds=seconds)
        return base64.b64decode(str(found.get("btsnoop", "")))
