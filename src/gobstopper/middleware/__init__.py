"""
Middleware components for Gobstopper framework.

This module provides production-ready middleware for common web application concerns:

- **CORSMiddleware**: Cross-Origin Resource Sharing support with configurable origins
- **SecurityMiddleware**: CSRF protection, secure sessions, and security headers
- **StaticFileMiddleware**: Secure static file serving (Pure Python)
- **RustStaticMiddleware**: High-performance static serving (Rust-accelerated)
- **LimitsMiddleware**: Request body size and timeout limits

All middleware follow the Gobstopper middleware pattern with async call methods.

Example:
    Basic middleware setup::

        from gobstopper import Wopr
        from gobstopper.middleware import (
            CORSMiddleware,
            SecurityMiddleware,
            StaticFileMiddleware,
            LimitsMiddleware
        )

        app = Wopr()

        # Add middleware in order (executed bottom to top)
        app.add_middleware(LimitsMiddleware(max_body_bytes=2_000_000, timeout_s=15.0))
        app.add_middleware(StaticFileMiddleware('static', '/static'))
        app.add_middleware(CORSMiddleware(origins=['https://example.com']))
        app.add_middleware(SecurityMiddleware(
            secret_key='your-secret-key',
            enable_csrf=True,
            enable_security_headers=True
        ))

Note:
    Middleware is executed in reverse order of registration. The last middleware
    added is the first to process each request.
"""

from .static import StaticFileMiddleware
from .cors import CORSMiddleware
from .security import SecurityMiddleware
from .limits import LimitsMiddleware

__all__ = [
    "StaticFileMiddleware",
    "CORSMiddleware", 
    "SecurityMiddleware",
    "LimitsMiddleware",
]