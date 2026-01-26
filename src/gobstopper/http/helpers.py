"""HTTP helper functions for Gobstopper framework.

This module provides Flask-style convenience functions for creating common
HTTP responses. These helpers simplify the creation of JSONResponse,
FileResponse, and StreamResponse objects with minimal boilerplate.

Functions:
    jsonify: Create JSON responses with automatic serialization
    send_file: Send files with proper headers and MIME type detection
    stream_template: Create streaming responses for template rendering
    flatten_form_data: Convert form data lists to single values where appropriate

Example:
    Using helper functions in route handlers:

    >>> @app.get("/api/users/<user_id>")
    >>> async def get_user(request, user_id):
    ...     user = await db.get_user(user_id)
    ...     return jsonify({"id": user.id, "name": user.name})

    >>> @app.get("/download/<filename>")
    >>> async def download(request, filename):
    ...     return send_file(f"uploads/{filename}")

    >>> @app.get("/report")
    >>> async def stream_report(request):
    ...     async def render():
    ...         yield "<html><body>"
    ...         async for row in db.stream_rows():
    ...             yield f"<div>{row}</div>"
    ...         yield "</body></html>"
    ...     return stream_template(render)

See Also:
    :mod:`gobstopper.http.response`: Response classes (Response, JSONResponse, FileResponse, StreamResponse)
"""

from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Union

from .response import JSONResponse, FileResponse, StreamResponse, Response
from .errors import HTTPException


def flatten_form_data(form_data: dict[str, list[str]]) -> dict[str, str | list[str]]:
    """Convert form data with single-value lists to plain strings.

    Form parsers typically return all values as lists to handle multiple values.
    This helper flattens single-value lists to strings for convenience.

    Args:
        form_data: Dictionary mapping field names to lists of values

    Returns:
        Dictionary with single-value lists converted to strings,
        multi-value lists preserved as lists

    Examples:
        Flatten typical form data:

        >>> form_data = {"name": ["John"], "email": ["john@example.com"], "tags": ["python", "web"]}
        >>> flattened = flatten_form_data(form_data)
        >>> # {"name": "John", "email": "john@example.com", "tags": ["python", "web"]}
        >>> print(flattened["name"])  # Direct string access
        John

        Use in route handler:

        >>> @app.post("/submit")
        >>> async def submit_form(request: Request):
        ...     form = await request.form()
        ...     form = flatten_form_data(form)
        ...     name = form.get("name", "")  # No need for [0]
        ...     return jsonify({"name": name})

    Note:
        Empty lists are converted to empty strings.
        Preserves multi-value fields as lists for checkboxes, multi-selects, etc.
    """
    result: dict[str, str | list[str]] = {}
    for key, values in form_data.items():
        if not values:
            result[key] = ""
        elif len(values) == 1:
            result[key] = values[0]
        else:
            result[key] = values
    return result


def jsonify(data: Any, status: int = 200) -> JSONResponse:
    """Create a JSON response with automatic serialization.

    Convenience function for creating JSONResponse objects. Provides a
    Flask-like interface for returning JSON data from route handlers.

    Args:
        data: Python object to serialize as JSON (dict, list, primitives)
        status: HTTP status code (default: 200)

    Returns:
        JSONResponse instance with serialized data

    Examples:
        Return a dictionary:

        >>> @app.get("/api/user/<user_id>")
        >>> async def get_user(request, user_id):
        ...     user = await db.get_user(user_id)
        ...     return jsonify({"id": user.id, "name": user.name})

        Return error with status:

        >>> @app.get("/api/resource/<id>")
        >>> async def get_resource(request, id):
        ...     resource = await db.get_resource(id)
        ...     if not resource:
        ...         return jsonify({"error": "Not found"}, status=404)
        ...     return jsonify(resource)

        Return a list:

        >>> @app.get("/api/items")
        >>> async def list_items(request):
        ...     items = await db.get_all_items()
        ...     return jsonify(items)

    Note:
        Uses high-performance msgspec for JSON serialization.

    See Also:
        :class:`JSONResponse`: The underlying response class
    """
    return JSONResponse(data, status)


def send_file(path: Union[str, Path], filename: Optional[str] = None) -> FileResponse:
    """Send a file as a downloadable response.

    Convenience function for creating FileResponse objects. Provides a
    Flask-like interface for serving files with proper headers and MIME types.

    Args:
        path: File path as string or Path object
        filename: Download filename (defaults to basename of path)

    Returns:
        FileResponse instance configured for file serving

    Examples:
        Serve a user's uploaded file:

        >>> @app.get("/download/<filename>")
        >>> async def download_file(request, filename):
        ...     file_path = f"uploads/{filename}"
        ...     return send_file(file_path)

        Serve with custom download name:

        >>> @app.get("/report")
        >>> async def download_report(request):
        ...     return send_file("reports/data.pdf",
        ...                     filename="monthly_report_2024.pdf")

        Serve generated content:

        >>> @app.get("/export/users")
        >>> async def export_users(request):
        ...     csv_path = await generate_user_export()
        ...     return send_file(csv_path, filename="users.csv")

    Note:
        Content-Type is automatically detected from file extension.
        Sets Content-Disposition header for download behavior.

    See Also:
        :class:`FileResponse`: The underlying response class
    """
    return FileResponse(path, filename)


def abort(status: int, description: str | None = None, response: Response | None = None):
    """Abort request handling and return an HTTP error response.

    Flask/Quart-style function to immediately stop request processing and
    return an error response. Raises HTTPException which is caught by the
    framework's error handling system.

    Args:
        status: HTTP status code (e.g., 404, 403, 500)
        description: Optional human-readable error description
        response: Optional Response object to return instead of default error page

    Raises:
        HTTPException: Always raised to trigger error response

    Examples:
        Simple 404 error:

        >>> @app.get('/users/<int:id>')
        >>> async def get_user(request, id):
        ...     user = await db.get_user(id)
        ...     if not user:
        ...         abort(404, "User not found")
        ...     return jsonify(user)

        Custom error response:

        >>> @app.get('/admin')
        >>> async def admin_panel(request):
        ...     if not request.session.get('is_admin'):
        ...         abort(403, response=jsonify({
        ...             "error": "Forbidden",
        ...             "reason": "Admin access required"
        ...         }))
        ...     return render_template('admin.html')

        With error handler:

        >>> @app.error_handler(404)
        >>> async def not_found(request, error):
        ...     return jsonify({"error": error.description}), 404

    Note:
        The raised HTTPException is caught by the application's error
        handling system. If a custom error handler is registered for the
        status code, it will be invoked. Otherwise, the framework's default
        error handler will be used.

    See Also:
        :class:`HTTPException`: The exception class raised by abort()
        :meth:`Gobstopper.error_handler`: Register custom error handlers
    """
    raise HTTPException(status, description, response)


def make_response(rv, status: int = 200, headers: dict[str, str] | None = None) -> Response:
    """Create a Response object from various return value formats.

    Flask/Quart-style response builder that converts various return value
    formats into Response objects. Useful when you need to modify response
    headers or cookies before returning.

    Args:
        rv: Return value - can be Response, str, bytes, dict, tuple, or JSONResponse
        status: HTTP status code (default: 200, ignored if rv includes status)
        headers: Optional headers dict to add to response

    Returns:
        Response object that can be further modified

    Examples:
        Build response with custom headers:

        >>> resp = make_response(jsonify({"data": results}), 201)
        >>> resp.headers['X-Custom'] = 'value'
        >>> resp.set_cookie('session', session_id)
        >>> return resp

        From tuple (body, status, headers):

        >>> resp = make_response(("Created", 201, {"Location": "/users/123"}))

        Modify existing response:

        >>> resp = make_response(jsonify(data))
        >>> resp.set_cookie('last_viewed', str(item_id))
        >>> return resp

        With string body:

        >>> resp = make_response("<h1>Hello</h1>")
        >>> resp.headers['Content-Type'] = 'text/html'
        >>> return resp

    Note:
        If rv is already a Response object, it's returned as-is (status and
        headers parameters are ignored). This allows make_response() to be
        called safely on any return value.

    See Also:
        :class:`Response`: Base response class
        :func:`jsonify`: Create JSON responses
    """
    # Already a Response object
    if isinstance(rv, Response):
        if headers:
            rv.headers.update(headers)
        return rv

    # Tuple unpacking: (body, status) or (body, status, headers)
    if isinstance(rv, tuple):
        if len(rv) == 3:
            body, status, rv_headers = rv
            headers = {**(rv_headers or {}), **(headers or {})}
        elif len(rv) == 2:
            body, status = rv
        else:
            body = rv
    else:
        body = rv

    # Create Response
    if isinstance(body, (JSONResponse, Response)):
        resp = body
    elif isinstance(body, dict):
        resp = JSONResponse(body, status)
    elif isinstance(body, (str, bytes)):
        resp = Response(body, status, headers)
    else:
        resp = Response(str(body), status, headers)

    # Add extra headers if provided
    if headers and not isinstance(body, dict):
        resp.headers.update(headers)

    return resp


def send_from_directory(directory: str | Path, filename: str, **kwargs) -> FileResponse:
    """Securely serve a file from a directory.

    Flask/Quart-style function for serving files with path traversal protection.
    Validates that the requested file is within the specified directory and exists
    before serving. Different from StaticFileMiddleware - this is for per-route
    dynamic file serving.

    Args:
        directory: Base directory containing files (string or Path)
        filename: Requested filename (will be sanitized)
        **kwargs: Additional arguments passed to FileResponse (status, headers)

    Returns:
        FileResponse: Response object for serving the file

    Raises:
        FileNotFoundError: If file doesn't exist
        PermissionError: If path escapes directory (security)
        IsADirectoryError: If filename points to a directory

    Examples:
        Serve user uploads:

        >>> @app.get('/uploads/<path:filename>')
        >>> async def serve_upload(request, filename):
        ...     return send_from_directory('uploads', filename)

        Serve with custom headers:

        >>> @app.get('/downloads/<filename>')
        >>> async def download(request, filename):
        ...     return send_from_directory(
        ...         'downloads',
        ...         filename,
        ...         headers={'Cache-Control': 'max-age=3600'}
        ...     )

        Secure file serving:

        >>> @app.get('/files/<path:filepath>')
        >>> async def serve_file(request, filepath):
        ...     # Automatically prevents ../../../etc/passwd attacks
        ...     return send_from_directory('/var/app/files', filepath)

        With authentication:

        >>> @app.get('/private/<filename>')
        >>> async def private_file(request, filename):
        ...     if not request.session.get('authenticated'):
        ...         abort(401, "Authentication required")
        ...     return send_from_directory('private', filename)

    Security:
        - Prevents directory traversal attacks (../../../etc/passwd)
        - Validates file is within specified directory
        - Checks file exists and is regular file (not directory)
        - Uses Path.resolve() for canonical path validation

    Note:
        This is for per-route file serving. For static asset serving across
        your application, use StaticFileMiddleware or RustStaticMiddleware instead.

    See Also:
        :class:`FileResponse`: File response class
        :class:`StaticFileMiddleware`: Global static file serving
        :func:`secure_filename`: Sanitize filenames
    """
    from pathlib import Path

    # Convert to Path objects
    base_dir = Path(directory).resolve()
    requested_file = base_dir / filename

    # Resolve to canonical path (follows symlinks, removes ..)
    try:
        requested_file = requested_file.resolve()
    except (OSError, RuntimeError) as e:
        raise PermissionError(f"Invalid file path: {filename}") from e

    # Security check: ensure resolved path is within base directory
    if not str(requested_file).startswith(str(base_dir)):
        raise PermissionError(f"Access denied: {filename} is outside allowed directory")

    # Check file exists
    if not requested_file.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    # Check it's a regular file (not directory)
    if not requested_file.is_file():
        raise IsADirectoryError(f"Not a file: {filename}")

    # Create and return FileResponse
    return FileResponse(requested_file, filename=requested_file.name, **kwargs)


def stream_template(template_generator: Callable[[], Awaitable]) -> StreamResponse:
    """Stream a template response for progressive rendering.

    Convenience function for creating StreamResponse objects configured for
    HTML template streaming. Useful for large templates that benefit from
    progressive rendering.

    Args:
        template_generator: Async generator function that yields HTML chunks

    Returns:
        StreamResponse instance configured for HTML streaming

    Examples:
        Stream a large template:

        >>> @app.get("/report")
        >>> async def view_report(request):
        ...     async def render():
        ...         yield "<html><body><h1>Report</h1>"
        ...         async for row in db.stream_report_rows():
        ...             yield f"<div>{row}</div>"
        ...         yield "</body></html>"
        ...     return stream_template(render)

        Stream with Rust template engine:

        >>> @app.get("/dashboard")
        >>> async def dashboard(request):
        ...     # Rust engine automatically provides streaming
        ...     async def render():
        ...         data = await get_dashboard_data()
        ...         async for chunk in app.rust_engine.render_stream("dashboard.html", data):
        ...             yield chunk
        ...     return stream_template(render)

    Note:
        Automatically sets Content-Type to text/html.
        Generator function must be async and yield string or bytes.
        Works well with Rust template engine's streaming capabilities.

    See Also:
        :class:`StreamResponse`: The underlying response class
        :class:`RustTemplateEngine`: Rust-based template engine with streaming
    """
    return StreamResponse(template_generator, content_type='text/html')