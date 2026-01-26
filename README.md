# Gobstopper Web Framework 🍬

> *"Like Willy Wonka's Everlasting Gobstopper - a simple wrapper that delivers a complete multi-course meal"*

A **production-ready**, high-performance async web framework built specifically for Granian's RSGI interface. Gobstopper takes the raw power of RSGI and wraps it in a simple, elegant API - giving you a full-featured web framework that's as easy to use as Flask but as fast as raw ASGI/RSGI.

**The Magic**: Just like Wonka's magical candy that contains an entire meal in a single piece, Gobstopper wraps RSGI's complexity into a simple interface while delivering everything you need: routing, templates, WebSockets, background tasks, sessions, security, and more.

## 🎯 Why Gobstopper?

**Simple Wrapper, Complex Power:**
- 🍬 **Simple API**: Flask-like simplicity wrapping RSGI's raw performance
- ⚡️ **RSGI Native**: Direct access to Granian's high-performance RSGI interface
- 🦀 **Rust-Accelerated**: Optional Rust components for routing, templates, and static files
- 🔋 **Batteries Included**: Complete framework - background tasks, WebSockets, sessions, and security
- 🎨 **Familiar Design**: Ergonomic API with modern async/await patterns
- 📦 **Layered Features**: Start simple, add complexity only when you need it

## 🏁 Benchmarks

```
🧪 Testing Gobstopper Benchmark Endpoints
==================================================
✅ Info              1.04ms  application/json
✅ JSON              0.44ms  application/json
✅ Plaintext         0.35ms  text/plain
✅ Single Query      1.51ms  application/json
✅ 5 Queries         1.64ms  application/json
✅ 3 Updates         2.77ms  application/json
✅ Fortunes          2.72ms  text/html; charset=utf-8
✅ 10 Cached        11.91ms  application/json
```

## 🚀 Features

### 🦀 **Rust-Powered Components**
- **Rust Router**: High-performance path routing with zero-copy parameter extraction
- **Rust Templates**: Blazing-fast Jinja2-compatible rendering with streaming support
- **Rust Static Files**: Ultra-fast static asset serving with intelligent caching
- **Hybrid Architecture**: Seamless fallback to Python components when Rust unavailable

### 🌐 **Core Framework**
- **RSGI Interface**: Built specifically for Granian's high-performance RSGI protocol
- **Type-Safe Validation**: Automatic request validation with msgspec Struct type hints
- **High-Performance JSON**: msgspec-powered JSON parsing and serialization (up to 10x faster)
- **Async/Await**: Full async support throughout the framework stack
- **Background Tasks**: Intelligent task system with DuckDB persistence, priorities, and retries
- **WebSocket Support**: Real-time communication with room management and broadcasting
- **Template Engine**: Jinja2 integration with async support and hot-reload
- **Middleware System**: Static files, CORS, security, and custom middleware

### 🔒 **Security & Production**
- **Security First**: CSRF protection, security headers, rate limiting, input validation
- **Production Ready**: Comprehensive error handling, logging, and monitoring
- **CLI Tools**: Project initialization, task workers, and management commands
- **Cross-Platform**: Native wheels for macOS ARM64, Linux x86_64/ARM64
- **Developer Experience**: Clean APIs, helpful error messages, hot reload

## 📦 Installation

```bash
# Basic installation (core framework only)
uv add gobstopper

# With all optional features
uv add "gobstopper[all]"

# Or specific features
uv add "gobstopper[templates,tasks,cli,charts]"

# For production with session backends
uv add "gobstopper[redis,postgres]"

# Development installation
uv add "gobstopper[dev]"
```

### Optional Dependencies

Gobstopper uses optional dependencies to keep the core lightweight:

- **`templates`**: Jinja2 template engine (`jinja2>=3.1.0`)
- **`tasks`**: Background task system with DuckDB persistence (`duckdb>=0.9.0`)
- **`cli`**: Command-line tools for project generation (`click>=8.0.0`)
- **`charts`**: Data visualization support (`pyecharts>=2.0.0`)
- **`redis`**: Redis session storage backend (`redis>=5.0`)
- **`postgres`**: PostgreSQL session storage backend (`asyncpg`)
- **`dev`**: Development tools (pytest, black, ruff, mypy, httpx)
- **`all`**: All optional features except dev dependencies

**Note**: All optional features have graceful fallbacks - the framework will work without them, but specific features will be unavailable.

## 🏃 Quick Start

### Create a New Project
```bash
# Install Gobstopper with CLI tools
uv add "gobstopper[cli]"

# Create new project
uv run gobstopper init my_app

# Navigate and run
cd my_app
uv sync
uv run gobstopper run --reload
```

### Simple Example
```python
from gobstopper import Gobstopper, Request, jsonify

app = Gobstopper(__name__)

@app.get("/")
async def hello(request: Request):
    return jsonify({"message": "Hello from Gobstopper!"})

@app.get("/users/<user_id>")
async def get_user(request: Request, user_id: str):
    return jsonify({"user_id": user_id, "name": f"User {user_id}"})

# Run with: gobstopper run
# Or: gobstopper run --reload  (with auto-reload)
# Or: gobstopper run -w 4      (with 4 workers)
```

## 📚 Examples

### 🌟 Interactive Demo (`example_app.py`)
Complete showcase of all framework features with a web UI:
```bash
uv sync --extra all
granian --interface rsgi --reload example_app:app
```
Visit http://localhost:8000 for interactive demos of:
- HTTP endpoints and routing
- Background task processing
- WebSocket communication
- Security features
- Middleware functionality

### 🧩 Blueprints Demo (`blueprints_demo`)
A blueprint-structured sample app demonstrating nested blueprints, per-blueprint static/templates, WebSockets, background tasks, middleware, and rate limiting.

Run:
```bash
uv sync --extra all
granian --interface rsgi --reload blueprints_demo.app:app
# or:
uv run granian -w 1 -h 0.0.0.0 -p 8080 -r blueprints_demo.app:app
```
Then visit http://localhost:8080/

### 📊 Data Handling (`data_example.py`)
RESTful API demonstrating data operations:
```bash
granian --interface rsgi --reload data_example:app
```
Features:
- CRUD operations with filtering and pagination
- Background data processing
- Real-time analytics
- Task monitoring

### 📈 Benchmarks (`benchmark_simple.py`)
Standard TechEmpower benchmark implementation:
```bash
granian --interface rsgi --workers 4 --threads 2 benchmark_simple:app
```
Benchmark endpoints:
- JSON serialization
- Database queries (simulated)
- Database updates (simulated)
- Plaintext response
- HTML template rendering
- Cached queries

## 🏗️ Architecture

```
src/gobstopper/
├── core/           # Main Gobstopper application class
├── http/           # Request/Response handling & routing  
├── websocket/      # WebSocket support & room management
├── tasks/          # Background task system with DuckDB
├── templates/      # Jinja2 template engine
├── middleware/     # Static files, CORS, security
├── cli/            # Command-line tools
└── utils/          # Rate limiting and utilities
```

## 🔧 Key Components

### Application & Type-Safe Validation
```python
from gobstopper import Gobstopper
from msgspec import Struct

app = Gobstopper(__name__, debug=True)
app.init_templates()  # Enable Jinja2 templates

# Define data models with automatic validation
class User(Struct):
    name: str
    email: str
    age: int = 0  # Optional field with default

class UpdateUser(Struct):
    name: str = None  # All fields optional for updates
    email: str = None

# Routes with automatic validation
@app.post("/api/users")
async def create_user(request, user: User):
    # user is automatically validated and typed!
    # No manual request.json() or validation needed
    return {"message": f"Created user: {user.name}"}

@app.put("/api/users/<user_id>")
async def update_user(request, user_id: str, updates: UpdateUser):
    # Path params + validated body automatically injected
    return {"updated": user_id, "changes": updates}

# Manual JSON parsing still available
@app.post("/api/data")
async def manual_data(request):
    data = await request.get_json()  # msgspec powered
    return {"received": data}

# Middleware
from gobstopper.middleware import CORSMiddleware
app.add_middleware(CORSMiddleware(origins=["*"]))
```

### Background Tasks
```python
import os
from gobstopper import should_run_background_workers

# Enable background tasks (required)
os.environ["WOPR_TASKS_ENABLED"] = "1"

@app.task("send_email", "notifications")
async def send_email(to: str, subject: str):
    # Task implementation
    return {"status": "sent"}

# Queue tasks
task_id = await app.add_background_task(
    "send_email", "notifications", TaskPriority.HIGH,
    to="user@example.com", subject="Welcome!"
)

# Start workers (only in main process when using multiple workers)
@app.on_startup
async def startup():
    if should_run_background_workers():
        await app.start_task_workers("notifications", worker_count=2)
```

### WebSocket
```python
@app.websocket("/ws/chat")
async def chat_handler(websocket):
    await websocket.accept()
    
    while True:
        message = await websocket.receive()
        await websocket.send_text(f"Echo: {message.data}")
```

### Templates
```python
@app.get("/")
async def index(request):
    return await app.render_template("index.html",
                                   message="Hello World!")
```

### File Uploads
```python
from gobstopper import FileStorage, secure_filename, send_from_directory

@app.post("/upload")
async def upload_file(request):
    files = await request.get_files()

    if 'document' in files:
        file: FileStorage = files['document']
        filename = secure_filename(file.filename)
        file.save(f"uploads/{filename}")
        return {"uploaded": filename}

    return {"error": "No file"}, 400

@app.get("/files/<path:filename>")
async def serve_file(request, filename: str):
    return send_from_directory("uploads", filename)
```

### Flask/Quart Convenience Features
```python
from gobstopper import abort, make_response, notification

@app.get("/users/<user_id>")
async def get_user(request, user_id: str):
    if not user_id.isdigit():
        abort(400, "Invalid user ID")

    user = find_user(user_id)
    if not user:
        abort(404, "User not found")

    return {"user": user}

@app.post("/users")
async def create_user(request):
    # Flash-style notifications
    notification(request, "User created successfully!", "success")

    # Flexible response building
    response = make_response({"id": 123}, 201, {"X-User-ID": "123"})
    return response
```

## 🛠️ CLI Tools

Gobstopper includes a comprehensive CLI for rapid development and project management:

### 🏃 Running Your Application

```bash
# Basic usage (Flask-like interface)
gobstopper run

# With auto-reload for development
gobstopper run --reload

# Production with multiple workers
gobstopper run -w 4

# Custom host and port
gobstopper run -h 0.0.0.0 -p 3000

# Specific app module
gobstopper run myapp:app

# Load from configuration file
gobstopper run --config dev              # Loads dev.json or dev.toml
gobstopper run --config production       # Loads production.json or production.toml

# Override config with CLI arguments
gobstopper run --config production -w 8  # Use production config but override workers

# All options
gobstopper run -w 4 -t 2 -h 0.0.0.0 -p 8080 --reload
```

**Configuration Files:**

Create `dev.json`, `production.json`, or use TOML format:

```json
{
  "app": "myapp:app",
  "host": "0.0.0.0",
  "port": 8080,
  "workers": 4,
  "threads": 2,
  "reload": false
}
```

```toml
# production.toml
app = "myapp:app"
host = "0.0.0.0"
port = 8080
workers = 4
threads = 2
reload = false
```

**Platform-Optimized Performance:**
- 🍎 **ARM (Apple Silicon)**: Automatically uses `--runtime-mode st` (single-threaded)
- 💻 **x86_64 (Intel/AMD)**: Automatically uses `--runtime-mode mt` (multi-threaded)

**Built-in Granian Optimizations:**
- `--log-level error`: Minimal logging overhead
- `--backlog 16384`: Large connection backlog for high throughput
- `--loop uvloop`: High-performance event loop
- `--respawn-failed-workers`: Automatic worker recovery

### 🚀 Project Generation

```bash
# Interactive project setup
gobstopper init

# Create specific project types  
gobstopper init my-api --usecase data-science --structure modular
gobstopper init my-cms --usecase content-management --structure blueprints
gobstopper init dashboard --usecase real-time-dashboard --structure microservices
gobstopper init simple-app --usecase microservice --structure single
```

**Available Use Cases:**
- **`data-science`**: ML APIs with data processing, model endpoints, and analytics
- **`real-time-dashboard`**: Live dashboards with WebSocket streaming and data visualization  
- **`content-management`**: Full CMS with admin interface, user management, and content APIs
- **`microservice`**: Lightweight service architecture for distributed systems

**Available Structures:**
- **`modular`**: Clean separation with modules (recommended for large projects)
- **`blueprints`**: Flask-style blueprints for organized route grouping
- **`microservices`**: Distributed service architecture with service discovery
- **`single`**: Single-file applications for simple projects and prototypes

### ⚡ Component Generation

```bash
# Generate data models with type hints
gobstopper generate model User -f name:str -f email:str -f created_at:datetime -f is_active:bool

# Generate API endpoints with automatic routing
gobstopper generate endpoint /api/users -m GET --auth
gobstopper generate endpoint /api/users -m POST --auth

# Generate background tasks with categories  
gobstopper generate task process_data --category data
gobstopper generate task send_notification --category notifications

# Generate WebSocket handlers
gobstopper generate websocket /ws/live --room-based
```

### 🔧 Development Commands

```bash
# Run background task workers
gobstopper run-tasks --categories data,notifications --workers 3

# Clean up old completed tasks
gobstopper cleanup-tasks --days 7
gobstopper cleanup-tasks --months 1

# Version and system info
gobstopper version
```

### 📁 Generated Project Structure

**Modular Structure:**
```
my_app/
├── app.py              # Main application
├── config.py           # Configuration
├── requirements.txt    # Dependencies
├── .env.example        # Environment template
├── modules/            # Feature modules
│   ├── auth/           # Authentication
│   ├── api/            # API routes
│   ├── admin/          # Admin interface
│   └── public/         # Public pages
├── models/             # Data models  
├── tasks/              # Background tasks
├── templates/          # Jinja2 templates
└── static/             # CSS, JS, images
```

**Blueprint Structure:**
```
my_app/
├── app.py              # Main application
├── blueprints/         # Route blueprints
│   ├── auth.py         # Auth routes
│   ├── api.py          # API routes
│   └── admin.py        # Admin routes
└── ...
```

### 🎯 Use Case Features

Each use case generates tailored code:

**Data Science:**
- Model training/inference endpoints
- Data processing pipelines  
- Analytics and metrics APIs
- Jupyter notebook integration

**Real-time Dashboard:**  
- WebSocket streaming endpoints
- Live data aggregation
- Chart and graph APIs
- Real-time metrics collection

**Content Management:**
- User authentication/authorization
- CRUD operations for content
- Media upload handling
- Admin dashboard interface

**Microservice:**
- Health check endpoints
- Service discovery integration
- Metrics and monitoring
- Minimal dependencies

## 🛡️ Security

- **CSRF Protection**: Built-in CSRF token generation and validation
- **Security Headers**: X-Frame-Options, CSP, HSTS, etc.
- **Rate Limiting**: Configurable rate limiting with decorators
- **Input Validation**: Request data validation and sanitization
- **Static File Security**: Path traversal protection

### JSON Limits (Size & Depth)
- Configure maximum JSON request body size via env `GOBSTOPPER_JSON_MAX_BYTES` (bytes). If exceeded, returns HTTP 413 (Request too large).
- Configure maximum JSON nesting depth via env `GOBSTOPPER_JSON_MAX_DEPTH`. If exceeded, returns HTTP 400 with a clear error.
- Limits are applied per-request; you can also set `request.max_body_bytes` / `request.max_json_depth` manually in middleware if needed.

### Secure Cookies (Production)
- When `ENV=production`, cookie attributes are enforced by default:
  - `Secure=True`, `HttpOnly=True`, `SameSite=Lax` (if not set)
- To explicitly allow insecure cookies in production (not recommended), set `GOBSTOPPER_ALLOW_INSECURE_COOKIES=true`.
- Gobstopper logs a warning when it has to override insecure cookie attributes in production.

### WebSocket Safety
- Max message size enforced via `MAX_WS_MESSAGE_BYTES` (default: 1 MiB). Oversized messages are closed with code 1009.
- Basic send backpressure with chunked writes (`WS_SEND_CHUNK_BYTES`, default: 64 KiB).

### Basic Rate Limiting
Use the built-in token-bucket limiter:
```python
from gobstopper.utils.rate_limiter import TokenBucketLimiter, rate_limit

limiter = TokenBucketLimiter(rate=5, capacity=10)  # 5 req/sec, burst 10

@app.get('/limited')
@rate_limit(limiter, key=lambda req: req.client_ip)
async def limited(request):
    return {'ok': True}
```

### Session Management

Gobstopper includes a production-grade, database-backed session system with a familiar API.

- **Pluggable Backends**: Supports Redis, PostgreSQL, and in-memory storage.
- **Secure by Default**: Optional HMAC-signed session IDs and secure cookie flags.
- **Ergonomic API**: Simple `request.session` access and `response.set_cookie()` helpers.

For more details, see the [Middleware documentation](./docs/core/middleware.md#session-management).

**Note**: The default file-based session storage is not recommended for production, especially in cloud or containerized environments. Use Redis or PostgreSQL for production deployments.

## ⚡ Performance

- **RSGI Interface**: Maximum performance with Granian server
- **Async Throughout**: Non-blocking operations everywhere
- **Background Tasks**: Offload heavy work to background queues
- **Efficient Routing**: Fast path matching with parameter extraction
- **Optional Dependencies**: Load only what you need

## 🧪 Testing

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests (when implemented)
uv run pytest

# Code quality
uv run black .          # Format code
uv run ruff check .     # Lint code  
uv run mypy src/        # Type checking
```

## 📖 Documentation

### Official Documentation

Build and view the complete Sphinx documentation:

```bash
./build_docs.sh
cd sphinx-docs
python -m http.server 8080 -d build/html
# Visit http://localhost:8080
```

Or use live preview:

```bash
cd sphinx-docs
pip install -r requirements.txt
sphinx-autobuild source build/html
# Visit http://127.0.0.1:8000
```

### Additional Resources

- **Example Applications**: Fully commented examples demonstrating all features
- **Inline Documentation**: Comprehensive docstrings and type hints throughout
- **Markdown Docs**: Additional guides in the `docs/` directory
- See the [Changelog](CHANGELOG.md) for release notes

## 🛠️ Building from Source

Gobstopper includes Rust extensions for maximum performance. Build tools are provided:

```bash
# Install build dependencies
uv add --dev maturin build

# 1) Fast dev install of Rust core into your current venv (recommended while iterating)
#    Defaults to features: router,templates,static
uv run python dev_install_rust.py --strip
# or explicitly:
MATURIN_FEATURES="router,templates,static" uv run python dev_install_rust.py --strip

# 2) Build wheels for the current platform (drops wheels in ./dist)
python build_wheels.py --platform local --features "router,templates,static"

# 3) Build Linux manylinux wheels for both x86_64 and aarch64 (requires Docker)
python build_wheels.py --platform linux --arch both --features "router,templates,static"

# 4) Build for all platforms
./build_linux_wheels.sh
```

To verify the Rust core is active at runtime, look for these logs on startup:

```
🚀 Found Rust extensions, using high-performance router.
🦀 Rust template engine initialized successfully
```

You can also run:

```bash
python -c "import gobstopper._core as core; print('Symbols:', [s for s in dir(core) if not s.startswith('_')][:20])"
```

## 📦 Distribution Packages

Pre-built wheels available for:
- **macOS ARM64**: Python 3.10, 3.11, 3.12, 3.13
- **Linux x86_64**: Python 3.10, 3.11, 3.12, 3.13
- **Linux ARM64**: Python 3.10, 3.11, 3.12, 3.13
- **Source Distribution**: Universal compatibility

## 🤝 Contributing

Gobstopper is built with modern Python and Rust:
- **Python 3.10+** (3.13 recommended) for latest async improvements
- **Rust** for high-performance components (optional)
- **Type hints** throughout the Python codebase
- **Modular architecture** for easy extension
- **Comprehensive error handling** and logging
- **Security-first design** with defense in depth

## 📄 License

MIT License - see LICENSE file for details.

## 🔗 Links

- **GitHub**: https://github.com/iristech-systems/Gobstopper
- **Documentation**: https://iristech-systems.github.io/Gobstopper-Docs/
- **PyPI**: https://pypi.org/project/gobstopper

---

**Gobstopper** - High-performance async web framework for modern Python web applications. 🎮