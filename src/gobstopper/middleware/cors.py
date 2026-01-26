"""
CORS middleware for Gobstopper framework.

This module provides Cross-Origin Resource Sharing (CORS) support for web applications,
enabling secure cross-origin requests from browsers. CORS is essential for modern
web applications that need to make requests from different domains.
"""

from typing import Callable, List, Optional, Awaitable, Any

from ..http.request import Request
from ..http.response import Response


class CORSMiddleware:
    """Middleware for handling Cross-Origin Resource Sharing (CORS).

    This middleware adds appropriate CORS headers to responses and handles
    preflight OPTIONS requests. It supports configurable origins, methods,
    headers, and credential handling.

    Security Considerations:
        - Use specific origins instead of '*' when possible
        - Never use '*' with credentials enabled (browsers will reject)
        - Always include Vary header when using specific origins
        - Consider the security implications of exposed headers

    Args:
        origins: List of allowed origins. Use ['*'] for all origins (default).
            Examples: ['https://example.com', 'https://app.example.com']
            Note: '*' cannot be used with credentials.
        methods: List of allowed HTTP methods.
            Defaults to ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'].
        headers: List of allowed request headers.
            Defaults to ['Content-Type', 'Authorization'].
        allow_credentials: Whether to allow credentials (cookies, auth headers).
            Default is False. When True, specific origins must be listed.
        max_age: How long (in seconds) browsers should cache preflight responses.
            Default is 3600 (1 hour). Maximum varies by browser (usually 86400).

    Examples:
        Basic CORS for public API::

            from gobstopper.middleware import CORSMiddleware

            # Allow all origins (no credentials)
            cors = CORSMiddleware()
            app.add_middleware(cors)

        CORS with specific origins and credentials::

            cors = CORSMiddleware(
                origins=['https://app.example.com', 'https://admin.example.com'],
                methods=['GET', 'POST', 'PUT', 'DELETE'],
                headers=['Content-Type', 'Authorization', 'X-Custom-Header'],
                allow_credentials=True,
                max_age=7200  # 2 hours
            )
            app.add_middleware(cors)

        Development setup (permissive)::

            cors = CORSMiddleware(
                origins=['http://localhost:3000', 'http://localhost:8080'],
                allow_credentials=True
            )
            app.add_middleware(cors)

    Note:
        - Preflight requests (OPTIONS) are handled automatically
        - The middleware adds 'Vary: Origin' header when using specific origins
        - Browsers enforce CORS; this middleware just provides the headers
        - Empty origin headers are rejected for security

    See Also:
        - SecurityMiddleware: For additional security headers
        - MDN CORS documentation: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
    """

    def __init__(self,
                 origins: Optional[List[str]] = None,
                 methods: Optional[List[str]] = None,
                 headers: Optional[List[str]] = None,
                 allow_credentials: bool = False,
                 max_age: int = 3600):
        
        self.origins = origins or ["*"]
        self.methods = methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.headers = headers or ["Content-Type", "Authorization"]
        self.allow_credentials = allow_credentials
        self.max_age = max_age
    
    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Response:
        """Process request and add CORS headers.

        This method handles both preflight OPTIONS requests and regular requests,
        adding appropriate CORS headers based on the middleware configuration.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or handler in the chain.

        Returns:
            Response with CORS headers added if the origin is allowed.

        Note:
            - Preflight requests receive a 204 No Content response
            - Regular requests are passed through with CORS headers added
            - Origins are validated before headers are added
        """
        origin = request.headers.get('origin', '')
        
        # Handle preflight OPTIONS request
        if request.method == 'OPTIONS':
            return self._handle_preflight(origin)
        
        # Process normal request
        response = await call_next(request)
        
        # Add CORS headers to response only if we have a response
        if response:
            self._add_cors_headers(response, origin)
        
        return response
    
    def _handle_preflight(self, origin: str) -> Response:
        """Handle CORS preflight OPTIONS request.

        Preflight requests are sent by browsers before certain cross-origin requests
        to determine if the actual request is safe to send.

        Args:
            origin: The origin header from the request.

        Returns:
            A 204 No Content response with CORS preflight headers including
            allowed methods, headers, and max-age for caching.

        Note:
            - Browsers send preflight for requests with custom headers or non-simple methods
            - The response includes Access-Control-Allow-Methods and Allow-Headers
            - Max-Age header tells browsers how long to cache this preflight response
        """
        response = Response("", status=204)
        self._add_cors_headers(response, origin)
        
        # Add preflight-specific headers
        response.headers['access-control-allow-methods'] = ', '.join(self.methods)
        response.headers['access-control-allow-headers'] = ', '.join(self.headers)
        response.headers['access-control-max-age'] = str(self.max_age)
        
        return response
    
    def _add_cors_headers(self, response: Response, origin: str):
        """Add CORS headers to response.

        Adds Access-Control-Allow-Origin and related headers to the response
        based on the middleware configuration and request origin.

        Args:
            response: The response object to modify.
            origin: The origin header from the request.

        Note:
            - Wildcard '*' is only used when credentials are disabled
            - When using specific origins, the Vary: Origin header is added
            - Credentials header is only added when allow_credentials=True
            - Origins are validated before headers are added
        """
        if self._is_origin_allowed(origin):
            if '*' in self.origins and not self.allow_credentials:
                response.headers['access-control-allow-origin'] = '*'
            else:
                response.headers['access-control-allow-origin'] = origin
        
        if self.allow_credentials:
            response.headers['access-control-allow-credentials'] = 'true'
        
        # Always add Vary header for Origin when not using wildcard
        if '*' not in self.origins:
            vary = response.headers.get('vary', '')
            if vary:
                response.headers['vary'] = f"{vary}, Origin"
            else:
                response.headers['vary'] = "Origin"
    
    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed.

        Validates whether a given origin is permitted to make cross-origin requests
        based on the configured allowed origins.

        Args:
            origin: The origin string from the request header (e.g., 'https://example.com').

        Returns:
            True if the origin is allowed (either wildcard or explicitly listed),
            False otherwise.

        Note:
            - Empty origins are rejected for security
            - Wildcard '*' matches all origins
            - Otherwise, origin must exactly match an entry in the allowed list
        """
        if not origin:
            return False
        
        return '*' in self.origins or origin in self.origins