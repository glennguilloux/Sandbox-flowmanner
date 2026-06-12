"""Depth policy models — adaptive reasoning depth decisions (Q2-Q3 Chunk 4).

Pydantic models for the deterministic depth policy that decides
shallow / normal / deep reasoning per step based on risk, uncertainty,
budget, and prior failures.
"""

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class DepthLevel(str, Enum):
    """Reasoning depth levels."""

    SHALLOW = "shallow"  # 0 reflection iterations (direct act)
    NORMAL = "normal"  # 1 reflection iteration
    DEEP = "deep"  # 3 reflection iterations (full loop)


class DepthDecision(BaseModel):
    """Result of a depth policy decision for a single step.

    Contains the chosen depth level, human-readable reason,
    HITL escalation flags, and the policy version that produced it.
    """

    level: DepthLevel = Field(..., description="Chosen reasoning depth")
    reason: str = Field(..., description="Human-readable explanation of why this level was chosen")
    escalate_to_hitl: bool = Field(default=False, description="Whether this step should escalate to HITL")
    hitl_reason: str | None = Field(default=None, description="Reason for HITL escalation, if any")
    policy_version: str = Field(default="v1.0.0", description="Version of the policy that made this decision")

    # Token cost projections (informational)
    estimated_reflection_iterations: int = Field(
        default=0,
        description="Number of reflection iterations this depth level maps to",
    )


class DepthTriggeredEvent(BaseModel):
    """Audit event payload emitted to the substrate event log.

    Uses field-level data only — no raw task text or tool input.
    """

    level: str
    reason: str
    risk: str
    uncertainty: float
    budget_remaining_usd: float
    prior_failures: int
    retry_count: int
    escalate_to_hitl: bool
    hitl_reason: str | None
    policy_version: str
    step_id: str | None = None
    mission_id: str | None = None
    workspace_id: str | None = None
    user_id: int | None = None
    estimated_reflection_iterations: int = 0
