"""Type adapter for Python dataclasses.

This module provides a TypeAdapter implementation that converts Python dataclasses
to OpenAPI JSON Schema, properly handling field types, required/optional fields,
and default values.

The adapter introspects dataclass fields using the dataclasses module and
get_type_hints to resolve forward references, then generates appropriate
JSON Schema with required field tracking.

Example:
    >>> from dataclasses import dataclass, field
    >>> from typing import Optional
    >>>
    >>> @dataclass
    >>> class User:
    ...     id: int
    ...     name: str
    ...     email: Optional[str] = None
    ...     tags: list[str] = field(default_factory=list)
    >>>
    >>> # Generates schema:
    >>> # {
    >>> #     "type": "object",
    >>> #     "properties": {
    >>> #         "id": {"type": "integer"},
    >>> #         "name": {"type": "string"},
    >>> #         "email": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    >>> #         "tags": {"type": "array", "items": {"type": "string"}}
    >>> #     },
    >>> #     "required": ["id", "name"]  # email and tags have defaults
    >>> # }

See Also:
    - Python dataclasses: https://docs.python.org/3/library/dataclasses.html
    - TypeRegistry: Type adapter registry
"""
from __future__ import annotations

from typing import Any, Dict, get_type_hints
import dataclasses as dc

from .typing_adapters import TypeRegistry


class DataclassesAdapter:
    """Type adapter for Python dataclasses.

    Converts dataclass definitions to OpenAPI JSON Schema by introspecting
    field names, types, and default values. Fields without defaults are
    marked as required.

    The adapter uses get_type_hints() to properly resolve forward references
    and string annotations, falling back to __annotations__ if type resolution
    fails.

    Methods:
        can_handle: Check if a type is a dataclass
        to_json_schema: Convert dataclass to JSON Schema with required tracking

    Example:
        >>> from dataclasses import dataclass
        >>>
        >>> @dataclass
        >>> class Product:
        ...     id: int
        ...     name: str
        ...     price: float
        ...     description: str = ""
        >>>
        >>> # Generates:
        >>> # {
        >>> #     "type": "object",
        >>> #     "properties": {
        >>> #         "id": {"type": "integer"},
        >>> #         "name": {"type": "string"},
        >>> #         "price": {"type": "number"},
        >>> #         "description": {"type": "string"}
        >>> #     },
        >>> #     "required": ["id", "name", "price"]
        >>> # }
    """

    def can_handle(self, tp: Any) -> bool:  # type: ignore[override]
        """Check if the type is a dataclass.

        Args:
            tp: Type to check.

        Returns:
            True if tp is a dataclass, False otherwise.
        """
        try:
            return isinstance(tp, type) and dc.is_dataclass(tp)
        except Exception:
            return False

    def to_json_schema(self, tp: Any, registry: TypeRegistry) -> Dict[str, Any]:  # type: ignore[override]
        """Convert a dataclass to JSON Schema.

        Introspects dataclass fields, resolves their types recursively via the
        registry, and determines required fields based on absence of default
        values and default_factory.

        Args:
            tp: Dataclass type to convert.
            registry: TypeRegistry for recursive type resolution.

        Returns:
            JSON Schema dict registered as a component with $ref.

        Example:
            >>> @dataclass
            >>> class Address:
            ...     street: str
            ...     city: str
            ...     country: str = "USA"
            >>>
            >>> adapter.to_json_schema(Address, registry)
            {'$ref': '#/components/schemas/mymodule.Address'}
            >>> # And registry.components contains:
            >>> # {
            >>> #     "mymodule.Address": {
            >>> #         "type": "object",
            >>> #         "properties": {
            >>> #             "street": {"type": "string"},
            >>> #             "city": {"type": "string"},
            >>> #             "country": {"type": "string"}
            >>> #         },
            >>> #         "required": ["street", "city"]
            >>> #     }
            >>> # }
        """
        # Resolve field types; prefer get_type_hints to handle forward refs
        try:
            hints = get_type_hints(tp)
        except Exception:
            hints = getattr(tp, "__annotations__", {}) or {}

        props: Dict[str, Any] = {}
        required: list[str] = []
        for f in dc.fields(tp):
            ft = hints.get(f.name, f.type)
            props[f.name] = registry.resolve_schema(ft)
            if f.default is dc.MISSING and f.default_factory is dc.MISSING:  # type: ignore[attr-defined]
                required.append(f.name)

        schema: Dict[str, Any] = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        return registry.ref_or_inline(tp, schema)
