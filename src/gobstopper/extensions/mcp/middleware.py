"""
MCP Middleware for cross-cutting concerns.

Middleware can intercept and transform MCP requests and responses,
enable logging, caching, rate limiting, and more.
"""

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class MiddlewareContext:
    """Context passed to middleware handlers."""

    method: str
    params: Dict[str, Any]
    source: str = "client"  # "client", "server", "internal"

    @property
    def tool_name(self) -> Optional[str]:
        """Get tool name if this is a tool call."""
        if self.method == "tools/call":
            return self.params.get("name")
        return None

    @property
    def resource_uri(self) -> Optional[str]:
        """Get resource URI if this is a resource read."""
        if self.method == "resources/read":
            return self.params.get("uri")
        return None


MiddlewareHandler = Callable[[MiddlewareContext, Callable], Any]


class MCPRequestLogger:
    """
    Middleware for logging MCP requests.

    Logs all incoming requests with timing information.
    """

    def __init__(self, logger=None, log_level: str = "info"):
        self.logger = logger
        self.log_level = log_level

    async def __call__(self, context: MiddlewareContext, next_handler: Callable) -> Any:
        """Log request and time its execution."""
        start = time.time()

        if self.logger:
            getattr(self.logger, self.log_level)(
                f"MCP {context.method} - {context.params}"
            )

        try:
            result = await next_handler()
            duration = time.time() - start

            if self.logger:
                self.logger.info(f"MCP {context.method} completed in {duration:.3f}s")

            return result
        except Exception as e:
            duration = time.time() - start

            if self.logger:
                self.logger.error(
                    f"MCP {context.method} failed after {duration:.3f}s: {e}"
                )

            raise


class MCPRateLimiter:
    """
    Middleware for rate limiting MCP tool calls.

    Uses a simple token bucket algorithm per tool.
    """

    def __init__(
        self,
        calls_per_minute: int = 60,
        calls_per_hour: int = 1000,
    ):
        self.calls_per_minute = calls_per_minute
        self.calls_per_hour = calls_per_hour

        self._minute_buckets: Dict[str, List[float]] = {}
        self._hour_buckets: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def __call__(self, context: MiddlewareContext, next_handler: Callable) -> Any:
        """Check rate limits before allowing request."""
        if context.method != "tools/call":
            return await next_handler()

        tool_name = context.tool_name
        now = time.time()

        async with self._lock:
            # Check minute limit
            minute_bucket = self._minute_buckets.setdefault(tool_name, [])
            minute_bucket = [t for t in minute_bucket if now - t < 60]
            self._minute_buckets[tool_name] = minute_bucket

            if len(minute_bucket) >= self.calls_per_minute:
                raise ValueError(
                    f"Rate limit exceeded for tool '{tool_name}' (60 calls/minute)"
                )

            # Check hour limit
            hour_bucket = self._hour_buckets.setdefault(tool_name, [])
            hour_bucket = [t for t in hour_bucket if now - t < 3600]
            self._hour_buckets[tool_name] = hour_bucket

            if len(hour_bucket) >= self.calls_per_hour:
                raise ValueError(
                    f"Rate limit exceeded for tool '{tool_name}' (1000 calls/hour)"
                )

            # Record this call
            minute_bucket.append(now)
            hour_bucket.append(now)

        return await next_handler()


class MCPCache:
    """
    Middleware for caching MCP responses.

    Caches tool call and resource read responses.
    """

    def __init__(self, ttl: int = 300):
        """
        Initialize cache.

        Args:
            ttl: Time-to-live in seconds (default 5 minutes)
        """
        self.ttl = ttl
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, context: MiddlewareContext) -> str:
        """Generate cache key from context."""
        if context.method == "tools/call":
            name = context.params.get("name", "")
            args = context.params.get("arguments", {})
            return f"tool:{name}:{hash(frozenset(args.items()))}"
        elif context.method == "resources/read":
            uri = context.params.get("uri", "")
            return f"resource:{uri}"
        return f"{context.method}:{hash(frozenset(context.params.items()))}"

    async def __call__(self, context: MiddlewareContext, next_handler: Callable) -> Any:
        """Check cache and use cached result if available."""
        # Only cache reads
        if context.method not in ("tools/call", "resources/read"):
            return await next_handler()

        key = self._make_key(context)
        now = time.time()

        async with self._lock:
            if key in self._cache:
                result, expires = self._cache[key]
                if now < expires:
                    return result
                del self._cache[key]

        result = await next_handler()

        async with self._lock:
            self._cache[key] = (result, now + self.ttl)

        return result


class MCPErrorHandler:
    """
    Middleware for handling MCP errors consistently.

    Converts exceptions to proper MCP error responses.
    """

    def __init__(self, mask_details: bool = True):
        self.mask_details = mask_details

    async def __call__(self, context: MiddlewareContext, next_handler: Callable) -> Any:
        """Handle errors from request processing."""
        try:
            return await next_handler()
        except ValueError as e:
            if self.mask_details:
                return {
                    "error": {"code": -32603, "message": "Internal error"},
                    "isError": True,
                }
            return {
                "error": {"code": -32603, "message": str(e)},
                "isError": True,
            }
        except Exception as e:
            return {
                "error": {"code": -32603, "message": str(e)},
                "isError": True,
            }


class MiddlewareChain:
    """
    Manages a chain of middleware for MCP requests.
    """

    def __init__(self, middlewares: Optional[List[MiddlewareHandler]] = None):
        self._middlewares: List[MiddlewareHandler] = middlewares or []

    def add(self, middleware: MiddlewareHandler) -> "MiddlewareChain":
        """Add a middleware to the chain."""
        self._middlewares.append(middleware)
        return self

    async def execute(self, context: MiddlewareContext, handler: Callable) -> Any:
        """Execute the middleware chain."""

        async def next():
            return await handler()

        # Build chain in reverse (last middleware wraps first)
        call_next = next
        for mw in reversed(self._middlewares):
            current_mw = mw
            call_next = lambda n=current_mw, c=call_next: n(context, c)

        return await call_next()
