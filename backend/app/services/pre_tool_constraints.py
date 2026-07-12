"""Pre-tool constraint enforcement (Epic 4.1b).

Loads the user's standing ``constraint`` claims (negative / prohibition
memory — "never run rm -rf on prod", "always require approval before
dropping a table") and decides whether a given tool call conflicts.

This is the *enforcement* half of Epic 4.1. Epic 4.1a added the
``constraint`` claim type to the model/schema/migration; Epic 4.2 added
the don't-over-learn-from-failures guardrail to the reviewer prompt.
This module is the runtime gate that turns stored constraints into a
hard stop or a human-approval escalation at tool dispatch.

Design invariants:

* **Fail-open.** If the memory lookup raises (DB down, cycle, missing
  table), we log and ALLOW the tool call. Constraints are an
  additive safety net, never a hard dependency of the execution path —
  a constraint store outage must never brick tool dispatch.

* **DESIGN DECISION: the gate is FAIL-OPEN.** If the constraint store is
  unavailable, ALL tool calls are ALLOWED — including payment/send
  categories. This is deliberate: bricking tool dispatch on a store blip
  is worse than a brief allow-all window. The threat-model implication
  (a constraint-store DoS/partition widens permissions to allow-all) is
  accepted. A memory-store-independent static deny-list for payment/send
  tools is a *future* hardening and is NOT implemented here.
* **Workspace-scoped.** Constraints are loaded by
  ``(user_id, workspace_id)``; the service never crosses a workspace
  boundary. The substrate ``Workflow.user_id`` is a UUID *string* while
  ``personal_memory_claims.user_id`` is an *int*, so we resolve
  best-effort (see ``resolve_user_id``) and still key on ``workspace_id``.
* **Deterministic verdict.** ``evaluate(tool_name)`` returns a
  ``ConstraintVerdict`` with one of three decisions: ``allow``,
  ``block`` (hard stop), or ``escalate`` (raise a HITL approval
  interrupt). The caller decides what to do with it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.personal_memory_models import PersonalMemoryClaim

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Default action when a constraint's ``object`` omits the field. Hard
# blocks are dangerous (they can halt a workflow), so the safe default
# is to ESCALATE to a human rather than silently forbidding the call.
DEFAULT_CONSTRAINT_ACTION = "escalate"

# Verdict decision values.
ALLOW = "allow"
BLOCK = "block"
ESCALATE = "escalate"


@dataclass
class ConstraintVerdict:
    """Outcome of evaluating a tool call against the user's constraints."""

    decision: str  # ALLOW | BLOCK | ESCALATE
    reason: str
    # The constraint claim that triggered a non-allow verdict (None on allow).
    triggered_claim_id: str | None = None
    # Human-readable subject of the triggered constraint (for the interrupt).
    constraint_subject: str | None = None

    @property
    def blocked(self) -> bool:
        return self.decision == BLOCK

    @property
    def requires_approval(self) -> bool:
        return self.decision == ESCALATE


@dataclass
class _Constraint:
    """A parsed standing constraint claim."""

    claim_id: str
    subject: str
    action: str  # block | escalate
    target_tools: set[str]
    reason: str


class PreToolConstraints:
    """Evaluate pending tool calls against a user's standing constraints."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._cache: list[_Constraint] | None = None

    @staticmethod
    def resolve_user_id(workflow_user_id: str | int | None) -> int | None:
        """Best-effort resolution of the *int* user_id the memory table uses.

        The substrate ``Workflow.user_id`` is a UUID string; the personal
        memory table keys on an integer ``users.id``. We can't reliably
        map a UUID to an int without a lookup, so we accept a real int as-is
        and return ``None`` for anything else — callers then key on
        ``workspace_id`` alone (constraints authored by anyone in the
        workspace still apply to the run).
        """
        if workflow_user_id is None:
            return None
        if isinstance(workflow_user_id, int):
            return workflow_user_id
        # Numeric string (e.g. "123") — coerce.
        if isinstance(workflow_user_id, str) and workflow_user_id.isdigit():
            return int(workflow_user_id)
        return None

    async def _load(self, user_id: int | None, workspace_id: str) -> list[_Constraint]:
        """Load + parse the user's active ``constraint`` claims.

        Fail-open: any exception returns an empty list (no constraints →
        everything allowed). The DB query is scoped to
        ``(user_id, workspace_id)`` when we have an int user_id; when we
        only have a workspace, we still scope by workspace (a workspace-
        level standing constraint applies to every run in that workspace).
        """
        if self._cache is not None:
            return self._cache
        try:
            stmt = select(PersonalMemoryClaim).where(
                PersonalMemoryClaim.claim_type == "constraint",
                PersonalMemoryClaim.workspace_id == workspace_id,
                PersonalMemoryClaim.deleted_at.is_(None),
            )
            if user_id is not None:
                stmt = stmt.where(PersonalMemoryClaim.user_id == user_id)
            result = await self._db.execute(stmt)
            rows = result.scalars().all()
            parsed: list[_Constraint] = [self._parse(row) for row in rows]
            self._cache = parsed
            return parsed
        except Exception as exc:  # fail-open by design
            logger.warning(
                "PreToolConstraints: constraint load failed (fail-open), allowing tool call. workspace=%s error=%s",
                workspace_id,
                exc,
            )
            self._cache = []
            return self._cache

    @staticmethod
    def _parse(row: PersonalMemoryClaim) -> _Constraint:
        """Parse a constraint claim row into a structured constraint.

        ``object`` shape (convention):
            {
              "target_tools": ["code_executor", "shell"],  # tools this
                                                            # constraint governs
              "action": "block" | "escalate",              # optional; defaults
                                                            # to escalate
              "reason": "..."                              # optional free text
            }
        If ``target_tools`` is absent/empty, the constraint is treated as
        governing ALL tools (a blanket standing prohibition).
        """
        obj = row.object if isinstance(row.object, dict) else {}
        target_tools_raw = obj.get("target_tools")
        if isinstance(target_tools_raw, list | tuple | set):
            target_tools = {str(t).lower() for t in target_tools_raw}
        else:
            target_tools = set()  # empty ⇒ governs every tool
        action = str(obj.get("action", DEFAULT_CONSTRAINT_ACTION)).lower()
        if action not in (BLOCK, ESCALATE):
            action = DEFAULT_CONSTRAINT_ACTION
        return _Constraint(
            claim_id=str(row.id),
            subject=row.subject,
            action=action,
            target_tools=target_tools,
            reason=str(obj.get("reason", "") or ""),
        )

    async def evaluate(
        self,
        tool_name: str,
        *,
        user_id: int | None,
        workspace_id: str,
    ) -> ConstraintVerdict:
        """Decide whether ``tool_name`` may run given the user's constraints.

        Args:
            tool_name: The tool about to be invoked.
            user_id: Resolved integer user id (may be None → workspace-scoped).
            workspace_id: Workspace the run belongs to (always required).

        Returns:
            ``ConstraintVerdict`` — ``allow`` unless a constraint matches.
        """
        if not workspace_id:
            # No workspace to scope by — cannot enforce; fail-open.
            return ConstraintVerdict(ALLOW, "no workspace_id; fail-open")

        constraints = await self._load(user_id, workspace_id)
        if not constraints:
            return ConstraintVerdict(ALLOW, "no active constraints")

        tool = tool_name.lower()
        for c in constraints:
            governs = (not c.target_tools) or (tool in c.target_tools)
            if not governs:
                continue
            if c.action == BLOCK:
                return ConstraintVerdict(
                    decision=BLOCK,
                    reason=(f"Blocked by standing constraint '{c.subject}'" + (f": {c.reason}" if c.reason else "")),
                    triggered_claim_id=c.claim_id,
                    constraint_subject=c.subject,
                )
            # escalate → human approval (default)
            return ConstraintVerdict(
                decision=ESCALATE,
                reason=(
                    f"Requires approval per standing constraint '{c.subject}'" + (f": {c.reason}" if c.reason else "")
                ),
                triggered_claim_id=c.claim_id,
                constraint_subject=c.subject,
            )
        return ConstraintVerdict(ALLOW, "no matching constraint")
