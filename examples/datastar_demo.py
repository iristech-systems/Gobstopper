
import asyncio
import datetime
from gobstopper import Gobstopper, Request, Response
from gobstopper.extensions.datastar import Datastar, MergeMode
from gobstopper.middleware.security import SecurityMiddleware
from gobstopper.middleware.cors import CORSMiddleware
from gobstopper.html import html as HTML, h1 as H1, p as P, div as Div, style as Style, script as Script

app = Gobstopper(name="datastar_demo", debug=True)

# Configure security with Datastar auto-configuration
# The datastar_enabled flag automatically sets COEP="", COOP="", and adds 'unsafe-eval' to CSP
security = SecurityMiddleware(
    enable_csrf=False,  # Disable CSRF for simpler demo interaction
    datastar_enabled=True,  # ✨ One flag enables all Datastar requirements!
    cookie_secure=False,  # Allow HTTP for development
)

# Allow CORS for CDN resources if needed (though CSP is usually the blocker for script tags)
cors = CORSMiddleware(
    origins=["*"],
    methods=["GET", "POST", "HEAD", "OPTIONS"],
    headers=["*"],
)

app.add_middleware(security)
app.add_middleware(cors)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Datastar POC</title>
    <!-- Load Datastar from CDN (Official) -->
    <script type="module" src="https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.0-RC.8/bundles/datastar.js"></script>
    <style>
        body { font-family: sans-serif; padding: 2rem; background: #111; color: #eee; }
        .clock { font-size: 3rem; font-weight: bold; color: #00ff88; }
    </style>
</head>
<body>
    <h1>✨ Gobstopper + Datastar</h1>
    
    <!-- 
      data-on-load: trigger SSE request to /clock
      data-bind: listen for updates
    -->
    <div data-init="@get('/clock')">
        <div id="clock_display" class="clock">Waiting...</div>
    </div>
    
    <div style="margin-top: 2rem;">
        <p>This clock is updated via Server-Sent Events (SSE) from Python.</p>
    </div>

</body>
</html>
"""

@app.get("/")
async def index(request: Request):
    return Response(HTML)

@app.get("/clock")
async def clock_stream(request: Request):
    async def event_generator():
        while True:
            now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            # Use htpy usage: Div(attrs)[children]
            
            # Use Datastar helper to format the SSE content
            yield Datastar.merge_fragments(Div("#clock_display.clock")[now], merge_mode=MergeMode.OUTER)
            
            await asyncio.sleep(0.1)
            
    return Datastar.stream(event_generator())

if __name__ == "__main__":
    # To run: uv run gobstopper run examples/datastar_demo.py
    pass
