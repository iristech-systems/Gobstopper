"""
MCP Providers for dynamic component sources.

Providers allow components (tools, resources, prompts) to be
dynamically generated at request time from external sources
like databases, APIs, or other systems.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set


class Provider(ABC):
    """
    Base class for MCP component providers.

    Providers can dynamically supply tools, resources, and prompts
    at request time, enabling dynamic component catalogs.

    Example:
        class DatabaseProvider(Provider):
            async def list_tools(self):
                # Fetch tools from database
                tools = await db.query("SELECT * FROM tools WHERE active = true")
                return [self._tool_from_row(row) for row in tools]
    """

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from this provider."""
        return []

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources from this provider."""
        return []

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts from this provider."""
        return []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool from this provider.

        Default implementation calls the registered handler.
        Override to implement custom routing.
        """
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support tool calls"
        )

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a resource from this provider.

        Default implementation reads the registered resource.
        Override to implement custom routing.
        """
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support resource reads"
        )

    async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a prompt from this provider.

        Default implementation gets the registered prompt.
        Override to implement custom routing.
        """
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support prompts"
        )


class LocalProvider(Provider):
    """
    Provider that manages locally registered components.

    This is the default provider that stores tools, resources,
    and prompts registered via decorators.
    """

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._resources: Dict[str, Callable] = {}
        self._prompts: Dict[str, Callable] = {}

    def add_tool(self, name: str, handler: Callable):
        """Add a tool handler."""
        self._tools[name] = handler

    def add_resource(self, uri: str, handler: Callable):
        """Add a resource handler."""
        self._resources[uri] = handler

    def add_prompt(self, name: str, handler: Callable):
        """Add a prompt handler."""
        self._prompts[name] = handler

    def remove_tool(self, name: str):
        """Remove a tool."""
        self._tools.pop(name, None)

    def remove_resource(self, uri: str):
        """Remove a resource."""
        self._resources.pop(uri, None)

    def remove_prompt(self, name: str):
        """Remove a prompt."""
        self._prompts.pop(name, None)

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools."""
        return [
            {
                "name": name,
                "description": handler.__doc__ or "",
                "inputSchema": _build_schema(handler),
            }
            for name, handler in self._tools.items()
        ]

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List all registered resources."""
        return [
            {
                "uri": uri,
                "name": handler.__name__,
                "description": handler.__doc__ or "",
                "mimeType": "application/json",
            }
            for uri, handler in self._resources.items()
        ]

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List all registered prompts."""
        return [
            {
                "name": name,
                "description": handler.__doc__ or "",
                "arguments": _build_arguments(handler),
            }
            for name, handler in self._prompts.items()
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a registered tool."""
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")

        handler = self._tools[name]
        result = handler(**arguments)

        if asyncio.iscoroutine(result):
            result = await result

        return {
            "content": [{"type": "text", "text": str(result)}],
        }

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a registered resource."""
        if uri not in self._resources:
            raise ValueError(f"Resource not found: {uri}")

        handler = self._resources[uri]
        result = handler()

        if asyncio.iscoroutine(result):
            result = await result

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": str(result),
                }
            ],
        }

    async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a registered prompt."""
        if name not in self._prompts:
            raise ValueError(f"Prompt not found: {name}")

        handler = self._prompts[name]
        result = handler(**arguments)

        if asyncio.iscoroutine(result):
            result = await result

        return {
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": result},
                }
            ],
        }


class AggregateProvider(Provider):
    """
    Provider that aggregates multiple providers.

    Useful for combining local and external component sources.
    """

    def __init__(self, providers: Optional[List[Provider]] = None):
        self._providers: List[Provider] = providers or []

    def add_provider(self, provider: Provider):
        """Add a provider to the aggregate."""
        self._providers.append(provider)

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List tools from all providers."""
        results = []
        for provider in self._providers:
            results.extend(await provider.list_tools())
        return results

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List resources from all providers."""
        results = []
        for provider in self._providers:
            results.extend(await provider.list_resources())
        return results

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List prompts from all providers."""
        results = []
        for provider in self._providers:
            results.extend(await provider.list_prompts())
        return results


class DatabaseProvider(Provider):
    """
    Provider that fetches components from a database.

    Example:
        provider = DatabaseProvider(db_pool)

        # Tool definitions stored in DB
        tools = await db.query("SELECT * FROM mcp_tools WHERE active = true")

        # Resource definitions stored in DB
        resources = await db.query("SELECT * FROM mcp_resources WHERE active = true")
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool


class HTTPProvider(Provider):
    """
    Provider that fetches components from a remote HTTP API.

    Example:
        provider = HTTPProvider("https://api.example.com/mcp")
    """

    def __init__(self, base_url: str):
        self.base_url = base_url


def _build_schema(func: Callable) -> Dict[str, Any]:
    """Build input schema from function signature."""
    import inspect

    sig = inspect.signature(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "return"):
            continue

        hint = param.annotation if param.annotation != inspect.Parameter.empty else str
        json_type = _python_type_to_json(hint)

        prop = {"type": json_type}

        if param.default != inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)

        properties[name] = prop

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required

    return schema


def _build_arguments(func: Callable) -> List[Dict[str, Any]]:
    """Build argument list from function signature."""
    import inspect

    sig = inspect.signature(func)
    arguments = []

    for name, param in sig.parameters.items():
        if name in ("self", "return"):
            continue

        arg = {
            "name": name,
            "required": param.default == inspect.Parameter.empty,
        }

        if param.default != inspect.Parameter.empty:
            arg["default"] = param.default

        arguments.append(arg)

    return arguments


def _python_type_to_json(hint: Any) -> str:
    """Convert Python type to JSON schema type."""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    if hint in type_map:
        return type_map[hint]

    return "string"
