"""
HTTP Request handling for Gobstopper framework
"""

import msgspec
from typing import Any, Optional
from logging import Logger
from urllib.parse import parse_qs

try:
    from granian.rsgi import Scope, HTTPProtocol
except ImportError:
    from typing import TypedDict
    # Fallback types for development without Granian
    class Scope(TypedDict, total=True):
        proto: str
        method: str
        path: str
        query_string: str
        headers: Any

    class HTTPProtocol:
        async def __call__(self): pass


class Request:
    """HTTP request object with async parsing capabilities.

    Wraps RSGI request scope and protocol, providing convenient access to
    request data including headers, query parameters, form data, and JSON payloads.
    All parsing operations are async and lazy-loaded for optimal performance.

    Args:
        scope: RSGI request scope containing request metadata (method, path, headers, etc.)
        protocol: RSGI protocol instance for reading request body asynchronously

    Attributes:
        scope (Scope): Original RSGI scope object with request metadata
        protocol (HTTPProtocol): RSGI protocol for async body reading
        method (str): HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, etc.)
        path (str): Request path without query string (e.g., "/api/users/123")
        query_string (str): Raw query string without leading '?' (e.g., "page=1&limit=10")
        headers (Dict[str, str]): HTTP headers with case-insensitive access (lowercase keys)
        args (Dict[str, List[str]]): Parsed query parameters (supports multiple values)
        client_ip (str): Client IP address (respects X-Forwarded-For header)
        session (Optional[Dict[str, Any]]): Session data dictionary (set by SecurityMiddleware)
        session_id (Optional[str]): Read-only session identifier (set by SecurityMiddleware)
        logger (Logger): Application or framework logger instance for request-scoped logging

    Examples:
        Basic request handling:

        >>> @app.post("/api/users")
        >>> async def create_user(request: Request):
        ...     data = await request.json()
        ...     user_ip = request.client_ip
        ...     request.logger.info(f"User created from {user_ip}")
        ...     return {"status": "created", "data": data}

        Access query parameters:

        >>> @app.get("/search")
        >>> async def search(request: Request):
        ...     # URL: /search?q=python&page=2
        ...     query = request.args.get("q", [""])[0]
        ...     page = int(request.args.get("page", ["1"])[0])
        ...     return {"query": query, "page": page}

        Session management:

        >>> @app.get("/profile")
        >>> async def profile(request: Request):
        ...     if not request.session or not request.session.get("user_id"):
        ...         return {"error": "Not authenticated"}, 401
        ...     user_id = request.session["user_id"]
        ...     return {"user_id": user_id}

    Note:
        Request parsing is lazy - methods like json(), form() only parse when called.
        Subsequent calls to the same parsing method return cached results.
        Body reading is async and may involve network I/O operations.
        Session attributes require SecurityMiddleware to be configured.

    See Also:
        Response: HTTP response objects
        JSONResponse: JSON response helper
        SecurityMiddleware: Provides session management
    """

    # Use __slots__ for memory efficiency and faster attribute access
    __slots__ = (
        'scope', 'protocol', '_body', '_json', '_form', '_files',
        '_multipart_parsed', 'session', '_session_id', 'endpoint',
        'view_args', 'url_rule', 'id', '_headers_dict', '_args', '_cookies',
        'app', 'max_body_bytes', 'max_json_depth'
    )

    def __init__(self, scope: Scope, protocol: HTTPProtocol):
        self.scope = scope
        self.protocol = protocol
        self._body = None
        self._json = None
        self._form = None
        self._files = None
        self._multipart_parsed = False
        # attrs initialized for IDE friendliness; middleware will set real values
        self.session = None
        self._session_id = None
        # Route matching attributes (set by app after routing)
        self.endpoint = None
        self.view_args = {}
        self.url_rule = None

        # Lazy header access - don't pre-compute dict, use Granian's RSGIHeaders directly
        # This avoids copying and lowercasing all headers on every request
        self._headers_dict = None
        self._args = None
        self._cookies = None

    @property
    def client_ip(self) -> str:
        """Get the client's IP address with proxy header support.

        Attempts to determine the real client IP address by checking the
        X-Forwarded-For header (for proxied requests) before falling back
        to the direct connection IP from the RSGI scope.

        Returns:
            str: Client IP address as string. Returns "unknown" if IP cannot
                be determined from headers or scope.

        Note:
            When behind a proxy or load balancer, X-Forwarded-For header is
            respected. Takes the first IP in the chain for multi-proxy setups.
            For direct connections, uses the client address from RSGI scope.

        Examples:
            Log client IP for requests:

            >>> @app.get("/api/endpoint")
            >>> async def handler(request: Request):
            ...     ip = request.client_ip
            ...     print(f"Request from: {ip}")
            ...     return {"client": ip}

            Rate limiting by IP:

            >>> from gobstopper.utils.rate_limiter import RateLimiter
            >>> limiter = RateLimiter(max_requests=100, window=60)
            >>>
            >>> @app.post("/api/action")
            >>> async def protected(request: Request):
            ...     if not limiter.check(request.client_ip):
            ...         return {"error": "Rate limit exceeded"}, 429
            ...     return {"status": "success"}
        """
        # Standard 'X-Forwarded-For' header
        if 'x-forwarded-for' in self.headers:
            return self.headers['x-forwarded-for'].split(',')[0].strip()

        # Fallback to remote address from scope if available
        if hasattr(self.scope, 'client') and self.scope.client:
            return self.scope.client[0]

        return "unknown"
        
    @property
    def method(self) -> str:
        """Get the HTTP request method.

        Returns:
            str: HTTP method in uppercase (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, etc.)

        Examples:
            Method-based routing logic:

            >>> @app.route("/resource", methods=["GET", "POST"])
            >>> async def handle_resource(request: Request):
            ...     if request.method == "GET":
            ...         return {"action": "retrieve"}
            ...     elif request.method == "POST":
            ...         data = await request.json()
            ...         return {"action": "create", "data": data}
        """
        return self.scope.method
    
    @property
    def path(self) -> str:
        """Get the request path without query string.

        Returns:
            str: URL path component (e.g., "/api/users/123"). Does not include
                query string, fragment, or domain.

        Examples:
            Path-based logic:

            >>> @app.get("/*")
            >>> async def catch_all(request: Request):
            ...     if request.path.startswith("/admin"):
            ...         # Check admin permissions
            ...         pass
            ...     return {"path": request.path}

            Extract path segments:

            >>> @app.get("/api/*")
            >>> async def api_handler(request: Request):
            ...     segments = request.path.strip("/").split("/")
            ...     # segments = ["api", "users", "123"]
            ...     return {"segments": segments}
        """
        return self.scope.path
    
    @property
    def query_string(self) -> str:
        """Get the raw query string from the URL.

        Returns:
            str: Raw query string without leading '?' (e.g., "page=1&limit=10").
                Empty string if no query parameters present.

        Note:
            For parsed query parameters as a dict, use the :attr:`args` property instead.

        Examples:
            Get raw query string:

            >>> @app.get("/search")
            >>> async def search(request: Request):
            ...     # URL: /search?q=python&page=2
            ...     raw = request.query_string  # "q=python&page=2"
            ...     return {"raw_query": raw}

        See Also:
            :attr:`args`: Parsed query parameters as dict
        """
        return self.scope.query_string
    
    @property
    def args(self) -> dict[str, list[str]]:
        """Get parsed query parameters as a dictionary.

        Parses the query string into a dictionary mapping parameter names to
        lists of values. Supports multiple values for the same parameter name.
        Parsing is lazy-loaded and cached.

        Returns:
            Dict[str, List[str]]: Dictionary mapping parameter names to lists of values.
                Empty dict if no query parameters present.

        Examples:
            Single parameter values:

            >>> @app.get("/search")
            >>> async def search(request: Request):
            ...     # URL: /search?q=python&page=2
            ...     query = request.args.get("q", [""])[0]  # "python"
            ...     page = int(request.args.get("page", ["1"])[0])  # 2
            ...     return {"query": query, "page": page}

            Multiple values for same parameter:

            >>> @app.get("/filter")
            >>> async def filter_items(request: Request):
            ...     # URL: /filter?tag=python&tag=web&tag=async
            ...     tags = request.args.get("tag", [])  # ["python", "web", "async"]
            ...     return {"tags": tags}

            Check if parameter exists:

            >>> @app.get("/report")
            >>> async def report(request: Request):
            ...     include_details = "details" in request.args
            ...     return {"detailed": include_details}

        Note:
            Returns lists even for single values to handle multiple values uniformly.
            Use `request.args.get("param", ["default"])[0]` to get single value with default.
            Parsing result is cached for subsequent access.

        See Also:
            :attr:`query_string`: Raw unparsed query string
        """
        # Lazy parsing - only parse when accessed
        if self._args is None:
            qs = self.query_string
            # Skip parsing empty query strings for performance
            self._args = parse_qs(qs) if qs else {}
        return self._args
    
    @property
    def headers(self) -> dict[str, str]:
        """Get HTTP request headers with case-insensitive access.

        Provides access to all HTTP headers sent with the request. Header names
        are normalized to lowercase for case-insensitive lookups. Headers are
        lazily computed only when accessed for optimal performance.

        Returns:
            Dict[str, str]: Dictionary mapping lowercase header names to values.
                Common headers include 'content-type', 'authorization', 'user-agent',
                'accept', 'cookie', etc.

        Examples:
            Check content type:

            >>> @app.post("/upload")
            >>> async def upload(request: Request):
            ...     content_type = request.headers.get("content-type", "")
            ...     if content_type.startswith("application/json"):
            ...         data = await request.json()
            ...     elif content_type.startswith("multipart/form-data"):
            ...         data = await request.multipart()
            ...     return {"received": True}

            Authentication header:

            >>> @app.get("/protected")
            >>> async def protected(request: Request):
            ...     auth = request.headers.get("authorization", "")
            ...     if not auth.startswith("Bearer "):
            ...         return {"error": "Unauthorized"}, 401
            ...     token = auth[7:]  # Remove "Bearer " prefix
            ...     # Validate token...
            ...     return {"status": "authenticated"}

            Custom headers:

            >>> @app.get("/api/data")
            >>> async def api(request: Request):
            ...     api_key = request.headers.get("x-api-key")
            ...     if not api_key:
            ...         return {"error": "API key required"}, 401
            ...     return {"data": "sensitive"}

        Note:
            Header names are normalized to lowercase (e.g., "Content-Type" becomes "content-type").
            Case-insensitive per HTTP specification (RFC 7230).
            Lazily computed only when accessed for optimal performance.
        """
        if self._headers_dict is None:
            # Lazy computation - only build dict when needed
            raw_headers = self.scope.headers
            self._headers_dict = {str(k).lower(): v for k, v in raw_headers.items()}
        return self._headers_dict

    @property
    def session_id(self) -> Optional[str]:
        """Get the current session ID if session middleware is enabled.

        Returns the session identifier set by SecurityMiddleware. This is a
        read-only property - session IDs cannot be modified directly.

        Returns:
            Optional[str]: Session ID string if SecurityMiddleware is enabled and
                a session exists. None if no session middleware or no active session.

        Examples:
            Check if user has active session:

            >>> @app.get("/dashboard")
            >>> async def dashboard(request: Request):
            ...     if not request.session_id:
            ...         return {"error": "No active session"}, 401
            ...     return {"session_id": request.session_id}

            Logging with session tracking:

            >>> @app.post("/action")
            >>> async def action(request: Request):
            ...     session = request.session_id or "anonymous"
            ...     request.logger.info(f"Action by session: {session}")
            ...     return {"status": "success"}

        Note:
            Requires SecurityMiddleware to be configured with session management.
            Session ID is typically a cryptographically secure random string.
            This is read-only - use request.session dict to store session data.

        See Also:
            :attr:`session`: Session data dictionary
            SecurityMiddleware: Session management middleware
        """
        return self._session_id

    @property
    def logger(self) -> Logger:
        """Get the application logger instance for request-scoped logging.

        Returns the application's configured logger if available, otherwise falls
        back to the framework's default logger. Useful for logging request-specific
        events and errors.

        Returns:
            Logger: Python logging.Logger instance for writing log messages.

        Examples:
            Log request information:

            >>> @app.post("/api/create")
            >>> async def create(request: Request):
            ...     request.logger.info(f"Creating resource from {request.client_ip}")
            ...     data = await request.json()
            ...     request.logger.debug(f"Received data: {data}")
            ...     return {"status": "created"}, 201

            Error logging:

            >>> @app.get("/api/data")
            >>> async def get_data(request: Request):
            ...     try:
            ...         result = await fetch_data()
            ...         return {"data": result}
            ...     except Exception as e:
            ...         request.logger.error(f"Data fetch failed: {e}", exc_info=True)
            ...         return {"error": "Internal error"}, 500

            Conditional debug logging:

            >>> @app.post("/api/process")
            >>> async def process(request: Request):
            ...     if request.logger.isEnabledFor(logging.DEBUG):
            ...         request.logger.debug(f"Headers: {request.headers}")
            ...     return {"status": "processed"}

        Note:
            Prefers application logger if set, falls back to framework logger.
            Logger is attached to request for convenient access in handlers.

        See Also:
            Tempest.logger: Application-level logger configuration
        """
        app = getattr(self, "app", None)
        if app is not None and getattr(app, "logger", None) is not None:
            return app.logger
        # Fallback import to avoid circular references at module import time
        from ..log import log  # type: ignore
        return log

    @property
    def cookies(self) -> dict[str, str]:
        """Get cookies from Cookie header as a dictionary.

        Parses the Cookie header into a dictionary mapping cookie names to values.
        Parsing is lazy-loaded and cached. Provides Flask/Quart-style convenient
        cookie access without manual header parsing.

        Returns:
            Dict[str, str]: Dictionary mapping cookie names to values.
                Empty dict if no cookies present.

        Examples:
            Access session cookie:

            >>> @app.get("/dashboard")
            >>> async def dashboard(request: Request):
            ...     session_id = request.cookies.get('session_id')
            ...     if not session_id:
            ...         return {"error": "Not authenticated"}, 401
            ...     return {"session": session_id}

            Check for specific cookie:

            >>> @app.get("/preferences")
            >>> async def preferences(request: Request):
            ...     theme = request.cookies.get('theme', 'light')
            ...     language = request.cookies.get('lang', 'en')
            ...     return {"theme": theme, "language": language}

            Multiple cookies:

            >>> @app.get("/tracking")
            >>> async def tracking(request: Request):
            ...     user_id = request.cookies.get('user_id')
            ...     tracking_id = request.cookies.get('tracking_id')
            ...     return {"user": user_id, "tracking": tracking_id}

        Note:
            Cookies are parsed from the Cookie header using standard HTTP format.
            Multi-value cookies and cookie attributes (path, domain, etc.) are not
            included - only name=value pairs.
            Parsing result is cached for subsequent access.

        See Also:
            Response.set_cookie(): Set cookies in response
            Response.delete_cookie(): Delete cookies
        """
        if not hasattr(self, '_cookies'):
            cookie_header = self.headers.get('cookie', '')
            self._cookies = {}
            if cookie_header:
                # Parse cookie header: "name1=value1; name2=value2"
                for cookie in cookie_header.split(';'):
                    cookie = cookie.strip()
                    if '=' in cookie:
                        name, value = cookie.split('=', 1)
                        self._cookies[name.strip()] = value.strip()
        return self._cookies

    @property
    def is_json(self) -> bool:
        """Check if request has JSON content type.

        Convenience property for checking if Content-Type header indicates JSON.
        Useful for conditional parsing logic and content negotiation.

        Returns:
            bool: True if Content-Type is application/json, False otherwise.

        Examples:
            Conditional JSON parsing:

            >>> @app.post("/data")
            >>> async def submit_data(request: Request):
            ...     if request.is_json:
            ...         data = await request.get_json()
            ...         return {"type": "json", "data": data}
            ...     else:
            ...         return {"error": "Expected JSON"}, 400

            Content negotiation:

            >>> @app.post("/process")
            >>> async def process(request: Request):
            ...     if request.is_json:
            ...         data = await request.get_json()
            ...     elif 'form' in request.headers.get('content-type', ''):
            ...         data = await request.get_form()
            ...     else:
            ...         return {"error": "Unsupported content type"}, 415
            ...     return {"received": True}

        Note:
            Checks if Content-Type starts with 'application/json'.
            Also matches 'application/json; charset=utf-8' and similar variants.
        """
        content_type = self.headers.get('content-type', '')
        return content_type.startswith('application/json')

    @property
    def scheme(self) -> str:
        """Get the URL scheme (http or https).

        Determines the scheme from RSGI scope, respecting X-Forwarded-Proto header
        for proxied requests. Flask/Quart compatibility property.

        Returns:
            str: 'http' or 'https' depending on connection type.

        Examples:
            Build URLs with correct scheme:

            >>> @app.get("/redirect")
            >>> async def redirect_to_secure(request: Request):
            ...     if request.scheme == 'http':
            ...         # Redirect to HTTPS
            ...         url = f"https://{request.host}{request.path}"
            ...         return redirect(url, status=301)
            ...     return {"secure": True}

            Generate absolute URLs:

            >>> @app.get("/share")
            >>> async def share(request: Request):
            ...     full_url = f"{request.scheme}://{request.host}{request.path}"
            ...     return {"share_url": full_url}

        Note:
            Respects X-Forwarded-Proto header for proxy/load balancer scenarios.
            Defaults to scope.proto from RSGI.
        """
        # Check for X-Forwarded-Proto header (proxy scenarios)
        forwarded_proto = self.headers.get('x-forwarded-proto', '')
        if forwarded_proto:
            return forwarded_proto.split(',')[0].strip()
        # Fallback to scope proto (RSGI uses 'proto' attribute, not dict 'scheme')
        return getattr(self.scope, 'proto', 'http')

    @property
    def host(self) -> str:
        """Get the host header value (hostname:port).

        Returns the Host header value, which includes hostname and optionally port.
        Flask/Quart compatibility property.

        Returns:
            str: Host header value (e.g., 'localhost:8000', 'example.com').

        Examples:
            Get hostname:

            >>> @app.get("/info")
            >>> async def info(request: Request):
            ...     return {"host": request.host}

            Domain-based routing:

            >>> @app.get("/")
            >>> async def home(request: Request):
            ...     if 'admin' in request.host:
            ...         return {"site": "admin"}
            ...     return {"site": "main"}

        Note:
            Respects X-Forwarded-Host header for proxy scenarios.
            Includes port number if non-standard (e.g., ':8000').
        """
        # Check for X-Forwarded-Host header
        forwarded_host = self.headers.get('x-forwarded-host', '')
        if forwarded_host:
            return forwarded_host.split(',')[0].strip()
        # Fallback to Host header
        return self.headers.get('host', 'localhost')

    @property
    def host_url(self) -> str:
        """Get the base URL including scheme and host.

        Constructs the base URL from scheme and host. Useful for building
        absolute URLs. Flask/Quart compatibility property.

        Returns:
            str: Base URL (e.g., 'http://localhost:8000', 'https://example.com').

        Examples:
            Build absolute URLs:

            >>> @app.post("/users")
            >>> async def create_user(request: Request):
            ...     user_id = await save_user()
            ...     location = f"{request.host_url}/users/{user_id}"
            ...     return {"location": location}, 201

            API base URL:

            >>> @app.get("/")
            >>> async def index(request: Request):
            ...     return {
            ...         "api_base": request.host_url,
            ...         "docs_url": f"{request.host_url}/docs"
            ...     }
        """
        return f"{self.scheme}://{self.host}"

    @property
    def base_url(self) -> str:
        """Get the request URL without query string.

        Constructs the full URL including scheme, host, and path, but excluding
        query string. Flask/Quart compatibility property.

        Returns:
            str: Complete URL without query string (e.g., 'http://localhost:8000/users/123').

        Examples:
            Get current page URL:

            >>> @app.get("/article/<id>")
            >>> async def article(request, id):
            ...     canonical_url = request.base_url
            ...     return {"canonical": canonical_url}

            Share URL without parameters:

            >>> @app.get("/search")
            >>> async def search(request: Request):
            ...     # URL: /search?q=python&page=2
            ...     share_url = request.base_url  # Without ?q=python&page=2
            ...     return {"share": share_url}
        """
        return f"{self.host_url}{self.path}"

    @property
    def url(self) -> str:
        """Get the complete request URL including query string.

        Constructs the full URL including scheme, host, path, and query string.
        Flask/Quart compatibility property.

        Returns:
            str: Complete URL with query string (e.g., 'http://localhost:8000/search?q=test').

        Examples:
            Get full URL:

            >>> @app.get("/search")
            >>> async def search(request: Request):
            ...     # URL: /search?q=python&page=2
            ...     full_url = request.url
            ...     # Returns: 'http://localhost:8000/search?q=python&page=2'
            ...     return {"url": full_url}

            Logging:

            >>> @app.before_request
            >>> async def log_request(request: Request):
            ...     request.logger.info(f"Request: {request.url}")
        """
        if self.query_string:
            return f"{self.base_url}?{self.query_string}"
        return self.base_url

    async def get_data(self) -> bytes:
        """Get the raw request body as bytes with optional size enforcement.

        Reads the complete request body from the RSGI protocol. Enforces maximum
        body size limit if configured via LimitsMiddleware. Body is lazy-loaded
        and cached for subsequent calls.

        Returns:
            bytes: Complete request body as raw bytes. Empty bytes object (b'')
                if no body sent with request.

        Raises:
            RequestTooLarge: If body size exceeds configured max_body_bytes limit
                (typically set by LimitsMiddleware).

        Examples:
            Read raw body:

            >>> @app.post("/upload/raw")
            >>> async def upload_raw(request: Request):
            ...     body = await request.get_data()
            ...     size = len(body)
            ...     return {"received_bytes": size}

            Custom binary processing:

            >>> @app.post("/image/process")
            >>> async def process_image(request: Request):
            ...     image_data = await request.get_data()
            ...     # Process binary image data...
            ...     return {"processed": True}

            Size limit handling:

            >>> from gobstopper.http.errors import RequestTooLarge
            >>>
            >>> @app.post("/upload")
            >>> async def upload(request: Request):
            ...     try:
            ...         data = await request.get_data()
            ...         return {"size": len(data)}
            ...     except RequestTooLarge:
            ...         return {"error": "File too large"}, 413

        Note:
            Body reading is async and may involve network I/O.
            Result is cached - subsequent calls return same bytes object.
            Size limit enforced if max_body_bytes attribute set by middleware.
            For JSON/form data, prefer using :meth:`json()` or :meth:`form()`.

        See Also:
            :meth:`get_body`: Alias for backwards compatibility
            :meth:`json`: Parse JSON body
            :meth:`form`: Parse form body
            LimitsMiddleware: Configures body size limits
        """
        if self._body is None:
            body = await self.protocol()
            # Enforce max body size if configured on the instance
            try:
                max_bytes = getattr(self, 'max_body_bytes', None)
                if max_bytes is not None and body and len(body) > int(max_bytes):
                    from .errors import RequestTooLarge
                    raise RequestTooLarge("Request body too large")
            except Exception:
                # If attribute missing or conversion fails, ignore and proceed
                pass
            self._body = body
        return self._body

    # Backwards-compat alias expected by app handler
    async def get_body(self) -> bytes:
        """Get the raw request body as bytes (alias for get_data).

        Backwards-compatible alias for :meth:`get_data()`. Provides the same
        functionality with identical behavior and caching.

        Returns:
            bytes: Complete request body as raw bytes.

        Note:
            This is an alias maintained for backwards compatibility.
            New code should prefer using :meth:`get_data()`.

        See Also:
            :meth:`get_data`: Primary method for reading raw body
        """
        return await self.get_data()
    
    async def get_json(self) -> Any:
        """Parse request body as JSON asynchronously using msgspec.
        
        Reads and parses the request body as JSON data. The parsing is
        lazy-loaded and cached - subsequent calls return the same parsed data.
        
        Returns:
            Parsed JSON data as Python dict, list, or primitive type.
            Returns None for empty request body.
            
        Raises:
            msgspec.DecodeError: If request body is not valid JSON.
            
        Examples:
            Parse JSON payload:
            
            >>> @app.post("/api/data")
            >>> async def handle_data(request: Request):
            ...     try:
            ...         data = await request.get_json()
            ...         return {"received": data}
            ...     except msgspec.DecodeError:
            ...         return {"error": "Invalid JSON"}, 400
            
        Note:
            Uses high-performance msgspec decoder.
            Result is cached for subsequent calls.
            
        See Also:
            :meth:`get_form`: Parse form data
            :meth:`get_data`: Get raw request body
        """
        if self._json is None:
            data = await self.get_data()
            if data:
                obj = msgspec.json.decode(data)
                # Optional max depth validation
                try:
                    max_depth = getattr(self, 'max_json_depth', None)
                except Exception:
                    max_depth = None
                if max_depth is not None:
                    def _depth(x, d=0):
                        if isinstance(x, (dict, list, tuple)):
                            if d >= int(max_depth):
                                return d + 1
                            if isinstance(x, dict):
                                return max([_depth(v, d+1) for v in x.values()] or [d+1])
                            else:
                                return max([_depth(v, d+1) for v in x] or [d+1])
                        return d+1
                    depth = _depth(obj, 0)
                    if depth > int(max_depth):
                        from .errors import BodyValidationError
                        raise BodyValidationError("JSON depth exceeds maximum")
                self._json = obj
            else:
                self._json = None
        return self._json
    
    async def _parse_multipart_once(self):
        """Parse multipart data once and cache both form and files."""
        if not self._multipart_parsed:
            content_type = self.headers.get('content-type', '')
            if 'multipart/form-data' in content_type:
                try:
                    from .multipart import parse_multipart
                    data = await self.get_data()
                    form_data, files = parse_multipart(data, content_type)
                    self._form = form_data
                    self._files = files
                except Exception:
                    self._form = {}
                    self._files = {}
            else:
                if self._form is None:
                    self._form = {}
                if self._files is None:
                    self._files = {}
            self._multipart_parsed = True

    async def get_form(self) -> dict[str, list[str]]:
        """Parse request body as form data asynchronously.

        Reads and parses the request body as URL-encoded or multipart form data.
        Supports both application/x-www-form-urlencoded and multipart/form-data.

        Returns:
            Dict mapping field names to lists of values.
            Multiple values with same name are preserved in lists.
            Empty dict for non-form requests or empty body.

        Raises:
            ValueError: If form data is malformed
            UnicodeDecodeError: If form data contains invalid UTF-8

        Examples:
            Handle form submission:
                Use inside an async handler: form = await request.get_form()
                name = form.get("name", [""])[0]
                message = form.get("message", [""])[0]
            Handle multiple values:
                # Form with multiple checkboxes: hobbies=reading&hobbies=coding
                hobbies = form.get("hobbies", [])  # ["reading", "coding"]
            Form validation:
                if not form.get("email"):
                    return {"error": "Email is required"}, 400

        Note:
            Supports both application/x-www-form-urlencoded and multipart/form-data.
            For multipart requests, only returns form fields (not files).
            Result is cached for subsequent calls.

        See Also:
            :meth:`get_json`: Parse JSON data
            :meth:`get_data`: Get raw request body
            :meth:`get_files`: Get uploaded files from multipart forms
            :attr:`args`: Query string parameters
        """
        if self._form is None:
            data = await self.get_data()
            content_type = self.headers.get('content-type', '')

            if data and content_type.startswith('application/x-www-form-urlencoded'):
                self._form = parse_qs(data.decode('utf-8'))
            elif 'multipart/form-data' in content_type:
                # Parse multipart once and cache both form and files
                await self._parse_multipart_once()
            else:
                self._form = {}
        return self._form

    async def get_files(self) -> dict[str, 'FileStorage']:
        """Parse uploaded files from multipart/form-data request.

        Extracts uploaded files from multipart/form-data requests. Returns a
        dictionary mapping field names to FileStorage objects. Flask/Quart
        compatibility method.

        Returns:
            Dict[str, FileStorage]: Mapping of field names to uploaded files.
                Empty dict if no files uploaded or not multipart request.

        Examples:
            Handle single file upload:

            >>> @app.post('/upload')
            >>> async def upload(request: Request):
            ...     files = await request.get_files()
            ...     avatar = files.get('avatar')
            ...     if avatar and avatar.filename:
            ...         avatar.save(f'uploads/{avatar.filename}')
            ...         return {"uploaded": avatar.filename}
            ...     return {"error": "No file uploaded"}, 400

            Handle multiple files:

            >>> @app.post('/upload-multiple')
            >>> async def upload_multiple(request: Request):
            ...     files = await request.get_files()
            ...     uploaded = []
            ...     for field_name, file in files.items():
            ...         if file.filename:
            ...             file.save(f'uploads/{file.filename}')
            ...             uploaded.append(file.filename)
            ...     return {"uploaded": uploaded}

            With form fields:

            >>> @app.post('/profile')
            >>> async def update_profile(request: Request):
            ...     # Get form data
            ...     body = await request.get_data()
            ...     content_type = request.headers.get('content-type', '')
            ...     from gobstopper.http.multipart import parse_multipart
            ...     form, files = parse_multipart(body, content_type)
            ...
            ...     # Access form fields
            ...     name = form.get('name', [''])[0]
            ...
            ...     # Access file
            ...     avatar = files.get('avatar')
            ...     if avatar:
            ...         avatar.save(f'uploads/{name}_avatar.jpg')
            ...
            ...     return {"name": name, "avatar": bool(avatar)}

        Note:
            Requires Content-Type: multipart/form-data
            Files are loaded into memory - consider streaming for large files
            Result is cached for subsequent calls

        See Also:
            :attr:`files`: Property wrapper for this method
            :class:`FileStorage`: File upload wrapper
            :func:`secure_filename`: Sanitize filenames
        """
        if self._files is None:
            content_type = self.headers.get('content-type', '')
            if 'multipart/form-data' in content_type:
                # Parse multipart once and cache both form and files
                await self._parse_multipart_once()
            else:
                self._files = {}
        return self._files

    @property
    async def files(self) -> dict[str, 'FileStorage']:
        """Uploaded files from multipart/form-data request (async property).

        Flask/Quart-style property for accessing uploaded files. This is an
        async property that must be awaited.

        Returns:
            Dict[str, FileStorage]: Uploaded files by field name

        Examples:
            Access uploaded file:

            >>> @app.post('/upload')
            >>> async def upload(request: Request):
            ...     files = await request.files
            ...     avatar = files.get('avatar')
            ...     if avatar:
            ...         avatar.save('uploads/avatar.jpg')
            ...         return {"uploaded": True}

        Note:
            This is an async property - must use `await request.files`
            For compatibility, also available as `await request.get_files()`

        See Also:
            :meth:`get_files`: Get uploaded files (method form)
            :class:`FileStorage`: File storage class
        """
        return await self.get_files()

    # New ergonomic parsers with model decoding and error signaling
    async def multipart(self, model: type[msgspec.Struct] | None = None, max_size: int | None = None) -> dict[str, list[str]] | msgspec.Struct | None:
        """Parse multipart/form-data request body (text fields only).

        Parses multipart/form-data encoded request bodies, supporting text fields
        only in the current implementation. Enforces Content-Type header validation
        and optional body size limits. File uploads are detected but not yet supported.

        Args:
            model: Optional msgspec.Struct type to decode parsed fields into.
                When provided, field values are converted to model instance.
            max_size: Optional maximum body size in bytes. Raises BodyValidationError
                if body exceeds this limit.

        Returns:
            Dict[str, List[str]]: Field name to values mapping if model is None.
            msgspec.Struct: Model instance if model type provided.
            None: If no body present and no model required.

        Raises:
            UnsupportedMediaType: If Content-Type is not multipart/form-data when body exists.
            BodyValidationError: If multipart parsing fails, size exceeds max_size,
                file upload encountered, or model conversion fails.

        Examples:
            Parse multipart text fields:

            >>> @app.post("/form/multipart")
            >>> async def handle_multipart(request: Request):
            ...     fields = await request.multipart()
            ...     name = fields.get("name", [""])[0]
            ...     email = fields.get("email", [""])[0]
            ...     return {"name": name, "email": email}

            With size limit:

            >>> @app.post("/upload/limited")
            >>> async def limited_upload(request: Request):
            ...     try:
            ...         # Limit to 1MB
            ...         fields = await request.multipart(max_size=1024*1024)
            ...         return {"status": "success"}
            ...     except BodyValidationError as e:
            ...         return {"error": str(e)}, 413

            With model validation:

            >>> import msgspec
            >>>
            >>> class ContactForm(msgspec.Struct):
            ...     name: str
            ...     email: str
            ...     message: str
            >>>
            >>> @app.post("/contact")
            >>> async def contact(request: Request):
            ...     try:
            ...         form = await request.multipart(model=ContactForm)
            ...         # form is ContactForm instance with validated fields
            ...         return {"received": form.name}
            ...     except BodyValidationError as e:
            ...         return {"error": "Invalid form data"}, 400

        Note:
            Current implementation supports text fields only.
            File uploads (filename= parameter) will raise BodyValidationError.
            Full file upload support is planned for future versions.
            Enforces CRLF line endings per multipart/form-data specification.
            When model provided, takes last value for fields with multiple values.

        See Also:
            :meth:`form`: Parse application/x-www-form-urlencoded data
            :meth:`json`: Parse JSON data
        """
        from .errors import UnsupportedMediaType, BodyValidationError
        ctype = (self.headers.get('content-type') or '').lower()
        if not ctype.startswith('multipart/form-data'):
            body = await self.get_body()
            if body:
                raise UnsupportedMediaType("Expected multipart/form-data body")
            return None if model is None else None
        # Extract boundary
        boundary = None
        for part in ctype.split(';'):
            part = part.strip()
            if part.startswith('boundary='):
                boundary = part.split('=', 1)[1].strip().strip('"')
                break
        if not boundary:
            raise BodyValidationError("Missing multipart boundary")
        raw = await self.get_body()
        if not raw:
            return {} if model is None else None
        if max_size is not None and len(raw) > int(max_size):
            raise BodyValidationError("Multipart body exceeds max_size")
        # Parse parts (simple CRLF-based parser for text fields only)
        btoken = ("--" + boundary).encode()
        endtoken = ("--" + boundary + "--").encode()
        # Ensure the body contains boundary markers
        if btoken not in raw:
            raise BodyValidationError("Invalid multipart payload: boundary not found in body")
        # Split by boundary; ignore preamble and epilogue
        parts = raw.split(btoken)
        fields: dict[str, list[str]] = {}
        for seg in parts:
            if not seg:
                continue
            # Trim leading CRLF and trailing whitespace
            seg = seg.lstrip(b"\r\n")
            if seg.startswith(b"--"):
                # closing boundary
                continue
            # Separate headers and content
            try:
                header_block, content = seg.split(b"\r\n\r\n", 1)
            except ValueError:
                # No header/content split
                continue
            # Strip the closing CRLF belonging to the part
            if content.endswith(b"\r\n"):
                content = content[:-2]
            # Parse headers
            headers: dict[str, str] = {}
            for line in header_block.split(b"\r\n"):
                if b":" not in line:
                    continue
                k, v = line.split(b":", 1)
                headers[k.decode().strip().lower()] = v.decode().strip()
            dispo = headers.get('content-disposition', '')
            # Expect: form-data; name="field"; filename="..." (filename optional)
            if 'form-data' not in dispo:
                continue
            # Parse disposition params
            parms = {}
            for p in dispo.split(';'):
                p = p.strip()
                if '=' in p and p.split('=')[0] != 'form-data':
                    key, val = p.split('=', 1)
                    parms[key.strip().lower()] = val.strip().strip('"')
            name = parms.get('name')
            filename = parms.get('filename')
            if not name:
                continue
            if filename:
                # For now we don't handle files in this minimal implementation
                raise BodyValidationError("File uploads not supported yet")
            # Text field; decode as UTF-8
            try:
                value = content.decode('utf-8')
            except UnicodeDecodeError:
                raise BodyValidationError("Invalid UTF-8 in multipart field")
            fields.setdefault(name, []).append(value)
        if model is None:
            return fields
        # Coerce to simple single-value mapping
        simple = {k: v[-1] if isinstance(v, list) and v else v for k, v in fields.items()}
        try:
            return msgspec.convert(simple, type=model)  # type: ignore[arg-type]
        except Exception as e:
            raise BodyValidationError(str(e))

    async def json(self, model: type[msgspec.Struct] | None = None) -> Any | msgspec.Struct | None:
        """Parse the request body as JSON with optional model validation.

        Parses JSON request body using high-performance msgspec decoder. Enforces
        Content-Type header validation and provides optional automatic model
        conversion and validation.

        Args:
            model: Optional msgspec.Struct type to decode JSON directly into.
                When provided, JSON is validated against model schema and returns
                a typed model instance. None for raw JSON dict/list parsing.

        Returns:
            Any: Decoded JSON as dict, list, or primitive type if model is None.
            msgspec.Struct: Validated model instance if model type provided.
            None: If request body is empty and no model required.

        Raises:
            UnsupportedMediaType: If Content-Type header is not application/json
                or compatible JSON media type (e.g., application/*+json) when body exists.
            BodyValidationError: If JSON decoding fails, validation fails, or empty
                body provided when model requires data.

        Examples:
            Parse JSON without model:

            >>> @app.post("/api/data")
            >>> async def handle_data(request: Request):
            ...     data = await request.json()
            ...     # data is dict, list, or primitive
            ...     return {"received": data}

            With model validation:

            >>> import msgspec
            >>>
            >>> class User(msgspec.Struct):
            ...     name: str
            ...     email: str
            ...     age: int
            >>>
            >>> @app.post("/api/users")
            >>> async def create_user(request: Request):
            ...     try:
            ...         user = await request.json(model=User)
            ...         # user is User instance with validated fields
            ...         return {"created": user.name, "email": user.email}
            ...     except BodyValidationError as e:
            ...         return {"error": str(e)}, 400

            Handle empty body:

            >>> @app.post("/api/optional")
            >>> async def optional_data(request: Request):
            ...     data = await request.json()
            ...     if data is None:
            ...         return {"message": "No data provided"}
            ...     return {"data": data}

            Content-Type validation:

            >>> from gobstopper.http.errors import UnsupportedMediaType
            >>>
            >>> @app.post("/api/strict")
            >>> async def strict_json(request: Request):
            ...     try:
            ...         data = await request.json()
            ...         return {"data": data}
            ...     except UnsupportedMediaType:
            ...         return {"error": "Content-Type must be application/json"}, 415

        Note:
            Uses high-performance msgspec JSON decoder.
            Accepts application/json and application/*+json media types.
            Empty body returns None if no model specified.
            Empty body with model requirement raises BodyValidationError.
            Result is cached internally via get_body() mechanism.

        See Also:
            :meth:`form`: Parse form-encoded data
            :meth:`multipart`: Parse multipart form data
            :meth:`get_json`: Legacy JSON parsing without model support
        """
        from .errors import UnsupportedMediaType, BodyValidationError
        # Content-Type check: allow application/json or +json
        ctype = (self.headers.get('content-type') or '').lower()
        if ctype and ('application/json' in ctype or ctype.endswith('+json') or '+json;' in ctype):
            pass
        elif ctype == '':
            # No content type; allow empty only if no body
            body = await self.get_body()
            if body:
                raise UnsupportedMediaType("Expected application/json body")
            # No body
            return None if model is None else None
        else:
            raise UnsupportedMediaType("Expected application/json body")

        data = await self.get_body()
        if not data:
            if model is None:
                return None
            raise BodyValidationError("Empty JSON body")

        # Single-pass decode with model if provided (avoids double parsing)
        try:
            if model is None:
                # Fast path: decode without model validation
                return msgspec.json.decode(data)
            else:
                # Optimized path: single-pass decode and validate using pre-created decoder
                # Cache the decoder on the model class for reuse across requests
                if not hasattr(model, '_msgspec_decoder_cache'):
                    model._msgspec_decoder_cache = msgspec.json.Decoder(model)
                return model._msgspec_decoder_cache.decode(data)
        except (msgspec.DecodeError, msgspec.ValidationError) as e:
            raise BodyValidationError(str(e))

    async def form(self, model: type[msgspec.Struct] | None = None) -> dict[str, list[str]] | msgspec.Struct | None:
        """Parse application/x-www-form-urlencoded request body with optional model validation.

        Parses URL-encoded form data from request body. Enforces Content-Type header
        validation and provides optional automatic model conversion and validation
        using msgspec.

        Args:
            model: Optional msgspec.Struct type to convert parsed form data into.
                When provided, form values are converted to model instance with
                validation. None for raw dict[str, list[str]] parsing.

        Returns:
            Dict[str, List[str]]: Field name to values mapping if model is None.
                Lists preserve multiple values for same field name.
            msgspec.Struct: Validated model instance if model type provided.
            None: If request body is empty and no model required.

        Raises:
            UnsupportedMediaType: If Content-Type is not application/x-www-form-urlencoded
                when body exists.
            BodyValidationError: If form parsing fails or model conversion/validation fails.

        Examples:
            Parse form data without model:

            >>> @app.post("/submit")
            >>> async def submit_form(request: Request):
            ...     form = await request.form()
            ...     # form = {"name": ["John"], "email": ["john@example.com"]}
            ...     name = form.get("name", [""])[0]
            ...     email = form.get("email", [""])[0]
            ...     return {"name": name, "email": email}

            Handle multiple values:

            >>> @app.post("/preferences")
            >>> async def preferences(request: Request):
            ...     form = await request.form()
            ...     # Form: hobbies=reading&hobbies=coding&hobbies=gaming
            ...     hobbies = form.get("hobbies", [])  # ["reading", "coding", "gaming"]
            ...     return {"hobbies": hobbies}

            With model validation:

            >>> import msgspec
            >>>
            >>> class LoginForm(msgspec.Struct):
            ...     username: str
            ...     password: str
            >>>
            >>> @app.post("/login")
            >>> async def login(request: Request):
            ...     try:
            ...         creds = await request.form(model=LoginForm)
            ...         # creds is LoginForm instance with validated fields
            ...         return {"username": creds.username}
            ...     except BodyValidationError as e:
            ...         return {"error": "Invalid form data"}, 400

            Content-Type enforcement:

            >>> from gobstopper.http.errors import UnsupportedMediaType
            >>>
            >>> @app.post("/form/strict")
            >>> async def strict_form(request: Request):
            ...     try:
            ...         form = await request.form()
            ...         return {"received": True}
            ...     except UnsupportedMediaType:
            ...         return {"error": "Content-Type must be application/x-www-form-urlencoded"}, 415

        Note:
            Enforces Content-Type header must be application/x-www-form-urlencoded.
            When model provided, takes last value for fields with multiple values.
            Uses Python's urllib.parse.parse_qs for form parsing.
            Result is cached internally via get_form() mechanism.
            Empty body returns None if no model specified.

        See Also:
            :meth:`json`: Parse JSON data
            :meth:`multipart`: Parse multipart form data
            :meth:`get_form`: Legacy form parsing without model support
            :attr:`args`: Query string parameters
        """
        from .errors import UnsupportedMediaType, BodyValidationError
        ctype = (self.headers.get('content-type') or '').lower()
        if ctype and ctype.startswith('application/x-www-form-urlencoded'):
            pass
        elif ctype == '':
            body = await self.get_body()
            if body:
                raise UnsupportedMediaType("Expected application/x-www-form-urlencoded body")
            return None if model is None else None
        else:
            # Wrong content type with possible body
            body = await self.get_body()
            if body:
                raise UnsupportedMediaType("Expected application/x-www-form-urlencoded body")
            return None if model is None else None
        # Proper content-type; parse
        try:
            form = await self.get_form()
        except Exception as e:
            raise BodyValidationError(str(e))
        if model is None:
            return form
        # Coerce single values (take last for multi)
        simple = {k: (v[-1] if isinstance(v, list) and v else v) for k, v in form.items()}
        try:
            return msgspec.convert(simple, type=model)  # type: ignore[arg-type]
        except Exception as e:
            raise BodyValidationError(str(e))
