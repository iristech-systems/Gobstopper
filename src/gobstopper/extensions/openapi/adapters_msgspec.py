"""Type adapter for msgspec.Struct models.

This module provides a TypeAdapter implementation that converts msgspec.Struct
definitions to OpenAPI JSON Schema. msgspec is a fast JSON serialization library
with schema validation support.

The adapter introspects Struct fields and their types, properly handling default
values and optional fields to generate accurate required field lists.

Example:
    >>> import msgspec
    >>>
    >>> class User(msgspec.Struct):
    ...     id: int
    ...     name: str
    ...     email: str | None = None
    ...     is_active: bool = True
    >>>
    >>> # Generates schema:
    >>> # {
    >>> #     "type": "object",
    >>> #     "properties": {
    >>> #         "id": {"type": "integer"},
    >>> #         "name": {"type": "string"},
    >>> #         "email": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    >>> #         "is_active": {"type": "boolean"}
    >>> #     },
    >>> #     "required": ["id", "name"]  # email and is_active have defaults
    >>> # }

See Also:
    - msgspec documentation: https://jcristharif.com/msgspec/
    - TypeRegistry: Type adapter registry
"""
from __future__ import annotations

from typing import Any, Dict, Optional, get_type_hints

try:
    import msgspec
except Exception:  # pragma: no cover - msgspec is declared in deps
    msgspec = None  # type: ignore

from .typing_adapters import TypeAdapter, TypeRegistry


class MsgspecAdapter:
    """Type adapter for msgspec.Struct models.

    Converts msgspec.Struct definitions to OpenAPI JSON Schema by introspecting
    struct fields and their type annotations. Determines required fields based
    on presence of default values.

    This adapter has high priority (typically 10) to handle msgspec types before
    generic fallbacks are tried.

    Methods:
        can_handle: Check if a type is a msgspec.Struct
        to_json_schema: Convert Struct to JSON Schema with required tracking

    Example:
        >>> import msgspec
        >>>
        >>> class Config(msgspec.Struct):
        ...     host: str
        ...     port: int = 8080
        ...     debug: bool = False
        >>>
        >>> # Generates:
        >>> # {
        >>> #     "type": "object",
        >>> #     "properties": {
        >>> #         "host": {"type": "string"},
        >>> #         "port": {"type": "integer"},
        >>> #         "debug": {"type": "boolean"}
        >>> #     },
        >>> #     "required": ["host"]
        >>> # }
    """

    def can_handle(self, tp: Any) -> bool:  # type: ignore[override]
        """Check if the type is a msgspec.Struct.

        Args:
            tp: Type to check.

        Returns:
            True if tp is a msgspec.Struct subclass, False otherwise or if
            msgspec is not installed.
        """
        if msgspec is None:
            return False
        try:
            return isinstance(tp, type) and issubclass(tp, msgspec.Struct)
        except Exception:
            return False

    def to_json_schema(self, tp: Any, registry: TypeRegistry) -> Dict[str, Any]:  # type: ignore[override]
        assert msgspec is not None
        # Gather fields from msgspec.Struct
        props: Dict[str, Any] = {}
        required: list[str] = []

        # Use msgspec's metadata if available
        fields = getattr(tp, "__struct_fields__", None)
        types_map: Dict[str, Any]
        try:
            # get_type_hints handles forward refs
            types_map = get_type_hints(tp)
        except Exception:
            types_map = {name: object for name in (fields or [])}

        if fields is None:
            # Fallback to __annotations__ order
            fields = list(types_map.keys())

        # Local unique sentinel to avoid relying on msgspec.UNSET across versions
        _SENTINEL = object()

        for name in fields:
            ftype = types_map.get(name, Any)
            schema = registry.resolve_schema(ftype)
            props[name] = schema

            # Determine required via default presence on the class definition
            val = getattr(tp, name, _SENTINEL)
            has_default = val is not _SENTINEL
            # msgspec treats default=... or default_factory as optional; if no default present, it's required
            if not has_default:
                required.append(name)

        obj_schema: Dict[str, Any] = {
            "type": "object",
            "properties": props,
        }
        if required:
            obj_schema["required"] = required

        return registry.ref_or_inline(tp, obj_schema)
