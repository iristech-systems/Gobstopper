#!/usr/bin/env python3
"""
Example Gobstopper application demonstrating all features
"""

import asyncio
import os
import time
from pathlib import Path

# Enable background tasks (required for task system)
os.environ["WOPR_TASKS_ENABLED"] = "1"

from gobstopper import (
    Gobstopper, Request, jsonify, TaskPriority,
    WebSocket, Response, abort, make_response,
    notification, get_notifications, should_run_background_workers, JSONResponse
)
from gobstopper.http import redirect, send_from_directory, FileStorage, secure_filename
from gobstopper.middleware import CORSMiddleware, SecurityMiddleware
from gobstopper.utils.rate_limiter import rate_limit, TokenBucketLimiter
from gobstopper.utils.idempotency import use_idempotency
from gobstopper.extensions.openapi import attach_openapi
from gobstopper.extensions.openapi.decorators import doc, response, request_body, param

# Try to use Rust static handler, fall back to Python if not available
try:
    from src.gobstopper.middleware.rust_static import RustStaticMiddleware

    static_middleware = RustStaticMiddleware("static", "/static")
    static_handler_name = "Rust-powered static files (blazing fast! 🦀)"
except ImportError:
    from src.gobstopper.middleware import StaticFileMiddleware

    static_middleware = StaticFileMiddleware("static", "/static")
    static_handler_name = "Python static files"

# Create Gobstopper application
app = Gobstopper(__name__, debug=True)
# Attach OpenAPI extension and docs endpoints
attach_openapi(app, title="Gobstopper Demo", version="0.1.0", description="Example Gobstopper demo app with OpenAPI docs")

# Rate limiter instances (example): 10 requests per 60s per client IP
health_limiter = TokenBucketLimiter(rate=10/60, capacity=10)

# Initialize templates with Rust engine (auto-detects availability)
app.init_templates("templates", use_rust=None, enable_streaming=True, enable_hot_reload=True)


# Template globals and filters
def get_app_name():
    return "Gobstopper Demo"


def get_version():
    return "0.1.0"


def currency_filter(amount):
    return f"${amount:,.2f}"


# Register template filter
app.template_engine.add_filter("currency", currency_filter)

# Add middleware (higher priority runs first)
app.add_middleware(static_middleware, priority=1)
app.add_middleware(CORSMiddleware(origins=["*"], allow_credentials=True), priority=10)
security = SecurityMiddleware(
     secret_key="dev-secret-key-change-me",
     debug=True,
     rolling_sessions=True,
     sign_session_id=True,
     cookie_secure=False,
     cookie_samesite="Lax",
     csp_policy=(
         "default-src * 'unsafe-inline' 'unsafe-eval'; "
         "connect-src *; "
         "style-src * 'unsafe-inline'; "
         "img-src * data: blob:; "
         "font-src * data:; "
         "object-src 'none'"
     ),
 )
app.add_middleware(security, priority=5)

# --- CSRF demo endpoints ---
@app.get("/csrf-demo")
async def csrf_demo_form(request: Request):
    # Generate token and store in session
    token = security.generate_csrf_token(request.session)
    html = f"""
    <html><body>
      <h1>CSRF Demo</h1>
      <form method=\"post\" action=\"/csrf-demo\" enctype=\"application/x-www-form-urlencoded\">
        <input type=\"hidden\" name=\"csrf_token\" value=\"{token}\" />
        <input type=\"text\" name=\"message\" />
        <button type=\"submit\">Submit</button>
      </form>
    </body></html>
    """
    return Response(html, content_type="text/html")

@app.post("/csrf-demo")
async def csrf_demo_submit(request: Request):
    form = await request.get_form()
    msg = (form.get("message") or [""])[0]
    return jsonify({"status": "ok", "message": msg})

# --- Idempotency demo ---
@app.post("/purchase")
@use_idempotency(ttl_seconds=30)
async def create_purchase(request: Request):
    data = await request.get_json()
    # pretend to process a charge
    await asyncio.sleep(0.1)
    return {"result": "charged", "amount": data.get("amount") if isinstance(data, dict) else None}


# Context processor
@app.context_processor
def inject_globals():
    return {
        'current_user': {'name': 'Demo User'},
        # Pass template globals as context for Rust engine compatibility
        'app_name': get_app_name(),
        'version': get_version()
    }


# Background tasks
@app.task("send_email", "notifications")
async def send_email(to: str, subject: str, body: str):
    """Send email task with simulated processing"""
    # Note: Tasks run outside of a request context, so we use the global logger
    app.logger.info(f"📧 Sending email to {to}: {subject}")
    await asyncio.sleep(2)  # Simulate email sending
    return {"status": "sent", "recipient": to, "timestamp": time.time()}


@app.task("process_data", "processing")
async def process_data(data: list):
    """Process data with progress tracking"""
    app.logger.info(f"🔄 Processing {len(data)} items")

    processed = []
    for i, item in enumerate(data):
        # Simulate processing
        await asyncio.sleep(0.1)
        processed.append(f"processed_{item}")

        # Update progress (in real app, you'd update the task info)
        progress = (i + 1) / len(data) * 100
        app.logger.debug(f"Progress: {progress:.1f}%")

    return {"processed_count": len(processed), "items": processed}


@app.task("long_running_task", "processing")
async def long_running_task(duration: int = 10):
    """Long running task for testing"""
    app.logger.info(f"⏱️  Starting long task for {duration} seconds")

    for i in range(duration):
        await asyncio.sleep(1)
        app.logger.debug(f"Long task progress: {i + 1}/{duration}")

    return {"duration": duration, "completed_at": time.time()}


# --- Session demo routes using new session system ---
@app.post("/login-demo")
async def login_demo(request: Request):
    """Create a demo session and set cookie using SecurityMiddleware helpers"""
    # Parse optional JSON body to customize user
    data = await request.get_json() or {}
    user = data.get("user", "demo")

    # Create a new session backend-side
    session_data = {"user": user, "created_at": time.time()}
    session_id = await security.create_session(session_data)

    # Sign the cookie value if enabled
    cookie_val = security.sign_cookie_value(session_id)

    # Redirect to home and set the cookie
    resp = Response("", status=302, headers={"Location": "/"})
    resp.set_cookie(
        security.cookie_name,
        cookie_val,
        path=security.cookie_path,
        domain=security.cookie_domain,
        max_age=security.cookie_max_age,
        secure=security.cookie_secure,
        httponly=security.cookie_httponly,
        samesite=security.cookie_samesite,
    )
    return resp


@app.get("/me-demo")
async def me_demo(request: Request):
    """Return current session contents or 401 if not authenticated"""
    if not request.session:
        return {"authenticated": False, "detail": "No active session"}, 401
    return {"authenticated": True, "session": request.session}


@app.post("/logout-demo")
async def logout_demo(request: Request):
    """Destroy current session and delete cookie"""
    # Destroy backend session if present
    sid = request.session_id
    if sid:
        await security.destroy_session(sid)

    # Redirect to home and delete cookie
    resp = Response("", status=302, headers={"Location": "/"})
    resp.delete_cookie(security.cookie_name, path=security.cookie_path, domain=security.cookie_domain)
    return resp


# --- End session demo routes ---

# Auth pages
@app.get("/login")
async def login_page(request: Request):
    """Render a simple login page that posts to /login-demo"""
    csrf_token = security.generate_csrf_token(request.session)
    return await app.render_template("login.html", csrf_token=csrf_token, page_title="Login")


@app.get("/me")
async def me_page(request: Request):
    """Render a profile page showing current session info"""
    csrf_token = security.generate_csrf_token(request.session)
    authenticated = bool(request.session)
    session_data = request.session if request.session else {}
    user = session_data.get("user") if session_data else None
    return await app.render_template(
        "me.html",
        csrf_token=csrf_token,
        authenticated=authenticated,
        session=session_data,
        user=user,
        page_title="Your Profile"
    )

# --- Flask/Quart Convenience Features Demo ---

@app.get("/demo/abort")
async def demo_abort(request: Request):
    """Demonstrate abort() for immediate error responses"""
    user_id = request.args.get("user_id", [None])[0]
    if not user_id:
        abort(400, "Missing user_id parameter")
    if user_id == "forbidden":
        abort(403, response=jsonify({"error": "Forbidden", "reason": "Access denied"}))
    if user_id != "123":
        abort(404, "User not found")
    return jsonify({"user_id": user_id, "name": "Demo User"})


@app.get("/demo/make-response")
async def demo_make_response(request: Request):
    """Demonstrate make_response() for flexible response building"""
    # Build response with custom headers and cookies
    resp = make_response(jsonify({"message": "Response with custom headers"}), 200)
    resp.headers['X-Custom-Header'] = 'Gobstopper-Demo'
    resp.headers['X-Request-ID'] = request.id
    resp.set_cookie('demo_cookie', 'custom_value', max_age=3600)
    return resp


@app.get("/demo/request-properties")
async def demo_request_properties(request: Request):
    """Demonstrate new Flask/Quart-style request properties"""
    return jsonify({
        # URL properties
        "url": request.url,
        "base_url": request.base_url,
        "host_url": request.host_url,
        "host": request.host,
        "scheme": request.scheme,
        # Route properties
        "endpoint": request.endpoint,
        "view_args": request.view_args,
        "url_rule": request.url_rule,
        # Content checks
        "is_json": request.is_json,
        # Cookies (if any)
        "cookies": dict(request.cookies),
    })


@app.post("/demo/notification-set")
async def demo_notification_set(request: Request):
    """Demonstrate notification() for setting flash messages"""
    data = await request.get_json()
    message = data.get("message", "Test notification")
    category = data.get("category", "info")

    notification(request, message, category)

    # Redirect to notification viewer (Post-Redirect-Get pattern)
    return redirect(app.url_for('demo_notification_view'), status=303)


@app.get("/demo/notification-view", name='demo_notification_view')
async def demo_notification_view(request: Request):
    """Demonstrate get_notifications() for retrieving flash messages"""
    notifications = get_notifications(request)

    if not notifications:
        return jsonify({
            "notifications": [],
            "message": "No notifications. POST to /demo/notification-set to create one."
        })

    return jsonify({
        "notifications": [
            {"category": cat, "message": msg}
            for cat, msg in notifications
        ]
    })


@app.get("/demo/convenience-features")
async def demo_convenience_features(request: Request):
    """Demo page for Flask/Quart convenience features"""
    csrf_token = security.generate_csrf_token(request.session)

    # Get any pending notifications
    notifications = get_notifications(request)

    return await app.render_template("convenience_demo.html",
                                     csrf_token=csrf_token,
                                     notifications=notifications,
                                     request_info={
                                         "endpoint": request.endpoint,
                                         "url": request.url,
                                         "scheme": request.scheme,
                                         "host": request.host,
                                     })


# --- File Upload Features Demo ---

@app.post("/demo/upload")
async def demo_upload(request: Request):
    """Demonstrate file upload with FileStorage"""
    files = await request.get_files()

    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    uploaded_files = []
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    for field_name, file in files.items():
        if file and file.filename:
            # Sanitize filename
            safe_name = secure_filename(file.filename)

            # Save file
            file_path = upload_dir / safe_name
            file.save(file_path)

            uploaded_files.append({
                "field": field_name,
                "original_filename": file.filename,
                "saved_as": safe_name,
                "size": file_path.stat().st_size,
                "content_type": file.content_type
            })

    notification(request, f"Uploaded {len(uploaded_files)} file(s) successfully!", "success")

    return jsonify({
        "uploaded": uploaded_files,
        "message": f"Successfully uploaded {len(uploaded_files)} file(s)"
    })


@app.get("/uploads/<path:filename>")
async def demo_serve_upload(request: Request, filename: str):
    """Demonstrate send_from_directory for serving uploaded files"""
    try:
        return send_from_directory("uploads", filename)
    except FileNotFoundError:
        abort(404, "File not found")
    except PermissionError:
        abort(403, "Access denied")


@app.get("/demo/upload-form")
async def demo_upload_form(request: Request):
    """Simple upload form for testing"""
    csrf_token = security.generate_csrf_token(request.session)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>File Upload Demo</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; }}
            .upload-box {{ border: 2px dashed #ccc; padding: 20px; text-align: center; }}
            button {{ background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            .success {{ color: green; margin-top: 20px; }}
            .error {{ color: red; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h1>File Upload Demo</h1>
        <div class="upload-box">
            <form method="POST" action="/demo/upload" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="{csrf_token}" />
                <h3>Select files to upload:</h3>
                <input type="file" name="file1" /><br/><br/>
                <input type="file" name="file2" /><br/><br/>
                <input type="file" name="file3" /><br/><br/>
                <button type="submit">Upload Files</button>
            </form>
        </div>
        <div style="margin-top: 30px;">
            <h3>Features Demonstrated:</h3>
            <ul>
                <li>✅ FileStorage class for handling uploads</li>
                <li>✅ secure_filename() for sanitizing filenames</li>
                <li>✅ request.get_files() / request.files</li>
                <li>✅ send_from_directory() for serving files</li>
                <li>✅ Directory traversal protection</li>
            </ul>
        </div>
        <div style="margin-top: 30px;">
            <h3>Try it:</h3>
            <p>1. Select one or more files</p>
            <p>2. Click "Upload Files"</p>
            <p>3. Files will be saved to the uploads/ directory</p>
            <p>4. Access uploaded files at /uploads/&lt;filename&gt;</p>
        </div>
    </body>
    </html>
    """
    return Response(html, content_type="text/html")


# Routes
@app.get('/Error')
async def create_error(request: Request):
    return 1 / 0


@app.get("/")
async def index(request: Request):
    """Home page showcasing Gobstopper features"""
    # Check what engines we're using
    rust_templates = hasattr(app.template_engine, 'using_rust') and app.template_engine.using_rust
    rust_static = "Rust" in static_handler_name

    # Get template engine stats
    template_stats = None
    if hasattr(app.template_engine, 'get_cache_stats'):
        template_stats = app.template_engine.get_cache_stats()

    # Generate CSRF token
    csrf_token = security.generate_csrf_token(request.session)

    return await app.render_template("index.html",
                                     csrf_token=csrf_token,
                                     message="Welcome to Gobstopper!",
                                     rust_powered=rust_templates or rust_static,
                                     template_engine_info={
                                         'using_rust': rust_templates,
                                         'engine_type': 'Rust (Tera)' if rust_templates else 'Jinja2',
                                         'streaming_capable': rust_templates,
                                         'hot_reload': rust_templates and hasattr(app.template_engine,
                                                                                  'enable_hot_reload'),
                                         'cache_stats': template_stats
                                     },
                                     static_engine_info={
                                         'using_rust': rust_static,
                                         'handler_type': static_handler_name
                                     },
                                     features=[
                                         "🚀 High-performance RSGI interface",
                                         "🦀 Rust-powered routing & static files" if rust_static else "📁 Static file serving",
                                         "🦀 Rust template engine with streaming" if rust_templates else "📄 Jinja2 templating with async",
                                         "⚡ Background task system with DuckDB",
                                         "🔌 WebSocket support with rooms",
                                         "🛡️ Built-in security middleware",
                                         "⏱️ Rate limiting",
                                         "🌐 CORS support",
                                         "🎨 Template filters & globals",
                                         "🔧 Custom error handling"
                                     ])


@app.get("/dashboard")
async def dashboard(request: Request):
    """Data-intensive dashboard to showcase streaming templates"""
    import random
    from datetime import datetime, timedelta

    # Check if we can use streaming
    rust_templates = hasattr(app.template_engine, 'using_rust') and app.template_engine.using_rust

    # Generate CSRF token
    csrf_token = security.generate_csrf_token(request.session)

    # Simulate data-intensive processing for large datasets
    request.logger.info(
        f"🔄 Generating dashboard data with {'Rust streaming' if rust_templates else 'standard rendering'}")

    # Generate realistic large dataset metrics
    base_users = 50000
    base_revenue = 250000.0

    current_metrics = {
        'active_users': base_users + random.randint(-5000, 15000),
        'revenue': base_revenue + random.uniform(-25000, 75000),
        'conversion_rate': 2.5 + random.uniform(-0.8, 1.2),
        'page_views': random.randint(800000, 1200000),
        'api_calls': random.randint(5000000, 8000000),
        'errors': random.randint(50, 500),
        'response_time': random.uniform(120, 280),
        'uptime': 99.9 + random.uniform(-0.5, 0.1)
    }

    # Calculate changes (simulate previous period comparison)
    def calculate_change():
        change = random.uniform(-25, 35)
        return f"{'+' if change > 0 else ''}{change:.1f}%", 'up' if change > 0 else 'down'

    dashboard_data = {
        'metrics': [
            {
                'name': 'Active Users',
                'value': current_metrics['active_users'],
                'change': calculate_change()[0],
                'status': calculate_change()[1]
            },
            {
                'name': 'Revenue',
                'value': current_metrics['revenue'],
                'change': calculate_change()[0],
                'status': calculate_change()[1]
            },
            {
                'name': 'Conversion Rate',
                'value': current_metrics['conversion_rate'],
                'change': calculate_change()[0],
                'status': calculate_change()[1]
            },
            {
                'name': 'Page Views',
                'value': current_metrics['page_views'],
                'change': calculate_change()[0],
                'status': calculate_change()[1]
            },
            {
                'name': 'API Calls',
                'value': current_metrics['api_calls'],
                'change': calculate_change()[0],
                'status': calculate_change()[1]
            },
            {
                'name': 'Error Rate',
                'value': current_metrics['errors'],
                'change': calculate_change()[0],
                'status': 'down' if random.random() > 0.3 else 'up'  # Prefer lower error rates
            },
            {
                'name': 'Avg Response Time',
                'value': f"{current_metrics['response_time']:.0f}ms",
                'change': calculate_change()[0],
                'status': 'down' if random.random() > 0.4 else 'up'  # Prefer lower response times
            },
            {
                'name': 'Uptime',
                'value': f"{current_metrics['uptime']:.2f}%",
                'change': calculate_change()[0],
                'status': 'up' if current_metrics['uptime'] > 99.5 else 'down'
            }
        ],

        # Generate extensive recent activity (simulate high-traffic system)
        'recent_activity': []
    }

    # Generate large activity dataset
    users = [
        'Alice Johnson', 'Bob Smith', 'Carol Davis', 'David Wilson', 'Eva Martinez',
        'Frank Chen', 'Grace O\'Connor', 'Henry Kim', 'Iris Patel', 'Jack Thompson',
        'Katie Rodriguez', 'Liam Murphy', 'Maya Singh', 'Noah Williams', 'Olivia Brown',
        'Paul Anderson', 'Quinn Taylor', 'Rachel Green', 'Sam Jackson', 'Tara Lee',
        'Uma Shah', 'Victor Zhang', 'Wendy Clark', 'Xavier Lopez', 'Yuki Tanaka', 'Zoe Adams'
    ]

    actions = [
        'Created new project', 'Updated profile', 'Completed task', 'Shared document',
        'Uploaded file', 'Started meeting', 'Sent message', 'Reviewed code',
        'Deployed application', 'Created report', 'Updated settings', 'Joined team',
        'Left comment', 'Approved request', 'Scheduled event', 'Downloaded data',
        'Generated analytics', 'Exported results', 'Modified permissions', 'Archived project'
    ]

    # Generate 100+ activity entries to test data-intensive rendering
    for i in range(120):
        time_ago = random.randint(1, 1440)  # 1 to 1440 minutes ago
        if time_ago < 60:
            time_str = f"{time_ago} minute{'s' if time_ago != 1 else ''} ago"
        else:
            hours = time_ago // 60
            time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"

        user_name = random.choice(users)
        dashboard_data['recent_activity'].append({
            'user': user_name,
            'initial': user_name[0].upper(),
            'action': random.choice(actions),
            'time': time_str
        })

    # Generate comprehensive chart data (2 years of monthly data)
    dashboard_data['chart_data'] = []
    base_date = datetime.now() - timedelta(days=730)  # 2 years ago
    prev_users = base_users

    for i in range(24):  # 24 months
        current_date = base_date + timedelta(days=30 * i)
        month_name = current_date.strftime('%b %Y')

        # Simulate growth trend with some variation
        growth_factor = 1 + (i * 0.08) + random.uniform(-0.15, 0.25)
        users = int(base_users * growth_factor * random.uniform(0.8, 1.2))
        revenue = base_revenue * growth_factor * random.uniform(0.7, 1.3)

        # Calculate growth rate compared to previous month
        if i > 0:
            growth_rate = f"{((users - prev_users) / prev_users * 100):.1f}%"
        else:
            growth_rate = "N/A"

        # Calculate conversion (revenue per user)
        conversion = f"${revenue / users:.2f}" if users > 0 else "$0.00"

        dashboard_data['chart_data'].append({
            'month': month_name,
            'users': users,
            'revenue': revenue,
            'growth_rate': growth_rate,
            'conversion': conversion
        })

        prev_users = users

    # Get template engine performance stats
    template_stats = None
    if hasattr(app.template_engine, 'get_cache_stats'):
        template_stats = app.template_engine.get_cache_stats()

    request.logger.info(f"📊 Generated {len(dashboard_data['metrics'])} metrics, "
                        f"{len(dashboard_data['recent_activity'])} activities, "
                        f"{len(dashboard_data['chart_data'])} data points")

    # Use streaming if Rust template engine is available
    import json
    try:
        request.logger.info("🔧 Starting dashboard template render with FULL data...")

        # Calculate total data points
        total_data_points = len(dashboard_data['metrics']) + len(dashboard_data['recent_activity']) + len(
            dashboard_data['chart_data'])

        # Prepare JSON for chart (handle escaping properly)
        chart_data_json = json.dumps(dashboard_data['chart_data'])

        # Check if we should use streaming
        use_streaming = rust_templates and total_data_points > 50

        if use_streaming:
            request.logger.info(f"🦀 Using Rust STREAMING render for {total_data_points} data points")
            # For streaming, we call the template engine directly with stream=True
            if hasattr(app.template_engine, 'render_template'):
                # Include context processor data
                context_data = inject_globals()  # Get context processor data
                context_data.update({
                    'csrf_token': csrf_token,
                    'dashboard_data': dashboard_data,
                    'chart_data_json': chart_data_json,
                    'streaming_enabled': True,
                    'template_engine_info': {
                        'using_rust': rust_templates,
                        'engine_type': 'Rust (Tera) - STREAMING',
                        'cache_stats': template_stats
                    },
                    'total_data_points': total_data_points,
                    'page_title': "Analytics Dashboard (Streaming)"
                })

                result = await app.template_engine.render_template(
                    "dashboard.html",
                    context=context_data,
                    stream=True  # Enable streaming
                )

                # If we get an async generator, convert to string
                if hasattr(result, '__aiter__'):
                    chunks = []
                    async for chunk in result:
                        chunks.append(chunk)
                    result = ''.join(chunks)
                    request.logger.info(f"✅ Streamed {len(chunks)} chunks")
            else:
                # Fallback to regular rendering
                result = await app.render_template("dashboard.html",
                                                   csrf_token=csrf_token,
                                                   dashboard_data=dashboard_data,
                                                   chart_data_json=chart_data_json,
                                                   streaming_enabled=True,
                                                   template_engine_info={
                                                       'using_rust': rust_templates,
                                                       'engine_type': 'Rust (Tera)',
                                                       'cache_stats': template_stats
                                                   },
                                                   total_data_points=total_data_points,
                                                   page_title="Analytics Dashboard")
        else:
            request.logger.info(f"📄 Using standard render for {total_data_points} data points")
            result = await app.render_template("dashboard.html",
                                               csrf_token=csrf_token,
                                               dashboard_data=dashboard_data,
                                               chart_data_json=chart_data_json,
                                               streaming_enabled=rust_templates,
                                               template_engine_info={
                                                   'using_rust': rust_templates,
                                                   'engine_type': 'Rust (Tera)' if rust_templates else 'Jinja2',
                                                   'cache_stats': template_stats
                                               },
                                               total_data_points=total_data_points,
                                               page_title="Analytics Dashboard")

        request.logger.info("✅ Dashboard template rendered successfully")
        return result

    except Exception as e:
        request.logger.error(f"❌ Dashboard template render failed: {type(e).__name__}: {e}", exc_info=True)

        # If Rust template fails, fall back to a simple error response
        request.logger.warning("🔄 Attempting to render simple error template instead...")
        try:
            return await app.render_template("error.html",
                                             error_code=500,
                                             error_message="Dashboard Rendering Error",
                                             error_description=f"Template rendering failed: {str(e)}",
                                             timestamp=time.strftime('%Y-%m-%d %H:%M:%S'))
        except Exception as fallback_error:
            request.logger.error(f"❌ Fallback template also failed: {fallback_error}")
            # Return a simple HTML response
            return f"""
            <html><head><title>Dashboard Error</title></head><body>
            <h1>Dashboard Error</h1>
            <p>Template rendering failed: {str(e)}</p>
            <p>Fallback error: {str(fallback_error)}</p>
            <a href="/">Return to Home</a>
            </body></html>
            """


@app.get("/api/health")
@doc(summary="Service health check", description="Returns the current health status of the service", tags=["System"])
@response(200, description="Service is healthy", content={
    "application/json": {
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "framework": {"type": "string"},
                "timestamp": {"type": "number"},
                "version": {"type": "string"}
            },
            "required": ["status", "timestamp"]
        }
    }
})
@rate_limit(health_limiter, key=lambda req: getattr(req, 'client_ip', 'global'))
async def health_check(request: Request):
    """Health check endpoint with rate limiting"""
    return jsonify({
        "status": "healthy",
        "framework": "Gobstopper",
        "timestamp": time.time(),
        "version": "0.1.0"
    })


# --- OpenAPI Demo: Type-first models and decorators ---
# Models used in the OpenAPI demo
import dataclasses as dc  # type: ignore
from typing import TypedDict, Optional, List  # type: ignore
import msgspec  # type: ignore

class OAUser(msgspec.Struct):
    id: int
    name: str
    email: Optional[str] = None

class CreateUserBody(TypedDict, total=False):
    name: str
    email: Optional[str]

@dc.dataclass
class Pet:
    id: int
    tags: List[str] = dc.field(default_factory=list)

@app.post("/openapi/users")
@doc(summary="Create user (type-first)", tags=["OpenAPI Demo"]) 
@request_body(model=CreateUserBody, media_types=["application/json", "application/x.msgpack"]) 
@response(201, description="Created", model=OAUser, media_types=["application/json"]) 
@param(name="verbose", in_="query", required=False, schema=bool, description="Verbose output")
async def oa_create_user(request: Request):
    data = await request.get_json() or {}
    name = data.get("name", "Anonymous")
    return {"id": 1, "name": name, "email": data.get("email")}, 201

@app.get("/openapi/pets/<int:id>")
@doc(summary="Get pet", tags=["OpenAPI Demo"]) 
@response(200, description="OK", model=Pet)
async def oa_get_pet(request: Request, id: int):
    return {"id": id, "tags": ["friendly"]}

# --- End OpenAPI Demo ---

@app.post("/api/users")
async def create_user(request: Request):
    """Create user endpoint with Post-Redirect-Get pattern using url_for and redirect"""
    data = await request.get_json()
    request.logger.info(f"Creating user with name: {data.get('name')}")

    # Simulate user creation
    user_id = f"user_{int(time.time())}"

    # Store in session for display after redirect
    request.session['last_created_user'] = {
        "id": user_id,
        "name": data.get("name"),
        "email": data.get("email"),
        "created_at": time.time()
    }

    # Post-Redirect-Get: Use 303 status to change POST to GET
    # Build URL using url_for with the named route
    user_url = app.url_for('get_user', user_id=user_id)
    return redirect(user_url, status=303)


@app.get("/users/<user_id>", name='get_user')
async def get_user(request: Request, user_id: str):
    """Get user by ID - named route for url_for demonstration"""
    # Check if we just created this user (from session)
    last_created = request.session.get('last_created_user') if request.session else None
    just_created = last_created and last_created.get('id') == user_id

    user_data = {
        "user_id": user_id,
        "name": last_created.get('name') if just_created else f"User {user_id}",
        "email": last_created.get('email') if just_created else f"user{user_id}@example.com",
        "created_at": last_created.get('created_at') if just_created else time.time() - 86400,
        "just_created": just_created
    }

    # Clear the session flag
    if just_created and request.session:
        request.session.pop('last_created_user', None)

    return jsonify(user_data)


@app.post("/api/tasks/email")
async def queue_email_task(request: Request):
    try:
        """Queue email task - demonstrates url_for for status check link"""
        data = await request.get_json()
        request.logger.info(f"Queuing email task for {data.get('to')}")

        task_id = await app.add_background_task(
            "send_email", "notifications", TaskPriority.HIGH,
            to=data.get("to", "user@example.com"),
            subject=data.get("subject", "Test Email"),
            body=data.get("body", "This is a test email from Gobstopper!")
        )

        # Generate status URL using url_for
        status_url = app.url_for('get_task_status', task_id=task_id)

        return jsonify({
            "task_id": task_id,
            "message": "Email task queued successfully",
            "priority": "HIGH",
            "status_url": status_url  # Include link to check task status
        })
    except Exception as e:
        request.logger.error(f"Error queuing email task: {e}")
        return JSONResponse({"error": str(e)})


@app.post("/api/tasks/process")
async def queue_processing_task(request: Request):
    """Queue data processing task"""
    data = await request.get_json()
    items = data.get("items", ["item1", "item2", "item3"])

    task_id = await app.add_background_task(
        "process_data", "processing", TaskPriority.NORMAL,
        data=items
    )

    return jsonify({
        "task_id": task_id,
        "message": f"Processing task queued for {len(items)} items"
    })


@app.post("/api/tasks/long")
async def queue_long_task(request: Request):
    """Queue long running task"""
    data = await request.get_json()
    duration = data.get("duration", 10)

    task_id = await app.add_background_task(
        "long_running_task", "processing", TaskPriority.LOW,
        max_retries=2,
        duration=duration
    )

    return jsonify({
        "task_id": task_id,
        "message": f"Long task queued for {duration} seconds",
        "max_retries": 2
    })


@app.get("/api/tasks/<task_id>", name='get_task_status')
async def get_task_status(request: Request, task_id: str):
    """Get task status - named route for url_for in queue endpoints"""
    task_info = await app.task_queue.get_task_info(task_id)

    if not task_info:
        return jsonify({"error": "Task not found"}, status=404)

    return jsonify({
        "id": task_info.id,
        "name": task_info.name,
        "category": task_info.category,
        "status": task_info.status.value,
        "priority": task_info.priority.value,
        "progress": task_info.progress,
        "progress_message": task_info.progress_message,
        "created_at": task_info.created_at.isoformat(),
        "started_at": task_info.started_at.isoformat() if task_info.started_at else None,
        "completed_at": task_info.completed_at.isoformat() if task_info.completed_at else None,
        "elapsed_seconds": task_info.elapsed_seconds,
        "result": task_info.result,
        "error": task_info.error,
        "retry_count": task_info.retry_count
    })


@app.get("/api/tasks")
async def list_tasks(request: Request):
    """List all tasks with stats"""
    stats = await app.task_queue.get_task_stats()
    return jsonify({
        "stats": stats,
        "message": "Task statistics retrieved successfully"
    })


@app.websocket("/ws/echo")
async def websocket_echo(websocket: WebSocket):
    """WebSocket echo endpoint"""
    await websocket.accept()

    try:
        while True:
            message = await websocket.receive()
            if message.kind == 0:  # Close message
                break
            elif message.kind == 2:  # Text message
                response = {
                    "type": "echo",
                    "original": message.data,
                    "timestamp": time.time()
                }
                await websocket.send_text(f"Echo: {message.data}")
    except Exception as e:
        app.logger.error(f"WebSocket error: {e}", exc_info=True)


@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket notifications endpoint"""
    await websocket.accept()

    try:
        # Send welcome message
        await websocket.send_text(jsonify({
            "type": "welcome",
            "message": "Connected to Gobstopper notifications",
            "timestamp": time.time()
        }).body)

        # Keep connection alive and send periodic updates
        counter = 0
        while True:
            await asyncio.sleep(5)
            counter += 1

            notification = {
                "type": "notification",
                "id": counter,
                "message": f"Periodic notification #{counter}",
                "timestamp": time.time()
            }

            await websocket.send_text(jsonify(notification).body)

    except Exception as e:
        app.logger.error(f"WebSocket error: {e}", exc_info=True)


# Error handlers
@app.error_handler(404)
async def not_found_handler(request: Request, error: Exception):
    """Custom 404 handler"""
    import time
    csrf_token = security.generate_csrf_token(request.session)
    return await app.render_template("error.html",
                                     csrf_token=csrf_token,
                                     error_code=404,
                                     error_message="Page Not Found",
                                     error_description=f"The requested page '{request.path}' could not be found.",
                                     timestamp=time.strftime('%Y-%m-%d %H:%M:%S'))


# Request/response hooks
# Startup function
@app.on_startup
async def startup():
    """Initialize application on startup"""
    app.logger.info("🚀 Starting Gobstopper application...")

    # Ensure template and static directories exist
    Path("templates").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)

    # Validate templates at startup
    try:
        from src.gobstopper.templates.validator import create_template_validator
        validator = create_template_validator(app.logger)
        app.logger.info("🔍 Running template validation...")

        results = validator.validate_directory("templates")
        report = validator.generate_report(results)

        summary = report["summary"]
        if summary["total_errors"] == 0:
            app.logger.success(
                f"✅ Template validation passed: {summary['valid_files']}/{summary['total_files']} files valid")
            app.logger.info(
                f"📊 Average scores - Syntax: {summary['average_syntax_score']}/100, Performance: {summary['average_performance_score']}/100")
        else:
            app.logger.warning(
                f"⚠️ Template validation issues: {summary['total_errors']} errors, {summary['total_warnings']} warnings")

    except Exception as e:
        app.logger.warning(f"⚠️ Template validation failed: {e}")

    # Log which static handler is being used
    app.logger.info(f"📁 Static file handler: {static_handler_name}")

    # Start task workers only in the main process (when using multiple workers)
    # This prevents DuckDB concurrency issues when running with granian --workers N
    if should_run_background_workers():
        await app.start_task_workers("notifications", 2)
        await app.start_task_workers("processing", 1)

        app.logger.info("✅ Gobstopper application ready!")
        app.logger.info("📊 Task workers started:")
        app.logger.info("   - notifications: 2 workers")
        app.logger.info("   - processing: 1 worker")
    else:
        app.logger.info("✅ Gobstopper application ready!")
        app.logger.info("⏭️  Skipping task workers (not main process)")


if __name__ == "__main__":
    print("🔥 Gobstopper Example Application")
    print("=" * 50)
    print("Run with: granian --interface rsgi --reload example_app:app")
    print("\nAvailable endpoints:")
    print("  GET  /                          - Home page")
    print("  GET  /dashboard                 - Data dashboard (streaming templates)")
    print("  GET  /demo/convenience-features - Flask/Quart convenience features demo")
    print("  GET  /demo/abort                - abort() demo (try ?user_id=123)")
    print("  GET  /demo/make-response        - make_response() demo")
    print("  GET  /demo/request-properties   - Request properties demo")
    print("  POST /demo/notification-set     - Set notification (flash message)")
    print("  GET  /demo/notification-view    - View notifications")
    print("  GET  /demo/upload-form          - File upload form")
    print("  POST /demo/upload               - Handle file upload")
    print("  GET  /uploads/<filename>        - Serve uploaded files")
    print("  GET  /api/health                - Health check (rate limited)")
    print("  POST /api/users                 - Create user (with PRG redirect)")
    print("  GET  /users/<id>                - Get user by ID")
    print("  POST /api/tasks/email           - Queue email task")
    print("  POST /api/tasks/process         - Queue processing task")
    print("  POST /api/tasks/long            - Queue long running task")
    print("  GET  /api/tasks/<id>            - Get task status")
    print("  GET  /api/tasks                 - Get task statistics")
    print("  WS   /ws/echo                   - WebSocket echo")
    print("  WS   /ws/notifications          - WebSocket notifications")
    print("\nMiddleware enabled:")
    print(f"  ✅ {static_handler_name} (/static)")
    print("  ✅ CORS support")
    print("  ✅ Security headers & CSRF protection")
    print("  ✅ Rate limiting on /api/health")
    print("\nFeatures demonstrated:")
    print("  ✅ HTTP routing with path parameters")
    print("  ✅ Flask/Quart-style url_for() and redirect()")
    print("  ✅ Flask/Quart convenience features:")
    print("     • abort() for immediate error responses")
    print("     • make_response() for flexible response building")
    print("     • notification() / get_notifications() (flash messages)")
    print("     • request.cookies, request.is_json, request.endpoint")
    print("     • request.url, request.base_url, request.view_args")
    print("     • FileStorage for file uploads")
    print("     • send_from_directory() for secure file serving")
    print("     • secure_filename() for path traversal protection")
    print("  ✅ Post-Redirect-Get pattern with named routes")
    print("  ✅ JSON requests/responses")
    print("  ✅ Background task system (3 different task types)")
    print("  ✅ WebSocket support (2 endpoints)")
    print("  ✅ Template rendering")
    print("  ✅ Error handling")
    print("  ✅ Request/response hooks")
    print("  ✅ Custom middleware")

    # Note: In a real application, you would call startup() when the RSGI server starts
    # For this example, we just show what would be called