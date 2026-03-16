import inspect
from pathlib import Path
from typing import Any, List, Optional, Callable, Union

from ...http.routing import RouteHandler
from ...middleware.static import StaticFileMiddleware

Handler = Callable[..., Any]

class RouterMixin:
    """Mixin for routing management in the Gobstopper application."""

    def __init__(self):
        # Attributes expected to be initialized by the main class or other mixins
        if not hasattr(self, '_all_routes'):
            self._all_routes: List[RouteHandler] = []
        if not hasattr(self, '_conflicts'):
            self._conflicts: List[dict] = []
        if not hasattr(self, 'routes'):
            self.routes: List[RouteHandler] = []
        if not hasattr(self, 'mounts'):
            self.mounts: list[tuple[str, Any]] = []
        if not hasattr(self, 'blueprints'):
            self.blueprints: list[Any] = []
        
        # These are usually set in Gobstopper.__init__
        # self.http_router
        # self.websocket_router
        # self.rust_router_available

    def _check_conflicts(self, new_handler: RouteHandler):
        """Collect conflicts between new route and existing ones for diagnostics."""
        try:
            new_is_ws = bool(new_handler.is_websocket)
            new_static = '<' not in new_handler.pattern and '>' not in new_handler.pattern and ':' not in new_handler.pattern
            new_regex = new_handler.regex
            for existing in self._all_routes:
                if bool(existing.is_websocket) != new_is_ws:
                    continue
                # Method intersection (ignore if none)
                if not new_is_ws:
                    if not set(m.upper() for m in new_handler.methods) & set(m.upper() for m in existing.methods):
                        continue
                exist_static = '<' not in existing.pattern and '>' not in existing.pattern and ':' not in existing.pattern
                # Duplicate static route
                if new_static and exist_static and existing.pattern == new_handler.pattern:
                    self._conflicts.append({
                        'existing': f"{existing.methods or ['WS']} {existing.pattern}",
                        'new': f"{new_handler.methods or ['WS']} {new_handler.pattern}",
                        'reason': 'duplicate static route for same path/method'
                    })
                # Dynamic shadows static
                if new_regex and exist_static and new_regex.match(existing.pattern):
                    self._conflicts.append({
                        'existing': f"{existing.methods or ['WS']} {existing.pattern}",
                        'new': f"{new_handler.methods or ['WS']} {new_handler.pattern}",
                        'reason': 'dynamic route may shadow a more specific static route'
                    })
                # Static shadows dynamic (reverse)
                if existing.regex and new_static and existing.regex.match(new_handler.pattern):
                    self._conflicts.append({
                        'existing': f"{existing.methods or ['WS']} {existing.pattern}",
                        'new': f"{new_handler.methods or ['WS']} {new_handler.pattern}",
                        'reason': 'dynamic route may shadow a more specific static route'
                    })
        except Exception:
            pass

    def mount(self, path: str, app: Any):
        """Mount a sub-application at the given path prefix."""
        if not path.startswith('/'):
            path = '/' + path
        if path.endswith('/'):
            path = path[:-1]
        self.mounts.append((path, app))
        return app

    def register_blueprint(self, blueprint, url_prefix: str | None = None):
        """Register a Blueprint on this app with an optional URL prefix."""
        base_prefix = url_prefix if url_prefix is not None else getattr(blueprint, 'url_prefix', None)

        def _join(prefix: str | None, path: str) -> str:
            if not prefix:
                return path
            if not prefix.startswith('/'):
                prefix_local = '/' + prefix
            else:
                prefix_local = prefix
            if prefix_local.endswith('/'):
                prefix_local = prefix_local[:-1]
            if not path.startswith('/'):
                path = '/' + path
            return prefix_local + path

        def _register(bp, acc_prefix: str | None, chain: list[Any]):
            # Attach hooks to app with signature validation
            for h in getattr(bp, 'before_request_handlers', []) or []:
                sig = inspect.signature(h)
                if len(sig.parameters) != 1:
                    raise TypeError(f"Blueprint before_request handler '{getattr(h, '__name__', h)}' must accept exactly 1 argument: (request)")
                self.before_request(h)
            for h in getattr(bp, 'after_request_handlers', []) or []:
                sig = inspect.signature(h)
                if len(sig.parameters) != 2:
                    raise TypeError(f"Blueprint after_request handler '{getattr(h, '__name__', h)}' must accept exactly 2 arguments: (request, response)")
                self.after_request(h)
            # Per-blueprint templates
            tpl = getattr(bp, 'template_folder', None)
            if tpl and getattr(self, 'template_engine', None):
                ns = getattr(bp, 'name', None) or (Path(tpl).name if isinstance(tpl, (str, Path)) else None)
                try:
                    self.template_engine.add_search_path(tpl, namespace=ns)
                except TypeError:
                    self.template_engine.add_search_path(tpl)
            # Per-blueprint static
            static_dir = getattr(bp, 'static_folder', None)
            if static_dir:
                static_prefix = _join(acc_prefix or '', '/static')
                self.add_middleware(StaticFileMiddleware(static_dir, url_prefix=static_prefix), priority=0)

            # Register routes for this blueprint
            for route in getattr(bp, 'routes', []) or []:
                full_path = _join(acc_prefix, route.pattern)
                if route.is_websocket:
                    handler = RouteHandler(full_path, route.handler, [], is_websocket=True)
                else:
                    handler = RouteHandler(full_path, route.handler, route.methods)
                # copy route-level middleware and set chain for scoped middleware
                for mw, prio in getattr(route, 'middleware', []) or []:
                    handler.use(mw, prio)
                handler.blueprint_chain = chain + [bp]

                # conflict detection
                self._check_conflicts(handler)

                if getattr(self, 'rust_router_available', False):
                    # New Rust router accepts Python path syntax directly
                    func_name = getattr(route.handler, '__name__', None)
                    bp_name = getattr(bp, 'name', None)
                    if bp_name and func_name:
                        route_name = f"{bp_name}.{func_name}"
                    else:
                        route_name = func_name

                    if route.is_websocket:
                        self.websocket_router.insert(full_path, "WEBSOCKET", handler, route_name)
                    else:
                        for method in route.methods:
                            self.http_router.insert(full_path, method.upper(), handler, route_name)
                else:
                    self.routes.append(handler)
                self._all_routes.append(handler)

            # Recurse into children
            for child, child_prefix in getattr(bp, 'children', []) or []:
                next_prefix = _join(acc_prefix, child_prefix if child_prefix is not None else getattr(child, 'url_prefix', None) or '')
                _register(child, next_prefix, chain + [bp])

        # Track blueprint root and register
        try:
            self.blueprints.append(blueprint)
        except Exception:
            pass
        _register(blueprint, base_prefix, [])

    def route(self, path: str, methods: list[str] = None, name: str = None,
              rate_limit: str = None, rate_limit_by: str = "ip"):
        """Decorator to register HTTP routes.

        Args:
            path: URL pattern (e.g. ``"/users/<int:id>"``).
            methods: HTTP methods. Defaults to ``["GET"]``.
            name: Optional route name for :meth:`url_for`.
            rate_limit: Optional rate-limit spec such as ``"20/minute"`` or
                ``"5/second"``.  Periods: ``second``, ``minute``, ``hour``.
            rate_limit_by: How to key the rate limiter.  ``"ip"`` (default)
                uses the client IP; ``"global"`` shares a single bucket for
                all callers.
        """
        if methods is None:
            methods = ['GET']

        def decorator(func: Handler) -> Handler:
            _func = func
            if rate_limit is not None:
                from ...utils.rate_limiter import _parse_rate_limit as _prl
                from ...http.problem import problem as _problem
                _limiter = _prl(rate_limit)
                _key = (lambda req: "__global__") if rate_limit_by == "global" \
                       else (lambda req: req.client_ip)
                _orig = _func

                async def _rate_limited(request, **kwargs):
                    if not _limiter.allow(_key(request)):
                        return _problem("Too Many Requests", 429)
                    return await _orig(request, **kwargs)

                _rate_limited.__name__ = func.__name__
                _rate_limited.__wrapped__ = _orig
                _func = _rate_limited

            handler = RouteHandler(path, _func, methods)
            for mw, prio in getattr(func, '__route_middleware__', []) or []:
                handler.use(mw, prio)
            # conflict detection
            self._check_conflicts(handler)
            # register
            if getattr(self, 'rust_router_available', False):
                for method in methods:
                    route_name = name if name else getattr(func, '__name__', None)
                    self.http_router.insert(path, method.upper(), handler, route_name)
            else:
                self.routes.append(handler)
            self._all_routes.append(handler)
            return func
        return decorator

    def get(self, path: str, name: str = None, **kwargs):
        return self.route(path, ['GET'], name, **kwargs)

    def post(self, path: str, name: str = None, **kwargs):
        return self.route(path, ['POST'], name, **kwargs)

    def put(self, path: str, name: str = None, **kwargs):
        return self.route(path, ['PUT'], name, **kwargs)

    def delete(self, path: str, name: str = None, **kwargs):
        return self.route(path, ['DELETE'], name, **kwargs)

    def patch(self, path: str, name: str = None, **kwargs):
        return self.route(path, ['PATCH'], name, **kwargs)

    def options(self, path: str, name: str = None, **kwargs):
        return self.route(path, ['OPTIONS'], name, **kwargs)

    def websocket(self, path: str):
        """Decorator for registering WebSocket routes."""
        def decorator(func: Handler) -> Handler:
            handler = RouteHandler(path, func, [], is_websocket=True)
            for mw, prio in getattr(func, '__route_middleware__', []) or []:
                handler.use(mw, prio)
            if getattr(self, 'rust_router_available', False):
                route_name = getattr(func, '__name__', None)
                self.websocket_router.insert(path, "WEBSOCKET", handler, route_name)
            else:
                self.routes.append(handler)
            self._all_routes.append(handler)
            return func
        return decorator

    def url_for(self, name: str, **params) -> str:
        """Build a URL for a named route with parameters (reverse routing)."""
        if getattr(self, 'rust_router_available', False) and getattr(self, 'http_router', None):
            # Use Rust router's url_for
            url = self.http_router.url_for(name, params if params else None)
            if url is None:
                raise ValueError(f"No route named '{name}' found")
            return url
        else:
            # Fallback: scan Python routes
            for route in self._all_routes:
                handler_name = getattr(route.handler, '__name__', None)

                # Check for exact match (function name)
                if handler_name == name:
                    # Build URL by replacing parameters in pattern
                    url = route.pattern
                    for key, value in params.items():
                        # Try different parameter formats
                        url = url.replace(f"<{key}>", str(value))
                        url = url.replace(f"<int:{key}>", str(value))
                        url = url.replace(f"<uuid:{key}>", str(value))
                        url = url.replace(f"<date:{key}>", str(value))
                        url = url.replace(f"<path:{key}>", str(value))
                    return url

                # Check for blueprint-qualified name (blueprint.function)
                if '.' in name and getattr(route, 'blueprint_chain', None):
                    # Get the last blueprint in the chain (closest to route)
                    bp = route.blueprint_chain[-1] if route.blueprint_chain else None
                    bp_name = getattr(bp, 'name', None) if bp else None
                    if bp_name and handler_name:
                        qualified_name = f"{bp_name}.{handler_name}"
                        if qualified_name == name:
                            url = route.pattern
                            for key, value in params.items():
                                url = url.replace(f"<{key}>", str(value))
                                url = url.replace(f"<int:{key}>", str(value))
                                url = url.replace(f"<uuid:{key}>", str(value))
                                url = url.replace(f"<date:{key}>", str(value))
                                url = url.replace(f"<path:{key}>", str(value))
                            return url
            raise ValueError(f"No route named '{name}' found") 
