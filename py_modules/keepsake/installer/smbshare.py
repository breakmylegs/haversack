"""Install from a Windows share (SMB 2) that is not mounted (ADR-0033, ADR-0034).

Uses the vendored pure-Python pysmb (``keepsake/_vendor``), imported only when
a share is first used. Nothing is mounted: shares and folders are listed over
the protocol, and the chosen ISO is copied into staging like an HTTP download.

Rules, matching the HTTP terms in ADR-0033:
- Only to a local address (the HTTP list in ``remote.LOCAL_NETWORKS``). The name
  is resolved once and Keepsake connects to that checked address.
- SMB 2 only. A server that offers only SMB 1 is refused. Signing is used
  whenever the server supports it.
- The user name and password go only to that one server, inside NTLMv2.

Runs in worker threads.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from .remote import (
    MAX_FILE,
    MAX_RESUMES,
    SPACE_MARGIN,
    Cancelled,
    RemoteError,
    Resolver,
    _resolve,
    _space_message,
    check_sha256,
    host_is_private,
)

PORT = 445
TIMEOUT = 30
CHUNK = 4 * 1024 * 1024
LIST_MAX = 5000
URL_MAX = 2000
_NAME = re.compile(r'^[^/\\\x00-\x1f"<>|:*?]{1,255}$')
_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_vendor")


def pysmb() -> Any:
    """The vendored ``smb.SMBConnection`` class; a plain error if this Python cannot load it."""
    if _VENDOR not in sys.path:
        sys.path.insert(0, _VENDOR)
    try:
        from smb.SMBConnection import SMBConnection
    except ImportError as exc:  # a stdlib module missing from Decky's frozen Python (ADR-0030)
        raise RemoteError(
            f"Windows shares are not available on this system ({exc.name or 'a module'} is missing)"
        ) from exc
    return SMBConnection


@dataclass(frozen=True)
class Address:
    host: str
    port: int
    share: str  # "" lists the server's shares
    path: str  # inside the share, "/"-separated, no leading or trailing "/"

    def url(self, share: str | None = None, path: str | None = None, folder: bool = True) -> str:
        share = self.share if share is None else share
        path = self.path if path is None else path
        port = f":{self.port}" if self.port != PORT else ""
        parts = [quote(p) for p in [share, *path.split("/")] if p]
        tail = "/".join(parts)
        return f"smb://{self.host}{port}/{tail}{'/' if folder and tail else ''}"


def parse(url: str) -> Address:
    """``smb://server[:port]/share/folder/...`` with no credentials, query or fragment."""
    url = str(url).strip()
    if not url or len(url) > URL_MAX or any(ord(c) < 32 or c == "\x7f" for c in url):
        raise RemoteError("enter an address such as smb://nas.local/games/")
    try:
        parts = urlsplit(url)
        port = parts.port or PORT
    except ValueError as exc:
        raise RemoteError("that address is not valid") from exc
    if parts.scheme != "smb" or not parts.hostname:
        raise RemoteError("a Windows share address starts with smb:// and names a server")
    if parts.username or parts.password:
        raise RemoteError("enter the user name and password in their own fields, not in the address")
    if parts.query or parts.fragment:
        raise RemoteError("enter the address without ? or #")
    names = [unquote(p) for p in parts.path.split("/") if p]
    for name in names:
        if not _NAME.match(name) or name in (".", ".."):
            raise RemoteError(f"the folder name {name[:40]!r} is not valid")
    return Address(parts.hostname.lower(), port, names[0] if names else "", "/".join(names[1:]))


Connector = Callable[[str, int, str, str, str], Any]


def _connect(ip: str, port: int, host: str, username: str, password: str) -> Any:
    smb_connection = pysmb()
    remote_name = host.split(".")[0].upper()[:15] or "SERVER"
    conn = smb_connection(
        username,
        password,
        "KEEPSAKE",
        remote_name,
        domain="",
        use_ntlm_v2=True,
        sign_options=smb_connection.SIGN_WHEN_SUPPORTED,
        is_direct_tcp=True,
    )
    try:
        ok = conn.connect(ip, port, timeout=TIMEOUT)
    except Exception:
        conn.close()
        raise
    if not ok:
        conn.close()
        raise RemoteError("the share refused the user name or password (or needs one)")
    return conn


@dataclass
class Share:
    """One user action against one server: its checked address and credentials."""

    url: str
    username: str = ""
    password: str = ""
    connect: Connector = _connect
    resolve: Resolver = _resolve

    def __post_init__(self) -> None:
        self.address = parse(self.url)
        self.home = self.address.host
        self._ip = ""

    def _checked_ip(self) -> str:
        if not self._ip:
            host = self.home.strip("[]")
            try:
                addresses = [host] if _looks_like_ip(host) else list(self.resolve(host))
            except (OSError, UnicodeError) as exc:
                raise RemoteError(f"could not find {self.home}") from exc
            # Resolved once: the addresses checked are the ones connected to.
            if not addresses or not host_is_private(host, lambda _h: addresses):
                raise RemoteError(f"{self.home} is not on your local network; Keepsake only uses Windows shares there")
            self._ip = addresses[0]
        return self._ip

    def open(self) -> Any:
        ip = self._checked_ip()
        try:
            conn = self.connect(ip, self.address.port, self.home, self.username, self.password)
        except RemoteError:
            raise
        except Exception as exc:  # pysmb raises its own and socket errors
            raise RemoteError(f"could not open the share on {self.home}: {type(exc).__name__}") from exc
        if not conn.isUsingSMB2():
            conn.close()
            raise RemoteError(f"{self.home} only offers SMB 1, which is not safe; turn on SMB 2 or 3 on the server")
        return conn


def _looks_like_ip(host: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET6 if ":" in host else socket.AF_INET, host.split("%")[0])
    except (OSError, ValueError):
        return False
    return True


def _failure(exc: BaseException, what: str) -> RemoteError:
    if isinstance(exc, RemoteError):
        return exc
    name = type(exc).__name__
    if name == "OperationFailure":
        return RemoteError(f"the server could not {what} (it may not exist, or you may not have access)")
    return RemoteError(f"the server could not {what}: {name}")


def list_folder(share: Share, url: str) -> list[dict[str, Any]]:
    """Shares on the server, or folders and ISO files in a share folder."""
    address = parse(url)
    if address.host != share.home or address.port != share.address.port:
        raise RemoteError("browse within the location you chose")
    conn = share.open()
    try:
        if not address.share:
            devices = conn.listShares(timeout=TIMEOUT)
            entries = [
                {"name": d.name, "url": address.url(d.name, ""), "kind": "folder"}
                for d in devices
                if d.type == 0 and not d.isSpecial and _NAME.match(str(d.name)) and not str(d.name).endswith("$")
            ]
        else:
            files = conn.listPath(address.share, "/" + address.path, timeout=TIMEOUT)
            entries = []
            for f in files[: LIST_MAX + 2]:
                name = str(f.filename)
                if name in (".", "..") or not _NAME.match(name):
                    continue
                inner = f"{address.path}/{name}" if address.path else name
                if f.isDirectory:
                    entries.append({"name": name, "url": address.url(path=inner), "kind": "folder"})
                elif name.lower().endswith(".iso"):
                    url_ = address.url(path=inner, folder=False)
                    entries.append({"name": name, "url": url_, "kind": "iso", "size": int(f.file_size)})
    except Exception as exc:
        raise _failure(exc, "list that folder") from exc
    finally:
        conn.close()
    return sorted(entries[:LIST_MAX], key=lambda e: (e["kind"] != "folder", e["name"].casefold()))


class _Sink:
    """The file object pysmb writes into: counts, hashes, and stops on cancel."""

    def __init__(self, out: Any, cancelled: Callable[[], bool], max_file: int) -> None:
        self.out, self.cancelled, self.max_file = out, cancelled, max_file
        self.digest = hashlib.sha256()
        self.done = 0

    def write(self, data: bytes) -> int:
        if self.cancelled():
            raise Cancelled("the download was cancelled")
        self.done += len(data)
        if self.done > self.max_file:
            raise RemoteError("the server sent more than the file's size")
        self.out.write(data)
        self.digest.update(data)
        return len(data)


def download(
    share: Share,
    url: str,
    dest_dir: str,
    *,
    sha256: str | None = None,
    progress: Callable[[int, int | None], None] = lambda done, total: None,
    cancelled: Callable[[], bool] = lambda: False,
    free_space: Callable[[str], int] = lambda path: shutil.disk_usage(path).free,
    max_file: int = MAX_FILE,
) -> str:
    """Copy one ISO from the share into ``dest_dir``, reconnecting after a dropped connection."""
    address = parse(url)
    if address.host != share.home or address.port != share.address.port:
        raise RemoteError("download from the location you chose")
    name = address.path.rsplit("/", 1)[-1] if address.path else ""
    if not address.share or not name.lower().endswith(".iso") or name.startswith("."):
        raise RemoteError("choose an .iso file")
    expected = check_sha256(sha256)
    os.makedirs(dest_dir, exist_ok=True)
    final = os.path.join(dest_dir, name)
    part = final + ".part"
    try:
        with open(part, "wb") as out:
            sink = _Sink(out, cancelled, max_file)
            _copy(share, address, sink, progress, free_space, dest_dir, max_file)
        if expected and sink.digest.hexdigest() != expected:
            raise RemoteError("the downloaded file does not match the SHA-256 you entered")
    except BaseException:
        try:
            os.unlink(part)
        except FileNotFoundError:
            pass
        raise
    os.replace(part, final)
    return final


def _copy(
    share: Share,
    address: Address,
    sink: _Sink,
    progress: Callable[[int, int | None], None],
    free_space: Callable[[str], int],
    folder: str,
    max_file: int,
) -> None:
    path = "/" + address.path
    total: int | None = None
    resumes = 0
    while True:
        conn = share.open()
        try:
            if total is None:
                total = int(conn.getAttributes(address.share, path, timeout=TIMEOUT).file_size)
                if total > max_file:
                    raise RemoteError(f"the file is larger than {max_file // 1024**3} GiB")
                if free_space(folder) < total + SPACE_MARGIN:
                    raise RemoteError(_space_message(total, free_space(folder)))
                sink.max_file = total
            while sink.done < total:
                before = sink.done
                conn.retrieveFileFromOffset(
                    address.share, path, sink, sink.done, min(CHUNK, total - sink.done), timeout=TIMEOUT
                )
                if sink.done == before:
                    raise RemoteError("the download ended early")
                progress(sink.done, total)
            return
        except (Cancelled, RemoteError):
            raise
        except Exception as exc:  # a dropped connection or a pysmb timeout: reconnect and carry on
            if type(exc).__name__ == "OperationFailure":
                raise _failure(exc, "read that file") from exc
            resumes += 1
            if resumes > MAX_RESUMES:
                raise RemoteError(f"the connection kept dropping ({type(exc).__name__})") from exc
        finally:
            conn.close()
