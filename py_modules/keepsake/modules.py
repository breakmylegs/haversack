"""Module registry (v2 spec 7.3, P13, ADR-0012).

Each module has a name, a flag in settings, a short "what it writes" text, an
optional start and stop, health checks and the lifecycle events it listens to.
A disabled module registers no listeners, runs no jobs and writes nothing. A
module whose start, stop or health check raises is marked failed and stopped,
and the others carry on: Saves never depends on another module.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .bus import EventBus, Handler
from .log import log_event

DEFAULT_FLAGS = {"saves": True, "advisor": True, "replication": False, "installer": True, "desktop": False}


@dataclass
class Module:
    name: str
    title: str
    description: str
    writes: str
    available: bool = True  # False until the module is built (later v2 slices)
    start: Callable[[], Awaitable[None]] | None = None
    stop: Callable[[], Awaitable[None]] | None = None
    health: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None
    listeners: dict[str, Handler] = field(default_factory=dict)


@dataclass
class ModuleState:
    running: bool = False
    failed: str | None = None


class ModuleRegistry:
    def __init__(self, bus: EventBus, flags: Callable[[], dict[str, bool]]) -> None:
        self.bus = bus
        self.flags = flags
        self.modules: dict[str, Module] = {}
        self.state: dict[str, ModuleState] = {}

    def register(self, module: Module) -> None:
        if module.name in self.modules:
            raise ValueError(f"module {module.name} is already registered")
        self.modules[module.name] = module
        self.state[module.name] = ModuleState()

    def enabled(self, name: str) -> bool:
        module = self.modules.get(name)
        if module is None or not module.available or self.state[name].failed:
            return False
        return bool(self.flags().get(name, DEFAULT_FLAGS.get(name, False)))

    def running(self, name: str) -> bool:
        return name in self.state and self.state[name].running

    async def start(self, name: str) -> None:
        module, state = self.modules[name], self.state[name]
        if state.running or not self.enabled(name):
            return
        try:
            if module.start:
                await module.start()
            for event, handler in module.listeners.items():
                self.bus.subscribe(event, name, handler)
            state.running = True
            log_event(logging.INFO, "module.started", "Module started", module=name)
        except Exception as exc:  # noqa: BLE001 - a failing module must not stop the others (P13)
            await self._fail(name, f"could not start: {exc}")

    async def stop(self, name: str) -> None:
        module, state = self.modules[name], self.state[name]
        self.bus.unsubscribe_all(name)
        if not state.running:
            return
        state.running = False
        try:
            if module.stop:
                await module.stop()
        except Exception as exc:  # noqa: BLE001
            state.failed = f"could not stop cleanly: {exc}"
        log_event(logging.INFO, "module.stopped", "Module stopped", module=name)

    async def _fail(self, name: str, reason: str) -> None:
        self.state[name].failed = reason
        log_event(logging.ERROR, "module.failed", "Module disabled after a failure", module=name, reason=reason)
        await self.stop(name)

    async def start_all(self) -> None:
        for name in self.modules:
            await self.start(name)

    async def stop_all(self) -> None:
        for name in self.modules:
            await self.stop(name)

    async def apply_flags(self) -> None:
        """Start newly enabled modules and stop disabled ones."""
        for name in self.modules:
            if self.enabled(name):
                await self.start(name)
            else:
                await self.stop(name)

    async def reset(self, name: str) -> None:
        """Clear a failure (from the Modules page) and try again if enabled."""
        self.state[name].failed = None
        await self.apply_flags()

    async def status(self) -> list[dict[str, Any]]:
        out = []
        for name, module in self.modules.items():
            state = self.state[name]
            checks: list[dict[str, Any]] = []
            if state.running and module.health:
                try:
                    checks = await module.health()
                except Exception as exc:  # noqa: BLE001
                    await self._fail(name, f"health check failed: {exc}")
            out.append(
                {
                    "name": name,
                    "title": module.title,
                    "description": module.description,
                    "writes": module.writes,
                    "available": module.available,
                    "flag": bool(self.flags().get(name, DEFAULT_FLAGS.get(name, False))),
                    "running": state.running,
                    "failed": state.failed,
                    "health": checks,
                }
            )
        return out
