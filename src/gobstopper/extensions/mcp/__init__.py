"""
Gobstopper MCP Extension

Model Context Protocol (MCP) support for Gobstopper applications.
Enables AI agents to interact with Gobstopper apps via MCP tools, resources, and prompts.

Based on the MCP specification: https://modelcontextprotocol.io/

IMPORTANT: Gobstopper uses RSGI (Rust Server Gateway Interface) powered by Granian.
For production, always use mcp.mount(app) to integrate MCP with the same
Granian/RSGI server running your application.

Example usage - Production (served by Granian):

    from gobstopper import Gobstopper
    from gobstopper.extensions.mcp import MCP

    app = Gobstopper(__name__)
    mcp = MCP(app)

    @mcp.tool()
    async def search_knowledge(query: str, limit: int = 10):
        \"\"\"Search the knowledge base.\"\"\"
        return await knowledge_search(query, limit)

    # Mount on same Granian/RSGI server
    mcp.mount(app, path="/mcp")

    # Run with: granian --interface rsgi main:app

Example usage - Blueprint-level MCP:

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
    admin_mcp.mount(app)  # Auto-mounts at /admin/mcp

Example usage - Claude Desktop (STDIO subprocess):

    # myapp.py
    if __name__ == "__main__":
        mcp.run(transport="stdio")

    # Configure Claude Desktop to run this as MCP server
"""

from .server import MCP, MCPServer
from .decorators import tool, resource, prompt
from .client import MCPClient
from .transport import STDIOTransport, mount_mcp
from .providers import Provider, LocalProvider
from .embedding import KnowledgeMCP, PipelineStep, StepStatus, RunStatus
from .docs import attach_mcp_docs

__all__ = [
    "MCP",
    "MCPServer",
    "tool",
    "resource",
    "prompt",
    "MCPClient",
    "STDIOTransport",
    "mount_mcp",
    "attach_mcp_docs",
    "Provider",
    "LocalProvider",
    "KnowledgeMCP",
    "PipelineStep",
    "StepStatus",
    "RunStatus",
]

__version__ = "0.1.0"
