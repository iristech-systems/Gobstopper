"""
Static file middleware for Gobstopper framework.

This module provides secure static file serving with automatic MIME type detection,
caching headers, and directory traversal protection. This is the pure Python
implementation, suitable for development and production use.
"""

import mimetypes
import os
from pathlib import Path
from typing import Callable, Awaitable, Any

from ..http.request import Request
from ..http.response import Response


class StaticFileMiddleware:
    """Middleware for serving static files securely.

    This middleware serves static files from a designated directory with built-in
    security features to prevent directory traversal attacks. It automatically
    detects MIME types and adds appropriate caching headers.

    Security Features:
        - Directory traversal protection (prevents '..' attacks)
        - Path validation to ensure files are within static directory
        - Automatic MIME type detection
        - 403 Forbidden for invalid paths
        - 404 Not Found for missing files

    Performance Features:
        - Cache-Control headers (1 hour default)
        - Content-Type auto-detection
        - Content-Length headers
        - Efficient file reading

    Args:
        static_dir: Directory containing static files. Can be relative or absolute.
            Default is 'static'. The directory must exist.
        url_prefix: URL prefix for static routes. Must start with '/'.
            Default is '/static'. Requests to this prefix will serve static files.

    Examples:
        Basic static file serving::

            from gobstopper.middleware import StaticFileMiddleware

            # Serve files from './static' at '/static' URLs
            static = StaticFileMiddleware()
            app.add_middleware(static)

        Custom directory and prefix::

            static = StaticFileMiddleware(
                static_dir='public',
                url_prefix='/assets'
            )
            app.add_middleware(static)

        Multiple static directories::

            # Serve from different directories with different prefixes
            app.add_middleware(StaticFileMiddleware('css', '/css'))
            app.add_middleware(StaticFileMiddleware('js', '/js'))
            app.add_middleware(StaticFileMiddleware('images', '/images'))

    Note:
        - For production with high traffic, consider using RustStaticMiddleware
        - The middleware automatically adds 'public, max-age=3600' cache headers
        - MIME types are detected using Python's mimetypes module
        - Unknown file types default to 'application/octet-stream'

    Security Considerations:
        - Never serve files from user-controlled directories
        - Be careful with symlinks (they can escape the static directory)
        - Consider using Content-Security-Policy headers
        - Validate file extensions if serving user-uploaded content

    See Also:
        - RustStaticMiddleware: High-performance Rust-based static serving
        - HybridStaticMiddleware: Combines Rust and Python for optimal performance
    """

    def __init__(self, static_dir: str = "static", url_prefix: str = "/static"):
        self.static_dir = Path(static_dir)
        self.url_prefix = url_prefix.rstrip('/')
    
    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Response:
        """Process request and serve static files if needed.

        Checks if the request path matches the static URL prefix. If so, serves
        the corresponding file; otherwise, passes the request to the next handler.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or handler in the chain.

        Returns:
            Response containing the file contents if path matches static prefix,
            otherwise the result from call_next().

        Note:
            - Only processes requests matching the configured url_prefix
            - Other requests are passed through unchanged
        """
        if request.path.startswith(self.url_prefix):
            return await self._serve_static_file(request)
        
        return await call_next(request)
    
    async def _serve_static_file(self, request: Request) -> Response:
        """Serve a static file with security checks.

        Validates the requested path, checks if the file exists, and serves it
        with appropriate headers. Includes multiple security checks to prevent
        directory traversal attacks.

        Args:
            request: The incoming HTTP request.

        Returns:
            Response with file contents and appropriate headers, or error response:
            - 403 Forbidden: Path contains '..' or escapes static directory
            - 404 Not Found: File doesn't exist or is not a regular file
            - 400 Bad Request: Invalid path or OS error
            - 500 Internal Server Error: IO error reading file

        Note:
            - Resolves paths to absolute form for security validation
            - Verifies file is within the static directory
            - Adds Cache-Control, Content-Type, and Content-Length headers
            - MIME type detection handles common web file types
        """
        # Remove URL prefix to get relative path
        relative_path = request.path[len(self.url_prefix):].lstrip('/')
        
        # Security: prevent directory traversal
        if '..' in relative_path or relative_path.startswith('/'):
            return Response("Forbidden", status=403)
        
        file_path = self.static_dir / relative_path
        
        # Check if file exists and is within static directory
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(self.static_dir.resolve())):
                return Response("Forbidden", status=403)
            
            if not file_path.exists() or not file_path.is_file():
                return Response("Not Found", status=404)
        except (OSError, ValueError):
            return Response("Bad Request", status=400)
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'application/octet-stream'
        
        # Read and serve file
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            headers = {
                'content-type': content_type,
                'content-length': str(len(content)),
                'cache-control': 'public, max-age=3600'  # Cache for 1 hour
            }
            
            return Response(content, headers=headers)
            
        except IOError:
            return Response("Internal Server Error", status=500)