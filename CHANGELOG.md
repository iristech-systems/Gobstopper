# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.7] - 2025-01-08

### Added
- **Multi-Process Worker Management**: New `should_run_background_workers()` helper function for safe background task deployment
  - Automatically detects worker process ID from environment variables (`GRANIAN_WORKER_ID`, `GUNICORN_WORKER_ID`)
  - Ensures background workers only run in main process (worker 0) to prevent DuckDB concurrency issues
  - Prevents database lock contention when running with multiple server workers
  - Manual override available with `WOPR_FORCE_WORKERS` environment variable
  - Exported at top-level: `from gobstopper import should_run_background_workers`
  - Updated documentation with multi-process deployment guidance

### Changed
- **Default Event Loop**: Changed from `rloop` to `uvloop` for better compatibility
  - Updated in CLI command (`src/gobstopper/cli/main.py:387`)
  - Updated in all documentation (README.md, docs/cli.md, sphinx-docs)
  - Note: `rloop` remains available as a dependency for compatibility

### Fixed
- **DuckDB Task Storage**: Fixed task status updates not persisting correctly
  - Changed from `INSERT OR REPLACE` syntax to explicit `INSERT ... ON CONFLICT DO UPDATE`
  - Now properly updates all columns including status, progress, and timestamps
  - Task status correctly transitions: `pending` → `started` → `success`/`failed`
  - Fixed msgspec serialization using `msgspec.structs.asdict()` instead of `dataclasses.asdict()`
  - Added explicit `connection.commit()` after saves
  - Fixed race condition by reordering finally block to save before removing from running_tasks
- **Request Attributes**: Fixed missing `_args` and `_cookies` initialization in `Request.__init__`
  - Both attributes now properly initialized to `None` (`src/gobstopper/http/request.py:117-118`)
  - Prevents `AttributeError` when accessing `request.args` or `request.cookies`

## [0.2.6] - 2025-01-07

### Fixed
- **Request Initialization**: Fixed `Request` object missing `_args` and `_cookies` attribute initialization
  - Added initialization of `_args` and `_cookies` to `None` in `Request.__init__` method
  - Resolves `AttributeError` when accessing `request.args` property before lazy initialization
  - Location: `src/gobstopper/http/request.py:117-118`

## [0.2.5] - 2025-01-06

### Added
- **Enhanced Template Error Handling**: Tera template errors now provide detailed, formatted error messages
  - Template name and context in error messages
  - Specific error types (template not found, filter not found, etc.)
  - Lists of available templates/filters when relevant
  - Full error details including line numbers from Tera engine
- **Form Data Helper**: New `flatten_form_data()` utility function
  - Converts single-value form lists to strings for easier access
  - Before: `form.get('name', [''])[0]`
  - After: `flatten_form_data(form).get('name', '')`
  - Preserves multi-value fields (checkboxes, multi-selects) as lists
  - Exported at top-level: `from gobstopper import flatten_form_data`
- **Top-Level Import Consolidation**: All core framework components now importable from `gobstopper` package
  - **Middleware**: `StaticFileMiddleware`, `CORSMiddleware`, `SecurityMiddleware`, `LimitsMiddleware`
  - **Session Storage**: `MemorySessionStorage`, `AsyncRedisSessionStorage`, `PostgresSessionStorage`
  - **Utils**: `TokenBucketLimiter`, `rate_limit`
  - **HTTP Helpers**: `flatten_form_data`, `problem` (RFC 7807)
  - **Core**: `Blueprint` (was previously nested)

## [0.2.4] - 2025-01-05

### Fixed
- **Critical: App Initialization Requiring Jinja2**: Gobstopper now truly works without Jinja2 installed
  - Made `TemplateEngine` import conditional in `src/gobstopper/core/app.py` (lines 37-43)
  - Error template engine now prefers Rust templates by default, with optional Jinja2 fallback (lines 260-279)
  - Added graceful fallback to plain-text error pages if no template engine available (lines 1930-1947, 1970-1991)
  - Error page rendering priority: Rust templates (default) → Jinja2 (if installed) → Plain text (if neither)
  - Root cause: `Gobstopper` class was unconditionally importing `TemplateEngine` (Jinja2) for error pages in `__init__`

### Changed
- **Rust Templates Truly Default**: Made all Jinja2 imports conditional across remaining modules
  - `src/gobstopper/templates/rust_engine.py`: Changed `fallback_to_jinja` default from `True` to `False` (line 69)
  - `src/gobstopper/cli/template_engine.py`: Added check in `TemplateEngine.__init__()` with error message (lines 73-77)
  - CLI project generator requires Jinja2, but core framework doesn't

### Verified
- ✅ Gobstopper imports without Jinja2 installed
- ✅ App creation works without Jinja2
- ✅ Error template engine uses Rust by default
- ✅ Error pages render correctly with Rust templates
- ✅ Graceful fallback to plain text if no template engine available
- ✅ CLI requires Jinja2 only for project generation (intended behavior)

## [0.2.3] - 2025-01-04

### Changed
- **Rust Templates Now Default**: Made Jinja2 completely optional across the codebase
  - Made all Jinja2 imports conditional in `src/gobstopper/templates/rust_engine.py` (lines 35-45)
  - Changed `fallback_to_jinja` default from `True` to `False` (line 69)
  - Added helpful error message when Jinja2 is needed but not installed (lines 132-136)
  - Made Jinja2 imports conditional in `src/gobstopper/cli/template_engine.py` (lines 12-19)
  - Added check in `TemplateEngine.__init__()` with helpful error message (lines 73-77)
  - Rust template engine is now the true default for the framework
  - Jinja2 only required for CLI project generator or when explicitly using `TemplateEngine` class

### Fixed
- **Remaining WOPR References**: Updated final instances of old project name
  - CLI help text: Changed examples from `wopr run` to `gobstopper run` (`src/gobstopper/cli/main.py:338-343`)
  - Error template: Changed framework name from "WOPR" to "Gobstopper" (`templates/error.html:32`)
  - Configuration files:
    - `config.production.toml:15`: Updated `WOPR_SECRET_KEY` → `GOBSTOPPER_SECRET_KEY`
    - `examples/config_example.py:149`: Updated `WOPR_` → `GOBSTOPPER_` prefix

### Updated
- **Package Description**: Updated feature list to mention "Rust-powered template engine (with optional Jinja2 fallback)" (`src/gobstopper/__init__.py:16`)

### Installation
- Basic framework: `pip install gobstopper` (no Jinja2 dependency)
- With Jinja2 fallback: `pip install 'gobstopper[templates]'`

## [0.2.2] - 2025-10-09

### Fixed
- **CLI Bug**: Fixed `gobstopper run` command using incorrect granian option `--threads` instead of `--runtime-threads`
- This resolves the error: "No such option: --threads (Possible options: --blocking-threads, --reload, --runtime-threads)"

## [0.2.1] - 2025-10-09

### Fixed
- Updated all environment variable references in README: `WOPR_*` → `GOBSTOPPER_*`
- Fixed remaining documentation references

## [0.2.0] - 2025-10-09

### 🍬 Major Rebrand: WOPR → Gobstopper

**Project renamed from WOPR to Gobstopper**

*"Like Willy Wonka's Everlasting Gobstopper - a simple wrapper that delivers a complete multi-course meal"*

The framework has been renamed to better represent its philosophy: wrapping RSGI's raw power and complexity into a simple, Flask-like API while delivering everything you need for production web applications.

### Changed
- **Package name**: `wopr` → `gobstopper`
- **Main class**: `WOPR` → `Gobstopper`
- **CLI command**: `wopr` → `gobstopper`
- **Module imports**: All `from wopr.*` → `from gobstopper.*`
- **Environment variables**: `WOPR_*` → `GOBSTOPPER_*`
- **Rust components**: `wopr_core_rs` → `gobstopper_core_rs`

### Updated
- Complete documentation rewrite with Gobstopper theme
- README with new tagline and branding
- All 80+ source files updated with new naming
- CLI templates and examples
- Configuration files
- Build scripts and tooling

### Notes
- This is a **breaking change** for existing users
- Functionality remains identical - only naming has changed
- Migration path: Replace all `wopr` imports with `gobstopper`

## [Unreleased]

## [0.1.0] - 2025-10-08

### Initial Public Release

#### Framework Core
- High-performance async web framework built for Granian's RSGI interface
- Optional Rust-powered components (router, templates, static files)
- Flask-like API with modern async/await
- Lightweight core with optional dependencies
- Cross-platform wheels (macOS ARM64, Linux x86_64/ARM64)

#### Features
- Background task system with DuckDB persistence
- WebSocket support with room management and broadcasting
- Session management (Redis, PostgreSQL, in-memory backends)
- Security features (CSRF protection, rate limiting, secure headers)
- Type-safe request validation with msgspec
- File upload handling with secure filenames
- Template engine with Jinja2 integration

#### CLI Tools
- **`wopr run`** - Flask-like development server with platform-optimized settings
  - Automatic platform detection (ARM64 → single-threaded, x86_64 → multi-threaded)
  - Built-in Granian optimizations (rloop, large backlog, worker respawn)
  - Auto-reload support for development
  - Configuration file support (JSON and TOML formats)
  - CLI arguments override config files for flexibility
  - Configurable workers, threads, host, and port
- **`wopr init`** - Project scaffolding with multiple templates
- **`wopr generate`** - Component generation (models, endpoints, tasks)
- Project templates for data science, real-time dashboards, CMS, and microservices

#### Optional Dependencies
- Properly isolated optional dependencies with graceful fallbacks
- `templates` (jinja2), `tasks` (duckdb), `cli` (click), `charts` (pyecharts)
- `redis` and `postgres` session storage backends
- Comprehensive `dev` extras for development tools

## Previous Versions (Pre-Release History)

## [0.3.6] - 2025-10-08

### Performance
- **Conservative Performance Optimizations (3-8% throughput improvement)**:
  - **Rust Router Enhancements**: URL decoding moved to Rust level
    - Path segments decoded using `percent_encoding` crate at native speed
    - Eliminates Python-level URL decoding overhead
    - Follows Granian's optimization patterns
    - ~3-5% improvement on routes with dynamic parameters
  - **Lazy Header Access**: Headers parsed only when accessed
    - Headers dict built lazily via property pattern
    - Zero overhead for endpoints that don't use headers
    - ~2-3% improvement for simple endpoints
  - **msgspec Decoder Caching**: JSON decoders cached on model classes
    - Decoders stored as `_msgspec_decoder_cache` on model class
    - Eliminates per-request decoder construction
    - ~2-3% improvement for msgspec.Struct validation
  - **Lazy Query String Parsing**: Query parameters parsed on demand
    - `parse_qs()` called only when `request.args` accessed
    - Empty query string fast path
    - ~1-2% improvement for requests without query params
  - **Overall Impact**:
    - 3-8% improvement for typical workloads
    - Best gains on endpoints without headers/query params
    - Modest but measurable performance boost
    - Maintains code simplicity and debuggability

### Changed
- Request headers now computed lazily (`_headers_dict` initially None - internal only)
- Query string parsing deferred until `request.args` accessed
- msgspec decoders cached on model classes (automatic, internal optimization)

## [0.3.5] - 2025-10-07

### Added
- **Comprehensive Top-Level Exports**: All major framework features now accessible from `wopr` package
  - Added missing exports: `WebSocketManager`, `TaskQueue`, `TaskStorage`
  - Added error classes: `UnsupportedMediaType`, `BodyValidationError`
  - Added routing utilities: `RouteHandler`, `use`, `register_converter`
  - Added content negotiation: `negotiate`, `negotiate_response`
  - Added SSE support: `format_sse`, `SSEStream`
  - Organized exports by category with clear documentation

### Fixed
- **Critical Session Management Fix**: New sessions now properly created and persisted
  - Fixed bug where new sessions weren't saved (missing session ID creation)
  - Added automatic session ID generation when session is modified but has no ID
  - Fixed missing Set-Cookie header for new sessions
  - Session cookies now properly set with all security attributes (Secure, HttpOnly, SameSite)
  - CSRF protection now works correctly for multipart form uploads
- **Multipart Form Data Parsing**: Enhanced form field extraction for CSRF tokens
  - `request.get_form()` now supports both `application/x-www-form-urlencoded` and `multipart/form-data`
  - Multipart data parsed once and cached for both form fields and files
  - CSRF tokens correctly extracted from multipart forms

## [0.3.1] - 2025-10-07

### Added
- **Flask/Quart-Style Reverse Routing**:
  - `app.url_for(name, **params)`: Build URLs from route names with parameter substitution
  - `redirect(location, status=302)`: Create HTTP redirect responses (supports 301, 302, 303, 307, 308)
  - Blueprint-qualified route names: `app.url_for('admin.login')` - Flask-style `blueprint.function` syntax
  - Route naming support: All HTTP method decorators now accept optional `name` parameter
  - Automatic route naming: Routes default to function name if no custom name provided
  - Rust-accelerated url_for with Python fallback for compatibility
- **Flask/Quart Convenience Features (Phase 1 & 2)**:
  - `abort(status, description, response)`: HTTP exception helper for immediate error responses
  - `make_response(rv, status, headers)`: Flexible response builder supporting multiple formats
  - `notification(request, message, category)`: Session-based notification system (Gobstopper's semantic naming for flash messages)
  - `get_notifications(request)`: Retrieve and clear notifications with category filtering
  - `peek_notifications(request)`: View notifications without clearing them
  - `clear_notifications(request)`: Manually clear all notifications
  - `HTTPException`: Exception class for abort() with custom response support
- **Enhanced Request Properties**:
  - `request.cookies`: Parsed cookie dictionary from Cookie header
  - `request.is_json`: Boolean property checking Content-Type for JSON
  - `request.endpoint`: Matched route name (function name)
  - `request.view_args`: Path parameters dictionary from route matching
  - `request.url_rule`: Original route pattern string
  - `request.url`: Complete URL including query string
  - `request.base_url`: URL without query string
  - `request.host_url`: Base URL with scheme and host
  - `request.host`: Host header value
  - `request.scheme`: URL scheme (http/https) with X-Forwarded-Proto support
- **File Upload Support (Phase 3)**:
  - `FileStorage` class: Flask-compatible file upload handler with `save()`, `read()`, `seek()`, `tell()` methods
  - `request.get_files()`: Parse uploaded files from multipart/form-data
  - `request.files`: Async property for accessing uploaded files
  - `secure_filename()`: Sanitize filenames to prevent path traversal attacks
  - `send_from_directory()`: Securely serve files with directory traversal protection
  - Multipart form data parser with file and field extraction
  - Directory creation, buffered I/O, and MIME type detection
- **Enhanced Rust Router (90% Complete)**:
  - 404/405 distinction with `allowed_methods()` and proper Allow header computation
  - Typed path converters: `<int:id>`, `<uuid:rid>`, `<date:dt>` with validation at match time
  - Trailing slash policy: `SlashPolicy.Strict`, `RedirectToSlash`, `RedirectToNoSlash`
  - Conflict detection on route registration with detailed diagnostics
  - Reverse routing support with `url_for(name, params)` in Rust
  - Router statistics: `RouterStats` with route count, nodes, dynamic segments, max depth

### Changed
- Route decorators updated: `@app.get(path, name=None)` and similar for all HTTP methods
- Blueprint routes automatically receive qualified names: `blueprint_name.function_name`
- Router integration fully updated to new Rust router API with backward compatibility

### Fixed
- WebSocket router integration with new Rust router signature
- UUID regex pattern in Python router (removed inline `(?i)` flag)
- Route pattern conversion no longer strips type information for Rust router
- RSGI Scope attribute access: Fixed `request.scheme` to use `scope.proto` attribute instead of dict access
- Request URL properties now work correctly with Granian's RSGI scope objects

## [0.3.0] - 2025-10-05

### Added
- **OpenAPI 3.1 Extension** (`src/wopr/extensions/openapi/`): Complete OpenAPI specification support with automatic schema generation
  - `/openapi.json` endpoint with full OpenAPI 3.1.0 spec generation
  - Interactive API documentation via Redoc (`/redoc`) and Stoplight Elements (`/elements`)
  - Rich metadata decorators: `@doc`, `@response`, `@request_body`, `@param`
  - Type-first schema generation with TypeRegistry and specialized adapters:
    - `MsgspecAdapter` for `msgspec.Struct` types
    - `TypedDictAdapter` with accurate required/optional field detection
    - `DataclassesAdapter` with `default`/`default_factory` semantics
  - Path parameter type mapping (int, uuid, date, path converters)
  - Multiple media type support per endpoint
  - Component schemas, security schemes, and external docs support
- **Charts Extension** (`src/wopr/extensions/charts/`): Interactive data visualization with pyecharts
  - Chart builders for Line, Bar, Pie, Scatter, Heatmap, and more
  - Streaming chart updates via SSE
  - Custom themes and styling
  - Template filters for inline chart rendering
  - Dashboard composition with multiple charts
  - Export to HTML, PNG, SVG formats
- **Blueprint System** (`src/wopr/core/blueprint.py`): Modular application structure
  - Nested blueprints with URL prefix inheritance
  - Scoped middleware (app → blueprint → route)
  - Per-blueprint template search paths
  - Static file mounting with `<prefix>/static` convention
  - Sub-app mounting with `app.mount()` and path-segment boundary validation
- **Configuration System** (`src/wopr/config.py`): Structured application configuration
  - TOML and JSON configuration file support
  - Environment variable overrides with `WOPR_` prefix
  - Type validation and default values
  - Nested configuration sections
  - Runtime configuration reloading
- **Enhanced HTTP Layer**:
  - **Content Negotiation** (`src/wopr/http/negotiation.py`): RFC 9110 Accept header parsing and response selection
  - **Problem Details** (`src/wopr/http/problem.py`): RFC 7807 problem+json error responses
  - **HTTP Errors** (`src/wopr/http/errors.py`): Structured exception hierarchy with status codes
  - **Server-Sent Events** (`src/wopr/http/sse.py`): SSE stream helpers with `format_sse()` and `SSEStream`
  - Typed request parsers: `request.json(model)`, `request.form(model)`, `request.multipart(model)`
- **Enhanced Router Features**:
  - `allowed_methods(path)`: Returns list of HTTP methods available for a path (enables proper 405 responses with Allow headers)
  - Trailing slash policy configuration: `'add_slash'`, `'remove_slash'`, or `None` (strict)
  - Method-preserving 308 Permanent Redirect for trailing slash normalization
  - Comprehensive route conflict detection at startup:
    - Duplicate static route detection
    - Dynamic/static route shadowing warnings
    - Clear diagnostic messages for configuration issues
  - Router statistics introspection: `Router.stats()` exposes route count, dynamic segments, nodes, and max depth
- **Middleware Enhancements**:
  - **Rate Limiting** (`src/wopr/middleware/limits.py`): Token bucket and sliding window rate limiters
  - Enhanced security middleware with modern headers and session management
  - Rust-powered static file serving for extreme performance
- **Utility Functions**:
  - **Idempotency** (`src/wopr/utils/idempotency.py`): Request idempotency keys and duplicate detection
  - Enhanced rate limiter with Redis backend support
- **Comprehensive Documentation**:
  - **Blueprints Guide** (`docs/blueprints.md`): Nested blueprints, middleware scoping, template paths, mounting
  - **Charts Extension** (`docs/charts_extension.md`): Interactive data visualization with pyecharts integration
  - **Configuration Guide** (`docs/configuration.md`): TOML/JSON config, environment variables, validation
  - **OpenAPI Extension** (`docs/openapi_extension.md`): Complete guide to OpenAPI features and decorators
  - **Performance Tuning** (`docs/performance_tuning.md`): Optimization strategies, benchmarking, profiling
  - **Security Best Practices** (`docs/security_best_practices.md`): CSRF, sessions, headers, input validation
  - Enhanced router and template engine documentation with v0.3.0 features

### Changed
- Router pattern handling improved: strips type hints from patterns (e.g., `<int:id>` → `:id`) and reapplies Python converter registry with proper URL-decoding
- Blueprint hook signature validation: `before_request(request)` and `after_request(request, response)` signatures validated at startup
- Example application updated to demonstrate OpenAPI decorators and documentation endpoints
- Documentation structure reorganized with comprehensive guides for all major features

### Fixed
- Enforced tail-only `<path:...>` parameter constraint to prevent routing conflicts
- Improved 404 vs 405 handling with correct Allow header population for both Rust and Python routers
- Mount prefix matching now respects path-segment boundaries correctly

## [0.2.5] - 2025-09-25
### Fixed
- Importability: re-exported `gobstopper.extensions` from the top-level package and added explicit `__all__` in `gobstopper.extensions.openapi` to ensure `from gobstopper.extensions.openapi import attach_openapi` works reliably in wheels.

### Changed
- Version bumped to 0.2.5.
- Example app imports updated to use `from gobstopper...` instead of `from src.gobstopper...`.

## [0.2.4] - 2025-09-25
### Fixed
- Packaging: ensured OpenAPI extensions are included in built wheels by removing Rust-only wheel builds. The build script now builds from the project root so Python sources under `src/` are bundled.

### Changed
- Version bumped to 0.2.4.
- Example app updated to display 0.2.4 and use the new OpenAPI extension.

## [0.2.3] - 2025-09-24
### Added
- OpenAPI extension endpoints: `/openapi.json`, `/redoc`, `/scalar` (via CDN). Swagger UI intentionally excluded.
- Type-first OpenAPI generation with TypeRegistry and adapters:
  - MsgspecAdapter for `msgspec.Struct`
  - TypedDictAdapter with accurate required/optional handling
  - DataclassesAdapter for `dataclasses` with `default`/`default_factory` semantics
- Example app: new OpenAPI demo routes using decorators (`@doc`, `@response`, `@request_body`, `@param`), multiple media types, and path parameter typing.
- Path converter mapping in generator: `int`, `uuid`, `date`, `path`.
- Initial unit tests for path conversion and adapters.

### Changed
- Version bumped to 0.2.3.
- Example app now shows OpenAPI usage and points to `/redoc` and `/scalar`.

### Fixed
- TypedDict required keys logic updated to use `__required_keys__`/`__optional_keys__`, supporting `total=False` and `Required`/`NotRequired`.

## [0.2.2] - 2025-09-13
### Added
- Blueprint system:
  - Nested blueprints with URL prefix joining and inheritance
  - Scoped middleware at app → blueprints → route with deterministic ordering
  - Per‑blueprint template search paths and static mounts (`<prefix>/static`)
  - Sub‑app mounting via `app.mount()` with path‑segment boundary checks
- Content negotiation utilities with RFC 9110 Accept parsing and `negotiate_response()` helper
- Typed Request parsers: `json(model)`, `form(model)`, `multipart(model, max_size)` with 415/422 error mapping via `application/problem+json`
- SSE helpers: `format_sse()` and `SSEStream` with correct headers and backpressure‑friendly streaming
- Routing visualization improvements and a shadow route list for Rust‑router mode
- Session management system:
  - Production‑grade, pluggable backends (Memory, Redis, Postgres) with backward‑compatible File store
  - `SecurityMiddleware` integration (optional ID signing, rolling sessions, configurable cookies)
  - Response cookie helpers: `set_cookie()` and `delete_cookie()` with multi‑cookie support

### Changed
- Router integration:
  - Rust router patterns strip types (`<int:id>` → `:id`) and reapply Python converter registry with URL‑decoding
  - Enforced tail‑only `<path:...>`
  - 404 vs 405 improved; `Allow` header populated for both routers
- Mount prefix matching fixed to respect path‑segment boundaries
- Cached handler signatures to reduce per‑request reflection overhead
- Access logging in hot path demoted to DEBUG when `app.debug` is true (no per‑request INFO logs)
- Benchmark apps/scripts:
  - `benchmark_simple.py` shows version 0.2.2, includes `rust_router` flag, and recommends `--log-level error`
  - `quick_benchmark.py` reuses a single `aiohttp` session with tuned connector and warm‑up
- Time APIs modernized: replace `datetime.utcnow()` with timezone‑aware `datetime.now(datetime.timezone.utc)`

### Fixed
- Prevent per‑request mutation of global `after_request` handlers; set `X-Request-ID` directly on each response
- Stabilize quick benchmark across runs by reusing a single `ClientSession` and adding a warm‑up request
- Eliminated periodic slow‑downs due to console I/O pressure from per‑request logging
