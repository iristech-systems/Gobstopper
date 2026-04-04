#!/usr/bin/env python3
"""
Example Gobstopper MCP application.

Demonstrates:
- Basic MCP server with tools, resources, and prompts
- Knowledge embedding pipeline with 4-step orchestration
- Blueprint-level MCP with namespaces
- Testing MCP endpoints

Run:
    # Mounted mode (production with Granian):
    python example_mcp_app.py

    # STDIO mode (Claude Desktop):
    python example_mcp_app.py --stdio
"""

import asyncio
import hashlib
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

# Add src to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from gobstopper import Gobstopper, Request, jsonify, Response
from gobstopper.core.blueprint import Blueprint
from gobstopper.extensions.mcp import (
    MCP,
    KnowledgeMCP,
    PipelineStep,
    StepStatus,
    RunStatus,
)
from gobstopper.middleware import CORSMiddleware, SecurityMiddleware


# ============================================================================
# EXAMPLE 1: Basic MCP with Tools, Resources, and Prompts
# ============================================================================

app = Gobstopper(__name__, debug=True)

# Simple in-memory "database" for demo
DEMO_DB = {
    "documents": {},
    "chunks": {},
    "users": {"admin": {"id": "admin", "role": "admin"}},
}


# ---- Basic MCP Setup ----

basic_mcp = MCP(app, name="demo", namespace="demo")


@basic_mcp.tool()
async def search_documents(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search documents by query string.

    Args:
        query: Search query
        limit: Maximum results to return

    Returns:
        List of matching documents
    """
    results = []
    query_lower = query.lower()

    for doc_id, doc in DEMO_DB["documents"].items():
        title = doc.get("title", "")
        text = doc.get("text", "")
        if query_lower in title.lower() or query_lower in text.lower():
            results.append(
                {
                    "id": doc_id,
                    "title": title,
                    "snippet": text[:200],
                }
            )
            if len(results) >= limit:
                break

    return results


@basic_mcp.tool()
async def get_document(document_id: str) -> Dict[str, Any]:
    """
    Get a document by ID.

    Args:
        document_id: Document identifier

    Returns:
        Document data or error
    """
    doc = DEMO_DB["documents"].get(document_id)
    if not doc:
        return {"error": f"Document not found: {document_id}"}
    return doc


@basic_mcp.tool()
async def create_document(
    title: str, text: str, author: str = "unknown"
) -> Dict[str, Any]:
    """
    Create a new document.

    Args:
        title: Document title
        text: Document content
        author: Author name

    Returns:
        Created document with ID
    """
    doc_id = str(uuid.uuid4())
    DEMO_DB["documents"][doc_id] = {
        "id": doc_id,
        "title": title,
        "text": text,
        "author": author,
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"id": doc_id, "status": "created"}


@basic_mcp.resource("demo://config")
def get_demo_config() -> Dict[str, Any]:
    """Get demo configuration."""
    return {
        "app_name": "Gobstopper MCP Demo",
        "version": "1.0.0",
        "features": ["search", "documents", "embedding"],
    }


@basic_mcp.resource("demo://stats")
async def get_demo_stats() -> Dict[str, Any]:
    """Get demo statistics."""
    return {
        "document_count": len(DEMO_DB["documents"]),
        "chunk_count": len(DEMO_DB["chunks"]),
        "uptime": "N/A",
    }


@basic_mcp.resource_template("demo://document/{document_id}")
async def get_document_resource(document_id: str) -> Dict[str, Any]:
    """Get a single document by ID."""
    return get_document(document_id)


@basic_mcp.prompt()
def analyze_document(document_id: str, focus_area: str = "summary") -> str:
    """
    Generate a prompt for analyzing a document.

    Args:
        document_id: Document to analyze
        focus_area: What aspect to focus on (summary, themes, action_items)

    Returns:
        Analysis prompt string
    """
    prompts = {
        "summary": f"Please provide a concise summary of the document {document_id}, highlighting the key points.",
        "themes": f"Identify and analyze the main themes present in document {document_id}. Provide supporting evidence from the text.",
        "action_items": f"Extract any action items, deadlines, or commitments from document {document_id}. Format as a structured list.",
    }
    return prompts.get(focus_area, prompts["summary"])


@basic_mcp.prompt()
def compare_documents(doc_id1: str, doc_id2: str) -> str:
    """
    Generate a prompt comparing two documents.

    Args:
        doc_id1: First document ID
        doc_id2: Second document ID

    Returns:
        Comparison prompt string
    """
    return f"""
Please compare and contrast the following two documents:

Document 1 ({doc_id1}):
Document 2 ({doc_id2}):

Provide a structured comparison covering:
1. Main similarities
2. Key differences
3. Complementary aspects
4. Overall relationship
""".strip()


# Mount basic MCP at /mcp
basic_mcp.mount(app, path="/mcp")


# ============================================================================
# EXAMPLE 2: Knowledge Embedding Pipeline with 4 Steps
# ============================================================================


# Simulated embedding - in production you'd call OpenAI, Anthropic, etc.
async def simulate_embedding(
    text: str, model: str = "text-embedding-3-small"
) -> List[float]:
    """Simulate embedding generation."""
    # Create deterministic fake embedding from text hash
    h = hashlib.sha256(text.encode()).digest()
    # Extend to typical embedding dimension (1536 for text-embedding-3-small)
    vector = list(h * (1536 // len(h) + 1))[:1536]
    return vector


async def simple_chunk_text(
    text: str, chunk_size: int = 900, overlap: int = 120
) -> List[Dict[str, Any]]:
    """Simple character-based chunking."""
    chunks = []
    start = 0
    chunk_num = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]

        # Avoid tiny final chunks
        if len(text) - end < chunk_size / 2 and chunks:
            break

        chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
        chunks.append(
            {
                "text": chunk_text,
                "chunk_num": chunk_num,
                "char_start": start,
                "char_end": end,
                "hash": chunk_hash,
            }
        )

        start = end - overlap
        chunk_num += 1

    return chunks


# Knowledge MCP with embedding pipeline
knowledge_mcp = KnowledgeMCP(app, namespace="knowledge")


# ---- Register Step Handlers ----


@knowledge_mcp.step(PipelineStep.INGEST)
async def ingest_document(ctx) -> Dict[str, Any]:
    """
    Step 1: INGEST - Validate and store source reference.

    In production, this would:
    - Verify blob exists and is accessible
    - Check tenant/partner ownership
    - Deduplicate based on content hash
    """
    source_kind = ctx.source.get("kind")
    source_value = ctx.source.get("value")

    # Simulate validation
    if source_kind == "blob_ref":
        # In production: fetch blob, compute hash
        content = f"Demo content for {source_value}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
    elif source_kind == "partner_document_id":
        # In production: lookup existing document
        content = f"Content of document {source_value}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
    else:
        raise ValueError(f"Unsupported source kind: {source_kind}")

    ctx.run.source_hash = content_hash

    return {
        "status": "ingested",
        "content_hash": content_hash,
        "source_kind": source_kind,
        "source_value": source_value,
    }


@knowledge_mcp.step(PipelineStep.EXTRACT_NORMALIZE)
async def extract_and_normalize(ctx) -> Dict[str, Any]:
    """
    Step 2: EXTRACT_NORMALIZE - Extract text and normalize.

    In production, this would:
    - Parse document format (PDF, DOCX, etc.)
    - Extract text and metadata
    - Normalize whitespace, encoding, etc.
    """
    # Get previous step output
    ingest_result = ctx.run.steps[PipelineStep.INGEST].result
    if hasattr(ingest_result, "output"):
        ingest_output = ingest_result.output
    else:
        ingest_output = ingest_result

    source_value = ingest_output.get("source_value", ctx.source.get("value"))

    # Simulate text extraction
    text = f"Extracted and normalized text content from {source_value}. " * 10

    # Normalize whitespace
    text = " ".join(text.split())

    return {
        "text": text,
        "char_count": len(text),
        "parser": "demo-parser",
        "warnings": [],
    }


@knowledge_mcp.step(PipelineStep.CHUNK_EMBED)
async def chunk_and_embed(ctx) -> Dict[str, Any]:
    """
    Step 3: CHUNK_EMBED - Create chunks and generate embeddings.

    In production, this would:
    - Apply semantic chunking strategy
    - Call embedding API
    - Store chunks with embeddings
    """
    # Get previous step output
    extract_result = ctx.run.steps[PipelineStep.EXTRACT_NORMALIZE].result
    if hasattr(extract_result, "output"):
        extract_output = extract_result.output
    else:
        extract_output = extract_result

    text = extract_output.get("text", "")

    # Get options
    chunk_size = ctx.options.get("chunk_size", 900)
    chunk_overlap = ctx.options.get("chunk_overlap", 120)
    embedding_model = ctx.options.get("embedding_model", "text-embedding-3-small")

    # Chunk text
    chunks = simple_chunk_text(text, chunk_size, chunk_overlap)

    # Generate embeddings
    for chunk in chunks:
        embedding = await simulate_embedding(chunk["text"], embedding_model)
        chunk["embedding_model"] = embedding_model
        chunk["embedding_dim"] = len(embedding)
        chunk["embedding"] = embedding[:8]  # Store first 8 dims for demo

    # Store chunks
    for chunk in chunks:
        chunk_id = chunk["hash"]
        DEMO_DB["chunks"][chunk_id] = {
            **chunk,
            "tenant_id": ctx.tenant_id,
            "partner_id": ctx.partner_id,
            "run_id": ctx.run.run_id,
        }

    return {
        "chunks": [{"id": c["hash"], "text": c["text"][:50] + "..."} for c in chunks],
        "chunk_count": len(chunks),
        "embedding_model": embedding_model,
        "embedding_dim": chunks[0]["embedding_dim"] if chunks else 0,
    }


@knowledge_mcp.step(PipelineStep.CONNECT_INDEX)
async def connect_and_index(ctx) -> Dict[str, Any]:
    """
    Step 4: CONNECT_INDEX - Link to lineage and mark query-ready.

    In production, this would:
    - Link chunks to partner/account/document
    - Run enrichment hooks
    - Update query-ready status
    - Emit downstream signals
    """
    chunk_result = ctx.run.steps[PipelineStep.CHUNK_EMBED].result
    if hasattr(chunk_result, "output"):
        chunk_output = chunk_result.output
    else:
        chunk_output = chunk_result

    chunk_ids = [c["id"] for c in chunk_output.get("chunks", [])]

    # Mark chunks as query-ready
    for chunk_id in chunk_ids:
        if chunk_id in DEMO_DB["chunks"]:
            DEMO_DB["chunks"][chunk_id]["query_ready"] = True
            DEMO_DB["chunks"][chunk_id]["indexed_at"] = datetime.utcnow().isoformat()

    # Update metrics
    ctx.run.metrics["chunk_count"] = len(chunk_ids)
    ctx.run.metrics["embedding_dim"] = chunk_output.get("embedding_dim", 0)

    return {
        "status": "indexed",
        "chunk_ids": chunk_ids,
        "query_ready": True,
    }


# Mount knowledge MCP at /knowledge/mcp
knowledge_mcp.mount(app, path="/knowledge/mcp")


# ============================================================================
# EXAMPLE 3: Blueprint-level MCP with Admin Namespace
# ============================================================================

admin_bp = Blueprint("admin", url_prefix="/admin")
admin_mcp = MCP(blueprint=admin_bp, namespace="admin")


@admin_mcp.tool()
async def admin_stats() -> Dict[str, Any]:
    """Get admin statistics across all tenants."""
    return {
        "total_documents": len(DEMO_DB["documents"]),
        "total_chunks": len(DEMO_DB["chunks"]),
        "tenants": ["demo-tenant"],
    }


@admin_mcp.tool()
async def admin_clear_data(confirm: str = "") -> Dict[str, Any]:
    """Clear all demo data. Requires confirm="YES"."""
    if confirm != "YES":
        return {"error": "Must confirm with confirm='YES'"}

    DEMO_DB["documents"].clear()
    DEMO_DB["chunks"].clear()

    return {"status": "cleared"}


@admin_mcp.resource("admin://system/status")
def admin_system_status() -> Dict[str, Any]:
    """Get system status for admin dashboard."""
    return {
        "status": "healthy",
        "mcp_servers": ["demo", "knowledge", "admin"],
        "timestamp": datetime.utcnow().isoformat(),
    }


app.register_blueprint(admin_bp)
admin_mcp.mount(app)  # Auto-mounts at /admin/mcp


# ============================================================================
# Standard Web Routes for Testing
# ============================================================================


@app.get("/")
async def index(request: Request) -> Response:
    """Index page with links to MCP endpoints."""
    html = """
    <html>
    <head><title>Gobstopper MCP Demo</title></head>
    <body>
        <h1>Gobstopper MCP Demo</h1>
        
        <h2>MCP Servers</h2>
        <ul>
            <li><a href="/mcp">Basic MCP (/mcp)</a> - Tools, resources, prompts</li>
            <li><a href="/mcp/ui">📖 Docs for Basic MCP</a></li>
            <li><a href="/knowledge/mcp">Knowledge MCP (/knowledge/mcp)</a> - Embedding pipeline</li>
            <li><a href="/knowledge/mcp/ui">📖 Docs for Knowledge MCP</a></li>
            <li><a href="/admin/mcp">Admin MCP (/admin/mcp)</a> - Admin tools</li>
            <li><a href="/admin/mcp/ui">📖 Docs for Admin MCP</a></li>
        </ul>
        
        <h2>Test Embedding Pipeline</h2>
        <form action="/test-embed" method="post">
            <button type="submit">Run Test Embedding</button>
        </form>
        
        <h2>Example MCP Calls</h2>
        <pre>
# List tools:
curl http://localhost:8000/mcp -X POST \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'

# Call search tool:
curl http://localhost:8000/mcp -X POST \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"demo_search_documents","arguments":{"query":"test"}},"id":2}'

# Run embedding pipeline:
curl http://localhost:8000/knowledge/mcp -X POST \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"knowledge_embed_pipeline_run","arguments":{"tenant_id":"test","partner_id":"p1","source":{"kind":"blob_ref","value":"test-doc-1"},"idempotency_key":"test-key-1","options":{}}},"id":3}'
        </pre>
    </body>
    </html>
    """
    return Response(html, content_type="text/html")


@app.post("/test-embed")
async def test_embed(request: Request):
    """Test the embedding pipeline directly."""
    from gobstopper.http.response import JSONResponse

    doc_id = str(uuid.uuid4())
    DEMO_DB["documents"][doc_id] = {
        "id": doc_id,
        "title": "Test Document",
        "text": "This is a test document with some content for embedding. " * 20,
        "author": "test",
        "created_at": datetime.utcnow().isoformat(),
    }

    run = await knowledge_mcp._mcp.server.handle_request(
        "tools/call",
        {
            "name": "knowledge_embed_pipeline_run",
            "arguments": {
                "tenant_id": "test-tenant",
                "partner_id": "test-partner",
                "source": {"kind": "blob_ref", "value": doc_id},
                "idempotency_key": f"test-{time.time()}",
                "options": {"chunk_size": 200, "chunk_overlap": 50},
                "requested_by": {"user_id": "test", "role": "admin"},
            },
        },
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gobstopper MCP Demo")
    parser.add_argument("--stdio", action="store_true", help="Run MCP in STDIO mode")
    args = parser.parse_args()

    if args.stdio:
        print("Starting Gobstopper MCP in STDIO mode...", file=sys.stderr)
        print(
            "Use with Claude Desktop or other MCP clients that support STDIO",
            file=sys.stderr,
        )
        basic_mcp.run(transport="stdio")
    else:
        print("Starting Gobstopper MCP Demo Server...", file=sys.stderr)
        print("MCP endpoints:", file=sys.stderr)
        print("  Basic MCP: http://localhost:8000/mcp", file=sys.stderr)
        print("  Knowledge MCP: http://localhost:8000/knowledge/mcp", file=sys.stderr)
        print("  Admin MCP: http://localhost:8000/admin/mcp", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run with: granian --interface rsgi example_mcp_app:app", file=sys.stderr)

        # For development, use uvicorn as fallback
        try:
            import granian
        except ImportError:
            print(
                "(granian not installed, using uvicorn for development)",
                file=sys.stderr,
            )
            import uvicorn

            uvicorn.run(app, host="127.0.0.1", port=8000)
