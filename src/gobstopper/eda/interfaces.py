from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable, Protocol

from .models import EventEnvelope


EventHandler = Callable[[EventEnvelope], Awaitable[None] | None]


class EventStore(Protocol):
    async def append(self, event: EventEnvelope) -> EventEnvelope: ...

    async def get(self, event_id: str) -> EventEnvelope | None: ...

    async def claim_next(
        self,
        topic: str,
        consumer_group: str,
        lease_owner: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> EventEnvelope | None: ...

    async def ack(
        self,
        event_id: str,
        consumer_group: str,
        lease_owner: str,
        now: datetime | None = None,
    ) -> bool: ...

    async def fail(
        self,
        event_id: str,
        consumer_group: str,
        lease_owner: str,
        error: str,
        now: datetime | None = None,
        retry_delay_seconds: float = 0.0,
    ) -> bool: ...

    async def reclaim_expired(
        self,
        topic: str,
        consumer_group: str,
        now: datetime | None = None,
        limit: int = 1000,
    ) -> int: ...

    async def list_dead_letters(
        self,
        topic: str,
        consumer_group: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventEnvelope]: ...


class BrokerBridge(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...

    async def subscribe(self, topic: str, handler: EventHandler) -> None: ...

    async def health(self) -> dict[str, str]: ...


class Dispatcher(Protocol):
    def register_handler(self, topic: str, handler: EventHandler) -> None: ...

    async def publish(self, topic: str, payload: object, **metadata: object) -> EventEnvelope: ...

    async def run_once(self, topic: str, consumer_group: str) -> bool: ...

    async def run_forever(self, topics: list[str], consumer_group: str) -> None: ...

    async def stop(self) -> None: ...
