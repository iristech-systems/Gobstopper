"""
MCP Authentication and authorization integration.

Provides integration with Gobstopper's SecurityMiddleware for
securing MCP endpoints and component-level auth.
"""

from typing import Any, Callable, Dict, Optional, Set
from dataclasses import dataclass
import hashlib
import hmac
import secrets


@dataclass
class AuthContext:
    """Authentication context for an MCP request."""

    user_id: Optional[str] = None
    session_id: Optional[str] = None
    roles: Set[str] = set()
    authenticated: bool = False


class MCPAuth:
    """
    MCP authentication handler.

    Provides authentication and authorization for MCP servers.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_expiry: int = 3600,
    ):
        """
        Initialize MCP auth.

        Args:
            secret_key: Secret for signing tokens
            token_expiry: Token expiry time in seconds
        """
        self.secret_key = secret_key or secrets.token_hex(32)
        self.token_expiry = token_expiry

    def generate_token(
        self,
        user_id: str,
        roles: Optional[Set[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate an MCP auth token.

        Args:
            user_id: User identifier
            roles: User roles
            extra: Extra data to include in token

        Returns:
            Signed token string
        """
        import json
        import time

        payload = {
            "user_id": user_id,
            "roles": list(roles or []),
            "extra": extra or {},
            "exp": time.time() + self.token_expiry,
            "nonce": secrets.token_hex(8),
        }

        payload_str = json.dumps(payload, sort_keys=True)
        payload_b64 = __import__("base64").b64encode(payload_str.encode()).decode()

        signature = hmac.new(
            self.secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode an MCP auth token.

        Args:
            token: Token to verify

        Returns:
            Token payload if valid, None if invalid
        """
        import json
        import time
        import base64

        try:
            payload_b64, signature = token.split(".", 1)

            expected_sig = hmac.new(
                self.secret_key.encode(),
                payload_b64.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            payload_str = base64.b64decode(payload_b64).decode()
            payload = json.loads(payload_str)

            if payload.get("exp", 0) < time.time():
                return None

            return payload
        except (ValueError, json.JSONDecodeError):
            return None

    def get_auth_context(self, token: Optional[str]) -> AuthContext:
        """
        Get auth context from token.

        Args:
            token: Auth token (from Authorization header)

        Returns:
            AuthContext with user info
        """
        if not token:
            return AuthContext()

        if token.startswith("Bearer "):
            token = token[7:]

        payload = self.verify_token(token)
        if not payload:
            return AuthContext()

        return AuthContext(
            user_id=payload.get("user_id"),
            session_id=payload.get("session_id"),
            roles=set(payload.get("roles", [])),
            authenticated=True,
        )


class ComponentAuth:
    """
    Component-level authorization for MCP.

    Allows securing individual tools, resources, and prompts
    based on user roles.
    """

    def __init__(self, auth: MCPAuth):
        self.auth = auth
        self._tool_auth: Dict[str, Callable[[AuthContext], bool]] = {}
        self._resource_auth: Dict[str, Callable[[AuthContext], bool]] = {}
        self._prompt_auth: Dict[str, Callable[[AuthContext], bool]] = {}

    def require_tool(self, tool_name: str, *required_roles: str):
        """
        Decorator to require specific roles for a tool.

        Args:
            tool_name: Name of the tool
            *required_roles: Roles that can access this tool

        Example:
            @component_auth.require_tool("admin_tool", "admin")
            async def admin_tool():
                ...
        """

        def decorator(func: Callable) -> Callable:
            self._tool_auth[tool_name] = lambda ctx: bool(
                ctx.authenticated
                and (
                    "admin" in ctx.roles or any(r in ctx.roles for r in required_roles)
                )
            )
            return func

        return decorator

    def require_resource(self, uri: str, *required_roles: str):
        """
        Decorator to require specific roles for a resource.

        Args:
            uri: Resource URI pattern
            *required_roles: Roles that can access this resource
        """

        def decorator(func: Callable) -> Callable:
            self._resource_auth[uri] = lambda ctx: bool(
                ctx.authenticated
                and (
                    "admin" in ctx.roles or any(r in ctx.roles for r in required_roles)
                )
            )
            return func

        return decorator

    def check_tool_access(self, tool_name: str, context: AuthContext) -> bool:
        """Check if user can access a tool."""
        checker = self._tool_auth.get(tool_name)
        if checker:
            return checker(context)
        return True  # No auth required

    def check_resource_access(self, uri: str, context: AuthContext) -> bool:
        """Check if user can access a resource."""
        checker = self._resource_auth.get(uri)
        if checker:
            return checker(context)
        return True  # No auth required


class GobstopperSessionAuth:
    """
    Integration with Gobstopper SecurityMiddleware sessions.

    Extracts auth context from Gobstopper request sessions.
    """

    def __init__(self, security_middleware):
        self.security = security_middleware

    def get_context_from_session(self, session: Dict[str, Any]) -> AuthContext:
        """
        Extract auth context from Gobstopper session.

        Args:
            session: Gobstopper session dict

        Returns:
            AuthContext with user info from session
        """
        if not session:
            return AuthContext()

        user = session.get("user", {})
        if not user:
            return AuthContext()

        return AuthContext(
            user_id=user.get("id") or user.get("username"),
            session_id=session.get("session_id"),
            roles=set(user.get("roles", [])),
            authenticated=bool(user.get("is_authenticated")),
        )
