"""
Simple in-memory token-bucket rate limiter and middleware helpers.

Usage example:
    from gobstopper.utils.rate_limiter import TokenBucketLimiter, rate_limit

    limiter = TokenBucketLimiter(rate=5, capacity=10)  # 5 tokens/sec, burst 10

    @app.get('/limited')
    @rate_limit(limiter, key=lambda req: req.client_ip)
    async def limited(request):
        return {'ok': True}
"""
from __future__ import annotations

import time
from typing import Callable, Any, Optional

from ..http.problem import problem


class TokenBucketLimiter:
    def __init__(self, rate: float, capacity: int):
        """
        rate: tokens added per second
        capacity: maximum number of tokens (burst)
        """
        self.rate = float(rate)
        self.capacity = int(capacity)
        self._buckets: dict[str, tuple[float, float]] = {}
        # maps key -> (tokens, last_ts)

    def _now(self) -> float:
        return time.monotonic()

    def _refill(self, tokens: float, last: float) -> tuple[float, float]:
        now = self._now()
        elapsed = max(0.0, now - last)
        tokens = min(self.capacity, tokens + elapsed * self.rate)
        return tokens, now

    def allow(self, key: str, cost: float = 1.0) -> bool:
        tokens, last = self._buckets.get(key, (self.capacity, self._now()))
        tokens, now = self._refill(tokens, last)
        if tokens >= cost:
            tokens -= cost
            self._buckets[key] = (tokens, now)
            return True
        else:
            self._buckets[key] = (tokens, now)
            return False


_PERIOD_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


def _parse_rate_limit(spec: str) -> TokenBucketLimiter:
    """Parse a ``"N/period"`` string into a :class:`TokenBucketLimiter`.

    Period may be ``second``, ``minute``, or ``hour``::

        _parse_rate_limit("20/minute")   # 20 rq/min, burst 20
        _parse_rate_limit("1/second")    # 1 rq/sec, burst 1
        _parse_rate_limit("500/hour")    # ~0.139 rq/sec, burst 500
    """
    try:
        n_str, period = spec.split("/", 1)
        n = int(n_str.strip())
        seconds = _PERIOD_SECONDS[period.strip().lower()]
    except (ValueError, KeyError):
        raise ValueError(
            f"Invalid rate limit spec {spec!r}. "
            "Expected 'N/period' where period is second, minute, or hour."
        )
    return TokenBucketLimiter(rate=n / seconds, capacity=n)


def rate_limit(limiter: TokenBucketLimiter, key: Optional[Callable[[Any], str]] = None, cost: float = 1.0):
    """
    Middleware decorator factory to enforce rate limits.

    Example:
        limiter = TokenBucketLimiter(rate=5, capacity=10)

        @app.get('/api/x')
        @rate_limit(limiter, key=lambda req: req.client_ip)
        async def handler(request):
            return {'ok': True}
    """
    def decorator(handler):
        async def wrapper(request, *args, **kwargs):
            k = key(request) if key else request.client_ip
            if not limiter.allow(k, cost=cost):
                return problem("Too Many Requests", 429, retry_after="1")
            return await handler(request, *args, **kwargs)
        return wrapper
    return decorator
