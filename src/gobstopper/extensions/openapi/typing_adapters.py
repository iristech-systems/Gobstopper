"""Type adapter system for converting Python types to JSON Schema.

This module provides a pluggable type adapter architecture for converting various
Python type systems (dataclasses, TypedDict, msgspec.Struct, etc.) to JSON Schema
compatible with OpenAPI 3.1.

The system uses a priority-based registry where adapters are tried in order until
one can handle the given type. This allows specialized adapters to take precedence
over generic fallbacks.

Key Components:
    TypeAdapter: Protocol defining the adapter interface
    TypeRegistry: Registry managing multiple adapters with priority ordering
    FallbackAdapter: Generic adapter for basic types and typing generics
    _stable_name: Helper for generating consistent schema component names

Architecture:
    1. Adapters implement can_handle() to claim types they can process
    2. Adapters implement to_json_schema() to generate JSON Schema
    3. Registry tries adapters in priority order (lower number = higher priority)
    4. Adapters can recursively call registry.resolve_schema() for nested types
    5. Complex types are registered as components with $ref references

Example:
    Basic usage (internal to generator)::

        from gobstopper.extensions.openapi.typing_adapters import TypeRegistry
        from gobstopper.extensions.openapi.adapters_dataclasses import DataclassesAdapter

        registry = TypeRegistry()
        registry.register_adapter(DataclassesAdapter(), priority=30)

        schema = registry.resolve_schema(MyDataclass)
        # Returns: {"$ref": "#/components/schemas/MyDataclass"}
        # Adds MyDataclass schema to registry.components

See Also:
    - adapters_dataclasses: Adapter for Python dataclasses
    - adapters_typeddict: Adapter for typing.TypedDict
    - adapters_msgspec: Adapter for msgspec.Struct
    - OpenAPI 3.1 Schema: https://spec.openapis.org/oas/v3.1.0#schema-object
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, Tuple, get_args, get_origin
import hashlib
import enum


class TypeAdapter(Protocol):
    """Protocol defining the interface for type adapters.

    Type adapters convert Python types to JSON Schema for OpenAPI specifications.
    Implementations should handle specific type systems (dataclasses, TypedDict, etc.)
    and delegate to the registry for nested type resolution.

    Methods:
        can_handle: Check if this adapter can process the given type
        to_json_schema: Convert the type to JSON Schema

    Example:
        Implementing a custom adapter::

            class MyCustomAdapter:
                def can_handle(self, tp: Any) -> bool:
                    return isinstance(tp, type) and hasattr(tp, '_my_marker')

                def to_json_schema(self, tp: Any, registry: TypeRegistry) -> Dict[str, Any]:
                    properties = {}
                    for field_name, field_type in tp._fields.items():
                        # Recursively resolve nested types
                        properties[field_name] = registry.resolve_schema(field_type)
                    return registry.ref_or_inline(tp, {
                        "type": "object",
                        "properties": properties
                    })
    """
    def can_handle(self, tp: Any) -> bool:
        """Check if this adapter can handle the given type.

        Args:
            tp: Python type to check.

        Returns:
            True if this adapter can convert the type, False otherwise.
        """
        ...

    def to_json_schema(self, tp: Any, registry: "TypeRegistry") -> Dict[str, Any]:
        """Convert the type to JSON Schema.

        Args:
            tp: Python type to convert.
            registry: TypeRegistry for resolving nested types.

        Returns:
            JSON Schema dictionary, possibly containing $ref to components.
        """
        ...


def _stable_name(tp: Any) -> str:
    """Generate a stable, unique name for a type for use in OpenAPI components.

    Creates a consistent identifier by combining the type's module and qualified name.
    Used to generate component schema names like "mymodule.models.User".

    Args:
        tp: Python type to generate name for.

    Returns:
        Stable string identifier in format "module.QualifiedName".

    Example:
        >>> from dataclasses import dataclass
        >>> @dataclass
        ... class User:
        ...     pass
        >>> _stable_name(User)
        '__main__.User'
    """
    # Base stable name from module + qualname if available
    base = f"{getattr(tp, '__module__', 'builtins')}.{getattr(tp, '__qualname__', getattr(tp, '__name__', str(tp)))}"
    return base


class TypeRegistry:
    """Registry for managing type adapters with priority-based resolution.

    The TypeRegistry coordinates multiple type adapters to convert Python types
    to JSON Schema. Adapters are tried in priority order (lower number = higher
    priority) until one successfully handles the type.

    The registry also manages the components/schemas section, collecting schema
    definitions for complex types and replacing them with $ref references.

    Attributes:
        _adapters: List of (priority, adapter) tuples sorted by priority.
        components: Dictionary of component schemas keyed by stable type names.

    Example:
        >>> registry = TypeRegistry()
        >>> registry.register_adapter(DataclassesAdapter(), priority=30)
        >>> registry.register_adapter(FallbackAdapter(), priority=1000)
        >>>
        >>> schema = registry.resolve_schema(MyDataclass)
        >>> # Returns: {"$ref": "#/components/schemas/mymodule.MyDataclass"}
        >>> # Adds schema to registry.components

    Note:
        - Lower priority numbers take precedence
        - Adapters should call registry.resolve_schema() for nested types
        - registry.ref_or_inline() decides whether to inline or reference schemas
    """

    def __init__(self):
        """Initialize an empty type registry."""
        self._adapters: list[tuple[int, TypeAdapter]] = []  # (priority, adapter)
        self.components: Dict[str, Dict[str, Any]] = {}

    def register_adapter(self, adapter: TypeAdapter, priority: int) -> None:
        """Register a type adapter with a specific priority.

        Args:
            adapter: TypeAdapter instance to register.
            priority: Integer priority (lower values = higher priority).
                Common values: 10 (msgspec), 20 (TypedDict), 30 (dataclasses),
                1000 (fallback).

        Note:
            Adapters are sorted after each registration to maintain priority order.
        """
        self._adapters.append((priority, adapter))
        self._adapters.sort(key=lambda x: x[0])

    def resolve_schema(self, tp: Any) -> Dict[str, Any]:
        """Resolve a Python type to JSON Schema using registered adapters.

        Tries each adapter in priority order until one can handle the type.
        If no adapter handles it, falls back to FallbackAdapter.

        Args:
            tp: Python type to convert (class, generic, typing construct, etc.).

        Returns:
            JSON Schema dict, possibly with $ref to components/schemas.

        Example:
            >>> registry.resolve_schema(int)
            {'type': 'integer'}
            >>> registry.resolve_schema(MyDataclass)
            {'$ref': '#/components/schemas/mymodule.MyDataclass'}
            >>> registry.resolve_schema(list[str])
            {'type': 'array', 'items': {'type': 'string'}}
        """
        # Try adapters
        for _prio, adapter in self._adapters:
            if adapter.can_handle(tp):
                return adapter.to_json_schema(tp, self)
        # Fallback inline schema
        return FallbackAdapter().to_json_schema(tp, self)

    def ref_or_inline(self, tp: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Decide whether to inline a schema or create a component reference.

        Complex types (classes, enums) are registered as components and replaced
        with $ref. Simple types (primitives, inline objects) are returned as-is.

        Args:
            tp: The Python type being converted.
            schema: The generated JSON Schema dict.

        Returns:
            Either the original schema (inline) or {"$ref": "..."} (component).

        Example:
            >>> # Complex type becomes a reference
            >>> registry.ref_or_inline(User, {"type": "object", "properties": {...}})
            {'$ref': '#/components/schemas/mymodule.User'}
            >>>
            >>> # Simple schema stays inline
            >>> registry.ref_or_inline(int, {"type": "integer"})
            {'type': 'integer'}

        Note:
            - Built-in types (str, int, float, bool, bytes) are always inlined
            - Classes are registered as components
            - The first call registers the schema, subsequent calls reuse it
        """
        # For classes and Enums, register a component and return $ref; for simple schemas, inline
        if isinstance(tp, type) and (hasattr(tp, "__mro__") and tp not in (str, int, float, bool, bytes)):
            name = _stable_name(tp)
            if name not in self.components:
                self.components[name] = schema
            return {"$ref": f"#/components/schemas/{name}"}
        return schema


class FallbackAdapter:
    """Generic type adapter for built-in types and typing module constructs.

    This adapter serves as the catch-all fallback for types not handled by
    specialized adapters. It supports:
        - Built-in primitives (str, int, float, bool, bytes)
        - Enums
        - typing module generics (Optional, Union, Literal, List, Dict)
        - Generic dataclasses (minimal object schema)
        - Unknown types (defaults to object schema)

    The FallbackAdapter should always be registered with the lowest priority
    (highest priority number) so specialized adapters take precedence.

    Attributes:
        SIMPLE: Mapping of built-in types to their JSON Schema representations.

    Example:
        >>> adapter = FallbackAdapter()
        >>> registry = TypeRegistry()
        >>>
        >>> adapter.to_json_schema(str, registry)
        {'type': 'string'}
        >>>
        >>> adapter.to_json_schema(Optional[int], registry)
        {'anyOf': [{'type': 'integer'}, {'type': 'null'}]}
        >>>
        >>> adapter.to_json_schema(list[str], registry)
        {'type': 'array', 'items': {'type': 'string'}}
    """
    SIMPLE: Dict[Any, Dict[str, Any]] = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        bytes: {"type": "string", "format": "byte"},
    }

    def can_handle(self, tp: Any) -> bool:
        """Check if this adapter can handle the given type.

        Returns:
            Always True, as this is the fallback adapter.
        """
        return True  # always last resort

    def to_json_schema(self, tp: Any, registry: TypeRegistry) -> Dict[str, Any]:
        origin = get_origin(tp)
        args = get_args(tp)

        # Plain builtins
        if tp in self.SIMPLE:
            return self.SIMPLE[tp]

        # Enum support
        if isinstance(tp, type) and issubclass(tp, enum.Enum):
            values = [member.value for member in tp]  # assume primitive values
            schema = {"enum": values}
            if all(isinstance(v, str) for v in values):
                schema["type"] = "string"
            elif all(isinstance(v, int) for v in values):
                schema["type"] = "integer"
            return registry.ref_or_inline(tp, schema)

        # Optional[T] == Union[T, None]
        if origin is Optional:
            inner = args[0]
            inner_schema = registry.resolve_schema(inner)
            return {"anyOf": [inner_schema, {"type": "null"}]}

        # Union
        if origin is None and hasattr(tp, "__args__") and getattr(tp, "__origin__", None) is None and getattr(tp, "__module__", "") == "typing":
            # Older typing forms; fallback do nothing special
            pass
        if origin is __import__("typing").Union:  # type: ignore[attr-defined]
            subs = [registry.resolve_schema(a) for a in args]
            return {"oneOf": subs}

        # Literal
        try:
            from typing import Literal  # py3.8+
            if origin is Literal:
                vals = list(args)
                schema: Dict[str, Any] = {"enum": vals}
                # attempt to infer a type if homogeneous
                if vals and all(isinstance(v, str) for v in vals):
                    schema["type"] = "string"
                elif vals and all(isinstance(v, int) for v in vals):
                    schema["type"] = "integer"
                return schema
        except Exception:
            pass

        # List[T]
        from typing import List, Sequence
        if origin in (list, List, Sequence):
            item_tp = args[0] if args else Any
            return {"type": "array", "items": registry.resolve_schema(item_tp)}

        # Dict[str, V]
        from typing import Dict as TDict, Mapping
        if origin in (dict, TDict, Mapping):
            key_tp = args[0] if args else str
            val_tp = args[1] if len(args) > 1 else Any
            # OpenAPI/JSON Schema only supports string keys for object
            if key_tp not in (str, Any):
                # degrade to string
                key_tp = str
            return {"type": "object", "additionalProperties": registry.resolve_schema(val_tp)}

        # Dataclass naive support (treat as object with no properties for now)
        try:
            import dataclasses
            if isinstance(tp, type) and dataclasses.is_dataclass(tp):
                # minimal: no fields expansion yet
                schema = {"type": "object"}
                return registry.ref_or_inline(tp, schema)
        except Exception:
            pass

        # Unknown types -> object
        if isinstance(tp, type):
            schema = {"type": "object"}
            return registry.ref_or_inline(tp, schema)

        # Fallback
        return {"type": "object"}
