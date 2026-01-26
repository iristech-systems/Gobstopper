"""OpenAPI 3.1 specification generator for Gobstopper applications.

This module contains the core logic for generating OpenAPI 3.1 specifications
from Gobstopper route handlers decorated with OpenAPI metadata decorators.

The generator:
    1. Introspects all registered route handlers
    2. Extracts path parameters from route patterns
    3. Collects metadata from @doc, @response, @request_body, @param decorators
    4. Resolves Python types to JSON Schema via pluggable type adapters
    5. Builds a complete OpenAPI 3.1 specification document

Type adapters are registered in priority order to handle different Python type
systems (msgspec.Struct, TypedDict, dataclasses) with appropriate fallbacks.

Classes:
    OpenAPIGenerator: Main spec generation orchestrator

Functions:
    build_default_info: Constructs OpenAPI info object from parameters
    _oa_path_from: Converts Gobstopper route patterns to OpenAPI path syntax
    _collect_path_params: Extracts path parameters from route patterns
    _param_schema_for: Maps path converters to JSON Schema types
    _schema_for_python: Simple fallback for basic Python types

See Also:
    - OpenAPI 3.1 Specification: https://spec.openapis.org/oas/v3.1.0
    - typing_adapters: Type adapter registry and protocol
    - decorators: Metadata attachment decorators
"""
from __future__ import annotations

import re
import inspect
from typing import Any, Optional

from .typing_adapters import TypeRegistry, FallbackAdapter
from .adapters_msgspec import MsgspecAdapter
from .adapters_typeddict import TypedDictAdapter
from .adapters_dataclasses import DataclassesAdapter

# Lightweight typing schema mapping; kept for potential inline fallbacks (unused now)
_SIMPLE_TYPE_MAP = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
}


def build_default_info(title: str, version: str, description: Optional[str], tos: Optional[str], contact: Optional[dict], license: Optional[dict]):
    """Build an OpenAPI info object from individual fields.

    Constructs the required 'info' section of an OpenAPI specification with
    title, version, and optional metadata like description, terms of service,
    contact information, and license details.

    Args:
        title: API title displayed in documentation.
        version: API version string (semantic versioning recommended).
        description: Markdown-formatted API description. Optional.
        tos: URL to the terms of service document. Optional.
        contact: Contact information dict with optional keys: name, url, email.
        license: License information dict with required 'name' and optional 'url'.

    Returns:
        OpenAPI info object dict with provided fields.

    Example:
        >>> build_default_info(
        ...     "My API",
        ...     "1.0.0",
        ...     "A great API",
        ...     "https://example.com/terms",
        ...     {"name": "Support", "email": "support@example.com"},
        ...     {"name": "MIT", "url": "https://opensource.org/licenses/MIT"}
        ... )
        {
            'title': 'My API',
            'version': '1.0.0',
            'description': 'A great API',
            'termsOfService': 'https://example.com/terms',
            'contact': {'name': 'Support', 'email': 'support@example.com'},
            'license': {'name': 'MIT', 'url': 'https://opensource.org/licenses/MIT'}
        }
    """
    info: dict[str, Any] = {"title": title, "version": version}
    if description:
        info["description"] = description
    if tos:
        info["termsOfService"] = tos
    if contact:
        info["contact"] = contact
    if license:
        info["license"] = license
    return info


_PARAM_TOKEN = re.compile(r"<([^>]+)>")
"""Regex pattern to match path parameter tokens like <id>, <int:user_id>, <uuid:item_id>."""


def _param_schema_for(conv_name: Optional[str]):
    """Map Gobstopper path converter names to JSON Schema types.

    Converts Gobstopper route pattern converters (int, uuid, date) to appropriate
    OpenAPI/JSON Schema type and format specifications for path parameters.

    Args:
        conv_name: The converter name from the route pattern (e.g., "int", "uuid").
            None for plain string parameters.

    Returns:
        JSON Schema dict with type and optional format.

    Example:
        >>> _param_schema_for("int")
        {'type': 'integer'}
        >>> _param_schema_for("uuid")
        {'type': 'string', 'format': 'uuid'}
        >>> _param_schema_for(None)
        {'type': 'string'}
    """
    if conv_name == "int":
        return {"type": "integer"}
    if conv_name == "uuid":
        return {"type": "string", "format": "uuid"}
    if conv_name == "date":
        return {"type": "string", "format": "date"}
    # path/default
    return {"type": "string"}


def _oa_path_from(pattern: str) -> str:
    """Convert Gobstopper route pattern to OpenAPI path syntax.

    Transforms Gobstopper path patterns like /users/<int:id> to OpenAPI format
    /users/{id}, stripping type converters and using curly braces.

    Args:
        pattern: Gobstopper route pattern with angle bracket parameters.
            Example: "/users/<int:id>/posts/<uuid:post_id>"

    Returns:
        OpenAPI path string with curly brace parameters.
            Example: "/users/{id}/posts/{post_id}"

    Example:
        >>> _oa_path_from("/users/<int:id>")
        '/users/{id}'
        >>> _oa_path_from("/items/<uuid:item_id>/details")
        '/items/{item_id}/details'
    """
    def repl(m: re.Match[str]):
        token = m.group(1)
        name = token.split(":", 1)[1] if ":" in token else token
        return "{" + name + "}"
    return re.sub(_PARAM_TOKEN, repl, pattern)


def _collect_path_params(pattern: str):
    """Extract path parameter specifications from a Gobstopper route pattern.

    Parses angle bracket parameters from route patterns and generates OpenAPI
    parameter objects with appropriate schemas based on type converters.

    Args:
        pattern: Gobstopper route pattern string.
            Example: "/users/<int:id>/posts/<uuid:post_id>"

    Returns:
        List of OpenAPI parameter objects for path parameters.

    Example:
        >>> _collect_path_params("/users/<int:id>/posts/<post_id>")
        [
            {
                'name': 'id',
                'in': 'path',
                'required': True,
                'schema': {'type': 'integer'}
            },
            {
                'name': 'post_id',
                'in': 'path',
                'required': True,
                'schema': {'type': 'string'}
            }
        ]

    Note:
        Path parameters are always marked as required per OpenAPI specification.
    """
    params = []
    for token in re.findall(_PARAM_TOKEN, pattern):
        if ":" in token:
            conv, name = token.split(":", 1)
        else:
            conv, name = None, token
        params.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": _param_schema_for(conv)
        })
    return params


def _schema_for_python(tp: Any) -> dict[str, Any] | None:
    """Simple fallback schema mapping for basic Python types.

    Maps common Python built-in types (str, int, float, bool) to JSON Schema.
    Used as a lightweight fallback; most schema generation is handled by type
    adapters for richer type introspection.

    Args:
        tp: Python type to convert.

    Returns:
        JSON Schema dict if type is recognized, None otherwise.

    Example:
        >>> _schema_for_python(str)
        {'type': 'string'}
        >>> _schema_for_python(int)
        {'type': 'integer'}
        >>> _schema_for_python(list)
        None

    Note:
        This is a minimal fallback. Type adapters provide comprehensive schema
        generation for dataclasses, TypedDict, msgspec.Struct, and generic types.
    """
    # Very small fallback; users can pass full dict schemas via decorators for more control
    return _SIMPLE_TYPE_MAP.get(tp)


class OpenAPIGenerator:
    """Core OpenAPI 3.1 specification generator for Gobstopper applications.

    This class orchestrates the generation of complete OpenAPI 3.1 specifications
    by introspecting Gobstopper route handlers, extracting metadata from decorators,
    resolving Python types to JSON Schema, and assembling the final spec document.

    The generator works in several phases:
        1. Register type adapters in priority order (msgspec, TypedDict, dataclasses)
        2. Iterate through all registered routes on the application
        3. Skip routes without OpenAPI metadata (opt-in model)
        4. For each route, extract path parameters and decorator metadata
        5. Resolve model types to JSON Schema via type adapter registry
        6. Build operation objects for each HTTP method
        7. Assemble paths, components, and top-level spec fields

    Attributes:
        app: The Gobstopper application instance being documented.
        state: OpenAPIState instance containing configuration and cache.

    Example:
        Generator is typically instantiated internally by attach_openapi()::

            from gobstopper.extensions.openapi import attach_openapi

            app = Gobstopper(__name__)
            attach_openapi(app, title="My API", version="1.0.0")
            # Generator created automatically, spec cached in app.openapi

    Note:
        - Only routes with explicit OpenAPI decorators are included in the spec.
        - WebSocket routes are automatically excluded from the spec.
        - Type adapters are registered with priority values (lower = higher priority).
        - Components (schemas) are automatically collected from resolved models.
        - The generated spec is cached in the state object to avoid regeneration.

    See Also:
        - attach_openapi: Main entry point for OpenAPI integration
        - TypeRegistry: Type adapter registry for schema resolution
        - OpenAPIState: State management and caching
    """

    def __init__(self, app, state):
        """Initialize the OpenAPI generator.

        Args:
            app: Gobstopper application instance with registered routes.
            state: OpenAPIState instance with configuration.
        """
        self.app = app
        self.state = state

    def build_spec(self) -> dict[str, Any]:
        """Build a complete OpenAPI 3.1 specification from the application routes.

        This method performs the entire specification generation process:
            1. Creates and configures a TypeRegistry with appropriate adapters
            2. Introspects all registered routes on the application
            3. Filters routes with OpenAPI metadata (opt-in documentation)
            4. Extracts path parameters from route patterns
            5. Collects decorator metadata (@doc, @response, @request_body, etc.)
            6. Resolves Python types to JSON Schema via type adapters
            7. Builds operation objects for each HTTP method
            8. Assembles paths, components, and top-level spec fields

        Type adapters are registered in priority order:
            - Priority 10: msgspec.Struct (if available)
            - Priority 20: TypedDict (if available)
            - Priority 30: dataclasses (if available)
            - Priority 1000: FallbackAdapter (always available)

        Lower priority numbers are tried first, allowing specialized adapters
        to handle specific types before falling back to generic adapters.

        Returns:
            Complete OpenAPI 3.1 specification as a dictionary. Structure:
                {
                    "openapi": "3.1.0",
                    "info": {...},
                    "paths": {...},
                    "components": {"schemas": {...}},
                    "servers": [...],
                    "tags": [...],
                    "security": [...],
                    "externalDocs": {...}
                }

        Example:
            Generated spec structure::

                {
                    "openapi": "3.1.0",
                    "info": {
                        "title": "My API",
                        "version": "1.0.0",
                        "description": "API description"
                    },
                    "paths": {
                        "/users/{id}": {
                            "get": {
                                "operationId": "get_users__id_",
                                "summary": "Get user by ID",
                                "tags": ["Users"],
                                "parameters": [
                                    {
                                        "name": "id",
                                        "in": "path",
                                        "required": true,
                                        "schema": {"type": "integer"}
                                    }
                                ],
                                "responses": {
                                    "200": {
                                        "description": "User found",
                                        "content": {
                                            "application/json": {
                                                "schema": {"$ref": "#/components/schemas/User"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "components": {
                        "schemas": {
                            "User": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer"},
                                    "name": {"type": "string"}
                                },
                                "required": ["id", "name"]
                            }
                        }
                    }
                }

        Note:
            - Only routes with __openapi__ metadata are included (opt-in).
            - WebSocket routes are automatically excluded.
            - Path parameters are auto-generated from route patterns.
            - Components/schemas are collected from model references.
            - The spec includes all top-level fields from state.config.
            - Type adapter errors are silently ignored to handle missing dependencies.

        See Also:
            - TypeRegistry.resolve_schema: Type to JSON Schema conversion
            - _oa_path_from: Route pattern to OpenAPI path conversion
            - _collect_path_params: Path parameter extraction
        """
        registry = TypeRegistry()
        # Register high-priority adapters first
        try:
            registry.register_adapter(MsgspecAdapter(), priority=10)
        except Exception:
            pass
        try:
            registry.register_adapter(TypedDictAdapter(), priority=20)
        except Exception:
            pass
        try:
            registry.register_adapter(DataclassesAdapter(), priority=30)
        except Exception:
            pass
        # Register minimal fallback adapter at lowest priority (higher number -> lower priority)
        registry.register_adapter(FallbackAdapter(), priority=1000)

        paths: dict[str, Any] = {}

        for rh in getattr(self.app, "_all_routes", []) or []:
            if getattr(rh, "is_websocket", False):
                continue
            # Only include routes explicitly decorated with OpenAPI metadata
            meta = getattr(rh.handler, "__openapi__", {}) or {}
            if not meta:
                continue

            path_oa = _oa_path_from(rh.pattern)
            path_item = paths.setdefault(path_oa, {})

            base_params = _collect_path_params(rh.pattern)

            # operation-level shared params from decorators
            extra_params = meta.get("parameters", [])

            for method in rh.methods:
                m = method.lower()
                op: dict[str, Any] = {
                    "operationId": meta.get("operationId") or f"{m}_{path_oa.strip('/').replace('/', '_') or 'root'}",
                    "responses": {},
                }
                # Merge doc fields allowing all OpenAPI fields
                doc_fields = meta.get("doc", {})
                for k, v in doc_fields.items():
                    op[k] = v
                # parameters
                merged_params = []
                if base_params:
                    merged_params.extend(base_params)
                if extra_params:
                    # resolve parameter schemas if schema is a Python type
                    for p in extra_params:
                        schema = p.get("schema")
                        if schema is not None and not isinstance(schema, dict):
                            p = dict(p)
                            p["schema"] = registry.resolve_schema(schema)
                        merged_params.append(p)
                if merged_params:
                    op["parameters"] = merged_params
                # request body
                rb = meta.get("requestBody")
                if rb:
                    rb_out = {k: v for k, v in rb.items() if not k.startswith("__")}
                    model = rb.get("__model__")
                    if model is not None:
                        media_types = rb.get("__media_types__") or ["application/json"]
                        schema = registry.resolve_schema(model)
                        content = {mt: {"schema": schema} for mt in media_types}
                        rb_out["content"] = content
                    op["requestBody"] = rb_out
                # responses
                resp_meta = meta.get("responses") or {"200": {"description": "Success"}}
                out_responses: dict[str, Any] = {}
                for code, r in resp_meta.items():
                    r_out = {k: v for k, v in r.items() if not k.startswith("__")}
                    model = r.get("__model__")
                    if model is not None:
                        media_types = r.get("__media_types__") or ["application/json"]
                        schema = registry.resolve_schema(model)
                        content = {mt: {"schema": schema} for mt in media_types}
                        r_out["content"] = content
                    if "description" not in r_out:
                        r_out["description"] = ""
                    out_responses[str(code)] = r_out
                op["responses"] = out_responses
                # security (operation-level)
                if meta.get("security"):
                    op["security"] = meta["security"]
                path_item[m] = op

        spec: dict[str, Any] = {
            "openapi": self.state.config.get("openapi", "3.1.0"),
            "info": self.state.config.get("info", {"title": "Gobstopper", "version": "0.1.0"}),
            "paths": paths,
        }
        # Top-level optional sections
        for key in ("servers", "tags", "externalDocs", "components", "security"):
            val = self.state.config.get(key)
            if val:
                spec[key] = val
        # Merge/emit components from registry
        if registry.components:
            comps = spec.get("components", {})
            schemas = comps.get("schemas", {})
            # Avoid overwriting pre-provided schemas
            schemas.update(registry.components)
            comps["schemas"] = schemas
            spec["components"] = comps
        return spec
