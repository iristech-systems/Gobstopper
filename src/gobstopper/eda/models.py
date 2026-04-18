from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from msgspec import Struct, field


class EventEnvelope(Struct, kw_only=True):
    id: str
    topic: str
    payload: Any
    created_at: datetime
    headers: dict[str, str] = field(default_factory=dict)
    key: str | None = None
    idempotency_key: str | None = None
    producer: str | None = None

    not_before: datetime | None = None
    next_attempt_at: datetime | None = None
    delivery_attempt: int = 0
    max_deliveries: int = 5

    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    claimed_at: datetime | None = None

    last_error: str | None = None
    acked_at: datetime | None = None
    dead_lettered_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.acked_at is not None or self.dead_lettered_at is not None


def new_event(
    topic: str,
    payload: Any,
    *,
    key: str | None = None,
    idempotency_key: str | None = None,
    producer: str | None = None,
    headers: dict[str, str] | None = None,
    not_before: datetime | None = None,
    max_deliveries: int = 5,
) -> EventEnvelope:
    return EventEnvelope(
        id=str(uuid4()),
        topic=topic,
        payload=payload,
        created_at=datetime.now(),
        key=key,
        idempotency_key=idempotency_key,
        producer=producer,
        headers=headers or {},
        not_before=not_before,
        next_attempt_at=not_before,
        max_deliveries=max(1, max_deliveries),
    )
