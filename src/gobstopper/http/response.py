"""HTTP Response handling for Gobstopper framework.

This module provides response classes and utilities for handling HTTP responses
in the Gobstopper web framework. It includes support for standard responses, JSON
serialization, file serving, and streaming responses with full RSGI protocol
integration.

Classes:
    Response: Standard HTTP response with flexible content types and headers
    JSONResponse: JSON response with high-performance msgspec serialization
    FileResponse: File serving response with automatic MIME type detection
    StreamResponse: Streaming response for server-sent events and large content

Key Features:
    - Automatic content type detection
    - Secure cookie management with production enforcement
    - RSGI protocol compatibility
    - High-performance JSON serialization via msgspec
    - File serving with MIME type detection
    - Streaming support for progressive content delivery
    - Comprehensive header and cookie management

Example:
    Basic response types:

    >>> # Standard text/HTML response
    >>> return Response("Hello World")

    >>> # JSON API response
    >>> return JSONResponse({"status": "success", "data": results})

    >>> # File download
    >>> return FileResponse("reports/data.pdf", filename="report.pdf")

    >>> # Streaming response
    >>> async def event_stream():
    ...     for i in range(100):
    ...         yield f"data: Event {i}\\n\\n"
    >>> return StreamResponse(event_stream(), content_type="text/event-stream")

See Also:
    :mod:`gobstopper.http.helpers`: Helper functions (jsonify, send_file, stream_template)
    :mod:`gobstopper.http.sse`: Server-sent events support (SSEStream, format_sse)
    :class:`gobstopper.core.app.Gobstopper`: Main application class with RSGI protocol handling
"""

import msgspec
import mimetypes
import os
from pathlib import Path
from typing import Any, Awaitable, Callable
from ..log import log


class Response:
    """HTTP response with flexible content types and headers.
    
    Represents an HTTP response with configurable status code, headers,
    and body content. Supports automatic content type detection and
    header management for RSGI protocol compatibility.
    
    Args:
        body: Response content as string or bytes
        status: HTTP status code (default: 200)
        headers: HTTP headers as dict (optional)
        content_type: MIME type override (auto-detected if not provided)
        
    Attributes:
        body: Response body content
        status: HTTP status code
        headers: Response headers dict
        
    Examples:
        Text response:
        
        >>> return Response("Hello World")
        >>> return Response("Error message", status=400)
        
        HTML response:
        
        >>> html = "<h1>Welcome</h1>"
        >>> return Response(html, content_type="text/html")
        
        Custom headers:
        
        >>> return Response("OK", headers={"X-Custom": "value"})
        
        Binary content:
        
        >>> return Response(image_bytes, content_type="image/png")
        
    Note:
        Content-Type is auto-detected: string content defaults to text/html,
        bytes content defaults to application/octet-stream.
    """
    
    def __init__(self,
                 body: str | bytes = "",
                 status: int = 200,
                 headers: dict[str, str] | None = None,
                 content_type: str | None = None):
        self.body = body
        self.status = status
        self.headers = headers or {}
        self._cookies: list[str] = []
        
        if content_type:
            self.headers['content-type'] = content_type
        elif 'content-type' not in self.headers:
            if isinstance(body, str):
                self.headers['content-type'] = 'text/html; charset=utf-8'
            else:
                self.headers['content-type'] = 'application/octet-stream'

    def set_cookie(self, name: str, value: str, *, path: str = "/", domain: str | None = None,
                   max_age: int | None = None, expires: str | None = None,
                   secure: bool = True, httponly: bool = True, samesite: str | None = "Strict"):
        """Set a cookie with comprehensive security options.

        Adds a Set-Cookie header to the response with secure defaults appropriate
        for production environments. In production (ENV=production), enforces
        secure cookie settings unless explicitly disabled via environment variable.

        Args:
            name: Cookie name
            value: Cookie value
            path: Cookie path scope (default: "/")
            domain: Cookie domain scope (optional, defaults to current domain)
            max_age: Cookie lifetime in seconds (optional, None means session cookie)
            expires: Cookie expiration date in HTTP format (optional, overridden by max_age)
            secure: Require HTTPS transmission (default: True, enforced in production)
            httponly: Prevent JavaScript access (default: True, enforced in production)
            samesite: CSRF protection level - "Strict", "Lax", or "None" (default: "Strict",
                     enforced to at least "Lax" in production)

        Examples:
            Basic session cookie:

            >>> response = Response("Welcome")
            >>> response.set_cookie("session_id", "abc123")

            Persistent cookie with expiration:

            >>> response.set_cookie("user_pref", "dark_mode",
            ...                    max_age=86400*30)  # 30 days

            Subdomain cookie:

            >>> response.set_cookie("auth_token", token,
            ...                    domain=".example.com",
            ...                    secure=True,
            ...                    httponly=True)

            Development-only insecure cookie:

            >>> # Set ENV=development and WOPR_ALLOW_INSECURE_COOKIES=true
            >>> response.set_cookie("debug", "1", secure=False)

        Note:
            Production security enforcement (when ENV=production):
            - secure=False is overridden to True with warning
            - httponly=False is overridden to True with warning
            - samesite=None is overridden to "Lax" with warning

            Set WOPR_ALLOW_INSECURE_COOKIES=true to disable enforcement.

        See Also:
            :meth:`delete_cookie`: Remove a cookie
        """
        # Enforce secure defaults in production unless explicitly overridden via env flag
        try:
            env = os.getenv("ENV", "development").lower()
            allow_insecure = os.getenv("WOPR_ALLOW_INSECURE_COOKIES", "false").lower() == "true"
            if env == "production" and not allow_insecure:
                if not secure:
                    log.warning("Overriding insecure cookie: Secure=False in production; forcing Secure=True")
                    secure = True
                if not httponly:
                    log.warning("Overriding insecure cookie: HttpOnly=False in production; forcing HttpOnly=True")
                    httponly = True
                if samesite is None:
                    log.warning("Overriding insecure cookie: SameSite not set in production; forcing SameSite=Lax")
                    samesite = "Lax"
        except Exception:
            pass
        parts = [f"{name}={value}", f"Path={path}"]
        if domain: parts.append(f"Domain={domain}")
        if max_age is not None: parts.append(f"Max-Age={max_age}")
        if expires: parts.append(f"Expires={expires}")
        if secure: parts.append("Secure")
        if httponly: parts.append("HttpOnly")
        if samesite: parts.append(f"SameSite={samesite}")
        self._cookies.append("; ".join(parts))

    def delete_cookie(self, name: str, *, path: str = "/", domain: str | None = None):
        """Delete a cookie by setting it to expire immediately.

        Removes a cookie from the client by setting an expired Set-Cookie header.
        The path and domain must match the original cookie for proper deletion.

        Args:
            name: Cookie name to delete
            path: Cookie path scope (must match original, default: "/")
            domain: Cookie domain scope (must match original, optional)

        Examples:
            Delete a session cookie:

            >>> response = Response("Logged out")
            >>> response.delete_cookie("session_id")

            Delete a subdomain cookie:

            >>> response.delete_cookie("auth_token", domain=".example.com")

            Delete a path-specific cookie:

            >>> response.delete_cookie("cart_id", path="/shop")

        Note:
            To successfully delete a cookie, path and domain must match
            the values used when the cookie was originally set.

        See Also:
            :meth:`set_cookie`: Set a cookie
        """
        self.set_cookie(name, "", path=path, domain=domain, max_age=0)

    def to_rsgi_headers(self) -> list[tuple[str, str]]:
        """Convert response headers to RSGI protocol format.

        Transforms the headers dictionary and cookie list into the list of tuples
        format required by the RSGI (Rust Server Gateway Interface) protocol.

        Returns:
            List of (name, value) tuples for RSGI response headers. Each cookie
            generates a separate ("set-cookie", cookie_string) tuple.

        Examples:
            >>> response = Response("OK", headers={"X-Custom": "value"})
            >>> response.set_cookie("session", "abc123")
            >>> response.to_rsgi_headers()
            [('content-type', 'text/html; charset=utf-8'),
             ('X-Custom', 'value'),
             ('set-cookie', 'session=abc123; Path=/; Secure; HttpOnly; SameSite=Strict')]

        Note:
            This method is called internally by the Gobstopper framework when
            sending responses through the RSGI protocol. You typically
            don't need to call it directly.

            Multiple Set-Cookie headers are properly handled as separate
            tuples, as required by HTTP specifications and RSGI protocol.

        See Also:
            :class:`Gobstopper`: Main application class handling RSGI protocol
        """
        items = [(k, v) for k, v in self.headers.items()]
        for c in self._cookies:
            items.append(("set-cookie", c))
        return items


class JSONResponse(Response):
    """HTTP response for JSON data with automatic, high-performance serialization.
    
    Convenience class for returning JSON responses with proper Content-Type
    headers and optimized JSON serialization using `msgspec`.
    
    Args:
        data: Python object to serialize as JSON (dict, list, primitives)
        status: HTTP status code (default: 200)
        **kwargs: Additional arguments passed to parent Response class
        
    Examples:
        Dictionary response:
        
        >>> return JSONResponse({"message": "Success", "data": results})
        
        List response:
        
        >>> return JSONResponse([1, 2, 3, 4, 5])
        
        With custom status:
        
        >>> return JSONResponse({"error": "Not found"}, status=404)
        
    Note:
        Uses high-performance `msgspec` for serialization.
        Automatically sets Content-Type to 'application/json'.
        
    See Also:
        :class:`Response`: Base response class
    """
    
    def __init__(self, data: Any, status: int = 200, **kwargs):
        body = msgspec.json.encode(data)
        super().__init__(body, status, content_type='application/json', **kwargs)


class FileResponse(Response):
    """HTTP response for serving files with proper headers and MIME detection.
    
    Optimized response class for serving static files, downloads, and attachments.
    Automatically detects MIME types, sets appropriate headers, and handles
    file serving through the RSGI protocol.
    
    Args:
        path: File path as string or Path object
        filename: Download filename (defaults to basename of path)
        status: HTTP status code (default: 200)  
        headers: Additional headers (optional)
        
    Attributes:
        file_path: Resolved file path as string
        filename: Filename for Content-Disposition header
        
    Examples:
        Serve static file:
        
        >>> @app.get("/download/<filename>")
        >>> async def download(request, filename):
        ...     return FileResponse(f"uploads/{filename}")
        
        Force download with custom name:
        
        >>> return FileResponse("report.pdf", filename="monthly_report.pdf")
        
        Image serving:
        
        >>> @app.get("/images/<image_id>")
        >>> async def serve_image(request, image_id):
        ...     path = f"images/{image_id}.jpg"
        ...     return FileResponse(path)
        
    Note:
        Automatically sets Content-Type based on file extension.
        Sets Content-Disposition: attachment for download behavior.
        File path resolution and existence checking is handled by RSGI protocol.
        
    See Also:
        :class:`Response`: Base response class
        :class:`StreamResponse`: For streaming large files
    """
    
    def __init__(self, path: str | Path,
                 filename: str | None = None,
                 status: int = 200,
                 headers: dict[str, str] | None = None):
        self.file_path = str(path)
        self.filename = filename or os.path.basename(self.file_path)
        
        content_type, _ = mimetypes.guess_type(self.file_path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        headers = headers or {}
        headers['content-type'] = content_type
        headers['content-disposition'] = f'attachment; filename="{self.filename}"'
        
        super().__init__("", status, headers)


class StreamResponse:
    """HTTP streaming response for real-time data and large content.
    
    Enables streaming HTTP responses for server-sent events, chunked transfer
    encoding, and progressive content delivery. Ideal for large datasets,
    real-time updates, and template streaming.
    
    Args:
        generator: Async generator function that yields string or bytes chunks
        status: HTTP status code (default: 200)
        headers: Additional headers (optional)
        content_type: MIME type (default: 'text/plain')
        
    Attributes:
        generator: Async generator for content chunks
        status: HTTP status code
        headers: Response headers dict
        
    Examples:
        Server-sent events:
        
        >>> @app.get("/events")
        >>> async def stream_events(request):
        ...     async def event_generator():
        ...         for i in range(100):
        ...             yield f"data: Event {i}\\n\\n"
        ...             await asyncio.sleep(1)
        ...     return StreamResponse(event_generator(), 
        ...                         content_type="text/event-stream")
        
        Large data streaming:
        
        >>> @app.get("/large-csv")
        >>> async def stream_csv(request):
        ...     async def csv_generator():
        ...         yield "id,name,email\\n"
        ...         async for user in get_all_users_stream():
        ...             yield f"{user.id},{user.name},{user.email}\\n"
        ...     return StreamResponse(csv_generator(), 
        ...                         content_type="text/csv")
        
        Template streaming (with Rust engine):
        
        >>> async def stream_template():
        ...     return await app.render_template("large_page.html", 
        ...                                     stream=True, 
        ...                                     data=huge_dataset)
        
    Note:
        Generator function must be async and yield string or bytes.
        Streaming reduces memory usage for large responses.
        Compatible with template streaming when using Rust engine.
        
    See Also:
        :class:`Response`: Standard response class
        :meth:`Gobstopper.render_template`: Template rendering with streaming
    """
    
    def __init__(self,
                 generator: Callable[[], Awaitable],
                 status: int = 200,
                 headers: dict[str, str] | None = None,
                 content_type: str = 'text/plain'):
        self.generator = generator
        self.status = status
        self.headers = headers or {}
        self.headers['content-type'] = content_type


def redirect(location: str, status: int = 302) -> Response:
    """Create a redirect response to the given location.

    Flask/Quart-style redirect helper that creates an HTTP redirect response.
    Commonly used with ``url_for()`` for type-safe redirects to named routes.

    Args:
        location: URL to redirect to. Can be absolute (/path) or relative (path)
            or full URL (https://example.com/path)
        status: HTTP redirect status code. Common values:
            - 301: Moved Permanently (cached by browsers)
            - 302: Found (temporary, default)
            - 303: See Other (POST → GET redirect)
            - 307: Temporary Redirect (preserves method)
            - 308: Permanent Redirect (preserves method)

    Returns:
        Response object with Location header and appropriate status code

    Examples:
        Simple redirect:

        >>> return redirect('/dashboard')

        Redirect to named route:

        >>> return redirect(app.url_for('user_profile', user_id=123))

        Permanent redirect:

        >>> return redirect('/new-location', status=301)

        Post-redirect-get pattern:

        >>> @app.post('/users')
        >>> async def create_user(request):
        ...     user_id = save_user()
        ...     return redirect(app.url_for('user_detail', id=user_id), status=303)

        External redirect:

        >>> return redirect('https://example.com/login')

    Note:
        - Default 302 is safe for most use cases
        - Use 301 carefully as browsers cache it permanently
        - Use 303 for POST → GET redirects (RESTful pattern)
        - Use 307/308 if you need to preserve the HTTP method

    See Also:
        :meth:`Gobstopper.url_for`: Build URLs for named routes
        :class:`Response`: Base response class
    """
    return Response('', status=status, headers={'Location': location})