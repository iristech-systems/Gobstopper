"""
MCP decorators for defining tools, resources, and prompts.

These decorators provide a clean way to register MCP components
on an MCP server instance.
"""

import functools
from typing import Any, Callable, Optional, Union


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[set[str]] = None,
    enabled: bool = True,
):
    """
    Decorator to register a function as an MCP tool.

    The function's type hints are used to automatically generate
    the tool's input schema.

    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to docstring)
        tags: Tags for filtering/visibility
        enabled: Whether tool is enabled

    Example:
        @mcp.tool()
        async def search(query: str, limit: int = 10) -> list[dict]:
            \"\"\"Search for documents matching query.\"\"\"
            return await db.search(query, limit)

        @mcp.tool(tags={"admin"})
        async def admin_only():
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Attach tool metadata to the function
        func._mcp_tool = True
        func._mcp_tool_name = name
        func._mcp_tool_description = description or func.__doc__ or ""
        func._mcp_tool_tags = tags or set()
        func._mcp_tool_enabled = enabled

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        # Preserve async nature
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def resource(
    uri: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    mime_type: Optional[str] = None,
    tags: Optional[set[str]] = None,
    enabled: bool = True,
):
    """
    Decorator to register a function as an MCP resource.

    Resources are URI-addressable data sources that AI can read.

    Args:
        uri: Resource URI (e.g., "knowledge://chunks/{id}")
        name: Resource name (defaults to function name)
        description: Resource description
        mime_type: MIME type of the resource content
        tags: Tags for filtering/visibility
        enabled: Whether resource is enabled

    Example:
        @mcp.resource("config://app")
        def get_config() -> dict:
            \"\"\"Return application configuration.\"\"\"
            return {"version": "1.0"}

        @mcp.resource("knowledge://chunks/{id}")
        async def get_chunk(id: str) -> dict:
            return await db.chunks.get(id)
    """

    def decorator(func: Callable) -> Callable:
        func._mcp_resource = True
        func._mcp_resource_uri = uri
        func._mcp_resource_name = name
        func._mcp_resource_description = description or func.__doc__ or ""
        func._mcp_resource_mime_type = mime_type or "application/json"
        func._mcp_resource_tags = tags or set()
        func._mcp_resource_enabled = enabled

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def resource_template(
    uri_template: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    mime_type: Optional[str] = None,
    tags: Optional[set[str]] = None,
    enabled: bool = True,
):
    """
    Decorator to register a resource template.

    Resource templates use URI patterns with variables that get
    expanded when a client reads the resource.

    Args:
        uri_template: URI template (e.g., "users://{user_id}/profile")
        name: Template name
        description: Template description
        mime_type: MIME type of the resource content
        tags: Tags for filtering/visibility
        enabled: Whether template is enabled

    Example:
        @mcp.resource_template("users://{user_id}/profile")
        async def get_user_profile(user_id: str) -> dict:
            return await db.users.get(user_id)
    """

    def decorator(func: Callable) -> Callable:
        func._mcp_resource_template = True
        func._mcp_resource_uri = uri_template
        func._mcp_resource_name = name
        func._mcp_resource_description = description or func.__doc__ or ""
        func._mcp_resource_mime_type = mime_type or "application/json"
        func._mcp_resource_tags = tags or set()
        func._mcp_resource_enabled = enabled

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def prompt(
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[set[str]] = None,
    enabled: bool = True,
):
    """
    Decorator to register a function as an MCP prompt.

    Prompts are reusable message templates that guide AI interactions.

    Args:
        name: Prompt name (defaults to function name)
        description: Prompt description
        tags: Tags for filtering/visibility
        enabled: Whether prompt is enabled

    Example:
        @mcp.prompt()
        def analyze_blocker(blocker: str, impact: str) -> str:
            \"\"\"
            Generate a comprehensive analysis of a blocker.

            Args:
                blocker: Description of the blocker
                impact: Impact assessment
            \"\"\"
            return f\"\"\"
            Please analyze this blocker:

            Blocker: {blocker}
            Impact: {impact}

            Provide a structured analysis with:
            1. Root cause
            2. Affected stakeholders
            3. Recommended resolution
            \"\"\"
    """

    def decorator(func: Callable) -> Callable:
        func._mcp_prompt = True
        func._mcp_prompt_name = name
        func._mcp_prompt_description = description or func.__doc__ or ""
        func._mcp_prompt_tags = tags or set()
        func._mcp_prompt_enabled = enabled

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def get_tool_metadata(func: Callable) -> Optional[dict]:
    """Extract MCP tool metadata from a decorated function."""
    if not getattr(func, "_mcp_tool", False):
        return None
    return {
        "name": func._mcp_tool_name,
        "description": func._mcp_tool_description,
        "tags": func._mcp_tool_tags,
        "enabled": func._mcp_tool_enabled,
        "func": func,
    }


def get_resource_metadata(func: Callable) -> Optional[dict]:
    """Extract MCP resource metadata from a decorated function."""
    if getattr(func, "_mcp_resource", False):
        return {
            "uri": func._mcp_resource_uri,
            "name": func._mcp_resource_name,
            "description": func._mcp_resource_description,
            "mime_type": func._mcp_resource_mime_type,
            "tags": func._mcp_resource_tags,
            "enabled": func._mcp_resource_enabled,
            "is_template": False,
            "func": func,
        }
    if getattr(func, "_mcp_resource_template", False):
        return {
            "uri": func._mcp_resource_uri,
            "name": func._mcp_resource_name,
            "description": func._mcp_resource_description,
            "mime_type": func._mcp_resource_mime_type,
            "tags": func._mcp_resource_tags,
            "enabled": func._mcp_resource_enabled,
            "is_template": True,
            "func": func,
        }
    return None


def get_prompt_metadata(func: Callable) -> Optional[dict]:
    """Extract MCP prompt metadata from a decorated function."""
    if not getattr(func, "_mcp_prompt", False):
        return None
    return {
        "name": func._mcp_prompt_name,
        "description": func._mcp_prompt_description,
        "tags": func._mcp_prompt_tags,
        "enabled": func._mcp_prompt_enabled,
        "func": func,
    }
