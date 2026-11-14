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

USER_AGENT = "Keepsake (+https://github.com/breakmylegs/keepsake)"
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


class NetError(Exception):
    """Network failure, disallowed host or oversized response."""


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


Fetcher = Callable[..., HttpResponse]


def check_url(url: str, allowed: frozenset[str] = ALLOWED_HOSTS) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise NetError(f"only https is allowed: {parts.scheme or 'none'}")
    host = (parts.hostname or "").lower()
    if host not in allowed:
        raise NetError(f"host not on the allowlist: {host or 'none'}")
    if parts.username or parts.password:
        raise NetError("credentials in URLs are not allowed")
    return url


def ssl_context() -> ssl.SSLContext:
    """Prefer certifi's bundle when present (Decky ships it), else the system store."""
    try:
        import certifi  # type: ignore[import-not-found, unused-ignore]

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


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
) -> HttpResponse:
    """GET ``url`` and stream a 200 body into ``dest`` (body is not kept in memory).

    Returns the status and headers; ``body`` is empty. Raises :class:`NetError`
    on transport errors or when the body exceeds ``max_bytes``.
    """
    check_url(url, allowed)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()), _AllowlistRedirect(allowed)
    )
    try:
        with opener.open(request, timeout=timeout) as response, open(dest, "wb") as out:
            written = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise NetError(f"response larger than {max_bytes} bytes")
                out.write(chunk)
            return HttpResponse(status=response.status, headers={k.lower(): v for k, v in response.headers.items()})
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=exc.code, headers={k.lower(): v for k, v in (exc.headers or {}).items()})
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
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes + 1) if exc.fp else b""
        status = exc.code
        response_headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
    except NetError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NetError(f"{type(exc).__name__}: {reason}") from exc
    if len(body) > max_bytes:
        raise NetError(f"response larger than {max_bytes} bytes")
    return HttpResponse(status=status, headers=response_headers, body=body)
