"""Replication policies every later slice builds on (ADR-0045)."""

from __future__ import annotations

import ssl
from typing import Any

GIB = 1024**3
SPACE_MARGIN_FRACTION = 0.05
SPACE_MARGIN_MIN = 2 * GIB
SLOW_MBPS = 10.0  # megabytes per second
SLOW_RTT_MS = 50.0


class PolicyError(Exception):
    pass


def require_no_compression(context: ssl.SSLContext) -> ssl.SSLContext:
    """Every Replication TLS context: compression off, and proven off (ADR-0045 rule 2)."""
    context.options |= ssl.OP_NO_COMPRESSION
    if not context.options & ssl.OP_NO_COMPRESSION:
        raise PolicyError("TLS compression could not be switched off")
    return context


def check_uncompressed(connection: Any) -> None:
    """After the handshake: refuse a connection that negotiated compression anyway."""
    if connection.compression() is not None:
        raise PolicyError("the connection negotiated TLS compression; refused")


def space_needed(total_bytes: int) -> int:
    """Bytes free before a transfer starts: the size plus 5 percent or 2 GiB, whichever is larger."""
    return total_bytes + max(int(total_bytes * SPACE_MARGIN_FRACTION), SPACE_MARGIN_MIN)


def link_verdict(megabytes_per_second: float, rtt_ms: float, overlay: bool = False) -> dict[str, Any]:
    """What to tell the user about a measured link. Keepsake cannot see a VPN's path, so it says so plainly."""
    slow = megabytes_per_second < SLOW_MBPS or rtt_ms > SLOW_RTT_MS
    message = None
    if slow:
        message = f"This link looks slow ({megabytes_per_second:.1f} MB/s, {rtt_ms:.0f} ms)."
        if overlay:
            message += " A VPN or Tailscale may be relaying it rather than connecting directly."
    return {"slow": slow, "megabytesPerSecond": megabytes_per_second, "rttMs": rtt_ms, "message": message}
