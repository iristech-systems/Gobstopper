"""
MCP transports for communication between clients and servers.

IMPORTANT: Gobstopper uses RSGI (Rust Server Gateway Interface) powered by Granian.
For production deployments, always use mcp.mount(app) to integrate MCP with the
same Granian/RSGI server running your application.

STDIO is used for local integration with MCP clients like Claude Desktop.

Example:

    # For Claude Desktop or local MCP clients - uses STDIO
    if __name__ == "__main__":
        mcp.run(transport="stdio")

    # For production (served by Granian) - mounted on your app
    mcp.mount(app, path="/mcp")
"""

import asyncio
import json
import sys
from typing import Any, Dict, Optional
from .server import MCPServer


class STDIOTransport:
    """
    STDIO transport for MCP communication.

    Reads JSON-RPC messages from stdin and writes responses to stdout.
    Used by MCP clients like Claude Desktop running Gobstopper MCP as a subprocess.

    This is the primary transport for local/CLI MCP integrations.

    Example:
        # Claude Desktop config might point to:
        # {"command": "python", "args": ["-m", "myapp", "--mcp-stdio"]}

        server = MCPServer(name="my_server")

        @server.tool()
        def hello(name: str) -> str:
            return f"Hello, {name}!"

        transport = STDIOTransport(server)
        transport.run()
    """

    def __init__(self, server: MCPServer):
        self.server = server
        self._running = False

    def run(self):
        """Run the STDIO transport loop."""
        self._running = True

        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = self._handle_message(request)

                    if response:
                        print(json.dumps(response), flush=True)
                except json.JSONDecodeError:
                    error = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None,
                    }
                    print(json.dumps(error), flush=True)
                except Exception as e:
                    error = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": f"Internal error: {e}"},
                        "id": None,
                    }
                    print(json.dumps(error), flush=True)

        except KeyboardInterrupt:
            self._running = False

    def _handle_message(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle an incoming STDIO message."""
        jsonrpc_version = request.get("jsonrpc")
        if jsonrpc_version != "2.0":
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid Request"},
                "id": request.get("id"),
            }

        method = request.get("method")
        params = request.get("params", {})
        id = request.get("id")

        try:
            # Handle request synchronously for STDIO
            if hasattr(self.server, "handle_request"):
                result = asyncio.run(self.server.handle_request(method, params))
            else:
                result = {}

            return {
                "jsonrpc": "2.0",
                "id": id,
                "result": result,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": id,
                "error": {"code": -32603, "message": str(e)},
            }


async def mcp_handler(request, server: MCPServer):
    """Handle MCP HTTP requests via Gobstopper RSGI."""
    from gobstopper.http.response import JSONResponse, Response

    if request.method == "GET":
        manifest = server.get_manifest()
        return JSONResponse(manifest)

    elif request.method == "POST":
        body = await request.json()

        jsonrpc_version = body.get("jsonrpc")
        if jsonrpc_version != "2.0":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": "Invalid Request"},
                    "id": body.get("id"),
                },
                status=400,
            )

        method = body.get("method")
        params = body.get("params", {})
        id = body.get("id")

        try:
            result = await server.handle_request(method, params)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": result,
                }
            )
        except Exception as e:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": id,
                    "error": {"code": -32603, "message": str(e)},
                }
            )

    return Response("Method not allowed", status=405)


def mount_mcp(app, path: str, server: MCPServer, *, enable_docs: bool = True):
    """
    Mount MCP endpoint on a Gobstopper app served by Granian/RSGI.

    This is the primary way to integrate MCP with a Gobstopper application
    running on Granian/RSGI. MCP endpoints are served by the same server
    as your application.

    By default, also mounts an interactive docs UI at {path}/ui.

    Args:
        app: Gobstopper app instance
        path: URL path for MCP endpoint (e.g., "/mcp")
        server: The MCPServer instance with tools/resources/prompts
        enable_docs: If True (default), also mount docs UI at {path}/ui

    Example:
        app = Gobstopper(__name__)
        mcp = MCP(app)

        @mcp.tool()
        def search(query: str):
            return [{"id": 1}]

        mount_mcp(app, "/mcp", mcp.server)

        # Run with: granian --interface rsgi main:app
        # Docs available at: http://localhost:8000/mcp/ui
    """
    from gobstopper.http.routing import RouteHandler

    async def handler(request):
        return await mcp_handler(request, server)

    route_handler = RouteHandler(path, handler, ["GET", "POST"])

    if getattr(app, "rust_router_available", False):
        app.http_router.insert(path, "GET", route_handler, "mcp_handler")
        app.http_router.insert(path, "POST", route_handler, "mcp_handler")
    else:
        app.routes.append(route_handler)

    app._all_routes.append(route_handler)

    if enable_docs:
        from .docs import attach_mcp_docs

        attach_mcp_docs(app, path, server)
