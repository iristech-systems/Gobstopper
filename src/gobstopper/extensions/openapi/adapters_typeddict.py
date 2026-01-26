"""Type adapter for typing.TypedDict.

This module provides a TypeAdapter implementation that converts typing.TypedDict
definitions to OpenAPI JSON Schema. TypedDict provides a way to define dictionary
structures with typed keys.

The adapter properly handles total/non-total TypedDicts and uses __required_keys__
and __optional_keys__ to determine which fields are required in the schema.

Example:
    >>> from typing import TypedDict
    >>>
    >>> class User(TypedDict):
    ...     id: int
    ...     name: str
    ...     email: str
    >>>
    >>> class PartialUser(TypedDict, total=False):
    ...     id: int
    ...     name: str
    ...     email: str
    >>>
    >>> # User generates required: ["id", "name", "email"]
    >>> # PartialUser generates required: []

See Also:
    - TypedDict documentation: https://docs.python.org/3/library/typing.html#typing.TypedDict
    - PEP 589: https://peps.python.org/pep-0589/
    - TypeRegistry: Type adapter registry
"""
from __future__ import annotations

from typing import Any, Dict, get_type_hints

try:
    from typing import TypedDict  # Python 3.8+
except Exception:  # pragma: no cover
    TypedDict = None  # type: ignore

from .typing_adapters import TypeRegistry


class TypedDictAdapter:
    """Type adapter for typing.TypedDict.

    Converts TypedDict definitions to OpenAPI JSON Schema by introspecting
    annotations and using __required_keys__ and __optional_keys__ to determine
    which fields must be present.

    Handles both total=True (all keys required by default) and total=False
    (all keys optional by default) TypedDict variants.

    Methods:
        can_handle: Check if a type is a TypedDict
        to_json_schema: Convert TypedDict to JSON Schema with required tracking

    Example:
        >>> from typing import TypedDict, NotRequired
        >>>
        >>> class Article(TypedDict):
        ...     title: str
        ...     author: str
        ...     published: bool
        ...     views: NotRequired[int]  # Optional in Python 3.11+
        >>>
        >>> # Generates:
        >>> # {
        >>> #     "type": "object",
        >>> #     "properties": {
        >>> #         "title": {"type": "string"},
        >>> #         "author": {"type": "string"},
        >>> #         "published": {"type": "boolean"},
        >>> #         "views": {"type": "integer"}
        >>> #     },
        >>> #     "required": ["title", "author", "published"]
        >>> # }
    """

    def can_handle(self, tp: Any) -> bool:  # type: ignore[override]
        """Check if the type is a TypedDict.

        Args:
            tp: Type to check.

        Returns:
            True if tp is a TypedDict, False otherwise or if TypedDict is not available.
        """
        if TypedDict is None:
            return False
        try:
            # TypedDict classes have __annotations__ and __total__
            return isinstance(tp, type) and hasattr(tp, "__total__") and hasattr(tp, "__annotations__")
        except Exception:
            return False

    def to_json_schema(self, tp: Any, registry: TypeRegistry) -> Dict[str, Any]:  # type: ignore[override]
        annotations = getattr(tp, "__annotations__", {}) or {}

        # get_type_hints to resolve forward refs
        try:
            type_hints = get_type_hints(tp)
        except Exception:
            type_hints = annotations

        properties: Dict[str, Any] = {}
        required: list[str] = []
        # Python provides accurate sets for required/optional keys
        req = set(getattr(tp, "__required_keys__", set()))
        opt = set(getattr(tp, "__optional_keys__", set()))

        for name, atype in type_hints.items():
            properties[name] = registry.resolve_schema(atype)
            # If Python marked it required, include it. If req is empty, infer by absence from optional keys.
            if name in req or (not req and name not in opt):
                required.append(name)

        schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return registry.ref_or_inline(tp, schema)
