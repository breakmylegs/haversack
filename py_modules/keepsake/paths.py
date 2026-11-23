"""Plugin directories, taken from the Decky environment.

Decky sets these variables for every plugin process (see ``decky.pyi``). Tests
build :class:`PluginPaths` directly from temporary folders.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PluginPaths:
    settings_dir: str
    runtime_dir: str
    log_dir: str
    plugin_dir: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> PluginPaths:
        source = os.environ if env is None else env
        home = source.get("DECKY_USER_HOME") or os.path.expanduser("~")
        fallback = os.path.join(home, "homebrew")
        return cls(
            settings_dir=source.get("DECKY_PLUGIN_SETTINGS_DIR", os.path.join(fallback, "settings", "Haversack")),
            runtime_dir=source.get("DECKY_PLUGIN_RUNTIME_DIR", os.path.join(fallback, "data", "Haversack")),
            log_dir=source.get("DECKY_PLUGIN_LOG_DIR", os.path.join(fallback, "logs", "Haversack")),
            plugin_dir=source.get("DECKY_PLUGIN_DIR", os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        )

    def ensure(self) -> None:
        for folder in (self.settings_dir, self.runtime_dir, self.log_dir):
            os.makedirs(folder, exist_ok=True)

    @property
    def write_roots(self) -> tuple[str, ...]:
        """Plugin-owned folders in the write allowlist (build prompt section 8)."""
        return (self.settings_dir, self.runtime_dir, self.log_dir)
