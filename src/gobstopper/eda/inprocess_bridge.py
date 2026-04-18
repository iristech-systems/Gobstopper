from __future__ import annotations

import asyncio
from collections import defaultdict

from .interfaces import BrokerBridge, EventHandler
from .models import EventEnvelope


class InProcessBridge(BrokerBridge):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def publish(self, event: EventEnvelope) -> None:
        handlers = list(self._handlers.get(event.topic, []))
        for handler in handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)

    async def health(self) -> dict[str, str]:
        return {"status": "ok", "kind": "in-process"}
