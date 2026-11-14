"""Structured, redacted, rotated JSON-lines logging.

Records go to ``keepsake.jsonl`` in the Decky plugin log folder. Every record
passes through :func:`keepsake.redact.redact` before it is written.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from collections import deque
from typing import Any

from .redact import redact, redact_text

LOG_FILE = "keepsake.jsonl"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
LOGGER_NAME = "keepsake"


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", record.name),
            "msg": redact_text(record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if fields:
            entry["fields"] = redact(fields)
        if record.exc_info:
            entry["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, sort_keys=True, default=str)


def setup_logging(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, LOG_FILE), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(JsonLinesFormatter())
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def log_event(level: int, event: str, msg: str, **fields: Any) -> None:
    get_logger().log(level, msg, extra={"event": event, "fields": fields or None})


def tail(log_dir: str, limit: int = 200) -> list[dict[str, Any]]:
    """Return the newest ``limit`` records, oldest first. Bad lines are skipped."""
    limit = max(1, min(int(limit), 2000))
    path = os.path.join(log_dir, LOG_FILE)
    lines: deque[str] = deque(maxlen=limit)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                lines.append(line)
    except FileNotFoundError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out
