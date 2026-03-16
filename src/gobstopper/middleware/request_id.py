"""
Request ID middleware — threads X-Request-ID through the request lifecycle.

Echoes an incoming ``X-Request-ID`` header when present; generates a random
UUID4 otherwise. The ID is attached to ``request.request_id`` so route
handlers and other middleware can reference it (e.g. for structured logging or
error correlation).
"""

import uuid


class RequestIDMiddleware:
    """Middleware that assigns every request a unique ``X-Request-ID``.

    Priority recommendation: 100 (outermost) so the ID is available in all
    downstream middleware, route handlers, and error pages.

    Example::

        app.add_middleware(RequestIDMiddleware(), priority=100)
    """

    HEADER = "x-request-id"

    async def __call__(self, request, next_handler):
        req_id = request.headers.get(self.HEADER) or str(uuid.uuid4())
        request.request_id = req_id
        response = await next_handler(request)
        if hasattr(response, "headers"):
            response.headers[self.HEADER] = req_id
        return response
