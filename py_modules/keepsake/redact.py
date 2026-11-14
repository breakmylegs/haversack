"""Redaction of secrets and personal data (threat model T9).

Applied to every log record and to the diagnostics export. Two layers:

* values under sensitive keys are replaced whatever they contain
* free text is scrubbed for token-shaped strings, email addresses and home
  folder paths that would reveal a username
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[redacted]"

SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "accesstoken",
        "authorization",
        "client_secret",
        "clientsecret",
        "code",
        "device_code",
        "devicecode",
        "id_token",
        "password",
        "refresh_token",
        "refreshtoken",
        "secret",
        "secret_access_key",
        "token",
        "user_code",
        "usercode",
        "account",
        "email",
        "username",
    }
)

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization headers and bearer tokens.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    # JSON Web Tokens.
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), REDACTED),
    # GitHub tokens.
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), REDACTED),
    # AWS access key IDs.
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
    # key=value or "key": "value" pairs with sensitive names inside free text.
    (
        re.compile(
            r"(?i)\b(access_token|refresh_token|id_token|client_secret|device_code|user_code|password|secret)"
            r"(\"?\s*[:=]\s*\"?)([^\s\"&,}]+)"
        ),
        r"\1\2" + REDACTED,
    ),
    # Email addresses.
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[email]"),
    # Home folders: /home/<user> and /var/home/<user> become ~.
    (re.compile(r"(?:/var)?/home/[^/\s\"']+"), "~"),
]


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact(value: Any, _depth: int = 0) -> Any:
    """Return a redacted deep copy of ``value``."""
    if _depth > 20:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower().replace("-", "_") in SENSITIVE_KEYS:
                out[key] = REDACTED
            else:
                out[key] = redact(item, _depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item, _depth + 1) for item in value]
    return value
