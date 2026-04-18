from __future__ import annotations

import asyncio
from datetime import datetime

from .config import EDAConfig
from .interfaces import Dispatcher, EventHandler, EventStore
from .models import EventEnvelope, new_event


class EventDispatcher(Dispatcher):
    def __init__(
        self,
        store: EventStore,
        *,
        config: EDAConfig | None = None,
        worker_name: str = "dispatcher-0",
    ) -> None:
        self.store = store
        self.config = config or EDAConfig()
        self.worker_name = worker_name
        self.handlers: dict[str, EventHandler] = {}
        self._stop_event = asyncio.Event()

    def register_handler(self, topic: str, handler: EventHandler) -> None:
        self.handlers[topic] = handler

    async def publish(self, topic: str, payload: object, **metadata: object) -> EventEnvelope:
        event = new_event(
            topic=topic,
            payload=payload,
            key=metadata.get("key") if isinstance(metadata.get("key"), str) else None,
            idempotency_key=(
                metadata.get("idempotency_key")
                if isinstance(metadata.get("idempotency_key"), str)
                else None
            ),
            producer=(
                metadata.get("producer")
                if isinstance(metadata.get("producer"), str)
                else None
            ),
            headers=(
                metadata.get("headers")
                if isinstance(metadata.get("headers"), dict)
                else None
            ),
            not_before=(
                metadata.get("not_before")
                if isinstance(metadata.get("not_before"), datetime)
                else None
            ),
            max_deliveries=(
                int(metadata.get("max_deliveries"))
                if isinstance(metadata.get("max_deliveries"), int)
                else 5
            ),
        )
        return await self.store.append(event)

    async def run_once(self, topic: str, consumer_group: str) -> bool:
        event = await self.store.claim_next(
            topic=topic,
            consumer_group=consumer_group,
            lease_owner=self.worker_name,
            lease_seconds=self.config.lease_seconds,
        )
        if event is None:
            return False

        handler = self.handlers.get(topic)
        if handler is None:
            await self.store.fail(
                event.id,
                consumer_group,
                self.worker_name,
                error=f"no handler registered for topic '{topic}'",
                retry_delay_seconds=0.0,
            )
            return True

        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
            await self.store.ack(event.id, consumer_group, self.worker_name)
        except Exception as exc:
            backoff = min(2 ** max(1, event.delivery_attempt), 60)
            await self.store.fail(
                event.id,
                consumer_group,
                self.worker_name,
                error=str(exc),
                retry_delay_seconds=float(backoff),
            )
        return True

    async def run_forever(self, topics: list[str], consumer_group: str) -> None:
        while not self._stop_event.is_set():
            made_progress = False
            for topic in topics:
                await self.store.reclaim_expired(topic, consumer_group)
                handled = await self.run_once(topic, consumer_group)
                made_progress = made_progress or handled

            if made_progress:
                await asyncio.sleep(self.config.poll_interval_seconds)
            else:
                await asyncio.sleep(self.config.idle_sleep_seconds)

    async def stop(self) -> None:
        self._stop_event.set()
