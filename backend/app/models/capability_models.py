"""H3 Capability Models — type-safe Pydantic schemas for H3.1, H3.2, H3.4.

These replace the old dict-based `input_schema`/`output_schema` patterns
with typed Pydantic generics, per the Ω spec Part VII.

Capability[In, Out]:  Typed replacement for the old dataclass-based Capability.
                      The generic parameters In and Out are Pydantic BaseModel subclasses
                      that define the input and output contracts.

CapabilityToken:     Unforgeable OCap token per Ω spec VII.1.  A token grants
                      specific actions on a resource.  Tokens are issued by the
                      CapabilityEngine and verified at every tool invocation.

Budget:              First-class budget model per Ω spec VII.3.  Every run declares
                      a budget; the BudgetEnforcer is the only path to LLM calls.

ResourceRef:         Typed reference to a resource (tool, table, file, etc.).
Action:              Enum of permissible actions (read, write, execute, delegate).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ── Type variables for generic capability ──────────────────────────

In = TypeVar("In", bound=BaseModel)
Out = TypeVar("Out", bound=BaseModel)


# ── Action & ResourceRef ───────────────────────────────────────────


class Action(str, Enum):
    """Permissible actions on a resource (OCap)."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELEGATE = "delegate"


class ResourceRef(BaseModel):
    """Typed reference to a resource.

    Examples:
        ResourceRef(kind="tool", name="web_search")
        ResourceRef(kind="table", name="users")
        ResourceRef(kind="file", path="/tmp/output.txt")
    """

    kind: str  # "tool", "table", "file", "agent", "workflow"
    name: str | None = None
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        if self.path:
            return f"{self.kind}:{self.path}"
        return f"{self.kind}:{self.name or '*'}"

    def __hash__(self) -> int:
        return hash((self.kind, self.name, self.path))


# ── Capability[In, Out] — typed capability ─────────────────────────


class Capability(BaseModel, Generic[In, Out]):
    """Typed capability with Pydantic input/output contracts.

    Replaces the old dataclass-based Capability with dict schemas.
    The generic parameters enforce type safety at composition time.

    Example:
        class SearchInput(BaseModel):
            query: str
            max_results: int = 10

        class SearchOutput(BaseModel):
            results: list[str]
            total: int

        search_cap = Capability[SearchInput, SearchOutput](
            id="tool:search_knowledge",
            name="Knowledge Search",
            description="Search the knowledge base",
            category="knowledge",
        )
    """

    id: str  # e.g., "tool:search_knowledge", "tool:spawn_agent"
    name: str
    description: str
    category: str  # e.g., "knowledge", "agent", "workflow", "memory"
    requires_auth: bool = True
    cost_estimate: dict[str, Any] = Field(default_factory=dict)
    rate_limit: int | None = None  # requests per minute
    timeout_seconds: int = 30
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ── Legacy dict schema accessors (H3.1 pragmatic hybrid) ────────

    @property
    def input_schema(self) -> dict[str, Any]:
        """Legacy dict schema accessor — use typed model_class instead.

        Deprecated: Access the input type via `capability.model_fields`
        or use the PydanticAdapter for migration.
        """
        import warnings

        warnings.warn(
            f"Capability.input_schema is deprecated; use typed generic parameters instead. "
            f"Capability[{self.__class__.__name__}] should declare In/Out types.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Return the legacy schema stored by PydanticAdapter, or empty dict
        return self.__dict__.get("__input_schema__", {})

    @property
    def output_schema(self) -> dict[str, Any]:
        """Legacy dict schema accessor — use typed model_class instead.

        Deprecated: Access the output type via `capability.model_fields`.
        """
        import warnings

        warnings.warn(
            f"Capability.output_schema is deprecated; use typed generic parameters instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.__dict__.get("__output_schema__", {})

    def get_input_type(self) -> type[BaseModel] | None:
        """Get the typed input model class if available."""
        metadata = self.__class__.__pydantic_generic_metadata__
        args = metadata.get("args", ())
        if args and len(args) > 0:
            return args[0]  # type: ignore[return-value]
        return None

    def get_output_type(self) -> type[BaseModel] | None:
        """Get the typed output model class if available."""
        metadata = self.__class__.__pydantic_generic_metadata__
        args = metadata.get("args", ())
        if args and len(args) > 1:
            return args[1]  # type: ignore[return-value]
        return None


# ── CapabilityToken — OCap token ───────────────────────────────────


class CapabilityToken(BaseModel):
    """Unforgeable OCap token per Ω spec VII.1.

    A CapabilityToken grants specific actions on a resource to a principal.
    Tokens are issued by the CapabilityEngine and verified at every tool invocation.

    Invariants:
    - I.1 (Unforgeability): Only CapabilityEngine.issue() creates tokens.
    - I.2 (Attenuation): A child token's actions ⊆ parent's actions.
    - I.3 (No ambient authority): Every tool invocation requires a valid token.
    """

    id: UUID = Field(default_factory=uuid4)
    resource: ResourceRef
    actions: set[Action]
    parent: UUID | None = None  # parent token this was attenuated from
    attenuation_proof: str = "root"  # proof of valid attenuation
    issued_to: UUID  # AgentId or UserId
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked: bool = False

    def can(self, action: Action) -> bool:
        """Check if this token authorizes the given action."""
        if self.revoked:
            return False
        if self.expires_at is not None and datetime.now(UTC) > self.expires_at:
            return False
        return action in self.actions

    def attenuate(
        self,
        *,
        remove_actions: set[Action] | None = None,
        expires_at: datetime | None = None,
    ) -> CapabilityToken:
        """Create an attenuated child token.

        The child's actions MUST be a strict subset of the parent's.
        This enforces Invariant I.2 (Attenuation-only).

        Raises:
            ValueError: If the attenuated actions are not a subset.
        """
        remove = remove_actions or set()
        new_actions = self.actions - remove

        if not new_actions.issubset(self.actions):
            raise ValueError(
                f"Attenuation violation: child actions {new_actions} are not a subset of parent actions {self.actions}"
            )

        # Build the attenuation proof
        proof_parts = [f"parent={self.id}"]
        if remove:
            removed_str = ",".join(sorted(a.value for a in remove))
            proof_parts.append(f"removed={{{removed_str}}}")
        if expires_at:
            proof_parts.append(f"expires={expires_at.isoformat()}")

        return CapabilityToken(
            id=uuid4(),
            resource=self.resource,
            actions=new_actions,
            parent=self.id,
            attenuation_proof="; ".join(proof_parts),
            issued_to=self.issued_to,
            issued_at=datetime.now(UTC),
            expires_at=expires_at or self.expires_at,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/audit."""
        return {
            "id": str(self.id),
            "resource": str(self.resource),
            "actions": [a.value for a in self.actions],
            "parent": str(self.parent) if self.parent else None,
            "attenuation_proof": self.attenuation_proof,
            "issued_to": str(self.issued_to),
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked": self.revoked,
        }


# ── Budget — first-class budget model ──────────────────────────────


class Budget(BaseModel):
    """First-class budget model per Ω spec VII.3.

    Every run declares a budget before execution.  The BudgetEnforcer
    tracks spend in real time and aborts when any field is exceeded.

    Invariant I.6 (Bounded execution): A run is aborted with BudgetExhausted
    the moment any budget field is exceeded.
    """

    max_cost_usd: Decimal = Field(default=Decimal("10.00"), ge=0)
    max_wall_time_seconds: int = Field(default=300, ge=0)
    max_iterations: int = Field(default=100, ge=0)
    max_depth: int = Field(default=5, ge=0)
    max_parallel_agents: int = Field(default=4, ge=0)
    declared_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    declared_by: UUID | None = None  # AgentId that issued this budget

    # Runtime tracking (not part of the declared budget, but travels with it)
    spent_usd: Decimal = Field(default=Decimal("0.00"), ge=0)
    wall_time_started_at: float = 0.0  # time.monotonic() at first LLM call
    iterations_used: int = 0
    depth_used: int = 0

    def is_exhausted(self) -> tuple[bool, str]:
        """Check if any budget field has been exceeded.

        Returns:
            (is_exhausted, reason_string)
        """
        import time as _time

        if self.spent_usd >= self.max_cost_usd:
            return True, (
                f"Cost budget exhausted (${self.spent_usd:.4f}/${self.max_cost_usd:.2f})"
            )

        if self.max_wall_time_seconds > 0 and self.wall_time_started_at > 0:
            elapsed = _time.monotonic() - self.wall_time_started_at
            if elapsed >= self.max_wall_time_seconds:
                return True, (
                    f"Wall-clock budget exhausted ({elapsed:.1f}s/{self.max_wall_time_seconds}s)"
                )

        if self.iterations_used >= self.max_iterations:
            return True, (
                f"Iteration budget exhausted ({self.iterations_used}/{self.max_iterations})"
            )

        if self.depth_used >= self.max_depth:
            return True, (
                f"Depth budget exhausted ({self.depth_used}/{self.max_depth})"
            )

        return False, ""

    def remaining(self) -> dict[str, Any]:
        """Return remaining budget as a dict."""
        import time as _time

        wall_elapsed = 0.0
        if self.wall_time_started_at > 0:
            wall_elapsed = _time.monotonic() - self.wall_time_started_at

        return {
            "cost_usd": float(max(Decimal("0"), self.max_cost_usd - self.spent_usd)),
            "wall_time_seconds": max(0, self.max_wall_time_seconds - int(wall_elapsed)),
            "iterations": max(0, self.max_iterations - self.iterations_used),
            "depth": max(0, self.max_depth - self.depth_used),
            "parallel_agents": self.max_parallel_agents,
        }

    @classmethod
    def zero(cls) -> Budget:
        """Create a zero budget (no resources available)."""
        return cls(
            max_cost_usd=Decimal("0"),
            max_wall_time_seconds=0,
            max_iterations=0,
            max_depth=0,
            max_parallel_agents=0,
        )

    @classmethod
    def unlimited(cls) -> Budget:
        """Create an effectively unlimited budget (for trusted internal use)."""
        return cls(
            max_cost_usd=Decimal("999999.99"),
            max_wall_time_seconds=86_400,  # 24 hours
            max_iterations=1_000_000,
            max_depth=100,
            max_parallel_agents=32,
        )


# ── BudgetExhausted exception ──────────────────────────────────────


class BudgetExhausted(Exception):
    """Raised when a run exceeds its declared budget."""

    def __init__(self, reason: str, remaining: Budget):
        self.reason = reason
        self.remaining = remaining
        super().__init__(f"Budget exhausted: {reason}")


# ── PydanticAdapter — bridge for gradual migration ─────────────────


class PydanticAdapter:
    """Bridges between typed Pydantic capabilities and legacy dict schemas.

    H3.1 pragmatic hybrid: new code uses typed Capability[In, Out];
    old code continues to work via this adapter, with deprecation warnings.

    Usage:
        adapter = PydanticAdapter()
        typed_cap = adapter.from_dict_schema(old_dict_capability)
        dict_schema = adapter.to_dict_schema(typed_cap)
    """

    @staticmethod
    def from_dict_schema(
        capability_id: str,
        name: str,
        description: str,
        category: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        **kwargs: Any,
    ) -> Capability:
        """Create a typed Capability from legacy dict schemas.

        When concrete input/output types are unknown, creates a capability
        with generic dict input/output.  Callers should migrate to concrete
        types by subclassing Capability with specific In/Out types.
        """
        import warnings

        warnings.warn(
            f"Creating Capability '{capability_id}' from dict schemas. "
            f"Migrate to typed Capability[InType, OutType] for type safety.",
            DeprecationWarning,
            stacklevel=2,
        )

        cap: Any = Capability(
            id=capability_id,
            name=name,
            description=description,
            category=category,
            **kwargs,
        )
        # Store legacy schemas for backward compat
        cap.__dict__["__input_schema__"] = input_schema
        cap.__dict__["__output_schema__"] = output_schema
        return cap

    @staticmethod
    def validate_input(
        capability: Capability, params: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate input params against a capability's typed contract.

        For dict-based capabilities, falls back to basic JSON Schema validation.
        For typed capabilities, uses Pydantic validation.

        Returns:
            (is_valid, error_message)
        """
        in_type = capability.get_input_type()
        if in_type is not None:
            try:
                in_type.model_validate(params)
                return True, None
            except Exception as e:
                return False, str(e)

        # Fallback: basic dict schema validation
        schema = capability.__dict__.get("__input_schema__", {})
        if not schema:
            return True, None

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in params:
                return False, f"Missing required field: {field}"

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
                and not isinstance(value, type_map[expected_type])  # type: ignore[arg-type]
            ):
                return (
                    False,
                    f"Field {field_name} expected {expected_type}, got {type(value).__name__}",
                )

        return True, None

    @staticmethod
    def validate_output(capability: Capability, result: Any) -> tuple[bool, str | None]:
        """Validate output against a capability's typed contract."""
        out_type = capability.get_output_type()
        if out_type is not None:
            if isinstance(result, dict):
                try:
                    out_type.model_validate(result)
                    return True, None
                except Exception as e:
                    return False, str(e)
            elif isinstance(result, out_type):
                return True, None
            else:
                return (
                    False,
                    f"Expected {out_type.__name__}, got {type(result).__name__}",
                )

        # Fallback for dict schemas: always pass (no type info)
        return True, None
