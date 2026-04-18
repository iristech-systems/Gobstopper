from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from surrealdb import RecordID
from surrealengine import Document
from surrealengine.context import using_connection
from surrealengine.exceptions import DoesNotExist
from surrealengine.fields import DateTimeField, IntField, StringField
from surrealengine.connection import create_connection

from .interfaces import EventStore
from .models import EventEnvelope


def _build_event_model(table: str):
    class EventRecord(Document):
        consumer_group = StringField(required=False)
        topic = StringField(required=True)
        payload_json = StringField(required=True)
        created_at = DateTimeField(required=True)
        headers_json = StringField(required=False, default="{}")
        key = StringField(required=False)
        idempotency_key = StringField(required=False)
        producer = StringField(required=False)
        not_before = DateTimeField(required=False)
        next_attempt_at = DateTimeField(required=False)
        delivery_attempt = IntField(required=False, default=0)
        max_deliveries = IntField(required=False, default=5)
        lease_owner = StringField(required=False)
        lease_expires_at = DateTimeField(required=False)
        claimed_at = DateTimeField(required=False)
        last_error = StringField(required=False)
        acked_at = DateTimeField(required=False)
        dead_lettered_at = DateTimeField(required=False)

        class Meta:
            collection = table

    return EventRecord


class SurrealEventStore(EventStore):
    """SurrealDB-backed EventStore for embedded and server modes.

    This implementation favors correctness and portability first:
    - Works with both embedded URLs (mem://, file://, surrealkv://) and server URLs
    - Uses record IDs derived from event IDs for stable idempotent writes
    - Uses model-based CRUD for maintainability
    - Uses conditional compare-and-set transitions for claim/ack/fail safety
    """

    def __init__(
        self,
        *,
        url: str = "surrealkv://.gobstopper/eda",
        namespace: str = "gobstopper",
        database: str = "eda",
        table: str = "gob_events",
    ) -> None:
        self.url = url
        self.namespace = namespace
        self.database = database
        self.table = table
        self._conn = None
        self._client = None
        self._event_model = _build_event_model(table)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._conn = create_connection(
            url=self.url,
            namespace=self.namespace,
            database=self.database,
            async_mode=True,
        )
        await self._conn.connect()
        self._client = self._conn.client

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.disconnect()
        self._conn = None
        self._client = None

    async def _ensure_client(self):
        if self._client is None:
            await self.connect()
        return self._client

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_dt(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return SurrealEventStore._normalize_dt(value)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            return SurrealEventStore._normalize_dt(parsed)
        return None

    def _to_record(self, event: EventEnvelope) -> dict[str, Any]:
        return {
            "consumer_group": None,
            "topic": event.topic,
            "payload_json": json.dumps(event.payload, default=str),
            "created_at": self._normalize_dt(event.created_at) or self._now(),
            "headers_json": json.dumps(event.headers or {}),
            "key": event.key,
            "idempotency_key": event.idempotency_key,
            "producer": event.producer,
            "not_before": self._normalize_dt(event.not_before),
            "next_attempt_at": self._normalize_dt(event.next_attempt_at),
            "delivery_attempt": event.delivery_attempt,
            "max_deliveries": event.max_deliveries,
            "lease_owner": event.lease_owner,
            "lease_expires_at": self._normalize_dt(event.lease_expires_at),
            "claimed_at": self._normalize_dt(event.claimed_at),
            "last_error": event.last_error,
            "acked_at": self._normalize_dt(event.acked_at),
            "dead_lettered_at": self._normalize_dt(event.dead_lettered_at),
        }

    def _extract_event_id(self, raw_id: Any) -> str:
        event_id = ""
        if raw_id is not None:
            if hasattr(raw_id, "record_id"):
                event_id = str(getattr(raw_id, "record_id"))
            else:
                id_text = str(raw_id)
                tail = id_text.split(":", 1)[1] if ":" in id_text else id_text
                event_id = tail.strip("<>").strip("⟨⟩")
        return event_id

    def _field(self, record: Any, name: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    def _from_record(self, record: Any) -> EventEnvelope:
        raw_id = self._field(record, "id")
        event_id = self._extract_event_id(raw_id)

        payload_json = self._field(record, "payload_json", "null") or "null"
        headers_json = self._field(record, "headers_json", "{}") or "{}"

        try:
            payload = json.loads(payload_json)
        except Exception:
            payload = payload_json

        try:
            headers = json.loads(headers_json)
            if not isinstance(headers, dict):
                headers = {}
        except Exception:
            headers = {}

        return EventEnvelope(
            id=event_id,
            topic=self._field(record, "topic", ""),
            payload=payload,
            created_at=self._parse_dt(self._field(record, "created_at"))
            or self._now(),
            headers=headers,
            key=self._field(record, "key"),
            idempotency_key=self._field(record, "idempotency_key"),
            producer=self._field(record, "producer"),
            not_before=self._parse_dt(self._field(record, "not_before")),
            next_attempt_at=self._parse_dt(self._field(record, "next_attempt_at")),
            delivery_attempt=int(self._field(record, "delivery_attempt", 0) or 0),
            max_deliveries=max(1, int(self._field(record, "max_deliveries", 1) or 1)),
            lease_owner=self._field(record, "lease_owner"),
            lease_expires_at=self._parse_dt(self._field(record, "lease_expires_at")),
            claimed_at=self._parse_dt(self._field(record, "claimed_at")),
            last_error=self._field(record, "last_error"),
            acked_at=self._parse_dt(self._field(record, "acked_at")),
            dead_lettered_at=self._parse_dt(self._field(record, "dead_lettered_at")),
        )

    async def _query_envelopes(self, query: str, params: dict[str, Any]) -> list[EventEnvelope]:
        client = await self._ensure_client()
        rows = await client.query(query, params)
        if isinstance(rows, str):
            raise RuntimeError(f"Surreal query failed: {rows}")
        if not rows:
            return []
        if isinstance(rows, dict):
            rows = [rows]
        return [self._from_record(row) for row in rows]

    async def _conditional_update(
        self,
        event_id: str,
        *,
        set_clause: str,
        where_clause: str,
        params: dict[str, Any],
    ) -> EventEnvelope | None:
        client = await self._ensure_client()
        query = (
            "UPDATE type::thing($table, $id) "
            f"SET {set_clause} "
            f"WHERE {where_clause} "
            "RETURN AFTER;"
        )
        result = await client.query(
            query,
            {
                "table": self.table,
                "id": event_id,
                **params,
            },
        )
        if isinstance(result, str):
            raise RuntimeError(
                f"Surreal conditional update failed for event {event_id}: {result}"
            )
        if not result:
            return None
        row = result[0] if isinstance(result, list) else result
        if row is None:
            return None
        return self._from_record(row)

    async def append(self, event: EventEnvelope) -> EventEnvelope:
        await self._ensure_client()
        record = self._to_record(event)
        doc = self._event_model(id=RecordID(self.table, event.id), **record)
        with using_connection(self._conn):
            await doc.save(connection=self._conn)
        return event

    async def get(self, event_id: str) -> EventEnvelope | None:
        await self._ensure_client()
        with using_connection(self._conn):
            try:
                doc = await self._event_model.objects.get(
                    id=RecordID(self.table, event_id)
                )
            except DoesNotExist:
                return None
            return self._from_record(doc)

    async def _list_topic_events(self, topic: str) -> list[EventEnvelope]:
        return await self._query_envelopes(
            "SELECT * FROM type::table($table) WHERE topic = $topic;",
            {"table": self.table, "topic": topic},
        )

    async def claim_next(
        self,
        topic: str,
        consumer_group: str,
        lease_owner: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> EventEnvelope | None:
        current = self._normalize_dt(now) or self._now()

        async with self._lock:
            lease_expires_at = current + timedelta(seconds=lease_seconds)

            fetch_limit = 128
            max_scan = 1024
            scanned = 0
            offset = 0

            while scanned < max_scan:
                candidates = await self._query_envelopes(
                    (
                        "SELECT * FROM type::table($table) "
                        "WHERE topic = $topic "
                        "AND acked_at = NONE "
                        "AND dead_lettered_at = NONE "
                        "AND (consumer_group = NONE OR consumer_group = $consumer_group) "
                        "AND (next_attempt_at = NONE OR next_attempt_at <= $now) "
                        "AND (not_before = NONE OR not_before <= $now) "
                        "AND (lease_expires_at = NONE OR lease_expires_at <= $now) "
                        "ORDER BY created_at ASC "
                        "LIMIT $limit START $offset;"
                    ),
                    {
                        "table": self.table,
                        "topic": topic,
                        "consumer_group": consumer_group,
                        "now": current,
                        "limit": fetch_limit,
                        "offset": offset,
                    },
                )
                if not candidates:
                    break

                scanned += len(candidates)
                offset += len(candidates)

                for candidate in candidates:
                    claimed = await self._conditional_update(
                        candidate.id,
                        set_clause=(
                            "consumer_group = IF consumer_group = NONE THEN $consumer_group ELSE consumer_group END, "
                            "lease_owner = $lease_owner, "
                            "lease_expires_at = $lease_expires_at, "
                            "claimed_at = IF claimed_at = NONE THEN $now ELSE claimed_at END, "
                            "delivery_attempt = IF delivery_attempt = NONE THEN 1 ELSE delivery_attempt + 1 END, "
                            "next_attempt_at = NONE"
                        ),
                        where_clause=(
                            "acked_at = NONE AND dead_lettered_at = NONE "
                            "AND (consumer_group = NONE OR consumer_group = $consumer_group) "
                            "AND (next_attempt_at = NONE OR next_attempt_at <= $now) "
                            "AND (not_before = NONE OR not_before <= $now) "
                            "AND (lease_expires_at = NONE OR lease_expires_at <= $now)"
                        ),
                        params={
                            "lease_owner": lease_owner,
                            "consumer_group": consumer_group,
                            "lease_expires_at": lease_expires_at,
                            "now": current,
                        },
                    )
                    if claimed is not None:
                        return claimed
            return None

    async def ack(
        self,
        event_id: str,
        consumer_group: str,
        lease_owner: str,
        now: datetime | None = None,
    ) -> bool:
        current = self._normalize_dt(now) or self._now()

        async with self._lock:
            updated = await self._conditional_update(
                event_id,
                set_clause=(
                    "acked_at = $now, "
                    "lease_owner = NONE, "
                    "lease_expires_at = NONE"
                ),
                where_clause=(
                    "lease_owner = $lease_owner "
                    "AND consumer_group = $consumer_group "
                    "AND acked_at = NONE "
                    "AND dead_lettered_at = NONE"
                ),
                params={
                    "lease_owner": lease_owner,
                    "consumer_group": consumer_group,
                    "now": current,
                },
            )
            return updated is not None

    async def fail(
        self,
        event_id: str,
        consumer_group: str,
        lease_owner: str,
        error: str,
        now: datetime | None = None,
        retry_delay_seconds: float = 0.0,
    ) -> bool:
        current = self._normalize_dt(now) or self._now()

        async with self._lock:
            next_attempt_at = current + timedelta(seconds=max(0.0, retry_delay_seconds))
            updated = await self._conditional_update(
                event_id,
                set_clause=(
                    "last_error = $error, "
                    "lease_owner = NONE, "
                    "lease_expires_at = NONE, "
                    "dead_lettered_at = IF delivery_attempt >= max_deliveries THEN $now ELSE dead_lettered_at END, "
                    "next_attempt_at = IF delivery_attempt >= max_deliveries THEN NONE ELSE $next_attempt_at END"
                ),
                where_clause=(
                    "lease_owner = $lease_owner "
                    "AND consumer_group = $consumer_group "
                    "AND acked_at = NONE "
                    "AND dead_lettered_at = NONE"
                ),
                params={
                    "lease_owner": lease_owner,
                    "consumer_group": consumer_group,
                    "error": error,
                    "now": current,
                    "next_attempt_at": next_attempt_at,
                },
            )
            return updated is not None

    async def reclaim_expired(
        self,
        topic: str,
        consumer_group: str,
        now: datetime | None = None,
        limit: int = 1000,
    ) -> int:
        current = self._normalize_dt(now) or self._now()
        reclaimed = 0

        async with self._lock:
            events = await self._query_envelopes(
                (
                    "SELECT * FROM type::table($table) "
                    "WHERE topic = $topic "
                    "AND consumer_group = $consumer_group "
                    "AND acked_at = NONE "
                    "AND dead_lettered_at = NONE "
                    "AND lease_expires_at != NONE "
                    "AND lease_expires_at < $now "
                    "ORDER BY lease_expires_at ASC LIMIT $limit;"
                ),
                {
                    "table": self.table,
                    "topic": topic,
                    "consumer_group": consumer_group,
                    "now": current,
                    "limit": limit,
                },
            )
            for event in events:
                if reclaimed >= limit:
                    break
                updated = await self._conditional_update(
                    event.id,
                    set_clause=(
                        "lease_owner = NONE, "
                        "lease_expires_at = NONE, "
                        "next_attempt_at = $now"
                    ),
                    where_clause=(
                        "consumer_group = $consumer_group "
                        "AND acked_at = NONE "
                        "AND dead_lettered_at = NONE "
                        "AND lease_expires_at != NONE "
                        "AND lease_expires_at < $now"
                    ),
                    params={"consumer_group": consumer_group, "now": current},
                )
                if updated is not None:
                    reclaimed += 1

        return reclaimed

    async def list_dead_letters(
        self,
        topic: str,
        consumer_group: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventEnvelope]:
        return await self._query_envelopes(
            (
                "SELECT * FROM type::table($table) "
                "WHERE topic = $topic "
                "AND consumer_group = $consumer_group "
                "AND dead_lettered_at != NONE "
                "ORDER BY dead_lettered_at DESC "
                "LIMIT $limit START $offset;"
            ),
            {
                "table": self.table,
                "topic": topic,
                "consumer_group": consumer_group,
                "limit": max(1, limit),
                "offset": max(0, offset),
            },
        )

    async def requeue_dead_letter(
        self,
        event_id: str,
        consumer_group: str,
        now: datetime | None = None,
        expected_topic: str | None = None,
    ) -> bool:
        current = self._normalize_dt(now) or self._now()

        async with self._lock:
            event = await self.get(event_id)
            if event is None or event.dead_lettered_at is None:
                return False
            if expected_topic is not None and event.topic != expected_topic:
                return False

            if await self._conditional_update(
                event_id,
                set_clause=(
                    "consumer_group = $consumer_group, "
                    "dead_lettered_at = NONE, "
                    "last_error = NONE, "
                    "acked_at = NONE, "
                    "lease_owner = NONE, "
                    "lease_expires_at = NONE, "
                    "claimed_at = NONE, "
                    "delivery_attempt = 0, "
                    "next_attempt_at = $now"
                ),
                where_clause=(
                    "dead_lettered_at != NONE "
                    "AND consumer_group = $consumer_group"
                ),
                params={"consumer_group": consumer_group, "now": current},
            ) is None:
                return False

            return True
