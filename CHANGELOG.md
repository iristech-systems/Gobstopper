# Changelog

## [0.4.2] - 2026-04-04

### Lifecycle + MCP + DX Fixes

#### Granian-native RSGI lifecycle hooks
- Added native RSGI lifecycle integration via `__rsgi_init__` and `__rsgi_del__` in `Gobstopper`.
- Startup/shutdown now run through Granian worker lifecycle instead of the previous SIGTERM workaround path.
- Added idempotent shutdown guards to avoid duplicate shutdown execution.

#### Primary-worker startup helper
- Added `@app.on_startup_primary` for one-time startup tasks (DB seeding, model preload, singleton worker startup) in multi-worker setups.
- Uses the existing worker-selection semantics from `should_run_background_workers()`.

#### SecurityMiddleware CSRF bypass API (trusted machine endpoints)
- Added CSRF exemption controls for non-browser trusted calls:
  - `csrf_exempt_paths`
  - `csrf_exempt_prefixes`
  - `csrf_trusted_headers`
  - `csrf_exempt_predicate`
- Added fluent runtime helpers:
  - `exempt_csrf_path()`
  - `exempt_csrf_prefix()`
  - `trust_csrf_header()`
  - `exempt_csrf_when()`

#### Datastar / gobstopper.html ergonomics + typing
- Added typed fragment support in Datastar extension (`FragmentLike = str | HasHtml | Renderable`).
- Added `Datastar.normalize_fragment(...)` and `Datastar.merge_many(...)` helpers.
- Added `fragment(...)` ergonomic alias for `Datastar.merge_fragments(...)`.
- Improved `gobstopper.html.datastar` typing with `DatastarAttrs` and recursive `JSONValue` aliases.

#### Router capability detection cleanup
- Router capability checks are now cached once at app init (`_router_supports_params`, `_router_supports_allowed_methods`).
- Removed repeated per-request exception-based version probing in route matching and allowed-method detection paths.

#### MCP protocol + transport hardening
- Added `MCPServer.handle_request(...)` for mounted HTTP MCP compatibility.
- Fixed MCP transport error-path import bug (`JSONResponse` scoping issue).
- Updated `initialize` response shape to MCP-compatible fields (`protocolVersion`, `capabilities`, `serverInfo`, `instructions`).
- Added/updated MCP docs attachment and UI flow for mounted endpoints.

#### Example app updates
- Removed the MCP-to-OpenAPI bridge endpoints from `example_mcp_app.py`.
- Updated demo search behavior to match query against both title and text for realistic tool-flow testing.

## [0.4.1] - 2026-03-14

### ✨ Test Client, Graceful Shutdown, Per-Route Rate Limiting

#### `TestClient` — In-Process Test Client
- New `gobstopper.testing.TestClient` drives the app's RSGI entry point directly; no real Granian server is needed.
- Use as a context manager: `on_startup` hooks fire on `__enter__`, `on_shutdown` hooks fire on `__exit__`.
- Supports `.get()`, `.post()`, `.put()`, `.patch()`, `.delete()` with `json=`, `data=` (form), `headers=`, and `params=` kwargs.
- `TestResponse` exposes `.status`, `.headers`, `.body`, `.json()`, `.text()`, `.get_cookie(name)`.
- `raise_server_errors=True` (default) turns 5xx responses into `AssertionError` so tests fail loudly.
- Import: `from gobstopper.testing import TestClient` — kept separate from the default star-export to avoid pulling test code into production paths.

#### Graceful Shutdown on SIGTERM
- `app.shutdown()` (which drains in-flight requests, runs `@on_shutdown` hooks, cancels `@app.repeat()` tasks, and drains the task queue) is now called automatically when the Granian worker receives SIGTERM.
- A `signal.signal(SIGTERM, ...)` handler is registered inside `_ensure_startup_complete()` after startup hooks succeed. Silently skipped when called from a non-main thread (as Granian worker threads require).
- CLI `proc.wait(timeout=5)` extended to `WOPR_SHUTDOWN_TIMEOUT + 3` seconds (default 13 s) so the parent process gives workers enough time to finish draining before `SIGKILL`.

#### Per-Route Rate Limiting
- `@app.get("/path", rate_limit="20/minute")` — rate-limit a single route inline without a manual `TokenBucketLimiter` object.
- `rate_limit_by="ip"` (default) keys by client IP; `rate_limit_by="global"` shares a single bucket across all callers.
- Period strings: `second`, `minute`, `hour` (e.g. `"5/second"`, `"100/hour"`).
- All HTTP method decorators (`get`, `post`, `put`, `patch`, `delete`, `options`) accept the new kwargs via `**kwargs` pass-through.
- `_parse_rate_limit(spec)` helper added to `gobstopper.utils.rate_limiter` for programmatic use.
- 429 responses use RFC 7807 Problem Details (`application/problem+json`) consistent with the rest of the framework.

## [0.4.0] - 2026-03-14

### ✨ Framework Enhancements

#### `@app.repeat(interval)` — Recurring Background Tasks
- New decorator that registers an async function to run on a fixed interval (seconds).
- Tasks start automatically on first request (alongside startup hooks) and are cancelled gracefully on shutdown.
- Example: `@app.repeat(30)` calls the function every 30 seconds.
- Multiple repeat tasks are supported; each runs as an independent `asyncio.Task`.

#### `RequestIDMiddleware` — Request ID Threading
- New `gobstopper.middleware.RequestIDMiddleware` (also exported from `gobstopper`).
- Echoes an incoming `X-Request-ID` header if present; generates a UUID4 otherwise.
- Sets `request.request_id` and adds the header to every response.
- Recommended priority: 100 (outermost).

#### Health / Readiness Endpoints
- `GET /health` — liveness probe: always 200 if the process is alive; returns `{"status": "ok", "version": "..."}`.
- `GET /ready` — readiness probe: checks optional subsystems (task queue); returns 200 or 503 with `{"status": "ok"|"degraded", "checks": {...}}`.
- Registered automatically (`health_check=True` default on `Gobstopper`). Opt out with `Gobstopper(__name__, health_check=False)`.

#### `url_for` in Jinja2 Templates
- `app.init_templates()` now registers `url_for` as a Jinja2 global. Use `{{ url_for("handler_name", id=5) }}` in any template without importing anything extra.

#### Routes Table in `/_gobstopper` Dashboard
- New `GET /_gobstopper/routes` endpoint returns the full route registry as JSON.
- Dashboard HTML now includes a **"🗺️ Registered Routes"** card with method badges (colour-coded: GET=blue, POST=green, PUT=orange, DELETE=red, PATCH=yellow, WS=purple), path, handler name, and blueprint.
- Routes are loaded once on page load, not polled.

### Architecture: DSL-first, Tera removed

- **DSL (`gobstopper.html`) is now the primary rendering approach** — zero-overhead `__str__()` rendering with full Python expressiveness.
- **Jinja2** remains fully supported for file-based templates.
- **Rust/Tera template engine removed** — the cffi round-trip (Python→Rust→Python) added latency without measurable benefit at realistic template sizes. The Rust *router* and *static file handler* are unaffected.

#### Removed

- `src/gobstopper/templates/rust_engine.py` — deleted
- `rust/gobstopper_core_rs/src/template_engine.rs` — deleted
- `rust/gobstopper_core_rs/src/template_streaming.rs` — deleted
- `rust/gobstopper_core_rs/src/template_watcher.rs` — deleted
- `RUST_AVAILABLE`, `RustTemplateEngineWrapper`, `get_template_engine`, `render_template`, `render_string`, `reset_template_engine` removed from `gobstopper.templates`

#### Changed

- **`TemplateRenderError`** moved to `gobstopper.templates.engine` (was `gobstopper.templates.rust_engine`). Jinja2 syntax and undefined errors are now raised as `TemplateRenderError` with `lineno` set, so Prism error pages remain rich.
- **`app.init_templates()`**: `use_rust`, `enable_streaming`, `enable_hot_reload` parameters removed. Now constructs a `TemplateEngine` directly.
- **`app.render_template()`**: `stream` parameter removed. Single code path using Jinja2.
- **`app.render_string()`**: Rust branch removed.
- Prism error page labels updated from "Tera Template Engine" to "Jinja2 Template Engine".

## [0.3.9] - 2026-03-14

### ⭐ Datastar RC.8 + Pro Support

- **Datastar RC.8**: Bumped all CDN references from `1.0.0-RC.7` to `v1.0.0-RC.8` across all examples and documentation.
- **`Datastar.script_tag(pro_src=None)`**: New helper that generates the correct `<script type="module">` tag for either the free CDN bundle or a self-hosted Datastar Pro bundle. Pass `pro_src="/static/js/datastar-pro.js"` to switch to Pro with no other changes.
- **`gobstopper.html.datastar_pro`**: New module providing Python DSL helpers for all Datastar Pro attributes and action expressions:
    - **Attributes**: `animate`, `custom_validity`, `match_media`, `on_raf`, `on_resize`, `persist`, `query_string`, `replace_url`, `rocket`, `scroll_into_view`, `view_transition`
    - **Action expressions** (return strings for use in other attributes): `clipboard`, `fit`, `intl`
    - `rocket()` validates the required kebab-case component name at import time — catches `"mycounter"` vs `"my-counter"` errors before they hit the browser.

### 🛠️ Datastar SSE Fixes

- **Newline normalisation in `Datastar.merge_fragments()`**: Multi-line HTML fragments are now collapsed to a single SSE `data:` line automatically. The `_merge_single_line` monkey-patch that apps had to copy is no longer needed and can be removed.
- **`MergeMode` renamed for clarity**: `REPLACE_ELEMENT` and `REPLACE_CONTENT` are now the canonical names for what were `OUTER` and `INNER`. The old names are kept as deprecated aliases — existing code continues to work without changes.
- **`__html__` protocol**: `merge_fragments()` now calls `__html__()` on non-string fragments (e.g. htpy elements) before string conversion, consistent with the rest of the framework.

### 🧰 Request / Response Helpers

- **`request.get_str(key, default="")`**: New method on `Request` that always returns a plain string from query parameters. Eliminates the `request.args.get("key", [""])[0]` boilerplate and the `_get_str_param()` helpers that were being written in every app.
- **`get_str(mapping, key, default="")`** in `gobstopper.http.helpers` (also exported from `gobstopper`): The same normalisation for any `dict[str, list[str]]` — covers both `request.args` and `await request.form()`.

### 📖 gobstopper.html DSL

- **Hazardous names documentation**: `gobstopper.html` now has a prominent module docstring listing every name that shadows a Python built-in (`input`, `map`, `object`) or common loop variable (`a`, `b`, `i`, `p`, `q`, `s`), with recommended import patterns (namespace import → named import → wildcard) and a complete element reference.

### ⚠️ Developer Warnings

- **Tailwind CDN + Datastar SSE**: `SecurityMiddleware(datastar_enabled=True)` now emits a startup warning explaining that Tailwind's CDN/JIT build silently drops styles for CSS classes that appear only in SSE-injected fragments (never in the initial HTML). Workarounds (full Tailwind build, pre-render, safelist) are included in the warning message.

## [0.3.8] - 2026-02-19

### 🦀 Deep Template Diagnostics
- **Error Chain Traversal**: The Rust template engine now traverses the full error source chain to identify the specific root cause of rendering failures.
- **Improved Line/Column Extraction**: Enhanced line and column number extraction to find details hidden in nested Tera errors.
- **Detailed Cause Reporting**: The Error Prism now displays the full "Cause" stack for template errors, making it clear which filter, include, or expression failed.

## [0.3.7] - 2026-02-19

### 🦀 Improved Template Error Reporting
- **Structured Rust Errors**: Switched to structured JSON-encoded error reporting from the Rust-powered template engine (Tera). Errors now include precise line and column information.
- **Enhanced Python Wrapper**: The `RustTemplateEngineWrapper` now decodes structured Rust errors and raises a detailed `TemplateRenderError` exception.
- **Beautiful Error Prism**: Improved the Error Prism (500 error page) to display template code snippets with the problematic line highlighted for template rendering errors.
- **Bug Fix**: Added the missing `render_string` method to `Gobstopper` class and `TemplateEngine` for consistency across engines.


## [0.3.6] - 2026-02-16

### 🪟 Windows Support

- **Platform-Specific Event Loops**: Added automatic platform detection for event loops. Windows users now get `winloop` by default for ~5x performance improvement over the default Windows asyncio event loop, while Linux/macOS users continue using `uvloop`.
- **Smart Defaults**: Changed default `--loop` from `uvloop` to `auto`, enabling automatic platform detection without manual configuration.

## [0.3.5] - 2026-02-16

### 🐛 Critical Bug Fixes

- **Datastar/HTMX Compatibility**: Fixed `data-*` attribute handling to preserve underscores in modifiers (e.g., `data-on:submit__prevent`, `data-on:click__stop`, `data-on:input__debounce_500ms`). Previously, all underscores were converted to hyphens, breaking Datastar RC.7+ and HTMX modifier functionality.
- **SSE Stability**: Added graceful handling for `RSGIProtocolClosed` exceptions when clients disconnect from SSE streams. This eliminates excessive error logging and prevents server instability under high connection churn. Client disconnections are now logged at debug level only.

## [0.3.4] - 2026-02-10

### 🚀 Charts & HTML DSL
- **Native Rendering**: Implemented the `__html__` protocol for all `Chart` objects, allowing them to be rendered directly within the `htpy` DSL (e.g., `div[chart]`).
- **Fluent HTML Attributes**: Added `**kwargs` support to all chart factory methods and builders. You can now pass standard HTML attributes like `id`, `class_`, and `style` directly to charts for seamless styling.
- **Standalone Snippets**: Rendered charts now output as clean HTML snippets rather than full documents, making them perfectly suited for embedding in layouts.

## [0.3.3] - 2026-02-10

### 🚀 Mission Control & UI
- **Dashboard Overhaul**: Implemented a premium "Glassmorphism" aesthetic with blurred backdrops and vibrant accents.
- **Typography**: Integrated the **Inter** font family for a professional, high-end feel.
- **Improved Hierarchy**: Redesigned the dashboard layout with a full-width **System Health** summary and side-by-side charts.

### 💻 CLI & Developer Experience
- **Process Resilience Feedback**: Added a `🛡️ Respawn on fail` status indicator to the server startup summary for better visibility of Granian's auto-respawn capabilities.
- **Metrics Visibility**: Added clear CLI indicators to show exactly which port Granian metrics are running on (or if they are disabled).
- **Robust Version Checking**: Rewrote the Granian version detection logic to handle multi-digit versions (e.g., v2.10.1) and provide better fallback messaging.
- **Diagnostic Logging**: Added framework-level diagnostic logs for metrics inheritance and startup progress to simplify debugging.

### 🛠️ Stability & Resilience
- **Graceful Startup**: Fixed a critical loop where a missing `duckdb` dependency would cause continuous startup retries. The framework now falls back to non-persistent storage with a clear warning.
- **Persistent Metrics**: Fixed unresponsive CPU Load charts by persisting process handles across requests.
- **Robust Serialization**: Standardized `pyecharts` option serialization to prevent JSON syntax errors in the browser.

### 🧹 Refactoring
- **Standardized Extensions**: Moved `gobstopper.ext.datastar` to `gobstopper.extensions.datastar` to align with the framework's extension architecture.

## [0.3.2] - 2026-02-09
- **Metrics & Polish**: Initial work on Mission Control metrics and diagnostic logs.

## [0.3.1] - 2026-02-07

### 🐛 Bug Fixes
- **Missing Sessions Init**: Restored `src/gobstopper/sessions/__init__.py` which was causing `ImportError` on startup in some environments.
- **Datastar Typing**: Updated `Datastar.merge_fragments` to automatically cast `htpy` components to strings, preventing `TypeError` during rendering.

## [0.3.0] - 2026-02-06

### 🎨 Type-Safe UI & Forms ("The Full Stack Update")
- **htpy Integration (Vendored)**: Integrated `htpy` directly into `src/gobstopper/html` for zero-overhead, Python-only HTML generation. Fixed upstream issues with fast rendering loops.
- **Type-Safe Forms**: New `gobstopper.forms` module providing Django-like forms that are:
    - Truly type-safe (built on `msgspec`)
    - Auto-renderable to HTML (implements `__html__` protocol)
    - Datastar-ready (reactive validation out of the box)
- **Automatic Rendering**: Updated `Response` class to automatically render any object implementing `__html__()` protocol. No more `str()` wrapping needed.
- **Datastar Helpers**: Added `gobstopper.html.datastar` with helper functions (`bind`, `on_click`, `signals`) for type-safe Datastar attribute generation.

### 🛡️ Security & Middleware
- **Security Middleware Upgrades**:
    - Exposed `request.csrf_token` for easy access.
    - Added `datastar_enabled` flag to automatically configure strict CSP headers for Datastar (allowing necessary unsafe-eval/inline-styles for reactivity).
    - Fixed immutable scope modification bugs in session handling.

### 🐛 Fixes
- **Request Tracebacks**: Added direct traceback printing to stdout for unhandled exceptions to bypass logging failures during critical crashes.

### 🚀 New Features ("The Wow Update")
- **Mission Control Dashboard**: built-in dashboard at `/_gobstopper` for real-time system monitoring.
    - **Visuals**: Real-time CPU/Memory charts using `pyecharts`.
    - **Security**: Secure-by-default Token Authentication (`?token=...`).
    - **Insights**: Background task tracking and route inspection.
- **Flash Preview**: `gobstopper run --share` generates a QR code and opens your app to the local network (binds 0.0.0.0 auto-magically).
- **Smart Watcher**: Enhanced generic reloader now watches `templates/`, `.env`, and config files automatically.
- **Error Prism**: Beautiful, interactive 500 error page with stack trace folding, request inspection, and one-click copy.
- **Datastar Integration (POC)**: `gobstopper.ext.datastar` for reactive UI.
    - **htpy Support**: First-class support for `htpy` component rendering.
    - **Streaming**: `Datastar.stream()` helper for easy Server-Sent Events.
    - **Signals**: Strict signal formatting and validation.
- **SDK Generator**: New CLI command `gobstopper sdk` generates robust, typed TypeScript clients for your API instantly. `gobstopper sdk --app app:app --out client.ts`.
- **Streaming Uploads**: Added `request.stream()` to efficiently handle large file uploads without memory bloat.
- **Granian Tuning**: Exposed full control over Granian's performance settings in CLI:
    - `--loop`: Select event loop (`uvloop`, `asyncio`, `auto`).
    - `--ssl-cert`/`--ssl-key`: Native valid SSL support for local development (mkcert recommended).
    - `--access-log`: Toggle access logging.

### 🐛 Bug Fixes & Stability
- **Task Queue Recovery**: Fixed issue where pending DuckDB tasks were lost on server restart. `TaskQueue.recover_tasks()` now restores them.
- **Recursive Error Rendering**: Fixed specific crash in `wopr_error.html` where accessing `request` attributes during a 500 error could trigger a secondary recursion error.
- **RSGI Streaming**: Fixed `StreamResponse` implementation to correctly handle async generators in Granian's RSGI protocol.

### 🛠️ Improvements
- **Logging**: Improved default log formats and added structured error logging for unhandled exceptions.
- **Documentation**: Updated walkthroughs and added future-proofing research for Python-based UI stacks.
