"""
MCP Server implementation for Gobstopper.

Handles MCP protocol communication and component management.
"""

import asyncio
import inspect
import json
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Set, Union
from dataclasses import dataclass, field
from enum import Enum

from .decorators import (
    get_tool_metadata,
    get_resource_metadata,
    get_prompt_metadata,
)


class TransportType(str, Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


@dataclass
class Tool:
    """Represents an MCP tool."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable
    tags: Set[str] = field(default_factory=set)
    enabled: bool = True

    async def run(self, arguments: Dict[str, Any]) -> Any:
        """Execute the tool with given arguments."""
        result = self.handler(**arguments)
        if asyncio.iscoroutine(result):
            return await result
        return result


@dataclass
class Resource:
    """Represents an MCP resource."""

    uri: str
    name: str
    description: str
    mime_type: str
    handler: Callable
    tags: Set[str] = field(default_factory=set)
    enabled: bool = True
    is_template: bool = False

    async def read(self, uri_params: Dict[str, str] = None) -> Any:
        """Read the resource."""
        args = uri_params or {}
        result = self.handler(**args)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def matches(self, uri: str) -> Optional[Dict[str, str]]:
        """Check if URI matches this resource template and extract params."""
        if not self.is_template:
            return {} if uri == self.uri else None

        # Convert URI template to regex
        pattern = self.uri
        for match in re.finditer(r"\{([^}]+)\}", pattern):
            param_name = match.group(1)
            pattern = pattern.replace(
                "{" + param_name + "}", f"(?P<{param_name}>[^/]+)"
            )
        pattern = f"^{pattern}$"

        match = re.match(pattern, uri)
        if match:
            return match.groupdict()
        return None


@dataclass
class Prompt:
    """Represents an MCP prompt."""

    name: str
    description: str
    arguments: List[Dict[str, Any]]
    handler: Callable
    tags: Set[str] = field(default_factory=set)
    enabled: bool = True

    async def render(self, arguments: Dict[str, Any]) -> str:
        """Render the prompt with given arguments."""
        result = self.handler(**arguments)
        if asyncio.iscoroutine(result):
            return await result
        return result


class MCPServer:
    """
    MCP Server for Gobstopper applications.

    Manages tools, resources, and prompts, and handles MCP protocol requests.

    Example:
        mcp = MCPServer(name="my_server")

        @mcp.tool()
        async def search(query: str):
            return [{"id": 1, "text": query}]

        @mcp.resource("config://app")
        def get_config():
            return {"version": "1.0"}

        @mcp.prompt()
        def analyze(text: str) -> str:
            return f"Please analyze: {text}"
    """

    def __init__(
        self,
        name: str = "gobstopper-mcp",
        version: str = "1.0.0",
        instructions: Optional[str] = None,
    ):
        self.name = name
        self.version = version
        self.instructions = instructions

        self._tools: Dict[str, Tool] = {}
        self._resources: Dict[str, Resource] = {}
        self._resource_templates: List[Resource] = []
        self._prompts: Dict[str, Prompt] = {}

        self._middleware: List[Callable] = []
        self._tags_enabled: Optional[Set[str]] = None
        self._tags_disabled: Set[str] = set()

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        enabled: bool = True,
    ):
        """
        Decorator to register a tool.

        Args:
            name: Tool name (defaults to function name)
            description: Tool description (defaults to docstring)
            tags: Tags for filtering
            enabled: Whether tool is enabled
        """

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or ""

            # Build input schema from type hints
            input_schema = self._build_input_schema(func)

            tool = Tool(
                name=tool_name,
                description=tool_desc,
                input_schema=input_schema,
                handler=func,
                tags=tags or set(),
                enabled=enabled,
            )
            self._tools[tool_name] = tool

            return func

        return decorator

    def resource(
        self,
        uri: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: str = "application/json",
        tags: Optional[Set[str]] = None,
        enabled: bool = True,
    ):
        """
        Decorator to register a resource.
        """

        def decorator(func: Callable) -> Callable:
            resource = Resource(
                uri=uri,
                name=name or func.__name__,
                description=description or func.__doc__ or "",
                mime_type=mime_type,
                handler=func,
                tags=tags or set(),
                enabled=enabled,
                is_template=False,
            )
            self._resources[uri] = resource
            return func

        return decorator

    def resource_template(
        self,
        uri_template: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: str = "application/json",
        tags: Optional[Set[str]] = None,
        enabled: bool = True,
    ):
        """
        Decorator to register a resource template.
        """

        def decorator(func: Callable) -> Callable:
            resource = Resource(
                uri=uri_template,
                name=name or func.__name__,
                description=description or func.__doc__ or "",
                mime_type=mime_type,
                handler=func,
                tags=tags or set(),
                enabled=enabled,
                is_template=True,
            )
            self._resource_templates.append(resource)
            return func

        return decorator

    def prompt(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        enabled: bool = True,
    ):
        """
        Decorator to register a prompt.
        """

        def decorator(func: Callable) -> Callable:
            prompt_name = name or func.__name__

            # Build arguments from type hints
            arguments = self._build_prompt_arguments(func)

            p = Prompt(
                name=prompt_name,
                description=description or func.__doc__ or "",
                arguments=arguments,
                handler=func,
                tags=tags or set(),
                enabled=enabled,
            )
            self._prompts[prompt_name] = p
            return func

        return decorator

    def _build_input_schema(self, func: Callable) -> Dict[str, Any]:
        """Build JSON schema from function type hints."""
        hints = func.__annotations__
        sig = inspect.signature(func)

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("return", "self"):
                continue

            # Get type hint
            hint = hints.get(param_name, str)
            json_type = self._python_type_to_json_type(hint)

            properties[param_name] = {
                "type": json_type,
                "description": "",  # Could add docstring parsing
            }

            # Check if required
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
            else:
                properties[param_name]["default"] = param.default

        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return schema

    def _build_prompt_arguments(self, func: Callable) -> List[Dict[str, Any]]:
        """Build prompt argument list from function type hints."""
        hints = func.__annotations__
        sig = inspect.signature(func)

        arguments = []

        for param_name, param in sig.parameters.items():
            if param_name in ("return", "self"):
                continue

            hint = hints.get(param_name, str)

            arg = {
                "name": param_name,
                "description": "",
                "required": param.default is inspect.Parameter.empty,
            }

            if param.default is not inspect.Parameter.empty:
                arg["default"] = param.default

            arguments.append(arg)

        return arguments

    def _python_type_to_json_type(self, hint: Any) -> str:
        """Convert Python type hint to JSON schema type."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        # Handle Optional types
        origin = getattr(hint, "__origin__", None)
        if origin is Union:
            # Get the non-None type
            args = getattr(hint, "__args__", ())
            for arg in args:
                if arg is type(None):
                    continue
                return self._python_type_to_json_type(arg)

        # Handle generic types like List[str]
        if origin is list:
            return "array"
        if origin is dict:
            return "object"

        # Handle regular types
        for py_type, json_type in type_map.items():
            if hint is py_type:
                return json_type

        return "string"  # Default to string

    def enable_tags(self, tags: Set[str], only: bool = False) -> "MCPServer":
        """Enable tags for component visibility."""
        self._tags_enabled = tags
        return self

    def disable_tags(self, tags: Set[str]) -> "MCPServer":
        """Disable tags for component visibility."""
        self._tags_disabled.update(tags)
        return self

    def _is_visible(self, component: Union[Tool, Resource, Prompt]) -> bool:
        """Check if a component is visible based on tags."""
        if not component.enabled:
            return False

        if self._tags_disabled:
            if component.tags & self._tags_disabled:
                return False

        if self._tags_enabled:
            if not (component.tags & self._tags_enabled):
                return False

        return True

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all visible tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
            if self._is_visible(t)
        ]

    def list_resources(self) -> List[Dict[str, Any]]:
        """List all visible resources."""
        return [
            {
                "uri": r.uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
            }
            for r in self._resources.values()
            if self._is_visible(r)
        ]

    def list_resource_templates(self) -> List[Dict[str, Any]]:
        """List all visible resource templates."""
        return [
            {
                "uriTemplate": r.uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
            }
            for r in self._resource_templates
            if self._is_visible(r)
        ]

    def list_prompts(self) -> List[Dict[str, Any]]:
        """List all visible prompts."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "arguments": p.arguments,
            }
            for p in self._prompts.values()
            if self._is_visible(p)
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool by name with arguments."""
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")

        tool = self._tools[name]

        if not self._is_visible(tool):
            raise ValueError(f"Tool not found: {name}")

        try:
            result = await tool.run(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource by URI."""
        # Check direct resources first
        if uri in self._resources:
            resource = self._resources[uri]
            if not self._is_visible(resource):
                raise ValueError(f"Resource not found: {uri}")

            result = await resource.read()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": resource.mime_type,
                        "text": json.dumps(result),
                    }
                ]
            }

        # Check templates
        for template in self._resource_templates:
            params = template.matches(uri)
            if params is not None:
                if not self._is_visible(template):
                    raise ValueError(f"Resource not found: {uri}")

                result = await template.read(params)
                return {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": template.mime_type,
                            "text": json.dumps(result),
                        }
                    ]
                }

        raise ValueError(f"Resource not found: {uri}")

    async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a rendered prompt."""
        if name not in self._prompts:
            raise ValueError(f"Prompt not found: {name}")

        prompt = self._prompts[name]

        if not self._is_visible(prompt):
            raise ValueError(f"Prompt not found: {name}")

        result = await prompt.render(arguments)
        return {
            "messages": [{"role": "user", "content": {"type": "text", "text": result}}]
        }

    def get_manifest(self) -> Dict[str, Any]:
        """Get the server manifest for MCP handshake."""
        return {
            "name": self.name,
            "version": self.version,
            "instructions": self.instructions,
            "tools": self.list_tools(),
            "resources": self.list_resources(),
            "resourceTemplates": self.list_resource_templates(),
            "prompts": self.list_prompts(),
        }

    def get_initialize_response(self) -> Dict[str, Any]:
        """Return MCP initialize response in protocol-compatible shape."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
            "instructions": self.instructions or "",
        }

    async def handle_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle an MCP protocol request directly on MCPServer."""
        if method == "tools/list":
            return {"tools": self.list_tools()}

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            return await self.call_tool(name, arguments)

        if method == "resources/list":
            return {
                "resources": self.list_resources(),
                "resourceTemplates": self.list_resource_templates(),
            }

        if method == "resources/read":
            uri = params.get("uri")
            return await self.read_resource(uri)

        if method == "prompts/list":
            return {"prompts": self.list_prompts()}

        if method == "prompts/get":
            name = params.get("name")
            arguments = params.get("arguments", {})
            return await self.get_prompt(name, arguments)

        if method == "initialize":
            return self.get_initialize_response()

        raise ValueError(f"Unknown method: {method}")


class MCP:
    """
    Gobstopper MCP extension.

    Provides MCP server functionality integrated with Gobstopper applications
    or blueprints. Supports namespace-scoped tools for blueprint integration.

    Example - App-level MCP:
        from gobstopper import Gobstopper
        from gobstopper.extensions.mcp import MCP

        app = Gobstopper(__name__)
        mcp = MCP(app)

        @mcp.tool()
        async def search(query: str, limit: int = 10):
            \"\"\"Search the knowledge base.\"\"\"
            return [{"id": 1, "text": query}]

        mcp.mount(app, path="/mcp")

    Example - Blueprint-level MCP:
        from gobstopper import Gobstopper
        from gobstopper.core.blueprint import Blueprint
        from gobstopper.extensions.mcp import MCP

        app = Gobstopper(__name__)
        admin_bp = Blueprint("admin", url_prefix="/admin")
        admin_mcp = MCP(blueprint=admin_bp, namespace="admin")

        @admin_mcp.tool()
        async def admin_stats():
            \"\"\"Admin-only statistics.\"\"\"
            return {"users": 100}

        app.register_blueprint(admin_bp)
        admin_mcp.mount(app, path="/admin/mcp")

    Example - Multiple namespaced MCP endpoints:
        # Public tools at /mcp
        public_mcp = MCP(app, namespace="public")
        # Admin tools at /admin/mcp
        admin_mcp = MCP(blueprint=admin_bp, namespace="admin")
    """

    def __init__(
        self,
        app=None,
        blueprint=None,
        name: str = "gobstopper-mcp",
        version: str = "1.0.0",
        instructions: Optional[str] = None,
        namespace: Optional[str] = None,
    ):
        """
        Initialize MCP extension.

        Args:
            app: Gobstopper app instance (for app-level MCP)
            blueprint: Blueprint instance (for blueprint-level MCP)
            name: Server name
            version: Server version
            instructions: Usage instructions for AI clients
            namespace: Prefix for all tool/resource names (e.g., "admin" → "admin_search")
        """
        if app is None and blueprint is None:
            raise ValueError("Must provide either app or blueprint")

        self.app = app
        self.blueprint = blueprint
        self.namespace = namespace

        server_name = name
        if namespace:
            server_name = f"{namespace}-{name}"

        self.server = MCPServer(
            name=server_name, version=version, instructions=instructions
        )

        # Alias decorators to server methods (with namespace support)
        self.tool = self._namespaced_tool()
        if namespace:
            self.resource, self.resource_template = self._namespaced_resource()
        else:
            self.resource = self.server.resource
            self.resource_template = self.server.resource_template
        self.prompt = self.server.prompt

    def _namespaced_tool(self):
        """Return a tool decorator that adds namespace prefix."""
        original_tool = self.server.tool

        def tool_decorator(
            name: Optional[str] = None,
            description: Optional[str] = None,
            tags: Optional[Set[str]] = None,
            enabled: bool = True,
        ):
            def decorator(func):
                tool_name = name or func.__name__
                if self.namespace:
                    tool_name = f"{self.namespace}_{tool_name}"
                return original_tool(
                    name=tool_name,
                    description=description,
                    tags=tags,
                    enabled=enabled,
                )(func)

            return decorator

        return tool_decorator

    def _namespaced_resource(self):
        """Return a resource decorator that adds namespace prefix to URI."""
        original_resource = self.server.resource
        original_template = self.server.resource_template

        def resource_decorator(
            uri: str,
            name: Optional[str] = None,
            description: Optional[str] = None,
            mime_type: str = "application/json",
            tags: Optional[Set[str]] = None,
            enabled: bool = True,
        ):
            def decorator(func):
                # Prefix URI with namespace
                prefixed_uri = uri
                if self.namespace:
                    if "://" in uri:
                        protocol, path = uri.split("://", 1)
                        prefixed_uri = f"{protocol}://{self.namespace}/{path}"
                    else:
                        prefixed_uri = f"{self.namespace}:{uri}"

                return original_resource(
                    uri=prefixed_uri,
                    name=name,
                    description=description,
                    mime_type=mime_type,
                    tags=tags,
                    enabled=enabled,
                )(func)

            return decorator

        def resource_template_decorator(
            uri_template: str,
            name: Optional[str] = None,
            description: Optional[str] = None,
            mime_type: str = "application/json",
            tags: Optional[Set[str]] = None,
            enabled: bool = True,
        ):
            def decorator(func):
                prefixed_uri = uri_template
                if self.namespace:
                    if "://" in uri_template:
                        protocol, path = uri_template.split("://", 1)
                        prefixed_uri = f"{protocol}://{self.namespace}/{path}"
                    else:
                        prefixed_uri = f"{self.namespace}:{uri_template}"

                return original_template(
                    uri_template=prefixed_uri,
                    name=name,
                    description=description,
                    mime_type=mime_type,
                    tags=tags,
                    enabled=enabled,
                )(func)

            return decorator

        # Return tuple of decorators
        return resource_decorator, resource_template_decorator

    def enable_tags(self, tags: Set[str], only: bool = False) -> "MCP":
        """Enable tags for component visibility."""
        self.server.enable_tags(tags, only)
        return self

    def disable_tags(self, tags: Set[str]) -> "MCP":
        """Disable tags for component visibility."""
        self.server.disable_tags(tags)
        return self

    def mount(self, app=None, path: Optional[str] = None):
        """
        Mount MCP endpoint on a Gobstopper app served by Granian/RSGI.

        This is the primary method for production use. MCP is served by the
        same Granian server that runs your application.

        For blueprint-level MCP, path defaults to "{blueprint_url_prefix}/mcp".

        Args:
            app: Gobstopper app instance (uses self.app if not provided)
            path: URL path for MCP endpoint (default "/mcp" or blueprint-prefixed)
        """
        from .transport import mount_mcp

        if app is None:
            app = self.app

        if path is None:
            if self.blueprint:
                prefix = self.blueprint.url_prefix or ""
                path = f"{prefix}/mcp".replace("//", "/")
            else:
                path = "/mcp"

        mount_mcp(app, path, self.server)

    def run(self, transport: str = "stdio"):
        """
        Run MCP server standalone.

        NOTE: For production deployments with Gobstopper, always use mount()
        to integrate MCP with your app served by Granian. This run() method
        is only for standalone MCP servers (e.g., Claude Desktop subprocess).

        Args:
            transport: Only "stdio" is supported for standalone mode
        """
        if transport == "stdio":
            from .transport import STDIOTransport

            t = STDIOTransport(self.server)
            t.run()
        else:
            raise ValueError(
                f"Standalone transport '{transport}' not supported. "
                "Use mcp.mount(app) for production deployments."
            )

    async def handle_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle an MCP protocol request."""
        if method == "tools/list":
            return {"tools": self.server.list_tools()}

        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            return await self.server.call_tool(name, arguments)

        elif method == "resources/list":
            return {
                "resources": self.server.list_resources(),
                "resourceTemplates": self.server.list_resource_templates(),
            }

        elif method == "resources/read":
            uri = params.get("uri")
            return await self.server.read_resource(uri)

        elif method == "prompts/list":
            return {"prompts": self.server.list_prompts()}

        elif method == "prompts/get":
            name = params.get("name")
            arguments = params.get("arguments", {})
            return await self.server.get_prompt(name, arguments)

        elif method == "initialize":
            return self.server.get_initialize_response()

        else:
            raise ValueError(f"Unknown method: {method}")
