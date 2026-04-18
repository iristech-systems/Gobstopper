from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from .interfaces import EventStore
from .models import EventEnvelope


class InMemoryEventStore(EventStore):
    """Reference EventStore implementation for local development and tests."""

    def __init__(self) -> None:
        self._events: dict[str, EventEnvelope] = {}
        self._lock = asyncio.Lock()

    async def append(self, event: EventEnvelope) -> EventEnvelope:
        async with self._lock:
            self._events[event.id] = event
            return event

    async def get(self, event_id: str) -> EventEnvelope | None:
        async with self._lock:
            return self._events.get(event_id)

    async def claim_next(
        self,
        topic: str,
        consumer_group: str,
        lease_owner: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> EventEnvelope | None:
        del consumer_group
        current = now or datetime.now()

        async with self._lock:
            candidates = [
                event
                for event in self._events.values()
                if event.topic == topic
                and not event.is_terminal
                and (event.next_attempt_at is None or event.next_attempt_at <= current)
                and (event.not_before is None or event.not_before <= current)
                and (
                    event.lease_expires_at is None or event.lease_expires_at <= current
                )
            ]

            if not candidates:
                return None

            candidates.sort(
                key=lambda e: (
                    e.next_attempt_at or e.not_before or e.created_at,
                    e.created_at,
                )
            )

            claimed = candidates[0]
            claimed.delivery_attempt += 1
            claimed.lease_owner = lease_owner
            claimed.claimed_at = claimed.claimed_at or current
            claimed.lease_expires_at = current + timedelta(seconds=lease_seconds)
            claimed.next_attempt_at = None
            return claimed

    async def ack(
        self,
        event_id: str,
        consumer_group: str,
        lease_owner: str,
        now: datetime | None = None,
    ) -> bool:
        del consumer_group
        current = now or datetime.now()

        async with self._lock:
            event = self._events.get(event_id)
            if event is None or event.lease_owner != lease_owner:
                return False

            event.acked_at = current
            event.lease_owner = None
            event.lease_expires_at = None
            return True

    async def fail(
        self,
        event_id: str,
        consumer_group: str,
        lease_owner: str,
        error: str,
        now: datetime | None = None,
        retry_delay_seconds: float = 0.0,
    ) -> bool:
        del consumer_group
        current = now or datetime.now()

        async with self._lock:
            event = self._events.get(event_id)
            if event is None or event.lease_owner != lease_owner:
                return False

            event.last_error = error
            event.lease_owner = None
            event.lease_expires_at = None

            if event.delivery_attempt >= event.max_deliveries:
                event.dead_lettered_at = current
                event.next_attempt_at = None
            else:
                delay = max(0.0, retry_delay_seconds)
                event.next_attempt_at = current + timedelta(seconds=delay)
            return True

    async def reclaim_expired(
        self,
        topic: str,
        consumer_group: str,
        now: datetime | None = None,
        limit: int = 1000,
    ) -> int:
        del consumer_group
        current = now or datetime.now()
        reclaimed = 0

        async with self._lock:
            for event in self._events.values():
                if reclaimed >= limit:
                    break
                if (
                    event.topic == topic
                    and not event.is_terminal
                    and event.lease_expires_at is not None
                    and event.lease_expires_at < current
                ):
                    event.lease_owner = None
                    event.lease_expires_at = None
                    event.next_attempt_at = current
                    reclaimed += 1

        return reclaimed

    async def list_dead_letters(
        self,
        topic: str,
        consumer_group: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventEnvelope]:
        del consumer_group
        async with self._lock:
            dead = [
                event
                for event in self._events.values()
                if event.topic == topic and event.dead_lettered_at is not None
            ]
            dead.sort(key=lambda e: e.dead_lettered_at or e.created_at, reverse=True)
            return dead[offset : offset + limit]
