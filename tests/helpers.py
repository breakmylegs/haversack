"""Synthetic fixture builders. No real save files or personal data here."""

from __future__ import annotations

import os
import struct
from typing import Any


def dumps_binary_vdf(value: dict[str, Any]) -> bytes:
    """Encode a dict as binary VDF, the way Steam writes ``shortcuts.vdf``.

    Test-only: Keepsake itself never writes VDF.
    """

    def encode(mapping: dict[str, Any]) -> bytes:
        out = bytearray()
        for key, item in mapping.items():
            name = key.encode("utf-8") + b"\x00"
            if isinstance(item, dict):
                out += b"\x00" + name + encode(item)
            elif isinstance(item, str):
                out += b"\x01" + name + item.encode("utf-8") + b"\x00"
            elif isinstance(item, int):
                out += b"\x02" + name + struct.pack("<i", item if item < 2**31 else item - 2**32)
            else:
                raise TypeError(type(item))
        out += b"\x08"
        return bytes(out)

    return encode(value) + b"\x08"


def shortcut_entry(appid_signed: int, name: str, exe: str, start_dir: str = "", last_play: int = 0) -> dict[str, Any]:
    return {
        "appid": appid_signed,
        "AppName": name,
        "Exe": f'"{exe}"',
        "StartDir": f'"{start_dir}"',
        "LaunchOptions": "",
        "LastPlayTime": last_play,
        "tags": {},
    }


def write_fake_proc(
    root: str,
    pid: int,
    ppid: int,
    comm: str,
    uid: int = 1000,
    starttime: int = 1000,
    env: dict[str, str] | None = None,
    cmdline: str = "",
) -> None:
    """Create a minimal ``/proc/<pid>`` entry under ``root``."""
    base = os.path.join(root, str(pid))
    os.makedirs(base, exist_ok=True)
    # Fields after "(comm)": state ppid pgrp session tty tpgid flags minflt cminflt majflt cmajflt
    # utime stime cutime cstime priority nice threads itrealvalue starttime
    fields = ["S", str(ppid)] + ["0"] * 17 + [str(starttime)] + ["0"] * 10
    with open(os.path.join(base, "stat"), "w", encoding="utf-8") as handle:
        handle.write(f"{pid} ({comm}) " + " ".join(fields) + "\n")
    with open(os.path.join(base, "status"), "w", encoding="utf-8") as handle:
        handle.write(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    with open(os.path.join(base, "cmdline"), "wb") as handle:
        handle.write(cmdline.replace(" ", "\x00").encode("utf-8"))
    with open(os.path.join(base, "environ"), "wb") as handle:
        handle.write(b"\x00".join(f"{k}={v}".encode() for k, v in (env or {}).items()))
