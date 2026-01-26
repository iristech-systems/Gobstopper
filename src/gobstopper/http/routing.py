"""
Routing system for Gobstopper framework

Enhancements:
- Converter registry supporting <int:id>, <uuid:uid>, <date:dt>, <path:rest>, and default str.
- Typed extraction using converter functions; raw values still available as strings if no converter.
- Per-route middleware via use() decorator.
"""

import re
import inspect
from typing import Callable, Any
from urllib.parse import unquote
from datetime import datetime
import uuid as _uuid

# Converter type: returns (regex, converter_func)
Converter = tuple[str, Callable[[str], Any]]

_CONVERTERS: dict[str, Converter] = {}


def register_converter(name: str, regex: str, converter: Callable[[str], Any]):
    """Register a custom path parameter converter.
    
    Example:
        register_converter('slug', r"[a-z0-9-]+", str)
    """
    _CONVERTERS[name] = (regex, converter)


# Built-in converters
register_converter('int', r"-?\d+", lambda s: int(s))
# Strict UUID regex (case-insensitive) with fixed hyphen positions
register_converter('uuid', r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", lambda s: _uuid.UUID(s))
register_converter('date', r"\d{4}-\d{2}-\d{2}", lambda s: datetime.strptime(s, "%Y-%m-%d").date())
# 'path' consumes the rest including slashes; handled specially in compile
register_converter('path', r".+", lambda s: s)


class RouteHandler:
    """Single route handler with pattern matching and converters"""

    def __init__(self, pattern: str, handler: Callable, methods: list[str], is_websocket: bool = False):
        self.pattern = pattern
        self.handler = handler
        self.methods = [m.upper() for m in methods]
        self.is_websocket = is_websocket
        # Cache handler signature to avoid per-request inspect cost
        try:
            self.signature = inspect.signature(handler)
            # Pre-extract parameter annotations for faster coercion
            self._param_annotations = {
                name: param.annotation
                for name, param in self.signature.parameters.items()
                if param.annotation != inspect._empty
            }
        except Exception:
            self.signature = None
            self._param_annotations = {}
        # list of tuples (name, converter_name or None)
        self.path_params: list[str] = []
        self._compiled_param_specs: list[tuple[str, Callable[[str], Any] | None]] = []
        self.regex: re.Pattern[str] | None = None
        self.middleware: list[tuple[Callable, int]] = []  # per-route middleware with priority
        self.blueprint_chain: list[Any] = []  # filled by app.register_blueprint
        self._cached_middleware_stack: list[tuple[Callable, int]] | None = None  # pre-computed middleware chain
        self._compile_pattern()
    
    def use(self, middleware: Callable, priority: int = 0):
        """Attach a middleware to this route. Higher priority runs earlier (outer)."""
        self.middleware.append((middleware, priority))
        self.middleware.sort(key=lambda x: x[1], reverse=True)
        return self

    def _compile_pattern(self):
        """Compile pattern for matching and parameter extraction with converters."""
        # Parse segments like <converter:name> or <name>
        param_regex = re.compile(r"<([^>]+)>")
        parts = param_regex.split(self.pattern)
        idx = 0
        out_regex = "^"
        self._compiled_param_specs.clear()
        self.path_params = []

        # Validate that any <path:...> token is in tail position (last parameter)
        # The split produces odd indices for parameter tokens
        last_param_index = len(parts) - 2 if len(parts) % 2 == 1 else len(parts) - 1
        for i in range(1, len(parts), 2):
            token = parts[i]
            if ":" in token:
                conv_name, _ = token.split(":", 1)
                if conv_name == 'path' and i != last_param_index:
                    raise ValueError("<path:...> must be the last parameter in the route")

        for part in parts:
            if idx % 2 == 0:
                # literal text
                out_regex += re.escape(part)
            else:
                token = part
                if ":" in token:
                    conv_name, name = token.split(":", 1)
                    conv = _CONVERTERS.get(conv_name)
                    if conv_name == 'path':
                        # path should match greedy to the end
                        regex, func = conv if conv else (r".+", lambda s: s)
                        out_regex += f"({regex})"
                    else:
                        regex, func = conv if conv else (r"[^/]+", lambda s: s)
                        out_regex += f"({regex})"
                    self._compiled_param_specs.append((name, func))
                    self.path_params.append(name)
                else:
                    name = token
                    out_regex += r"([^/]+)"
                    self._compiled_param_specs.append((name, lambda s: s))
                    self.path_params.append(name)
            idx += 1
        out_regex += "$"
        self.regex = re.compile(out_regex)
    
    def match(self, path: str, method: str) -> dict[str, Any] | None:
        """Check if this route matches the request and return typed params if possible."""
        if self.is_websocket or method.upper() in self.methods:
            match = self.regex.match(path) if self.regex else None
            if match:
                params: dict[str, Any] = {}
                for i, (name, conv) in enumerate(self._compiled_param_specs):
                    raw_val = match.group(i + 1)
                    # Defer URL decoding - only decode if value contains percent-encoded chars
                    decoded = unquote(raw_val) if '%' in raw_val else raw_val
                    try:
                        params[name] = conv(decoded) if conv else decoded
                    except Exception:
                        # mark a special key for conversion error; app will return 400
                        params['__conversion_error__'] = True
                        return params
                return params
        return None


def use(middleware: Callable, priority: int = 0):
    """Decorator to attach middleware to a route function.
    Usage:
        @app.get('/x')
        @use(my_mw, priority=10)
        def handler(request): ...
    """
    def decorator(func: Callable):
        # Attach attribute; RouteHandler will read it on creation time in app/blueprint
        mws = getattr(func, '__route_middleware__', [])
        mws.append((middleware, priority))
        setattr(func, '__route_middleware__', sorted(mws, key=lambda x: x[1], reverse=True))
        return func
    return decorator