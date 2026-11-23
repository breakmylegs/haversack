"""HTTPS client with a host allowlist (build prompt section 6).

Every request and every redirect target must be HTTPS to an allowlisted host.
Hosts are added here as features need them; adding one outside the build
prompt's allowlist is an escalation item.

Runs in worker threads (stdlib ``urllib``), never on the asyncio loop.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

USER_AGENT = "Keepsake (+https://github.com/breakmylegs/haversack)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 4 * 1024 * 1024

# GitHub API, release pages and the hosts release asset downloads redirect to.
ALLOWED_HOSTS = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "raw.githubusercontent.com",
    }
)


# Microsoft sign-in and Graph (build prompt section 6), used only by the OneDrive store.
MICROSOFT_HOSTS = frozenset({"login.microsoftonline.com", "graph.microsoft.com"})
# Upload-session and download URLs that Graph hands out for OneDrive personal (ADR-0008).
# Only ever reached through URLs returned by Graph, and never sent the bearer token.
MICROSOFT_CONTENT_SUFFIXES = (".1drv.com", ".microsoftpersonalcontent.com")
# Google sign-in and the Drive API (build prompt section 6), used only by the Google Drive store.
GOOGLE_HOSTS = frozenset({"oauth2.googleapis.com", "www.googleapis.com"})


class NetError(Exception):
    """Network failure, disallowed host or oversized response."""


class DisallowedHost(NetError):
    """The URL is not HTTPS to an allowlisted host. Never retried."""


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


Fetcher = Callable[..., HttpResponse]


def check_url(url: str, allowed: frozenset[str] = ALLOWED_HOSTS, suffixes: tuple[str, ...] = ()) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DisallowedHost(f"only https is allowed: {parts.scheme or 'none'}")
    host = (parts.hostname or "").lower()
    # Suffixes start with a dot, so "evil1drv.com" never matches ".1drv.com".
    if host not in allowed and not any(host.endswith(s) and len(host) > len(s) for s in suffixes):
        raise DisallowedHost(f"host not on the allowlist: {host or 'none'}")
    if parts.username or parts.password:
        raise DisallowedHost("credentials in URLs are not allowed")
    return url


def ssl_context() -> ssl.SSLContext:
    """Prefer certifi's bundle when present (Decky ships it), else the system store."""
    try:
        import certifi  # type: ignore[import-not-found, unused-ignore]

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _headers(message: Any) -> dict[str, str]:
    """Lower-cased response headers. Repeated `Set-Cookie` lines are kept, joined by newlines (sessions need them)."""
    out: dict[str, str] = {}
    for key, value in (message or {}).items():
        key = key.lower()
        out[key] = f"{out[key]}\n{value}" if key == "set-cookie" and key in out else value
    return out


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed: frozenset[str]) -> None:
        self.allowed = allowed

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        check_url(newurl, self.allowed)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_to_file(
    url: str,
    dest: str,
    headers: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed: frozenset[str] = ALLOWED_HOSTS,
    progress: Callable[[int, int | None], None] | None = None,
) -> HttpResponse:
    """GET ``url`` and stream a 200 body into ``dest`` (body is not kept in memory).

    Returns the status and headers; ``body`` is empty. Raises :class:`NetError`
    on transport errors or when the body exceeds ``max_bytes``. ``progress`` is
    called after each chunk with the bytes written so far and the expected
    total from ``Content-Length`` (None when the server does not say).
    """
    check_url(url, allowed)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()), _AllowlistRedirect(allowed)
    )
    try:
        with opener.open(request, timeout=timeout) as response, open(dest, "wb") as out:
            written = 0
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise NetError(f"response larger than {max_bytes} bytes")
                out.write(chunk)
                if progress is not None:
                    progress(written, total)
            return HttpResponse(status=response.status, headers=_headers(response.headers))
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=exc.code, headers=_headers(exc.headers))
    except NetError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NetError(f"{type(exc).__name__}: {reason}") from exc


def fetch(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed: frozenset[str] = ALLOWED_HOSTS,
) -> HttpResponse:
    """GET ``url``. HTTP error statuses are returned, not raised; transport errors raise :class:`NetError`."""
    check_url(url, allowed)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()), _AllowlistRedirect(allowed)
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            status = response.status
            response_headers = _headers(response.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes + 1) if exc.fp else b""
        status = exc.code
        response_headers = _headers(exc.headers)
    except NetError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NetError(f"{type(exc).__name__}: {reason}") from exc
    if len(body) > max_bytes:
        raise NetError(f"response larger than {max_bytes} bytes")
    return HttpResponse(status=status, headers=response_headers, body=body)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        return None  # the caller sees the 3xx and decides, so credentials never follow a redirect


Transport = Callable[..., HttpResponse]


def request(
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 60.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    dest: str | None = None,
    allowed: frozenset[str] = MICROSOFT_HOSTS,
    suffixes: tuple[str, ...] = MICROSOFT_CONTENT_SUFFIXES,
) -> HttpResponse:
    """One HTTPS request that never follows redirects.

    With ``dest``, a 200 body is streamed to that file instead of memory.
    HTTP error statuses (and 3xx) are returned, not raised.
    """
    check_url(url, allowed, suffixes)
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context()), _NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            response_headers = _headers(response.headers)
            if dest is not None and response.status == 200:
                written = 0
                with open(dest, "wb") as out:
                    while chunk := response.read(1024 * 1024):
                        written += len(chunk)
                        if written > max_bytes:
                            raise NetError(f"response larger than {max_bytes} bytes")
                        out.write(chunk)
                return HttpResponse(status=response.status, headers=response_headers)
            data = response.read(max_bytes + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        data = exc.read(max_bytes + 1) if exc.fp else b""
        status = exc.code
        response_headers = _headers(exc.headers)
    except NetError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NetError(f"{type(exc).__name__}: {reason}") from exc
    if len(data) > max_bytes:
        raise NetError(f"response larger than {max_bytes} bytes")
    return HttpResponse(status=status, headers=response_headers, body=data)


def google_request(
    method: str, url: str, headers: Mapping[str, str] | None = None, body: bytes | None = None, **kw: Any
) -> HttpResponse:
    """:func:`request` limited to Google's sign-in and Drive API hosts."""
    return request(method, url, headers, body, allowed=GOOGLE_HOSTS, suffixes=(), **kw)


def endpoint_transport(base_url: str) -> Transport:
    """A transport limited to the single HTTPS host of a user-configured WebDAV or S3 endpoint.

    The build prompt allowlists user-configured WebDAV and S3 endpoints; only
    HTTPS is accepted, so credentials never travel in clear text.
    """
    check_url(base_url, frozenset({(urlsplit(base_url).hostname or "").lower()}))
    allowed = frozenset({(urlsplit(base_url).hostname or "").lower()})

    def transport(
        method: str, url: str, headers: Mapping[str, str] | None = None, body: bytes | None = None, **kw: Any
    ) -> HttpResponse:
        return request(method, url, headers, body, allowed=allowed, suffixes=(), **kw)

    return transport
