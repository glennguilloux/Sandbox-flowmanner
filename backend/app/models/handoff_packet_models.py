"""Typed HandoffPacket schemas — replaces free-form context/constraints dicts.

Chunk 5 of Q2-Q3 agentic workflow plan.  The HandoffPacket is the typed
payload that travels with every handoff between agents, carrying goal,
success criteria, retrieved context IDs, tool candidates, budget state,
HITL state, and depth policy state.

All Pydantic models use frozen=True where appropriate to enforce
immutability after construction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HandoffBudget(BaseModel):
    """Budget state carried in a handoff packet."""

    model_config = ConfigDict(frozen=True)

    remaining_usd: Decimal = Field(
        ..., ge=0, description="What the receiver can still spend"
    )
    initial_usd: Decimal = Field(
        ..., gt=0, description="Total budget allocated to this handoff"
    )
    enforcer_policy: Literal["strict", "warn", "off"] = "strict"
    spent_so_far_usd: Decimal = Field(default=Decimal("0"), ge=0)


class HandoffHITLState(BaseModel):
    """Pending HITL items the receiver should be aware of (scoped to user/workspace)."""

    pending_items: list[dict] = Field(
        default_factory=list,
        description=(
            "Pending HITL items, each "
            "{id, kind, summary, awaiting_user_id, workspace_id}"
        ),
    )
    awaiting_user_id: str | None = None
    workspace_id: str | None = None


class HandoffDepthPolicyState(BaseModel):
    """Last depth decision for the receiving agent to continue with."""

    last_level: Literal["shallow", "normal", "deep"]
    last_reason: str
    policy_version: str
    decision_count: int = 0


class HandoffPacket(BaseModel):
    """Typed handoff packet — what the receiving agent needs to resume work.

    Replaces the free-form ``context: dict`` and ``constraints: dict`` on
    HandoffRecord.  All fields are required except ``depth_policy_state``
    (which is only set when chunk 4 is in use) and the optional ``metadata_``.
    """

    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    from_agent_id: str
    from_agent_name: str | None = None
    to_agent_id: str
    to_agent_name: str | None = None
    goal: str = Field(..., min_length=1, max_length=4000)
    success_criteria: list[str] = Field(..., min_length=1, max_length=20)
    retrieved_context_ids: list[str] = Field(default_factory=list, max_length=50)
    tool_candidates: list[str] = Field(default_factory=list, max_length=50)
    budget: HandoffBudget
    hitl_state: HandoffHITLState = Field(default_factory=HandoffHITLState)
    depth_policy_state: HandoffDepthPolicyState | None = None
    parent_handoff_id: str | None = None
    metadata_: dict | None = Field(default=None, alias="metadata")
