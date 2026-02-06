"""
Gobstopper Error Prism - Beautiful, Interactive Error Pages
"""
import sys
import traceback
import typing as t
from pathlib import Path
from gobstopper.html import html, head, body, div, style, script, meta, h1, h2, span, pre, code, ul, li, a
from gobstopper.html import datastar
from gobstopper.http import Request, Response

class PrismErrorPage:
    """Renders a rich error page for unhandled exceptions."""
    
    def __init__(self, request: Request, exception: Exception):
        self.request = request
        self.exception = exception
        self.exc_type = type(exception).__name__
        self.exc_value = str(exception)
        self.traceback_obj = traceback.extract_tb(exception.__traceback__)

    def __html__(self) -> str:
        return str(html(lang="en")[
            head[
                meta(charset="utf-8"),
                meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                style[self._css()],
                # datastar.script(),  # Include Datastar for interactivity if needed later
            ],
            body[
                div(class_="prism-layout")[
                    self._header(),
                    div(class_="prism-container")[
                        div(class_="prism-sidebar")[
                            self._request_info(),
                        ],
                        div(class_="prism-main")[
                            self._stack_trace(),
                        ]
                    ]
                ]
            ]
        ])

    def _header(self):
        return div(class_="prism-header")[
            div(class_="prism-badge")["500"],
            div(class_="prism-title")[
                h1[self.exc_type],
                div(class_="prism-message")[self.exc_value]
            ]
        ]

    def _stack_trace(self):
        frames = []
        for frame in reversed(self.traceback_obj):
            is_app_code = "gobstopper/src" in frame.filename or "/app.py" in frame.filename or "examples/" in frame.filename
            
            # Read snippet
            snippet = ""
            try:
                if Path(frame.filename).exists():
                    lines = Path(frame.filename).read_text().splitlines()
                    start = max(0, frame.lineno - 3)
                    end = min(len(lines), frame.lineno + 2)
                    snippet = "\n".join([
                        f"{i+1:4} | {line}" + ("  <-- ERROR" if i+1 == frame.lineno else "")
                        for i, line in enumerate(lines)
                        if start <= i < end
                    ])
            except Exception:
                pass

            classes = "frame"
            if is_app_code:
                classes += " frame-app"
            
            frames.append(div(class_=classes)[
                div(class_="frame-header")[
                    span(class_="frame-func")[frame.name],
                    span(class_="frame-file")[f"{frame.filename}:{frame.lineno}"]
                ],
                pre(class_="frame-code")[code[snippet]] if snippet else ""
            ])
            
        return div(class_="stack-trace")[
            h2["Stack Trace"],
            div(class_="frames")[frames]
        ]

    def _request_info(self):
        return div(class_="request-info")[
            h2["Request Details"],
            ul[
                li[span(class_="label")["Method"], code[self.request.method]],
                li[span(class_="label")["URL"], code[str(self.request.url)]],
                li[span(class_="label")["Client"], code[self.request.client_ip]],
            ],
            h2["Headers"],
            div(class_="headers-list")[
                [div(class_="header-item")[
                    span(class_="header-key")[k],
                    span(class_="header-val")[v]
                ] for k, v in self.request.headers.items()]
            ]
        ]

    def _css(self):
        return """
        :root {
            --bg: #0f1117;
            --surface: #1e212b;
            --primary: #ff4757;
            --text: #e1e1e6;
            --text-dim: #a1a1aa;
            --border: #2d303e;
            --code-bg: #161821;
        }
        body { margin: 0; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; }
        .prism-layout { display: flex; flex-direction: column; height: 100vh; }
        
        .prism-header { 
            background: var(--surface); border-bottom: 1px solid var(--border); 
            padding: 24px; display: flex; align-items: flex-start; gap: 24px;
        }
        .prism-badge { 
            background: var(--primary); color: white; font-weight: bold; 
            padding: 4px 12px; border-radius: 4px; font-size: 14px; 
        }
        .prism-title h1 { margin: 0 0 8px 0; font-size: 24px; color: var(--primary); }
        .prism-message { font-family: monospace; font-size: 16px; color: var(--text-dim); }

        .prism-container { flex: 1; display: flex; overflow: hidden; }
        
        .prism-sidebar { 
            width: 350px; background: #13151c; border-right: 1px solid var(--border);
            padding: 20px; overflow-y: auto; font-size: 14px;
        }
        .prism-main { flex: 1; padding: 30px; overflow-y: auto; }

        h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); margin-top: 0; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
        
        .label { display: inline-block; width: 60px; color: var(--text-dim); }
        ul { list-style: none; padding: 0; }
        li { margin-bottom: 8px; }
        
        .header-item { display: flex; gap: 10px; font-family: monospace; font-size: 12px; margin-bottom: 4px; }
        .header-key { color: var(--primary); min-width: 120px; text-align: right; }
        .header-val { color: var(--text-dim); word-break: break-all; }

        .frame { margin-bottom: 16px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
        .frame-app { border-color: var(--primary); border-width: 2px; }
        .frame-header { 
            background: var(--surface); padding: 8px 12px; 
            display: flex; justify-content: space-between; font-family: monospace; font-size: 13px;
        }
        .frame-func { font-weight: bold; color: #7dd3fc; }
        .frame-file { color: var(--text-dim); }
        .frame-code { margin: 0; padding: 12px; background: var(--code-bg); font-size: 13px; overflow-x: auto; }
        """
