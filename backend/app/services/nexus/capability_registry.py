"""
Capability Registry - Central registry for all system capabilities

Every capability (RAG search, agent execution, workflow run, etc.)
registers here with a standardized schema.
"""

import logging
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """Represents a single system capability.

    ⚠️ H3.1 DEPRECATION: input_schema and output_schema as raw dicts are deprecated.
    Migrate to typed Pydantic `app.models.capability_models.Capability[In, Out]`
    for type-safe composition.  See the migration guide in capability_models.py.

    The dict schemas will continue to work via the PydanticAdapter bridge,
    but new capabilities should use the typed generic form.
    """

    id: str  # e.g., "tool:search_knowledge", "tool:spawn_agent"
    name: str  # Human-readable name
    description: str
    category: str  # e.g., "knowledge", "agent", "workflow", "memory"
    handler: Callable[[dict[str, Any]], Awaitable[Any]]  # Async function to execute
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    requires_auth: bool = True
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    rate_limit: int | None = None  # Requests per minute
    timeout_seconds: int = 30
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Emit deprecation warning for dict-based schemas (H3.1)."""
        if self.input_schema or self.output_schema:
            warnings.warn(
                f"Capability '{self.id}' uses dict-based input_schema/output_schema. "
                f"Migrate to typed app.models.capability_models.Capability[In, Out] "
                f"for type-safe composition (H3.1).",
                DeprecationWarning,
                stacklevel=3,
            )

    async def execute(self, params: dict[str, Any]) -> Any:
        """Execute this capability with given parameters"""
        return await self.handler(params)


class CapabilityRegistry:
    """
    Central registry where all capabilities live.

    Capabilities are registered with a standardized format:
    - id: "tool:action" format (e.g., "tool:search_knowledge")
    - handler: Async function that performs the action
    - schemas: Input/output validation schemas
    - metadata: Cost, rate limits, auth requirements
    """

    def __init__(self):
        self._capabilities: dict[str, Capability] = {}
        self._categories: dict[str, list[str]] = {}
        self._aliases: dict[str, str] = {}

    def register(self, capability: Capability) -> bool:
        """
        Register a new capability.

        Args:
            capability: The Capability to register

        Returns:
            True if registered successfully, False if ID already exists
        """
        if capability.id in self._capabilities:
            logger.warning(f"Capability {capability.id} already registered, updating")

        self._capabilities[capability.id] = capability

        # Track by category
        if capability.category not in self._categories:
            self._categories[capability.category] = []
        if capability.id not in self._categories[capability.category]:
            self._categories[capability.category].append(capability.id)

        logger.info(f"Registered capability: {capability.id} ({capability.name})")
        return True

    def unregister(self, capability_id: str) -> bool:
        """Remove a capability from the registry"""
        if capability_id not in self._capabilities:
            return False

        cap = self._capabilities.pop(capability_id)
        if cap.category in self._categories:
            self._categories[cap.category] = [
                c for c in self._categories[cap.category] if c != capability_id
            ]

        # Remove any aliases pointing to this capability
        self._aliases = {k: v for k, v in self._aliases.items() if v != capability_id}

        logger.info(f"Unregistered capability: {capability_id}")
        return True

    def get(self, capability_id: str) -> Capability | None:
        """Get a capability by ID or alias"""
        # Check for alias
        if capability_id in self._aliases:
            capability_id = self._aliases[capability_id]
        return self._capabilities.get(capability_id)

    def list_all(self, category: str | None = None) -> list[Capability]:
        """List all capabilities, optionally filtered by category"""
        if category:
            ids = self._categories.get(category, [])
            return [self._capabilities[i] for i in ids if i in self._capabilities]
        return list(self._capabilities.values())

    def list_capabilities(self, category: str | None = None) -> list[Capability]:
        return self.list_all(category)

    def list_categories(self) -> list[str]:
        """List all capability categories"""
        return list(self._categories.keys())

    def add_alias(self, alias: str, capability_id: str) -> bool:
        """Add an alias for a capability"""
        if capability_id not in self._capabilities:
            logger.warning(f"Cannot add alias: capability {capability_id} not found")
            return False
        self._aliases[alias] = capability_id
        logger.info(f"Added alias '{alias}' -> '{capability_id}'")
        return True

    def search(self, query: str) -> list[Capability]:
        """Search capabilities by name or description"""
        query_lower = query.lower()
        results = []

        for cap in self._capabilities.values():
            if (
                query_lower in cap.name.lower()
                or query_lower in cap.description.lower()
                or query_lower in cap.id.lower()
            ):
                results.append(cap)

        return results

    def get_schema(self, capability_id: str) -> dict[str, Any] | None:
        """Get the input/output schemas for a capability"""
        cap = self.get(capability_id)
        if cap:
            return {"input": cap.input_schema, "output": cap.output_schema}
        return None

    def validate_input(
        self, capability_id: str, params: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """
        Validate input parameters against the capability's schema.

        Returns:
            (is_valid, error_message)
        """
        cap = self.get(capability_id)
        if not cap:
            return False, f"Capability not found: {capability_id}"

        schema = cap.input_schema
        if not schema:
            return True, None  # No schema means no validation

        # Check required fields
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for required_field in required:
            if required_field not in params:
                return False, f"Missing required field: {required_field}"

        # Check field types (basic validation)
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        for field_name, value in params.items():
            expected_type = properties.get(field_name, {}).get("type")
            if (
                expected_type
                and expected_type in type_map
                and not isinstance(value, type_map[expected_type])
            ):
                return (
                    False,
                    f"Field {field_name} expected {expected_type}, got {type(value).__name__}",
                )

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Export registry as a dictionary for API responses"""
        return {
            "capabilities": [
                {
                    "id": cap.id,
                    "name": cap.name,
                    "description": cap.description,
                    "category": cap.category,
                    "requires_auth": cap.requires_auth,
                    "cost_estimate": cap.cost_estimate,
                }
                for cap in self._capabilities.values()
            ],
            "categories": self._categories,
            "aliases": self._aliases,
            "total_count": len(self._capabilities),
        }

    async def hydrate_from_db(self, session) -> int:
        """Load all enabled capabilities from Postgres and populate the registry.

        Returns the number of capabilities hydrated.  Caller is responsible
        for committing / closing the session.

        Phase 2.2 — canonical hydration path replacing the inline loop in
        ``lifespan._hydrate_capabilities_from_db``.
        """
        from sqlalchemy import select

        from app.models.capability_catalog_models import Capability as CapModel

        result = await session.execute(
            select(CapModel).where(CapModel.enabled.is_(True))
        )
        db_caps = result.scalars().all()

        hydrated = 0
        for row in db_caps:
            try:
                handler = None
                if row.handler_ref:
                    resolved = self._resolve_handler(row.handler_ref)
                    if resolved is not None and callable(resolved):
                        handler = resolved

                if handler is None:
                    # Fallback: create a passthrough handler
                    async def _make_handler(_row=row):
                        async def _handler(params: dict):
                            return {
                                "capability": {
                                    "id": _row.slug,
                                    "name": _row.name,
                                    "description": _row.description,
                                }
                            }

                        return _handler

                    handler = await _make_handler()

                capability = Capability(
                    id=row.slug,
                    name=row.name,
                    description=row.description or "",
                    category=row.category or "general",
                    handler=handler,
                    input_schema=row.input_schema or {},
                    output_schema=row.output_schema or {},
                    rate_limit=row.rate_limit,
                    timeout_seconds=row.timeout_seconds or 30,
                    metadata=row.metadata_ or {},
                )
                self.register(capability)
                hydrated += 1
            except Exception as exc:
                logger.warning("Failed to hydrate capability %s: %s", row.slug, exc)

        logger.info(
            "CapabilityRegistry.hydrate_from_db: %d capabilities hydrated", hydrated
        )
        return hydrated

    @staticmethod
    def _resolve_handler(handler_ref: str):
        """Resolve a dotted Python path — delegates to shared utility."""
        from app.tools.base import resolve_handler_ref

        return resolve_handler_ref(handler_ref)


# Helper function to create capabilities easily
def create_capability(
    id: str,
    name: str,
    description: str,
    category: str,
    handler: Callable[[dict[str, Any]], Awaitable[Any]],
    **kwargs,
) -> Capability:
    """Helper to create a Capability with less boilerplate"""
    return Capability(
        id=id,
        name=name,
        description=description,
        category=category,
        handler=handler,
        **kwargs,
    )


# Singleton instance
_capability_registry: Optional["CapabilityRegistry"] = None


def get_capability_registry() -> CapabilityRegistry:
    """Get or create the capability registry singleton"""
    global _capability_registry
    if _capability_registry is None:
        _capability_registry = CapabilityRegistry()
    return _capability_registry
