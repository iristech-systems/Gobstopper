
import asyncio
from typing import Callable, Any, Awaitable
from ..http.request import Request
from ..http.response import Response

CLIENT_SCRIPT = """
<script>
(function() {
    var ws = new WebSocket("ws://" + window.location.host + "/_hot_reload");
    ws.onclose = function() {
        console.log("Hot reload connection lost. Reconnecting...");
        setTimeout(function() {
             window.location.reload();
        }, 1000);
    };
    ws.onmessage = function(msg) {
        if (msg.data === "reload") {
            window.location.reload();
        }
    };
})();
</script>
"""

class HotReloadMiddleware:
    """
    Middleware that injects a hot-reload script into HTML responses.
    Only active when debug=True.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, request: Request, next_handler: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await next_handler(request)
        
        # Only inject into HTML responses
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type and getattr(self.app, 'debug', False):
            if isinstance(response.body, str):
                if "</body>" in response.body:
                    response.body = response.body.replace("</body>", CLIENT_SCRIPT + "</body>")
                else:
                    response.body += CLIENT_SCRIPT
            elif isinstance(response.body, bytes):
                try:
                    body_str = response.body.decode("utf-8")
                    if "</body>" in body_str:
                         body_str = body_str.replace("</body>", CLIENT_SCRIPT + "</body>")
                    else:
                         body_str += CLIENT_SCRIPT
                    response.body = body_str.encode("utf-8")
                except UnicodeDecodeError:
                    pass
        
        return response
