"""MCP documentation UI generator using gobstopper.html (vendored htpy) with Datastar."""

from __future__ import annotations

import json
from typing import Any

from ... import html as hp
from ...http.response import JSONResponse, Response


PAGE_STYLE = """
:root {
    --sidebar-width: 280px;
    --header-height: 60px;
    --bg-primary: #0f0f1a;
    --bg-secondary: #1a1a2e;
    --bg-tertiary: #252542;
    --accent-primary: #6366f1;
    --accent-secondary: #818cf8;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border-color: #334155;
    --success: #10b981;
    --error: #ef4444;
    --warning: #f59e0b;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
}

/* Sidebar */
.sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    width: var(--sidebar-width);
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    overflow-y: auto;
    padding: 1.5rem;
    z-index: 100;
}

.sidebar-header {
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border-color);
}

.sidebar-header h1 {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
}

.sidebar-header .subtitle {
    font-size: 0.75rem;
    color: var(--text-muted);
}

.nav-section {
    margin-bottom: 1.5rem;
}

.nav-section-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.75rem;
    font-weight: 600;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem 0.875rem;
    border-radius: 8px;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.875rem;
    transition: all 0.2s;
    cursor: pointer;
    border: none;
    background: transparent;
    width: 100%;
    text-align: left;
}

.nav-item:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.nav-item.active {
    background: var(--accent-primary);
    color: white;
}

.nav-item .icon {
    font-size: 1rem;
    width: 20px;
    text-align: center;
}

.nav-item .count {
    margin-left: auto;
    background: var(--bg-tertiary);
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
}

.nav-item.active .count {
    background: rgba(255,255,255,0.2);
}

/* Main content */
.main-content {
    margin-left: var(--sidebar-width);
    min-height: 100vh;
}

/* Header */
.header {
    position: sticky;
    top: 0;
    height: var(--header-height);
    background: rgba(15, 15, 26, 0.9);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    padding: 0 2rem;
    z-index: 50;
}

.header h2 {
    font-size: 1rem;
    font-weight: 500;
}

/* Content sections */
.section {
    padding: 2rem;
    border-bottom: 1px solid var(--border-color);
}

.section-header {
    margin-bottom: 1.5rem;
}

.section-title {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.section-desc {
    color: var(--text-secondary);
    font-size: 0.95rem;
}

/* Cards */
.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    transition: border-color 0.2s;
}

.card:hover {
    border-color: var(--accent-primary);
}

.card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1rem;
}

.card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.card-desc {
    color: var(--text-secondary);
    font-size: 0.875rem;
    margin-bottom: 1rem;
}

/* Schema */
.schema-container {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    overflow: hidden;
}

.schema-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.schema-body {
    padding: 1rem;
    overflow-x: auto;
}

.schema-body pre {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.8rem;
    line-height: 1.7;
    color: var(--text-secondary);
}

/* Badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.625rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
}

.badge-tool {
    background: rgba(99, 102, 241, 0.2);
    color: #818cf8;
    border: 1px solid rgba(99, 102, 241, 0.3);
}

.badge-resource {
    background: rgba(16, 185, 129, 0.2);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-prompt {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.badge-template {
    background: rgba(139, 92, 246, 0.2);
    color: #a78bfa;
    border: 1px solid rgba(139, 92, 246, 0.3);
}

/* Buttons */
.btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1.25rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    border: none;
}

.btn-primary {
    background: var(--accent-primary);
    color: white;
}

.btn-primary:hover {
    background: var(--accent-secondary);
}

.btn-secondary {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border: 1px solid var(--border-color);
}

.btn-secondary:hover {
    border-color: var(--text-muted);
    color: var(--text-primary);
}

/* Form elements */
.form-group {
    margin-bottom: 1rem;
}

.form-label {
    display: block;
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
}

.form-input, .form-textarea, .form-select {
    width: 100%;
    padding: 0.625rem 0.875rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.875rem;
    transition: border-color 0.2s;
}

.form-input:focus, .form-textarea:focus, .form-select:focus {
    outline: none;
    border-color: var(--accent-primary);
}

.form-textarea {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.8rem;
    min-height: 120px;
    resize: vertical;
}

/* Response area */
.response-area {
    margin-top: 1rem;
    padding: 1rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
}

.response-area pre {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.8rem;
    white-space: pre-wrap;
    word-break: break-all;
}

.response-success {
    border-color: var(--success);
}

.response-error {
    border-color: var(--error);
}

/* Loading state */
.loading {
    opacity: 0.6;
    pointer-events: none;
}

.spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-color);
    border-top-color: var(--accent-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Empty state */
.empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--text-muted);
}

.empty-state-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}

.empty-state-text {
    font-size: 1rem;
}

/* Code block */
.code-block {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
    overflow-x: auto;
}

.code-block code {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.8rem;
    color: var(--text-secondary);
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}
"""


def tool_card(tool: dict[str, Any], index: int, endpoint: str) -> str:
    """Generate a tool card with interactive testing."""
    name = tool.get("name", "unnamed")
    desc = tool.get("description", "No description provided")
    input_schema = tool.get("inputSchema", {})

    if isinstance(input_schema, str):
        try:
            input_schema = json.loads(input_schema)
        except Exception:
            input_schema = {"type": "object"}

    schema_json = json.dumps(input_schema, indent=2)
    props = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    form_fields = ""
    for field_name, field_schema in props.items():
        field_type = field_schema.get("type", "string")
        field_desc = field_schema.get("description", "")
        is_required = field_name in required
        default = field_schema.get("default", "")

        if field_type == "string":
            form_fields += f"""
            <div class="form-group">
                <label class="form-label">{field_name}{" *" if is_required else ""}</label>
                <input type="text" name="args.{field_name}" class="form-input"
                       placeholder="{field_desc or ("Enter " + field_name)}"
                       value="{default if default else ""}">
            </div>
            """
        elif field_type == "integer":
            form_fields += f"""
            <div class="form-group">
                <label class="form-label">{field_name}{" *" if is_required else ""}</label>
                <input type="number" name="args.{field_name}" class="form-input"
                       value="{default if default else ""}">
            </div>
            """
        elif field_type == "boolean":
            form_fields += f"""
            <div class="form-group">
                <label class="form-label">{field_name}{" *" if is_required else ""}</label>
                <select name="args.{field_name}" class="form-select">
                    <option value="true">True</option>
                    <option value="false">False</option>
                </select>
            </div>
            """
        elif field_type in ("array", "object"):
            form_fields += f"""
            <div class="form-group">
                <label class="form-label">{field_name}{" *" if is_required else ""}</label>
                <textarea name="args.{field_name}" class="form-textarea"></textarea>
            </div>
            """

    return f"""
<div class="card" id="tool-{index}">
    <div class="card-header">
        <div>
            <div class="card-title"><span class="badge badge-tool">Tool</span>{name}</div>
            <div class="card-desc">{desc}</div>
        </div>
    </div>

    <details class="schema-container">
        <summary class="schema-header"><span>Input Schema</span><span>▼</span></summary>
        <div class="schema-body"><pre>{schema_json}</pre></div>
    </details>

    <div style="margin-top: 1rem;">
        <button type="button" class="btn btn-secondary" onclick="toggleForm({index})" style="width: 100%; justify-content: center;">Test This Tool</button>
    </div>

    <div id="test-form-{index}" style="display: none; margin-top: 1rem;">
        <form onsubmit="callTool(event, {index}, '{name}', '{endpoint}')">
            {form_fields}
            <div style="display: flex; gap: 0.5rem; margin-top: 1rem;">
                <button type="submit" class="btn btn-primary" id="submitBtn-{index}">Run Tool</button>
                <button type="button" class="btn btn-secondary" onclick="toggleForm({index})">Cancel</button>
            </div>
        </form>
        <div id="response-{index}" class="response-area" style="display: none;"><pre id="responseText-{index}"></pre></div>
    </div>
</div>
"""


def resource_card(resource: dict[str, Any], is_template: bool = False) -> str:
    """Generate a resource card."""
    uri = resource.get("uriTemplate") or resource.get("uri", "unknown")
    desc = resource.get("description", "No description")
    mime_type = resource.get("mimeType", "application/json")

    return f"""
<div class="card">
    <div class="card-header">
        <div>
            <div class="card-title">
                <span class="badge {"badge-template" if is_template else "badge-resource"}">
                    {"Template" if is_template else "Resource"}
                </span>
                {uri}
            </div>
            <div class="card-desc">{desc}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.5rem;">
                MIME: <code>{mime_type}</code>
            </div>
        </div>
    </div>
</div>
"""


def prompt_card(prompt: dict[str, Any]) -> str:
    """Generate a prompt card."""
    name = prompt.get("name", "unnamed")
    desc = prompt.get("description", "No description")
    arguments = prompt.get("arguments", [])

    args_html = ""
    if arguments:
        args_html = '<div style="margin-top: 1rem;"><div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem;">Arguments:</div>'
        for arg in arguments:
            arg_name = arg.get("name", "")
            arg_desc = arg.get("description", "")
            arg_required = arg.get("required", False)
            args_html += f"""
            <div style="font-size: 0.8rem; padding: 0.5rem; background: var(--bg-primary); border-radius: 6px; margin-bottom: 0.25rem;">
                <strong>{arg_name}</strong>{" <span style='color: var(--error);'>(required)</span>" if arg_required else ""}
                {f'<div style="color: var(--text-secondary); margin-top: 0.25rem;">{arg_desc}</div>' if arg_desc else ""}
            </div>
            """
        args_html += "</div>"

    return f"""
<div class="card">
    <div class="card-header">
        <div>
            <div class="card-title">
                <span class="badge badge-prompt">Prompt</span>
                {name}
            </div>
            <div class="card-desc">{desc}</div>
            {args_html}
        </div>
    </div>
</div>
"""


def mcp_docs_html(
    manifest: dict[str, Any],
    endpoint: str = "/mcp",
    title: str = "MCP Documentation",
) -> str:
    """Generate complete MCP documentation HTML page."""
    server_name = manifest.get("name", "MCP Server")
    server_version = manifest.get("version", "1.0.0")
    tools = manifest.get("tools", [])
    resources = manifest.get("resources", [])
    resource_templates = manifest.get("resourceTemplates", [])
    prompts = manifest.get("prompts", [])

    # Sidebar navigation items
    tools_nav = (
        f"""
    <a href="#tools" class="nav-item active" onclick="scrollToSection(event)">
        <span class="icon">🛠️</span>
        <span>Tools</span>
        <span class="count">{len(tools)}</span>
    </a>
    """
        if tools
        else ""
    )

    resources_nav = (
        f"""
    <a href="#resources" class="nav-item" onclick="scrollToSection(event)">
        <span class="icon">📄</span>
        <span>Resources</span>
        <span class="count">{len(resources) + len(resource_templates)}</span>
    </a>
    """
        if resources or resource_templates
        else ""
    )

    prompts_nav = (
        f"""
    <a href="#prompts" class="nav-item" onclick="scrollToSection(event)">
        <span class="icon">💬</span>
        <span>Prompts</span>
        <span class="count">{len(prompts)}</span>
    </a>
    """
        if prompts
        else ""
    )

    # Tool cards
    tools_html = ""
    if tools:
        tools_html = "\n".join(tool_card(t, i, endpoint) for i, t in enumerate(tools))
    else:
        tools_html = """
        <div class="empty-state">
            <div class="empty-state-icon">🛠️</div>
            <div class="empty-state-text">No tools available</div>
        </div>
        """

    # Resource cards
    resources_html = ""
    if resources or resource_templates:
        if resources:
            resources_html += '<h3 style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1rem; text-transform: uppercase;">Resources</h3>'
            resources_html += "\n".join(resource_card(r, False) for r in resources)
        if resource_templates:
            resources_html += '<h3 style="font-size: 0.9rem; color: var(--text-muted); margin: 2rem 0 1rem; text-transform: uppercase;">Templates</h3>'
            resources_html += "\n".join(
                resource_card(r, True) for r in resource_templates
            )
    else:
        resources_html = """
        <div class="empty-state">
            <div class="empty-state-icon">📄</div>
            <div class="empty-state-text">No resources available</div>
        </div>
        """

    # Prompt cards
    prompts_html = ""
    if prompts:
        prompts_html = "\n".join(prompt_card(p) for p in prompts)
    else:
        prompts_html = """
        <div class="empty-state">
            <div class="empty-state-icon">💬</div>
            <div class="empty-state-text">No prompts available</div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script type="module" src="https://cdn.jsdelivr.net/npm/datastar@1.0.0/datastar.js"></script>
    <style>{PAGE_STYLE}</style>
</head>
<body>
    <nav class="sidebar">
        <div class="sidebar-header">
            <h1>{server_name}</h1>
            <div class="subtitle">v{server_version}</div>
        </div>
        
        <div class="nav-section">
            <div class="nav-section-title">Overview</div>
            <a href="#" class="nav-item active">
                <span class="icon">📊</span>
                <span>Documentation</span>
            </a>
        </div>
        
        <div class="nav-section">
            <div class="nav-section-title">API Reference</div>
            {tools_nav}
            {resources_nav}
            {prompts_nav}
        </div>
        
        <div class="nav-section" style="margin-top: auto; padding-top: 1rem; border-top: 1px solid var(--border-color);">
            <a href="{endpoint}" class="nav-item" target="_blank">
                <span class="icon">🔗</span>
                <span>Manifest JSON</span>
            </a>
        </div>
    </nav>
    
    <main class="main-content">
        <header class="header">
            <h2>📚 {title}</h2>
        </header>
        
        <section id="tools" class="section">
            <div class="section-header">
                <h2 class="section-title">
                    <span>🛠️</span>
                    Tools
                </h2>
                <p class="section-desc">Callable functions that extend the AI's capabilities</p>
            </div>
            {tools_html}
        </section>
        
        <section id="resources" class="section">
            <div class="section-header">
                <h2 class="section-title">
                    <span>📄</span>
                    Resources
                </h2>
                <p class="section-desc">Data sources the AI can read from</p>
            </div>
            {resources_html}
        </section>
        
        <section id="prompts" class="section">
            <div class="section-header">
                <h2 class="section-title">
                    <span>💬</span>
                    Prompts
                </h2>
                <p class="section-desc">Reusable prompt templates</p>
            </div>
            {prompts_html}
        </section>
    </main>
    
    <script>
        function scrollToSection(event) {{
            event.preventDefault();
            const href = event.currentTarget.getAttribute('href');
            if (href && href.startsWith('#')) {{
                const section = document.querySelector(href);
                if (section) {{
                    section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
            }}
        }}

        function toggleForm(index) {{
            const form = document.getElementById(`test-form-${{index}}`);
            if (!form) return;
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
        }}

        async function callTool(event, index, toolName, endpoint) {{
            event.preventDefault();
            const form = event.target;
            const formData = new FormData(form);
            const args = {{}};

            for (const [key, value] of formData.entries()) {{
                if (!key.startsWith('args.')) continue;
                const field = key.slice(5);
                if (value.trim() === '') continue;
                try {{
                    args[field] = JSON.parse(value);
                }} catch {{
                    args[field] = value;
                }}
            }}

            const btn = document.getElementById(`submitBtn-${{index}}`);
            const responseArea = document.getElementById(`response-${{index}}`);
            const responseText = document.getElementById(`responseText-${{index}}`);

            if (btn) btn.classList.add('loading');
            if (btn) btn.textContent = 'Running...';

            try {{
                const response = await fetch(endpoint, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        jsonrpc: '2.0',
                        id: index,
                        method: 'tools/call',
                        params: {{ name: toolName, arguments: args }}
                    }})
                }});

                const data = await response.json();
                if (responseArea) {{
                    responseArea.style.display = 'block';
                    responseArea.className = 'response-area' + (data.error ? ' response-error' : ' response-success');
                }}
                if (responseText) {{
                    responseText.textContent = JSON.stringify(data, null, 2);
                }}
            }} catch (err) {{
                if (responseArea) {{
                    responseArea.style.display = 'block';
                    responseArea.className = 'response-area response-error';
                }}
                if (responseText) {{
                    responseText.textContent = 'Error: ' + err.message;
                }}
            }} finally {{
                if (btn) {{
                    btn.classList.remove('loading');
                    btn.textContent = 'Run Tool';
                }}
            }}
        }}

        function updateActiveNav() {{
            const sections = ['tools', 'resources', 'prompts'];
            const navItems = document.querySelectorAll('.nav-item[href^="#"]');
            const scrollPos = window.scrollY + 240;
            const atPageBottom = window.innerHeight + window.scrollY >= document.body.offsetHeight - 4;
            let currentSection = 'tools';

            for (const section of sections) {{
                const el = document.getElementById(section);
                if (!el) continue;
                if (scrollPos >= el.offsetTop) {{
                    currentSection = section;
                }}
            }}

            if (atPageBottom) {{
                currentSection = 'prompts';
            }}

            navItems.forEach((item) => {{
                item.classList.toggle('active', item.getAttribute('href') === `#${{currentSection}}`);
            }});
        }}

        window.addEventListener('scroll', updateActiveNav);
        window.addEventListener('load', updateActiveNav);
    </script>
</body>
</html>
"""


async def mcp_docs_handler(request, server, endpoint: str = "/mcp"):
    """Handle MCP docs requests."""
    if request.method == "GET":
        manifest = server.get_manifest()
        server_name = server.name if hasattr(server, "name") else "MCP Server"
        html = mcp_docs_html(manifest, endpoint, f"{server_name} - Documentation")
        return Response(html, content_type="text/html; charset=utf-8")

    return Response("Method not allowed", status=405)


async def mcp_manifest_handler(request, server):
    """Handle MCP manifest requests."""
    manifest = server.get_manifest()
    return JSONResponse(manifest)


def attach_mcp_docs(app, path: str, server, *, name: str | None = None):
    """Attach MCP documentation UI to a Gobstopper app.

    This registers:
        - GET {path}: MCP manifest (JSON)
        - GET {path}/ui: Interactive documentation UI

    Args:
        app: Gobstopper application instance
        path: URL path for the MCP endpoint (e.g., "/mcp" or "/admin/mcp")
        server: The MCPServer instance
        name: Optional name for the docs title. Defaults to server.name

    Example:
        app = Gobstopper(__name__)
        mcp = MCP(app, name="my_server")

        @mcp.tool()
        def search(query: str):
            return []

        attach_mcp_docs(app, "/mcp", mcp.server)

        # Now available:
        # GET /mcp - manifest
        # GET /mcp/ui - interactive docs
    """
    from ...http.routing import RouteHandler

    docs_name = name or (server.name if hasattr(server, "name") else "MCP")
    base_path = path.rstrip("/")

    async def manifest_handler(request):
        return await mcp_manifest_handler(request, server)

    async def docs_handler(request):
        return await mcp_docs_handler(request, server, base_path)

    manifest_route = RouteHandler(base_path, manifest_handler, ["GET"])
    docs_route = RouteHandler(f"{base_path}/ui", docs_handler, ["GET"])

    if getattr(app, "rust_router_available", False):
        app.http_router.insert(
            base_path, "GET", manifest_route, f"{docs_name}_manifest"
        )
        app.http_router.insert(
            f"{base_path}/ui", "GET", docs_route, f"{docs_name}_docs"
        )
    else:
        app.routes.append(manifest_route)
        app.routes.append(docs_route)

    app._all_routes.append(manifest_route)
    app._all_routes.append(docs_route)

    return {"manifest": base_path, "docs": f"{base_path}/ui"}


__all__ = ["attach_mcp_docs", "mcp_docs_html"]
