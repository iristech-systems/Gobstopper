# Changelog

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
