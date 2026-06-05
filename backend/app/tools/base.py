"""
Base Tool Infrastructure for FlowManner Backend.

Provides foundation for all agent-callable tools with:
- Standardized metadata (ToolMetadata)
- Abstract base class for tools (BaseTool)
- Tool registry for discovery and execution
- Support for OpenAI, Anthropic, LangChain formats
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Callable

router = APIRouter()


class ToolStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class ToolInput(BaseModel):
    """Base class for tool input validation. Override in subclasses with specific fields."""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_extra(cls) -> dict[str, Any]:
        return cls.model_json_schema()


class ToolResult(BaseModel):
    tool_id: str
    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success_result(cls, tool_id: str, result: Any, **kwargs) -> ToolResult:
        return cls(tool_id=tool_id, success=True, result=result, **kwargs)

    @classmethod
    def error_result(cls, tool_id: str, error: str, **kwargs) -> ToolResult:
        return cls(tool_id=tool_id, success=False, error=error, **kwargs)


class ToolMetadata(BaseModel):
    tool_id: str
    name: str
    description: str
    category: str = Field("general", description="knowledge|agent|workflow|generation")
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    source_service: str = ""
    requires_auth: bool = True
    cost_estimate: dict[str, Any] = Field(default_factory=dict)
    rate_limit: int | None = None
    timeout_seconds: int = 30
    tags: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.tool_id,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        return {
            "name": self.tool_id,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_langchain_tool(self) -> dict[str, Any]:
        return {
            "name": self.tool_id,
            "description": self.description,
            "args_schema": self.input_schema,
        }


class BaseTool(ABC):
    def __init__(self, metadata: ToolMetadata, handler: Callable | None = None):
        self.metadata = metadata
        self._handler = handler
        self._registry = None

    @property
    def tool_id(self) -> str:
        return self.metadata.tool_id

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def category(self) -> str:
        return self.metadata.category

    @property
    def tags(self) -> list[str]:
        return self.metadata.tags

    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        pass

    def to_openai_schema(self) -> dict[str, Any]:
        return self.metadata.to_openai_tool()

    def to_anthropic_schema(self) -> dict[str, Any]:
        return self.metadata.to_anthropic_tool()

    def to_langchain_schema(self) -> dict[str, Any]:
        return self.metadata.to_langchain_tool()

    def set_registry(self, registry) -> None:
        self._registry = registry


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}
        self._tags: dict[str, list[str]] = {}
        self._aliases: dict[str, str] = {}
        self._compositions: dict[str, list[str]] = {}

    def register(self, tool: BaseTool) -> bool:
        if tool.tool_id in self._tools:
            tool.metadata.updated_at = datetime.now(UTC)

        self._tools[tool.tool_id] = tool
        tool.set_registry(self)

        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool.tool_id not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.tool_id)

        for tag in tool.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            if tool.tool_id not in self._tags[tag]:
                self._tags[tag].append(tool.tool_id)

        return True

    def unregister(self, tool_id: str) -> bool:
        if tool_id not in self._tools:
            return False

        tool = self._tools.pop(tool_id)

        if tool.category in self._categories:
            self._categories[tool.category] = [
                t for t in self._categories[tool.category] if t != tool_id
            ]

        for tag in tool.tags:
            if tag in self._tags:
                self._tags[tag] = [t for t in self._tags[tag] if t != tool_id]

        self._aliases = {k: v for k, v in self._aliases.items() if v != tool_id}
        return True

    def get(self, tool_id: str) -> BaseTool | None:
        if tool_id in self._aliases:
            tool_id = self._aliases[tool_id]
        return self._tools.get(tool_id)

    def list_all(self, category: str | None = None) -> list[BaseTool]:
        if category:
            ids = self._categories.get(category, [])
            return [self._tools[i] for i in ids if i in self._tools]
        return list(self._tools.values())

    def list_categories(self) -> list[str]:
        return list(self._categories.keys())

    def list_tags(self) -> list[str]:
        return list(self._tags.keys())

    def by_tag(self, tag: str) -> list[BaseTool]:
        ids = self._tags.get(tag, [])
        return [self._tools[i] for i in ids if i in self._tools]

    def search(self, query: str) -> list[BaseTool]:
        query_lower = query.lower()
        results = []

        for tool in self._tools.values():
            score = 0
            if query_lower in tool.name.lower():
                score += 10
            if query_lower in tool.description.lower():
                score += 5
            for tag in tool.tags:
                if query_lower in tag.lower():
                    score += 3
            if query_lower in tool.category.lower():
                score += 2
            if score > 0:
                results.append((tool, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results]

    def add_alias(self, alias: str, tool_id: str) -> bool:
        if tool_id not in self._tools:
            return False
        self._aliases[alias] = tool_id
        return True

    def compose(self, name: str, tool_ids: list[str]) -> bool:
        for tid in tool_ids:
            if tid not in self._tools:
                return False
        self._compositions[name] = tool_ids
        return True

    def get_composition(self, name: str) -> list[str] | None:
        return self._compositions.get(name)

    def to_openai_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        tools = self.list_all(category)
        return [t.to_openai_schema() for t in tools]

    def to_anthropic_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        tools = self.list_all(category)
        return [t.to_anthropic_schema() for t in tools]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "tool_id": t.tool_id,
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "source_service": t.metadata.source_service,
                    "requires_auth": t.metadata.requires_auth,
                    "tags": t.tags,
                }
                for t in self._tools.values()
            ],
            "categories": self._categories,
            "tags": self._tags,
            "compositions": self._compositions,
            "total_count": len(self._tools),
        }

    async def hydrate_from_db(self, session) -> int:
        """Load all enabled tools from Postgres and populate the registry.

        Returns the number of tools hydrated.  Caller is responsible for
        committing / closing the session.

        Phase 2.1 — this becomes the canonical hydration path, replacing
        the inline loop in ``lifespan._hydrate_tools_from_db``.
        """
        import logging

        from sqlalchemy import select

        from app.models.tool_catalog_models import Tool as ToolModel

        _log = logging.getLogger(__name__)

        result = await session.execute(
            select(ToolModel).where(ToolModel.enabled.is_(True))
        )
        db_tools = result.scalars().all()

        hydrated = 0
        for row in db_tools:
            if not row.handler_ref:
                continue

            handler_cls = self._resolve_handler(row.handler_ref)
            if handler_cls is None:
                continue

            try:
                tool_instance = handler_cls()  # type: ignore[operator]
                self.register(tool_instance)
                hydrated += 1
            except Exception as exc:
                _log.warning("Failed to instantiate tool %s: %s", row.slug, exc)

        _log.info("ToolRegistry.hydrate_from_db: %d tools hydrated", hydrated)
        return hydrated

    @staticmethod
    def _resolve_handler(handler_ref: str):
        """Resolve a dotted Python path — delegates to :func:`resolve_handler_ref`."""
        return resolve_handler_ref(handler_ref)


_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def register_tool(tool: BaseTool) -> None:
    registry = get_tool_registry()
    registry.register(tool)


def is_placeholder(value: str) -> bool:
    """Detect common placeholder values in env-var config strings.

    Returns True for values like ``***REPLACE_ME***``, ``your_key_here``,
    ``CHANGE_ME``, or any string containing ``REPLACE_ME`` / ``***``.
    Used by auth-required tools to fail fast with a clear message instead
    of sending placeholder tokens to live APIs.
    """
    if not value:
        return False
    v = value.strip()
    return "***" in v or "REPLACE_ME" in v.upper() or v.lower().startswith("your_")


def resolve_handler_ref(handler_ref: str):
    """Resolve a dotted Python path to the actual class / function.

    Shared utility used by both ``ToolRegistry.hydrate_from_db`` and
    ``CapabilityRegistry.hydrate_from_db`` (Phase 2).  Also used by
    ``lifespan._resolve_handler_ref`` which delegates here for
    backwards-compatibility with existing tests.

    Example: ``'app.tools.browser_ping.BrowserPingTool'`` → class.
    Returns ``None`` on failure.
    """
    import importlib
    import logging

    _log = logging.getLogger(__name__)

    try:
        module_path, attr_name = handler_ref.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    except Exception as exc:
        _log.warning("Cannot resolve handler_ref '%s': %s", handler_ref, exc)
        return None
