"""
Datastar Example 1: Live Clock (SSE Streaming)

Demonstrates real-time server-sent events with Datastar.
The clock updates 10 times per second showing millisecond precision.
"""

import asyncio
from datetime import datetime
from gobstopper import Gobstopper
from gobstopper.extensions.datastar import Datastar, MergeMode
from gobstopper.middleware.security import SecurityMiddleware

app = Gobstopper(name="live_clock", debug=True)

# Security with Datastar auto-configuration
security = SecurityMiddleware(
    enable_csrf=False,
    datastar_enabled=True,
    cookie_secure=False,
)
app.add_middleware(security)

@app.get("/")
async def index(request):
    """Render the main page with Datastar clock."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Clock - Datastar Example</title>
        <script type="module" src="https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.0-RC.8/bundles/datastar.js"></script>
        <style>
            body {
                font-family: 'Courier New', monospace;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .clock {
                font-size: 4rem;
                color: #00ff88;
                text-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
                padding: 2rem;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 1rem;
            }
        </style>
    </head>
    <body>
        <div data-init="@get('/clock')">
            <div id="clock_display" class="clock">
                Waiting for time...
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.get("/clock")
async def clock_stream(request):
    """Stream live clock updates via SSE."""
    async def generator():
        try:
            while True:
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                fragment = f'<div id="clock_display" class="clock">{now}</div>'
                
                yield Datastar.merge_fragments(fragment, merge_mode=MergeMode.OUTER)
                
                await asyncio.sleep(0.1)  # Update 10 times per second
        except (ConnectionError, BrokenPipeError, Exception):
            # Client disconnected - this is normal for SSE
            pass
            
    return Datastar.stream(generator())

if __name__ == "__main__":
    print("🕐 Live Clock Example")
    print("Visit: http://localhost:8000")
    print("Press Ctrl+C to stop")
