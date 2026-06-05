"""
Tool Registry - Central registry where all tools live

Every capability gets wrapped as a tool with a standard schema.
Tools can be discovered, composed, and executed uniformly.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """Represents a unified tool with standardized schema"""

    tool_id: str  # e.g., "rag_search", "workflow_run"
    name: str  # Human-readable name
    description: str
    category: str  # e.g., "knowledge", "agent", "workflow", "generation"
    tier: int = 1  # 1=foundational, 2=specialized, 3=advanced, 4=expert
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable[[dict[str, Any]], Awaitable[Any]] | None = None
    source_service: str = ""  # Which service provides this tool
    requires_auth: bool = True
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    rate_limit: int | None = None  # Requests per minute
    timeout_seconds: int = 30
    tags: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format"""
        return {
            "type": "function",
            "function": {
                "name": self.tool_id,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Convert to Anthropic tool format"""
        return {
            "name": self.tool_id,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_langchain_tool(self) -> dict[str, Any]:
        """Convert to LangChain tool format"""
        return {
            "name": self.tool_id,
            "description": self.description,
            "args_schema": self.input_schema,
        }


class ToolRegistry:
    """
    Central registry where all tools live.

    Features:
    - Register tools from any service
    - Discover tools by capability, category, or natural language
    - Convert tools to different AI framework formats
    - Compose multiple tools into compound operations
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, list[str]] = {}
        self._tags: dict[str, list[str]] = {}
        self._aliases: dict[str, str] = {}
        self._compositions: dict[str, list[str]] = {}

    def register(self, tool: Tool) -> bool:
        """
        Register a new tool.

        Args:
            tool: The Tool to register

        Returns:
            True if registered successfully
        """
        if tool.tool_id in self._tools:
            logger.warning(f"Tool {tool.tool_id} already registered, updating")
            tool.updated_at = datetime.now(UTC)

        self._tools[tool.tool_id] = tool

        # Track by category
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool.tool_id not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.tool_id)

        # Track by tags
        for tag in tool.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            if tool.tool_id not in self._tags[tag]:
                self._tags[tag].append(tool.tool_id)

        logger.info(f"Registered tool: {tool.tool_id} ({tool.name})")
        return True

    def unregister(self, tool_id: str) -> bool:
        """Remove a tool from the registry"""
        if tool_id not in self._tools:
            return False

        tool = self._tools.pop(tool_id)

        # Remove from category tracking
        if tool.category in self._categories:
            self._categories[tool.category] = [
                t for t in self._categories[tool.category] if t != tool_id
            ]

        # Remove from tag tracking
        for tag in tool.tags:
            if tag in self._tags:
                self._tags[tag] = [t for t in self._tags[tag] if t != tool_id]

        # Remove aliases
        self._aliases = {k: v for k, v in self._aliases.items() if v != tool_id}

        logger.info(f"Unregistered tool: {tool_id}")
        return True

    def get(self, tool_id: str) -> Tool | None:
        """Get a tool by ID or alias"""
        if tool_id in self._aliases:
            tool_id = self._aliases[tool_id]
        return self._tools.get(tool_id)

    def list_all(self, category: str | None = None) -> list[Tool]:
        """List all tools, optionally filtered by category"""
        if category:
            ids = self._categories.get(category, [])
            return [self._tools[i] for i in ids if i in self._tools]
        return list(self._tools.values())

    def list_categories(self) -> list[str]:
        """List all tool categories"""
        return list(self._categories.keys())

    def list_tags(self) -> list[str]:
        """List all tool tags"""
        return list(self._tags.keys())

    def by_tag(self, tag: str) -> list[Tool]:
        """Get all tools with a specific tag"""
        ids = self._tags.get(tag, [])
        return [self._tools[i] for i in ids if i in self._tools]

    def search(self, query: str) -> list[Tool]:
        """Search tools by name, description, or tags"""
        query_lower = query.lower()
        results = []

        for tool in self._tools.values():
            score = 0

            # Name match (highest priority)
            if query_lower in tool.name.lower():
                score += 10

            # Description match
            if query_lower in tool.description.lower():
                score += 5

            # Tag match
            for tag in tool.tags:
                if query_lower in tag.lower():
                    score += 3

            # Category match
            if query_lower in tool.category.lower():
                score += 2

            if score > 0:
                results.append((tool, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results]

    def add_alias(self, alias: str, tool_id: str) -> bool:
        """Add an alias for a tool"""
        if tool_id not in self._tools:
            return False
        self._aliases[alias] = tool_id
        return True

    def compose(self, name: str, tool_ids: list[str]) -> bool:
        """Create a composition of multiple tools"""
        for tid in tool_ids:
            if tid not in self._tools:
                logger.warning(f"Cannot compose: tool {tid} not found")
                return False

        self._compositions[name] = tool_ids
        logger.info(f"Created tool composition: {name} = {tool_ids}")
        return True

    def get_composition(self, name: str) -> list[str] | None:
        """Get the tools in a composition"""
        return self._compositions.get(name)

    def to_openai_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        """Export all tools in OpenAI function calling format"""
        tools = self.list_all(category)
        return [t.to_openai_tool() for t in tools]

    def to_anthropic_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        """Export all tools in Anthropic format"""
        tools = self.list_all(category)
        return [t.to_anthropic_tool() for t in tools]

    def to_dict(self) -> dict[str, Any]:
        """Export registry as a dictionary"""
        return {
            "tools": [
                {
                    "tool_id": t.tool_id,
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "source_service": t.source_service,
                    "requires_auth": t.requires_auth,
                    "tags": t.tags,
                }
                for t in self._tools.values()
            ],
            "categories": self._categories,
            "tags": self._tags,
            "compositions": self._compositions,
            "total_count": len(self._tools),
        }


# Global registry instance
_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
