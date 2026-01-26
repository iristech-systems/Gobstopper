"""
Blueprint system for grouping routes and related hooks.

Provides a Flask-like Blueprint API that allows organizing routes into reusable
modules that can be registered on an application with an optional URL prefix.
"""
from __future__ import annotations

from typing import Callable, Any, Awaitable
import re
from pathlib import Path

from ..http.routing import RouteHandler

# Type aliases consistent with app.py
Handler = Callable[..., Any]
Middleware = Callable[["Request", Callable[["Request"], Awaitable[Any]]], Awaitable["Response"]]
MiddlewareTuple = tuple[Middleware, int]


class Blueprint:
    """A collection of routes and hooks that can be registered on a Gobstopper app.

    Args:
        name: Identifier for the blueprint.
        url_prefix: Optional URL prefix applied when registering on an app.
    """

    def __init__(self, name: str, url_prefix: str | None = None, *, static_folder: str | None = None, template_folder: str | None = None):
        self.name = name
        self.url_prefix = url_prefix
        self.routes: list[RouteHandler] = []
        self.before_request_handlers: list[Handler] = []
        self.after_request_handlers: list[Handler] = []
        self.middleware: list[MiddlewareTuple] = []
        self.children: list[tuple[Blueprint, str | None]] = []
        self.static_folder = static_folder
        self.template_folder = template_folder

    # ---- Route registration ----
    def route(self, path: str, methods: list[str] | None = None):
        if methods is None:
            methods = ["GET"]

        def decorator(func: Handler) -> Handler:
            handler = RouteHandler(path, func, methods)
            # pick up any @use middleware attached to the function
            for mw, prio in getattr(func, '__route_middleware__', []) or []:
                handler.use(mw, prio)
            self.routes.append(handler)
            return func

        return decorator

    def get(self, path: str):
        return self.route(path, ["GET"])

    def post(self, path: str):
        return self.route(path, ["POST"])

    def put(self, path: str):
        return self.route(path, ["PUT"])

    def delete(self, path: str):
        return self.route(path, ["DELETE"])

    def patch(self, path: str):
        return self.route(path, ["PATCH"])

    def options(self, path: str):
        return self.route(path, ["OPTIONS"])

    def websocket(self, path: str):
        def decorator(func: Handler) -> Handler:
            handler = RouteHandler(path, func, [], is_websocket=True)
            # pick up route-level middleware
            for mw, prio in getattr(func, '__route_middleware__', []) or []:
                handler.use(mw, prio)
            self.routes.append(handler)
            return func

        return decorator

    # ---- Nested blueprints and mounts ----
    def register_blueprint(self, blueprint: "Blueprint", url_prefix: str | None = None):
        self.children.append((blueprint, url_prefix))
        return blueprint

    # ---- Hooks and middleware (applied at app level upon registration) ----
    def before_request(self, func: Handler) -> Handler:
        self.before_request_handlers.append(func)
        return func

    def after_request(self, func: Handler) -> Handler:
        self.after_request_handlers.append(func)
        return func

    def add_middleware(self, middleware: Middleware, priority: int = 0):
        self.middleware.append((middleware, priority))
        self.middleware.sort(key=lambda item: item[1], reverse=True)


def _join_paths(prefix: str | None, path: str) -> str:
    if not prefix:
        return path
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if prefix.endswith("/"):
        prefix = prefix[:-1]
    if not path.startswith("/"):
        path = "/" + path
    return prefix + path
