"""Lifecycle bus (v2 spec section 7.2, ADR-0012).

Core publishes ``game_started``, ``game_frozen``, ``game_released`` and
``game_exited`` with the game's ``gameKey`` and app ID. Modules subscribe
instead of adding their own launch wrapper or Steam listener. A subscriber that
raises is logged and isolated: it never stops other subscribers or the publisher
(P13). Unsubscribing everything a module registered is one call, so a disabled
module keeps no listeners.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .log import log_event

EVENTS = ("game_started", "game_frozen", "game_released", "game_exited")
Handler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, Handler]]] = {event: [] for event in EVENTS}
        self.failures: list[tuple[str, str, str]] = []  # (owner, event, error), most recent last

    def subscribe(self, event: str, owner: str, handler: Handler) -> None:
        if event not in self._handlers:
            raise ValueError(f"unknown event {event}")
        self._handlers[event].append((owner, handler))

    def unsubscribe_all(self, owner: str) -> None:
        for event, handlers in self._handlers.items():
            self._handlers[event] = [(o, h) for o, h in handlers if o != owner]

    def subscribers(self, event: str) -> list[str]:
        return [owner for owner, _ in self._handlers.get(event, [])]

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        for owner, handler in list(self._handlers.get(event, [])):
            try:
                await handler({"event": event, **payload})
            except Exception as exc:  # noqa: BLE001 - one module's fault must not reach the others (P13)
                self.failures = [*self.failures[-49:], (owner, event, str(exc))]
                log_event(
                    logging.WARNING,
                    "bus.handler_failed",
                    "A module's event handler failed",
                    owner=owner,
                    busEvent=event,
                )
