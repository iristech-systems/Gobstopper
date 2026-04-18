from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


def _json_default(value: Any) -> str:
    return str(value)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float
    stale_until: float | None = None
    version_token: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class CacheStore(Protocol):
    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None: ...

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: float,
        stale_ttl: float | None = None,
        version_token: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None: ...

    def delete(self, key: str) -> None: ...

    def mget(self, keys: list[str], *, allow_stale: bool = False) -> dict[str, CacheEntry]: ...

    def invalidate_prefix(self, prefix: str) -> int: ...


class MemoryCacheStore(CacheStore):
    """In-process L1 cache store with TTL and optional stale window."""

    def __init__(self) -> None:
        self._data: dict[str, CacheEntry] = {}

    @staticmethod
    def _now() -> float:
        return time.time()

    def _is_fresh(self, entry: CacheEntry, now: float) -> bool:
        return now <= entry.expires_at

    def _is_servable_stale(self, entry: CacheEntry, now: float) -> bool:
        return entry.stale_until is not None and now <= entry.stale_until

    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        entry = self._data.get(key)
        if entry is None:
            return None

        now = self._now()
        if self._is_fresh(entry, now):
            return entry

        if allow_stale and self._is_servable_stale(entry, now):
            return entry

        # Keep stale-servable entries in store for possible SWR reads.
        if not self._is_servable_stale(entry, now):
            self._data.pop(key, None)
        return None

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: float,
        stale_ttl: float | None = None,
        version_token: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        now = self._now()
        expires_at = now + max(0.0, ttl)
        stale_until = None
        if stale_ttl is not None:
            stale_until = now + max(0.0, stale_ttl)
            if stale_until < expires_at:
                stale_until = expires_at

        self._data[key] = CacheEntry(
            value=value,
            expires_at=expires_at,
            stale_until=stale_until,
            version_token=version_token,
            meta=meta or {},
        )

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def mget(self, keys: list[str], *, allow_stale: bool = False) -> dict[str, CacheEntry]:
        out: dict[str, CacheEntry] = {}
        for key in keys:
            entry = self.get(key, allow_stale=allow_stale)
            if entry is not None:
                out[key] = entry
        return out

    def invalidate_prefix(self, prefix: str) -> int:
        keys = [k for k in self._data.keys() if k.startswith(prefix)]
        for key in keys:
            self._data.pop(key, None)
        return len(keys)


class SurrealCacheStore(CacheStore):
    """Synchronous Surreal-backed L2 cache store.

    Supports embedded and remote URLs (e.g. ``surrealkv://...``, ``mem://...``,
    ``ws://...``, ``wss://...``) via ``surrealengine`` sync connection mode.
    """

    def __init__(
        self,
        *,
        url: str = "surrealkv://.gobstopper/cache",
        namespace: str = "gobstopper",
        database: str = "cache",
        table: str = "cache_entries",
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        auto_connect: bool = True,
    ) -> None:
        self.url = url
        self.namespace = namespace
        self.database = database
        self.table = table
        self.username = username
        self.password = password
        self.token = token
        self._conn = None
        self._client = None
        self._write_lock = threading.Lock()

        if auto_connect:
            self.connect()

    @staticmethod
    def _now() -> float:
        return time.time()

    def connect(self) -> None:
        if self._client is not None:
            return
        from surrealengine.connection import create_connection

        self._conn = create_connection(
            url=self.url,
            namespace=self.namespace,
            database=self.database,
            username=self.username,
            password=self.password,
            token=self.token,
            async_mode=False,
            auto_connect=False,
        )
        self._conn.connect()
        self._client = self._conn.client

    def close(self) -> None:
        if self._conn is not None:
            self._conn.disconnect()
        self._conn = None
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self.connect()
        return self._client

    def _row_to_entry(self, row: dict[str, Any]) -> CacheEntry:
        value_raw = row.get("value_json", "null")
        meta_raw = row.get("meta_json", "{}")
        try:
            value = json.loads(value_raw)
        except Exception:
            value = value_raw
        try:
            meta = json.loads(meta_raw)
            if not isinstance(meta, dict):
                meta = {}
        except Exception:
            meta = {}

        return CacheEntry(
            value=value,
            expires_at=float(row.get("expires_at") or 0.0),
            stale_until=(
                float(row.get("stale_until"))
                if row.get("stale_until") is not None
                else None
            ),
            version_token=row.get("version_token"),
            meta=meta,
        )

    @staticmethod
    def _version_rank(token: str | None) -> tuple[int, str | None]:
        if not token:
            return (0, None)
        if token.startswith("v") and token[1:].isdigit():
            return (1, str(int(token[1:])))
        return (2, token)

    def _should_write(self, existing: CacheEntry | None, incoming_token: str | None) -> bool:
        if existing is None:
            return True

        existing_token = existing.version_token
        if existing_token is None:
            return True
        if incoming_token is None:
            return False
        if existing_token == incoming_token:
            return True

        existing_kind, existing_val = self._version_rank(existing_token)
        incoming_kind, incoming_val = self._version_rank(incoming_token)

        # Numeric version tokens compare by integer magnitude.
        if existing_kind == incoming_kind == 1 and existing_val is not None and incoming_val is not None:
            return int(incoming_val) >= int(existing_val)

        # For non-numeric/version-mismatched tokens, avoid stale clobber by rejecting overwrite.
        return False

    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        client = self._ensure_client()
        rows = client.query(
            "SELECT * FROM type::thing($table, $id);",
            {"table": self.table, "id": key},
        )
        if not rows:
            return None
        row = rows[0] if isinstance(rows, list) else rows
        entry = self._row_to_entry(row)

        now = self._now()
        if now <= entry.expires_at:
            return entry
        if allow_stale and entry.stale_until is not None and now <= entry.stale_until:
            return entry

        if entry.stale_until is None or now > entry.stale_until:
            self.delete(key)
        return None

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: float,
        stale_ttl: float | None = None,
        version_token: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        client = self._ensure_client()

        # Guard against local TOCTOU races between read-check-write operations.
        with self._write_lock:
            existing = self.get(key, allow_stale=True)
            if not self._should_write(existing, version_token):
                return

            now = self._now()
            expires_at = now + max(0.0, ttl)
            stale_until = None
            if stale_ttl is not None:
                stale_until = now + max(0.0, stale_ttl)
                if stale_until < expires_at:
                    stale_until = expires_at

            data = {
                "key": key,
                "value_json": json.dumps(value, default=_json_default),
                "expires_at": expires_at,
                "stale_until": stale_until,
                "version_token": version_token,
                "meta_json": json.dumps(meta or {}, default=_json_default),
                "updated_at": now,
            }
            client.query(
                "UPSERT type::thing($table, $id) CONTENT $data RETURN NONE;",
                {"table": self.table, "id": key, "data": data},
            )

    def delete(self, key: str) -> None:
        client = self._ensure_client()
        client.query(
            "DELETE type::thing($table, $id);",
            {"table": self.table, "id": key},
        )

    def mget(self, keys: list[str], *, allow_stale: bool = False) -> dict[str, CacheEntry]:
        out: dict[str, CacheEntry] = {}
        for key in keys:
            entry = self.get(key, allow_stale=allow_stale)
            if entry is not None:
                out[key] = entry
        return out

    def invalidate_prefix(self, prefix: str) -> int:
        client = self._ensure_client()
        rows = client.query("SELECT * FROM type::table($table);", {"table": self.table})
        removed = 0
        for row in rows or []:
            cache_key = row.get("key")
            if isinstance(cache_key, str) and cache_key.startswith(prefix):
                self.delete(cache_key)
                removed += 1
        return removed


@dataclass(slots=True)
class CacheFacade:
    """Multi-tier cache facade (L1 memory + optional L2 store).

    Phase-1 implementation: L1-first with optional L2 read-through/write-through and
    feature flags for safe rollout.
    """

    l1: CacheStore = field(default_factory=MemoryCacheStore)
    l2: CacheStore | None = None
    cache_enabled: bool = False
    cache_l2_enabled: bool = False
    cache_swr_enabled: bool = False

    namespace_versions: dict[str, int] = field(default_factory=dict)
    _singleflight_lock: threading.Lock = field(default_factory=threading.Lock)
    _singleflight_events: dict[str, threading.Event] = field(default_factory=dict)
    l2_failure_count: int = 0

    def _version_token(self, namespace: str) -> str:
        return f"v{self.namespace_versions.get(namespace, 1)}"

    def bump_version(self, namespace: str) -> str:
        next_version = self.namespace_versions.get(namespace, 1) + 1
        self.namespace_versions[namespace] = next_version
        return f"v{next_version}"

    def build_key(
        self,
        namespace: str,
        *,
        tenant: str | None = None,
        params: dict[str, Any] | None = None,
        auth_scope: str | None = None,
        cacheability: str = "public",
    ) -> str:
        payload = {
            "tenant": tenant,
            "params": params or {},
            "auth_scope": auth_scope,
            "cacheability": cacheability,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{namespace}:{self._version_token(namespace)}:{digest}"

    def get(self, key: str, *, allow_stale: bool = False) -> Any | None:
        if not self.cache_enabled:
            return None

        allow_stale = allow_stale and self.cache_swr_enabled
        hit = self._get_entry(key, allow_stale=allow_stale)
        if hit is not None:
            return hit.value

        return None

    def _get_entry(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        l1_hit = self.l1.get(key, allow_stale=allow_stale)
        if l1_hit is not None:
            return l1_hit

        if self.cache_l2_enabled and self.l2 is not None:
            try:
                l2_hit = self.l2.get(key, allow_stale=allow_stale)
            except Exception:
                self.l2_failure_count += 1
                return None
            if l2_hit is not None:
                ttl_remaining = max(0.0, l2_hit.expires_at - time.time())
                stale_remaining = (
                    max(0.0, l2_hit.stale_until - time.time())
                    if l2_hit.stale_until is not None
                    else None
                )
                self.l1.set(
                    key,
                    l2_hit.value,
                    ttl=ttl_remaining,
                    stale_ttl=stale_remaining,
                    version_token=l2_hit.version_token,
                    meta=l2_hit.meta,
                )
                return l2_hit

        return None

    def _singleflight_try_lead(self, key: str) -> tuple[threading.Event, bool]:
        with self._singleflight_lock:
            event = self._singleflight_events.get(key)
            if event is not None:
                return event, False
            event = threading.Event()
            self._singleflight_events[key] = event
            return event, True

    def _singleflight_release(self, key: str, event: threading.Event) -> None:
        event.set()
        with self._singleflight_lock:
            current = self._singleflight_events.get(key)
            if current is event:
                self._singleflight_events.pop(key, None)

    def _refresh_once(
        self,
        key: str,
        loader: Callable[[], Any],
        *,
        ttl: float,
        stale_ttl: float | None,
        version_token: str | None,
        meta: dict[str, Any] | None,
    ) -> None:
        event, is_leader = self._singleflight_try_lead(key)
        if not is_leader:
            return

        def _run() -> None:
            try:
                value = loader()
                self.set(
                    key,
                    value,
                    ttl=ttl,
                    stale_ttl=stale_ttl,
                    version_token=version_token,
                    meta=meta,
                )
            finally:
                self._singleflight_release(key, event)

        threading.Thread(target=_run, daemon=True).start()

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: float,
        stale_ttl: float | None = None,
        version_token: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not self.cache_enabled:
            return

        self.l1.set(
            key,
            value,
            ttl=ttl,
            stale_ttl=stale_ttl,
            version_token=version_token,
            meta=meta,
        )

        if self.cache_l2_enabled and self.l2 is not None:
            try:
                self.l2.set(
                    key,
                    value,
                    ttl=ttl,
                    stale_ttl=stale_ttl,
                    version_token=version_token,
                    meta=meta,
                )
            except Exception:
                self.l2_failure_count += 1

    def delete(self, key: str) -> None:
        self.l1.delete(key)
        if self.cache_l2_enabled and self.l2 is not None:
            try:
                self.l2.delete(key)
            except Exception:
                self.l2_failure_count += 1

    def invalidate_prefix(self, prefix: str) -> int:
        removed = self.l1.invalidate_prefix(prefix)
        if self.cache_l2_enabled and self.l2 is not None:
            try:
                removed += self.l2.invalidate_prefix(prefix)
            except Exception:
                self.l2_failure_count += 1
        return removed

    def get_or_set(
        self,
        key: str,
        loader: Callable[[], Any],
        *,
        ttl: float,
        stale_ttl: float | None = None,
        version_token: str | None = None,
        meta: dict[str, Any] | None = None,
        singleflight_timeout: float = 5.0,
    ) -> Any:
        if not self.cache_enabled:
            return loader()

        now = time.time()
        cached_entry = self._get_entry(key, allow_stale=self.cache_swr_enabled)
        if cached_entry is not None:
            is_stale = now > cached_entry.expires_at
            if not is_stale:
                return cached_entry.value

            if self.cache_swr_enabled:
                self._refresh_once(
                    key,
                    loader,
                    ttl=ttl,
                    stale_ttl=stale_ttl,
                    version_token=version_token,
                    meta=meta,
                )
                return cached_entry.value

        event, is_leader = self._singleflight_try_lead(key)
        if is_leader:
            try:
                value = loader()
                self.set(
                    key,
                    value,
                    ttl=ttl,
                    stale_ttl=stale_ttl,
                    version_token=version_token,
                    meta=meta,
                )
                return value
            finally:
                self._singleflight_release(key, event)

        event.wait(timeout=max(0.0, singleflight_timeout))
        after_wait = self.get(key, allow_stale=self.cache_swr_enabled)
        if after_wait is not None:
            return after_wait

        # Fallback if leader failed/timed out.
        value = loader()
        self.set(
            key,
            value,
            ttl=ttl,
            stale_ttl=stale_ttl,
            version_token=version_token,
            meta=meta,
        )
        return value

    def handle_eda_event(self, topic: str, payload: dict[str, Any] | None = None) -> int | str | None:
        """Apply cache invalidation policy from EDA events.

        Supported topics:
        - ``entity.updated`` / ``entity.deleted``: invalidate prefix from payload
          (`cache_prefix` or `namespace`)
        - ``schema.bump``: bump namespace version token
        """
        data = payload or {}
        if topic in {"entity.updated", "entity.deleted"}:
            prefix = data.get("cache_prefix")
            if not prefix:
                namespace = data.get("namespace")
                if namespace:
                    prefix = f"{namespace}:"
            if isinstance(prefix, str) and prefix:
                return self.invalidate_prefix(prefix)
            return 0

        if topic == "schema.bump":
            namespace = data.get("namespace")
            if isinstance(namespace, str) and namespace:
                return self.bump_version(namespace)
            return None

        return None


def cache_from_env(*, l1: CacheStore | None = None) -> CacheFacade:
    """Build a CacheFacade from environment variables.

    Supports L1 memory and optional L2 Surreal cache.
    For remote Surreal URLs (ws/wss/http/https), credentials are required via
    ``GOBSTOPPER_CACHE_SURREAL_TOKEN`` or
    ``GOBSTOPPER_CACHE_SURREAL_USERNAME`` + ``GOBSTOPPER_CACHE_SURREAL_PASSWORD``.
    """

    cache_enabled = _env_bool("GOBSTOPPER_CACHE_ENABLED", False)
    cache_swr_enabled = _env_bool("GOBSTOPPER_CACHE_SWR_ENABLED", False)
    cache_l2_enabled = _env_bool("GOBSTOPPER_CACHE_L2_ENABLED", False)

    l1_store = l1 or MemoryCacheStore()
    l2_store: CacheStore | None = None

    backend = os.getenv("GOBSTOPPER_CACHE_L2_BACKEND", "surreal").strip().lower()
    if cache_l2_enabled and backend == "surreal":
        url = os.getenv("GOBSTOPPER_CACHE_SURREAL_URL", "surrealkv://.gobstopper/cache")
        namespace = os.getenv("GOBSTOPPER_CACHE_SURREAL_NAMESPACE", "gobstopper")
        database = os.getenv("GOBSTOPPER_CACHE_SURREAL_DATABASE", "cache")
        table = os.getenv("GOBSTOPPER_CACHE_SURREAL_TABLE", "cache_entries")
        username = os.getenv("GOBSTOPPER_CACHE_SURREAL_USERNAME")
        password = os.getenv("GOBSTOPPER_CACHE_SURREAL_PASSWORD")
        token = os.getenv("GOBSTOPPER_CACHE_SURREAL_TOKEN")

        remote = url.startswith(("ws://", "wss://", "http://", "https://"))
        if remote and not token and not (username and password):
            raise ValueError(
                "Remote Surreal cache requires credentials: set "
                "GOBSTOPPER_CACHE_SURREAL_TOKEN or "
                "GOBSTOPPER_CACHE_SURREAL_USERNAME and GOBSTOPPER_CACHE_SURREAL_PASSWORD"
            )

        l2_store = SurrealCacheStore(
            url=url,
            namespace=namespace,
            database=database,
            table=table,
            username=username,
            password=password,
            token=token,
            auto_connect=False,
        )

    return CacheFacade(
        l1=l1_store,
        l2=l2_store,
        cache_enabled=cache_enabled,
        cache_l2_enabled=cache_l2_enabled,
        cache_swr_enabled=cache_swr_enabled,
    )
