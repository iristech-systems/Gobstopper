"""
Request limits middleware for Gobstopper framework.

This module provides protection against resource exhaustion by enforcing limits on
request body size and request processing time. These limits are essential for
production deployments to prevent denial-of-service attacks and resource exhaustion.
"""
from __future__ import annotations

import asyncio
from ..http.problem import problem


class LimitsMiddleware:
    """Middleware for enforcing request body size and timeout limits.

    This middleware protects your application from resource exhaustion by limiting
    both the size of request bodies and the time allowed for request processing.
    These limits help prevent:
    - Memory exhaustion from large uploads
    - Slowloris attacks and slow clients
    - Resource starvation from long-running requests
    - Denial-of-service attacks

    The middleware sets request.max_body_bytes which is enforced by Request.get_data(),
    Request.get_json(), and Request.get_form(). If a request exceeds the body size
    limit, a 413 Payload Too Large response is returned.

    For timeout enforcement, the middleware wraps the handler chain with asyncio.wait_for().
    If processing exceeds the timeout, a 504 Gateway Timeout response is returned.

    Args:
        max_body_bytes: Maximum request body size in bytes.
            Default is 2,000,000 (2MB). Can be overridden by MAX_BODY_BYTES env var.
            Set to 0 for unlimited (not recommended for production).
        timeout_s: Maximum request processing time in seconds.
            Default is 15.0 seconds. Includes all middleware and handler execution.

    Examples:
        Basic usage with defaults::

            from gobstopper.middleware import LimitsMiddleware

            # 2MB body limit, 15 second timeout
            limits = LimitsMiddleware()
            app.add_middleware(limits)

        Custom limits for file upload endpoint::

            # Allow larger uploads, longer timeout
            limits = LimitsMiddleware(
                max_body_bytes=50_000_000,  # 50MB
                timeout_s=60.0  # 1 minute
            )
            app.add_middleware(limits)

        Strict limits for public API::

            # Smaller bodies, faster timeout
            limits = LimitsMiddleware(
                max_body_bytes=100_000,  # 100KB
                timeout_s=5.0  # 5 seconds
            )
            app.add_middleware(limits)

        Environment-based configuration::

            import os

            limits = LimitsMiddleware(
                max_body_bytes=int(os.getenv('MAX_BODY_BYTES', '2000000')),
                timeout_s=float(os.getenv('REQUEST_TIMEOUT', '15.0'))
            )
            app.add_middleware(limits)

    Note:
        - Body size limit is enforced when reading request body (get_data, get_json, get_form)
        - Timeout includes all middleware execution time
        - MAX_BODY_BYTES environment variable overrides max_body_bytes parameter
        - Timeouts use asyncio.TimeoutError which is caught and converted to 504
        - For different limits per route, apply multiple instances with route conditions

    Response Codes:
        - 413 Payload Too Large: Request body exceeds max_body_bytes
        - 504 Gateway Timeout: Request processing exceeds timeout_s

    Security Considerations:
        - Always set limits in production to prevent resource exhaustion
        - Consider lower limits for public endpoints
        - Higher limits may be needed for file upload endpoints
        - Monitor timeout rates to detect attacks or slow dependencies
        - Combine with rate limiting for comprehensive protection

    Performance Impact:
        - Minimal overhead (asyncio.wait_for wrapper)
        - No body size overhead until body is actually read
        - Timeout enforcement adds <1ms per request

    See Also:
        - Request.get_data(): Enforces max_body_bytes limit
        - SecurityMiddleware: Additional security features
        - RateLimiter: Request rate limiting
    """

    def __init__(self, max_body_bytes: int = 2_000_000, timeout_s: float = 15.0):
        # Allow env override while keeping explicit args highest priority
        try:
            import os
            env_val = os.getenv("MAX_BODY_BYTES")
            effective_max = int(env_val) if env_val is not None else max_body_bytes
        except Exception:
            effective_max = max_body_bytes
        self.max_body_bytes = int(effective_max)
        self.timeout_s = float(timeout_s)

    async def __call__(self, request, next_handler):
        """Process request with size and timeout limits enforced.

        Sets the body size limit on the request object and wraps handler execution
        with a timeout. Returns appropriate error responses if limits are exceeded.

        Args:
            request: The incoming HTTP request.
            next_handler: The next middleware or handler in the chain.

        Returns:
            Response from the handler, or error response:
            - 413 Payload Too Large: If body size exceeds limit (from Request methods)
            - 504 Gateway Timeout: If processing exceeds timeout

        Note:
            - Sets request.max_body_bytes for enforcement by Request methods
            - Uses asyncio.wait_for for timeout enforcement
            - Timeout includes all middleware and handler execution
            - Body size is only checked when body is actually read
        """
        # Expose limit to Request instance
        setattr(request, 'max_body_bytes', self.max_body_bytes)
        try:
            return await asyncio.wait_for(next_handler(request), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            return problem("Request timed out", 504)
