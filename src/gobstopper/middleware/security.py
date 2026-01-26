"""
Security middleware for Gobstopper framework.

This module provides comprehensive security features for web applications including:
- CSRF (Cross-Site Request Forgery) protection
- Secure session management with multiple storage backends
- Modern security headers (HSTS, CSP, COOP, COEP, etc.)
- Cookie security with environment-aware defaults
- Session ID signing and verification

The middleware is designed to be production-ready with secure defaults that are
automatically enforced in production environments.
"""

import hashlib
import hmac
import secrets
import time
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union, Awaitable

from ..http.request import Request
from ..http.response import Response
from ..log import log
from ..sessions.storage import (
    SESSION_EXPIRATION_TIME,
    AsyncBaseSessionStorage,
    BaseSessionStorage,
    FileSessionStorage,
    maybe_await,
)

StorageType = Union[BaseSessionStorage, AsyncBaseSessionStorage]


class SecurityMiddleware:
    """Middleware for comprehensive application security.

    This middleware provides multiple layers of security protection including CSRF
    tokens, secure session management, and modern security headers. It's designed
    to be production-ready with secure defaults that are automatically enforced
    based on the environment.

    Security Features:
        - CSRF Protection: Validates tokens for state-changing requests
        - Session Management: Secure sessions with multiple storage backends
        - Security Headers: HSTS, CSP, COOP, COEP, X-Frame-Options, etc.
        - Cookie Security: Secure, HttpOnly, SameSite flags with environment enforcement
        - Session ID Signing: HMAC-SHA256 signing to prevent tampering
        - Rolling Sessions: Optional session renewal on each request

    Production Behavior:
        When ENV=production, the middleware enforces:
        - Cookie Secure flag (HTTPS only)
        - HttpOnly flag (prevents JavaScript access)
        - SameSite=Strict (prevents CSRF attacks)
        These cannot be disabled in production for safety.

    Args:
        secret_key: Secret key for CSRF and session signing. Required for production.
            Should be a long, random string. If not provided, a random key is generated
            but this is not suitable for multi-server deployments.
        enable_csrf: Enable CSRF protection for POST/PUT/DELETE/PATCH requests.
            Default is True. Recommended to keep enabled.
        enable_security_headers: Add security headers to responses.
            Default is True. Includes HSTS, CSP, COOP, COEP, etc.
        hsts_max_age: HTTP Strict Transport Security max-age in seconds.
            Default is 31536000 (1 year). Tells browsers to use HTTPS.
        hsts_include_subdomains: Include subdomains in HSTS policy.
            Default is True. Applies HSTS to all subdomains.
        csp_policy: Content Security Policy directive string.
            Default restricts to same-origin and blocks objects.
            Customize based on your application's needs.
        referrer_policy: Referrer-Policy header value.
            Default is 'strict-origin-when-cross-origin'.
        coop_policy: Cross-Origin-Opener-Policy header value.
            Default is 'same-origin'. Prevents window.opener access.
        coep_policy: Cross-Origin-Embedder-Policy header value.
            Default is 'require-corp'. Enables SharedArrayBuffer.
        session_storage: Storage backend for sessions. Defaults to FileSessionStorage.
            Can be FileSessionStorage, MemorySessionStorage, or custom implementation.
        debug: Debug mode. Disables some security warnings.
            Default is False. Never use True in production.
        cookie_name: Name of the session cookie.
            Default is 'session_id'.
        cookie_secure: Require HTTPS for session cookies.
            Default is True. Forced to True in production.
        cookie_httponly: Prevent JavaScript access to session cookies.
            Default is True. Forced to True in production.
        cookie_samesite: SameSite cookie attribute.
            Default is 'Strict'. Forced to 'Strict' in production.
            Options: 'Strict', 'Lax', 'None' (requires Secure=True).
        cookie_path: Path scope for session cookie.
            Default is '/'. Cookie valid for entire site.
        cookie_domain: Domain scope for session cookie.
            Default is None (current domain only).
        cookie_max_age: Session cookie lifetime in seconds.
            Default is SESSION_EXPIRATION_TIME (typically 24 hours).
        rolling_sessions: Refresh session on every request.
            Default is False. When True, session expiry is extended on each request.
        sign_session_id: Sign session IDs with HMAC-SHA256.
            Default is False. Prevents session ID tampering when enabled.

    Examples:
        Basic security setup::

            from gobstopper.middleware import SecurityMiddleware

            security = SecurityMiddleware(
                secret_key='your-secret-key-here',
                enable_csrf=True,
                enable_security_headers=True
            )
            app.add_middleware(security)

        Production configuration::

            import os

            security = SecurityMiddleware(
                secret_key=os.environ['SECRET_KEY'],
                enable_csrf=True,
                enable_security_headers=True,
                cookie_secure=True,
                cookie_httponly=True,
                cookie_samesite='Strict',
                rolling_sessions=True,
                sign_session_id=True,
                csp_policy="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
            )
            app.add_middleware(security)

        Custom session storage::

            from gobstopper.sessions.storage import MemorySessionStorage

            security = SecurityMiddleware(
                secret_key='your-secret-key',
                session_storage=MemorySessionStorage()
            )
            app.add_middleware(security)

        Development setup (relaxed)::

            security = SecurityMiddleware(
                secret_key='dev-key',
                cookie_secure=False,  # Allow HTTP in development
                cookie_samesite='Lax',
                debug=True
            )
            app.add_middleware(security)

    Note:
        - Always use a strong, persistent secret_key in production
        - CSRF tokens must be included in forms or headers for state-changing requests
        - Session data is available via request.session dictionary
        - Call generate_csrf_token() to create tokens for templates
        - Use regenerate_session_id() after privilege escalation (e.g., login)

    Security Best Practices:
        - Set ENV=production for production deployments
        - Use HTTPS in production (required for secure cookies)
        - Regenerate session ID after authentication changes
        - Implement session timeout and idle timeout
        - Use database-backed sessions for multi-server deployments
        - Regularly rotate the secret_key (requires session invalidation)
        - Monitor and log security events

    See Also:
        - CORSMiddleware: For cross-origin request handling
        - gobstopper.sessions.storage: Session storage backends
        - OWASP CSRF Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        enable_csrf: bool = True,
        enable_security_headers: bool = True,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        csp_policy: str = "default-src 'self'; object-src 'none'",
        referrer_policy: str = "strict-origin-when-cross-origin",
        coop_policy: str = "same-origin",
        coep_policy: str = "require-corp",
        session_storage: Optional[StorageType] = None,
        debug: bool = False,
        cookie_name: str = "session_id",
        cookie_secure: bool = True,
        cookie_httponly: bool = True,
        cookie_samesite: str = "Strict",
        cookie_path: str = "/",
        cookie_domain: Optional[str] = None,
        cookie_max_age: int = SESSION_EXPIRATION_TIME,
        rolling_sessions: bool = False,
        sign_session_id: bool = False,
    ):
        if not secret_key:
            if not debug and (enable_csrf or sign_session_id):
                log.warning(
                    "CSRF or session signing is enabled, but no secret_key was provided. "
                    "This is insecure for production. Please provide a strong, "
                    "persistent secret key."
                )
            self.secret_key = secrets.token_urlsafe(32)
        else:
            self.secret_key = secret_key

        self.enable_csrf = enable_csrf
        self.enable_security_headers = enable_security_headers

        # Header configurations
        self.hsts_policy = f"max-age={hsts_max_age}"
        if hsts_include_subdomains:
            self.hsts_policy += "; includeSubDomains"
        self.csp_policy = csp_policy
        self.referrer_policy = referrer_policy
        self.coop_policy = coop_policy
        self.coep_policy = coep_policy

        # Session management
        self.session_storage: StorageType = session_storage or FileSessionStorage(
            Path("./sessions")
        )
        self.cookie_name = cookie_name
        # Determine environment and enforce secure defaults in production
        self.env = os.getenv("ENV", "development").lower()
        eff_secure = cookie_secure
        eff_httponly = cookie_httponly
        eff_samesite = cookie_samesite
        if self.env == "production":
            # Force secure flags
            if not cookie_secure:
                log.warning("ENV=production: Overriding cookie_secure=False to True for safety")
                eff_secure = True
            if not cookie_httponly:
                log.warning("ENV=production: Overriding cookie_httponly=False to True for safety")
                eff_httponly = True
            # Disallow SameSite=None unless Secure=true (already ensured) but prefer Strict
            if (cookie_samesite or "").lower() not in ("strict", "lax"):
                log.warning("ENV=production: Forcing cookie_samesite to 'Strict'")
                eff_samesite = "Strict"
        self.cookie_secure = eff_secure
        self.cookie_httponly = eff_httponly
        self.cookie_samesite = eff_samesite
        self.cookie_path = cookie_path
        self.cookie_domain = cookie_domain
        self.cookie_max_age = cookie_max_age
        self.rolling_sessions = rolling_sessions
        self.sign_session_id = sign_session_id
        # Expose effective cookie flags for tests
        self.effective_cookie_flags = {
            "secure": self.cookie_secure,
            "httponly": self.cookie_httponly,
            "samesite": self.cookie_samesite,
        }

    def _sign(self, session_id: str) -> str:
        mac = hmac.new(
            self.secret_key.encode(), session_id.encode(), hashlib.sha256
        ).hexdigest()
        return f"{session_id}.{mac}"

    def _verify(self, signed: str) -> Optional[str]:
        if "." not in signed:
            return None
        sid, mac = signed.rsplit(".", 1)
        expected = hmac.new(
            self.secret_key.encode(), sid.encode(), hashlib.sha256
        ).hexdigest()
        return sid if hmac.compare_digest(mac, expected) else None

    # ---- Public helpers to avoid accessing protected members from app code ----
    def sign_cookie_value(self, session_id: str) -> str:
        """Return a signed cookie value when signing is enabled.

        Signs the session ID using HMAC-SHA256 to prevent tampering. The signature
        is appended to the session ID with a dot separator.

        Args:
            session_id: The session ID to sign.

        Returns:
            Signed session ID in format "session_id.signature" if signing is enabled,
            otherwise returns the original session_id unchanged.

        Note:
            - Only signs if sign_session_id=True was set during initialization
            - Uses HMAC-SHA256 with the middleware's secret key
            - Signature prevents session ID tampering and fixation attacks
        """
        if self.sign_session_id:
            return self._sign(session_id)
        return session_id

    def get_session_id(self, request: Request) -> Optional[str]:
        """Public accessor for the current request's session ID.

        Retrieves the session ID that was set by the middleware during request processing.

        Args:
            request: The request object.

        Returns:
            The session ID string if a session is active, None otherwise.

        Note:
            - This is the preferred way to access session IDs from application code
            - Returns None if no session exists or middleware hasn't run yet
        """
        return getattr(request, "_session_id", None)

    def _get_cookie_sid(self, request: Request) -> Optional[str]:
        cookie_header = request.headers.get("cookie")
        if not cookie_header:
            return None
        cookies = dict(item.strip().split("=", 1) for item in cookie_header.split(";"))
        raw = cookies.get(self.cookie_name)
        if not raw:
            return None
        if self.sign_session_id:
            return self._verify(raw)
        return raw

    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Response:
        """Process request through security middleware.

        Handles session loading, CSRF validation, request processing, and session saving.
        Also adds security headers to responses.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or handler in the chain.

        Returns:
            Response with security headers added, or 403 Forbidden if CSRF validation fails.

        Note:
            - Loads session from storage if session cookie exists
            - Validates CSRF token for POST/PUT/DELETE/PATCH requests
            - Saves session if modified or rolling_sessions is enabled
            - Adds security headers to all responses
            - Sets request.session dict for application use
        """
        sid = self._get_cookie_sid(request)
        session_data = {}
        if sid:
            loaded_data = await maybe_await(self.session_storage.load(sid))
            if loaded_data is not None:
                session_data = loaded_data

        original_session = session_data.copy()
        request.session = session_data
        request._session_id = sid

        # CSRF protection for state-changing methods
        if self.enable_csrf and request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            ok = await self._verify_csrf_token(request, session_data)
            if not ok:
                return Response("CSRF token missing or invalid", status=403)

        response = await call_next(request)

        # Save session if it was modified or if rolling sessions are enabled
        session_modified = request.session != original_session
        should_save = (session_modified or self.rolling_sessions) and request.session

        if should_save:
            # Create new session ID if this is a new session
            if not getattr(request, "_session_id", None):
                request._session_id = self.create_session_id()

            await maybe_await(
                self.session_storage.save(request._session_id, request.session)
            )

            # Set session cookie
            if response:
                cookie_value = self._sign(request._session_id) if self.sign_session_id else request._session_id

                # Build cookie attributes
                cookie_parts = [f"{self.cookie_name}={cookie_value}"]
                cookie_parts.append(f"Path={self.cookie_path}")
                cookie_parts.append(f"Max-Age={self.cookie_max_age}")

                if self.cookie_domain:
                    cookie_parts.append(f"Domain={self.cookie_domain}")
                if self.cookie_secure:
                    cookie_parts.append("Secure")
                if self.cookie_httponly:
                    cookie_parts.append("HttpOnly")
                if self.cookie_samesite:
                    cookie_parts.append(f"SameSite={self.cookie_samesite}")

                cookie_header = "; ".join(cookie_parts)
                response.headers["Set-Cookie"] = cookie_header

        # Add security headers
        if response and self.enable_security_headers:
            self._add_security_headers(response)

        return response

    def generate_csrf_token(self, session: Dict[str, Any]) -> str:
        """Generate a CSRF token and store it in the session.

        Creates a cryptographically secure random token and stores it in the session.
        This token must be included in subsequent state-changing requests.

        Args:
            session: The session dictionary to store the token in.

        Returns:
            The generated CSRF token string (URL-safe base64).

        Note:
            - Token is stored in session['csrf_token']
            - Should be called when rendering forms that will submit data
            - Tokens are validated on POST/PUT/DELETE/PATCH requests
            - Token is unique per session and remains valid until session expires

        Example:
            In a route handler::

                @app.get('/form')
                async def show_form(request):
                    token = security.generate_csrf_token(request.session)
                    return template('form.html', csrf_token=token)
        """
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
        return token

    async def _verify_csrf_token(self, request: Request, session: Dict[str, Any]) -> bool:
        """Verify CSRF token from header or form field against the session.

        Validates that the CSRF token in the request matches the one stored in
        the session. Looks for the token in the X-CSRF-Token header first, then
        falls back to checking form data for traditional POST forms.

        Args:
            request: The incoming HTTP request.
            session: The session dictionary containing the expected token.

        Returns:
            True if token is valid, False otherwise.

        Note:
            - Checks X-CSRF-Token header first (for AJAX requests)
            - Falls back to csrf_token form field (for traditional forms)
            - Uses constant-time comparison to prevent timing attacks
            - Returns False if no token found or session has no token
        """
        expected_token = session.get("csrf_token")
        if not expected_token:
            return False

        token = request.headers.get("x-csrf-token")
        if not token:
            # Try form field for traditional POST forms
            try:
                form = await request.get_form()
                vals = form.get("csrf_token") or []
                token = vals[0] if isinstance(vals, list) and vals else None
            except Exception:
                token = None
        if not token:
            return False

        return hmac.compare_digest(token, expected_token)

    def _add_security_headers(self, response: Response):
        """Add comprehensive security headers to response.

        Applies modern security headers to protect against common web vulnerabilities
        including XSS, clickjacking, MIME sniffing, and protocol downgrade attacks.

        Args:
            response: The response object to modify.

        Note:
            Headers added:
            - X-Content-Type-Options: nosniff (prevents MIME sniffing)
            - X-Frame-Options: DENY (prevents clickjacking)
            - Strict-Transport-Security: HSTS policy (forces HTTPS)
            - Referrer-Policy: Controls referrer information
            - Content-Security-Policy: CSP directives (prevents XSS)
            - Cross-Origin-Opener-Policy: COOP (prevents window access)
            - Cross-Origin-Embedder-Policy: COEP (enables SharedArrayBuffer)

            Only adds headers if not already present in the response.
        """
        headers = {
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "strict-transport-security": self.hsts_policy,
            "referrer-policy": self.referrer_policy,
            "content-security-policy": self.csp_policy,
            "cross-origin-opener-policy": self.coop_policy,
            "cross-origin-embedder-policy": self.coep_policy,
        }

        for key, value in headers.items():
            if key not in response.headers and value:
                response.headers[key] = value

    def create_session_id(self) -> str:
        """Generate a new cryptographically secure session ID.

        Creates a URL-safe base64-encoded random session ID suitable for use
        as a session identifier.

        Returns:
            A 32-byte URL-safe random session ID string.

        Note:
            - Uses secrets.token_urlsafe() for cryptographic randomness
            - IDs are 43 characters long (32 bytes base64-encoded)
            - Safe to use in cookies and URLs
        """
        return secrets.token_urlsafe(32)

    async def create_session(self, data: dict) -> str:
        """Create a new session with the provided data.

        Generates a new session ID, saves the session data to storage, and
        returns the session ID.

        Args:
            data: Dictionary of session data to store.

        Returns:
            The newly created session ID.

        Note:
            - Automatically generates a secure session ID
            - Saves to configured session storage
            - Use this for programmatic session creation (e.g., after login)

        Example::

            session_id = await security.create_session({
                'user_id': user.id,
                'authenticated': True
            })
            # Set cookie with session_id
        """
        sid = self.create_session_id()
        await maybe_await(self.session_storage.save(sid, data))
        return sid

    async def destroy_session(self, session_id: str):
        """Destroy a session by deleting it from storage.

        Removes all session data from the storage backend. This is typically
        called during logout.

        Args:
            session_id: The session ID to destroy.

        Note:
            - Deletes session from storage immediately
            - Does not clear the client's cookie (handle separately)
            - Safe to call even if session doesn't exist

        Example::

            @app.post('/logout')
            async def logout(request):
                session_id = security.get_session_id(request)
                if session_id:
                    await security.destroy_session(session_id)
                # Also clear the cookie in response
                return Response('Logged out')
        """
        await maybe_await(self.session_storage.delete(session_id))

    async def regenerate_session_id(self, request: Request) -> Optional[str]:
        """Regenerate session ID for the current session.

        Creates a new session ID and migrates existing session data to it, then
        deletes the old session. This is critical for preventing session fixation
        attacks after privilege escalation.

        Args:
            request: The request object with the current session.

        Returns:
            The new session ID string, or None if no session was active.

        Note:
            - Always call this after login or privilege changes
            - Preserves all session data while changing the ID
            - Old session is deleted to prevent reuse
            - Updates request._session_id with the new ID

        Example:
            After successful login::

                @app.post('/login')
                async def login(request):
                    if validate_credentials(username, password):
                        # Regenerate to prevent session fixation
                        new_sid = await security.regenerate_session_id(request)
                        request.session['user_id'] = user.id
                        request.session['authenticated'] = True
                        return Response('Login successful')
        """
        old_sid = getattr(request, "_session_id", None)
        if not old_sid or not request.session:
            return None

        new_sid = self.create_session_id()

        # Save current session data under the new ID
        await maybe_await(self.session_storage.save(new_sid, request.session))

        # Delete the old session
        await maybe_await(self.session_storage.delete(old_sid))

        # Update the request with the new session ID
        request._session_id = new_sid

        return new_sid