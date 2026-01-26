class HTTPException(Exception):
    """Base HTTP exception for abort() functionality.

    Flask/Quart-style exception that can be raised to immediately return
    an HTTP error response with a specific status code and optional body.

    Args:
        status: HTTP status code (e.g., 404, 403, 500)
        description: Human-readable error description
        response: Optional Response object to return instead of default error page

    Examples:
        >>> raise HTTPException(404, "User not found")
        >>> raise HTTPException(403, response=jsonify({"error": "Forbidden"}))
    """
    def __init__(self, status: int, description: str | None = None, response=None):
        self.status = status
        self.description = description
        self.response = response
        super().__init__(description or f"HTTP {status}")


class UnsupportedMediaType(Exception):
    """Raised when the Content-Type of a request does not match the expected parser.
    Maps to HTTP 415.
    """
    pass


class BodyValidationError(Exception):
    """Raised when decoding/validation of the request body fails.
    Maps to HTTP 422.
    """
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


class RequestTooLarge(Exception):
    """Raised when request body exceeds configured limits.
    Maps to HTTP 413.
    """
    pass
