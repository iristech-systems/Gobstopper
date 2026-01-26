"""
Idempotency helper for POST endpoints.

Provides a simple in-memory TTL store to deduplicate requests based on
an Idempotency-Key header or provided key argument. Suitable for a single
process. For multi-process deployments, use a shared cache (Redis, etc.).
"""
from __future__ import annotations

import time
import threading
from typing import Any, Callable, Optional, Tuple


class _TTLCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, Tuple[float, Any]] = {}

    def set(self, key: str, value: Any, ttl_seconds: float):
        expire_at = time.time() + ttl_seconds
        with self._lock:
            self._data[key] = (expire_at, value)

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expire_at, value = item
            if expire_at < now:
                # expired; remove
                self._data.pop(key, None)
                return None
            return value

    def exists(self, key: str) -> bool:
        return self.get(key) is not None


_memory_cache = _TTLCache()


def use_idempotency(ttl_seconds: float = 60.0):
    """Decorator to enforce idempotency for handlers.

    Reads key from request headers (Idempotency-Key) or request.args["idempotency_key"].
    Caches the result for ttl_seconds and returns cached response for repeated keys.

    Note: Returns the exact previous handler return value. If the handler returns
    a Response, it will be reused as-is; for dict/list the JSONResponse wrapping
    will happen as usual in the app pipeline.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(request, *args, **kwargs):
            key = request.headers.get('idempotency-key')
            if not key:
                # try query args
                try:
                    key = (request.args.get('idempotency_key') or [''])[0]
                except Exception:
                    key = None
            if not key:
                return await func(request, *args, **kwargs)
            cached = _memory_cache.get(key)
            if cached is not None:
                return cached
            result = await func(request, *args, **kwargs)
            _memory_cache.set(key, result, ttl_seconds)
            return result
        return wrapper
    return decorator


def remember_idempotency(key: str, value: Any, ttl_seconds: float = 60.0):
    """Manually store a result for an idempotency key with TTL."""
    _memory_cache.set(key, value, ttl_seconds)


def get_idempotent(key: str) -> Optional[Any]:
    """Get a cached result for a given idempotency key if present and not expired."""
    return _memory_cache.get(key)
