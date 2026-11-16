"""One SQLite database for module state, with migrations namespaced per module (v2 spec 7.2, ADR-0024).

Saves keeps its v1 JSON files (not moved for cosmetic reasons). New state goes
here: each module owns tables prefixed with its name and a list of forward
migrations; ``_migrations`` records how far each module has got. A migration
runs in one transaction, so a failure leaves that module at its previous
version and does not touch the others (P13). A database written by a newer
version (higher version for a module than this build knows) is opened
read-only for that module.

If the embedded Python has no ``sqlite3`` (assumption A9), :func:`open_db`
returns None and modules that need state disable themselves with a clear
health message; Saves is unaffected.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from typing import Any

try:
    import sqlite3
except ImportError:  # pragma: no cover - depends on the embedded Python
    sqlite3 = None  # type: ignore[assignment]

DB_FILE = "keepsake.db"


def sqlite_available() -> bool:
    return sqlite3 is not None


class StateError(Exception):
    pass


class StateDB:
    def __init__(self, path: str) -> None:
        if sqlite3 is None:
            raise StateError("sqlite3 is not available")
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS _migrations (module TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        if os.name == "posix":
            os.chmod(path, 0o600)

    def version(self, module: str) -> int:
        row = self._conn.execute("SELECT version FROM _migrations WHERE module = ?", (module,)).fetchone()
        return int(row[0]) if row else 0

    def migrate(self, module: str, steps: Sequence[str]) -> int:
        """Run ``module``'s migrations not yet applied, each in its own transaction. Returns the version reached.

        Raises :class:`StateError` if the database is newer than ``steps`` (a rollback):
        the module must then treat its state as read-only.
        """
        if not module.isidentifier():
            raise StateError("module names are identifiers")
        with self._lock:
            current = self.version(module)
            if current > len(steps):
                raise StateError(f"{module} state was written by a newer Keepsake (version {current})")
            for number in range(current + 1, len(steps) + 1):
                self._conn.execute("BEGIN")
                try:
                    for statement in _statements(steps[number - 1]):
                        self._conn.execute(statement)
                    self._conn.execute(
                        "INSERT INTO _migrations (module, version) VALUES (?, ?) "
                        "ON CONFLICT(module) DO UPDATE SET version = excluded.version",
                        (module, number),
                    )
                    self._conn.execute("COMMIT")
                except Exception as exc:
                    self._conn.execute("ROLLBACK")
                    raise StateError(f"{module} migration {number} failed: {exc}") from exc
            return len(steps)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _statements(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


def open_db(runtime_dir: str) -> StateDB | None:
    if sqlite3 is None:
        return None
    return StateDB(os.path.join(runtime_dir, DB_FILE))
