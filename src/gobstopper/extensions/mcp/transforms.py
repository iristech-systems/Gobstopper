"""
MCP Transforms for modifying component presentation.

Transforms can modify how tools, resources, and prompts are
presented to clients without changing the underlying implementation.
"""

from typing import Any, Callable, Dict, List, Optional, Set
from abc import ABC, abstractmethod


class Transform(ABC):
    """
    Base class for MCP transforms.

    Transforms modify components as they pass through the transform chain.
    """

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Transform tool list."""
        return tools

    async def transform_resources(
        self, resources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Transform resource list."""
        return resources

    async def transform_prompts(
        self, prompts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Transform prompt list."""
        return prompts


class Namespace(Transform):
    """
    Transform that adds namespace prefixes to components.

    Useful when combining multiple MCP servers or providers.

    Example:
        transform = Namespace("api")
        # Tool "search" becomes "api_search"
        # Resource "config://app" becomes "api://config/app"
    """

    def __init__(self, namespace: str):
        self.namespace = namespace

    def _namespace_tool(self, name: str) -> str:
        """Add namespace to tool name."""
        return f"{self.namespace}_{name}"

    def _namespace_uri(self, uri: str) -> str:
        """Add namespace to resource URI."""
        if "://" in uri:
            protocol, path = uri.split("://", 1)
            return f"{protocol}://{self.namespace}/{path}"
        return f"{self.namespace}:{uri}"

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add namespace to tool names."""
        result = []
        for tool in tools:
            tool = dict(tool)
            tool["name"] = self._namespace_tool(tool["name"])
            result.append(tool)
        return result

    async def transform_resources(
        self, resources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add namespace to resource URIs."""
        result = []
        for resource in resources:
            resource = dict(resource)
            resource["uri"] = self._namespace_uri(resource["uri"])
            result.append(resource)
        return result


class FilterByTag(Transform):
    """
    Transform that filters components by tags.

    Example:
        # Only show tools with "public" tag
        transform = FilterByTag(allowed_tags={"public"})

        # Hide tools with "internal" tag
        transform = FilterByTag(disallowed_tags={"internal"})
    """

    def __init__(
        self,
        allowed_tags: Optional[Set[str]] = None,
        disallowed_tags: Optional[Set[str]] = None,
    ):
        self.allowed_tags = allowed_tags
        self.disallowed_tags = disallowed_tags or set()

    def _has_allowed_tag(self, tags: Set[str]) -> bool:
        """Check if component has an allowed tag."""
        if not self.allowed_tags:
            return True
        return bool(tags & self.allowed_tags)

    def _has_disallowed_tag(self, tags: Set[str]) -> bool:
        """Check if component has a disallowed tag."""
        return bool(tags & self.disallowed_tags)

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter tools by tags."""
        return [
            tool
            for tool in tools
            if self._has_allowed_tag(set(tool.get("tags", [])))
            and not self._has_disallowed_tag(set(tool.get("tags", [])))
        ]


class RenameTool(Transform):
    """
    Transform that renames specific tools.

    Example:
        transform = RenameTool({
            "old_name": "new_name",
            "search": "find",
        })
    """

    def __init__(self, renames: Dict[str, str]):
        self.renames = renames

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rename tools according to mapping."""
        result = []
        for tool in tools:
            tool = dict(tool)
            name = tool.get("name", "")
            if name in self.renames:
                tool["name"] = self.renames[name]
            result.append(tool)
        return result


class DescribeTool(Transform):
    """
    Transform that adds or modifies tool descriptions.

    Useful for adding usage examples or clarifying behavior.

    Example:
        transform = DescribeTool({
            "search": "Search for documents. Args: query (str), limit (int, optional)"
        })
    """

    def __init__(self, descriptions: Dict[str, str]):
        self.descriptions = descriptions

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Update tool descriptions."""
        result = []
        for tool in tools:
            tool = dict(tool)
            name = tool.get("name", "")
            if name in self.descriptions:
                tool["description"] = self.descriptions[name]
            result.append(tool)
        return result


class DeprecateTool(Transform):
    """
    Transform that marks tools as deprecated.

    Example:
        transform = DeprecateTool(
            deprecated=["old_search"],
            replacement="new_search"
        )
    """

    def __init__(
        self,
        deprecated: List[str],
        replacement: Optional[str] = None,
    ):
        self.deprecated = set(deprecated)
        self.replacement = replacement

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Mark deprecated tools."""
        result = []
        for tool in tools:
            tool = dict(tool)
            name = tool.get("name", "")
            if name in self.deprecated:
                tool["deprecated"] = True
                if self.replacement:
                    tool["replacement"] = self.replacement
            result.append(tool)
        return result


class AddMetadata(Transform):
    """
    Transform that adds metadata to components.

    Example:
        transform = AddMetadata({
            "tools": {"version": "2.0"},
            "resources": {"cached": True}
        })
    """

    def __init__(self, metadata: Dict[str, Dict[str, Any]]):
        self.metadata = metadata

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add metadata to tools."""
        tools_meta = self.metadata.get("tools", {})
        return [{**tool, **tools_meta} for tool in tools]

    async def transform_resources(
        self, resources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add metadata to resources."""
        resources_meta = self.metadata.get("resources", {})
        return [{**resource, **resources_meta} for resource in resources]

    async def transform_prompts(
        self, prompts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add metadata to prompts."""
        prompts_meta = self.metadata.get("prompts", {})
        return [{**prompt, **prompts_meta} for prompt in prompts]


class ChainTransform(Transform):
    """
    Transform that chains multiple transforms together.

    Example:
        chain = ChainTransform([
            Namespace("api"),
            FilterByTag(allowed_tags={"public"}),
            DeprecateTool(deprecated=["legacy_search"], replacement="api_search"),
        ])
    """

    def __init__(self, transforms: List[Transform]):
        self.transforms = transforms

    async def transform_tools(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply all transforms to tools in order."""
        result = tools
        for transform in self.transforms:
            result = await transform.transform_tools(result)
        return result

    async def transform_resources(
        self, resources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply all transforms to resources in order."""
        result = resources
        for transform in self.transforms:
            result = await transform.transform_resources(result)
        return result

    async def transform_prompts(
        self, prompts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply all transforms to prompts in order."""
        result = prompts
        for transform in self.transforms:
            result = await transform.transform_prompts(result)
        return result
