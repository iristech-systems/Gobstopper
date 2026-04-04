"""
MCP Client for calling external MCP servers.

Provides a client interface to interact with MCP servers,
supporting tools, resources, and prompts.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result from calling an MCP tool."""

    content: List[Dict[str, Any]]
    is_error: bool = False

    @property
    def text(self) -> str:
        """Get text content from result."""
        for item in self.content:
            if item.get("type") == "text":
                return item.get("text", "")
        return ""

    def json(self) -> Any:
        """Parse text content as JSON."""
        text = self.text
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return None


@dataclass
class ResourceContent:
    """A resource content item."""

    uri: str
    mime_type: str
    text: str = ""
    blob: Optional[str] = None


@dataclass
class PromptMessage:
    """A prompt message."""

    role: str
    content: Dict[str, Any]


class MCPClient:
    """
    Client for calling external MCP servers.

    Supports calling tools, reading resources, and getting prompts.

    Example:
        client = MCPClient("http://localhost:9000")

        # Call a tool
        result = await client.call_tool("search", {"query": "hello"})
        print(result.text)

        # Read a resource
        resource = await client.read_resource("config://app")
        print(resource.text)

        # Get a prompt
        prompt = await client.get_prompt("analyze", {"text": "hello"})
        print(prompt)
    """

    def __init__(
        self,
        url: str = "http://localhost:9000",
        timeout: float = 30.0,
    ):
        """
        Initialize MCP client.

        Args:
            url: Base URL of MCP server
            timeout: Request timeout in seconds
        """
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._session_id: Optional[str] = None

    async def _post(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request to the MCP server."""
        import urllib.request
        import urllib.error

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": id(self),
        }

        data = json.dumps(request).encode("utf-8")

        req = urllib.request.Request(
            f"{self.url}/mcp",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))

                if "error" in result:
                    raise ValueError(f"MCP error: {result['error']}")

                return result.get("result", {})
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise ValueError(f"HTTP error {e.code}: {error_body}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools on the server."""
        result = await self._post("tools/list", {})
        return result.get("tools", [])

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources on the server."""
        result = await self._post("resources/list", {})
        return result.get("resources", [])

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts on the server."""
        result = await self._post("prompts/list", {})
        return result.get("prompts", [])

    async def call_tool(
        self, name: str, arguments: Dict[str, Any] = None
    ) -> ToolResult:
        """
        Call a tool on the server.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            ToolResult with content and optional error flag
        """
        arguments = arguments or {}
        result = await self._post(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )

        content = result.get("content", [])
        is_error = result.get("isError", False)

        return ToolResult(content=content, is_error=is_error)

    async def read_resource(self, uri: str) -> ResourceContent:
        """
        Read a resource from the server.

        Args:
            uri: Resource URI

        Returns:
            ResourceContent with the resource data
        """
        result = await self._post("resources/read", {"uri": uri})

        contents = result.get("contents", [])
        if not contents:
            raise ValueError(f"No content returned for resource: {uri}")

        content = contents[0]
        return ResourceContent(
            uri=content.get("uri", uri),
            mime_type=content.get("mimeType", "text/plain"),
            text=content.get("text", ""),
            blob=content.get("blob"),
        )

    async def get_prompt(self, name: str, arguments: Dict[str, Any] = None) -> str:
        """
        Get a rendered prompt from the server.

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            Rendered prompt text
        """
        arguments = arguments or {}
        result = await self._post(
            "prompts/get",
            {
                "name": name,
                "arguments": arguments,
            },
        )

        messages = result.get("messages", [])
        if not messages:
            return ""

        # Return content of first message
        first = messages[0]
        content = first.get("content", {})
        if content.get("type") == "text":
            return content.get("text", "")

        return str(content)

    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize the MCP session.

        Returns server manifest.
        """
        result = await self._post(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "gobstopper-mcp-client",
                    "version": "0.1.0",
                },
            },
        )

        self._session_id = result.get("sessionId")
        return result


class MCPToolProxy:
    """
    A proxy that wraps an MCP tool for local use.

    Provides a callable interface to an MCP tool on a remote server.

    Example:
        client = MCPClient("http://localhost:9000")

        search = MCPToolProxy(client, "search")
        result = await search(query="hello", limit=10)
    """

    def __init__(self, client: MCPClient, tool_name: str):
        self.client = client
        self.tool_name = tool_name

    async def __call__(self, **kwargs) -> ToolResult:
        """Call the remote tool."""
        return await self.client.call_tool(self.tool_name, kwargs)


class MCPResourceProxy:
    """
    A proxy that wraps an MCP resource for local use.

    Provides a property-like interface to an MCP resource on a remote server.

    Example:
        client = MCPClient("http://localhost:9000")

        config = MCPResourceProxy(client, "config://app")
        data = await config.read()
    """

    def __init__(self, client: MCPClient, uri: str):
        self.client = client
        self.uri = uri

    async def read(self) -> Any:
        """Read the remote resource."""
        content = await self.client.read_resource(self.uri)
        if content.text:
            try:
                return json.loads(content.text)
            except json.JSONDecodeError:
                return content.text
        return None
