"""Skills service — Q3 dedicated skill registry.

Owns CRUD + progressive disclosure for the ``skills`` table and the
PATCH > ADD > CREATE enforcement (Q3-E). Skills are NOT personal-memory
claims and NOT ``MemoryEntry`` KV — they are a structured, versioned
registry of reusable procedural knowledge the background reviewer distills.

Progressive disclosure (Q3-D):
- ``skills_list`` returns only name + description (~small, cacheable in
  the stable tier). It never loads the heavy ``body`` column.
- ``skill_view`` loads the full body on-demand (after the cache boundary)
  so expensive bodies stay out of cached prefixes.

PATCH > ADD > CREATE (Q3-E):
- Names are class-level and stable. A body for an *existing* name is a
  PATCH (version bump) even if the reviewer said ``add``.
- A genuine CREATE is hard-guarded: a regex rejects date/task suffixes, a
  per-workspace cap bounds growth, and an optional embedding-similarity
  check (reuse the project's ``all-MiniLM-L6-v2`` 384-d vectors) blocks a
  CREATE that is ~too close to an existing skill and suggests PATCH
  instead.
"""

from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from sqlalchemy import select

from app.models.skill_models import ALL_SKILL_TRUST_TIERS, Skill

logger = logging.getLogger(__name__)

# Hard cap on skills per workspace — bounds unbounded CREATE growth.
SKILL_PER_WORKSPACE_CAP = 200

# Cosine similarity above which a CREATE is rejected in favour of PATCH.
# 0.85 is deliberately high: we only block near-duplicates, never a
# legitimately distinct skill. Documented per the Q3-E open-question default.
CREATE_SIMILARITY_THRESHOLD = 0.85

# Max normalized name length (class-level names stay short).
SKILL_NAME_MAX = 128

# Reject ephemeral, task-scoped names — skills must be durable & class-level.
_DATE_TASK_SUFFIX_RE = re.compile(
    r"(?:[-_ ]?(?:20\d{2}(?:[-.]?\d{2}){2})"  # 2026-07-10 / 2026.07.10 / 20260710
    r"|[-_ ]?(?:task|ticket|issue|pr|jira)[-_ ]?\d+)$",  # task-123 / pr_42
    re.IGNORECASE,
)


def normalize_skill_name(raw: str | None) -> str | None:
    """Normalize a raw skill name.

    Collapses whitespace, trims, lowercases for comparison stability, and
    truncates. Returns ``None`` if the name is empty or carries a
    date/task suffix (Q3-E hard guard).
    """
    if not raw or not isinstance(raw, str):
        return None
    name = re.sub(r"\s+", "_", raw.strip())
    name = name.strip("_- ")
    if not name:
        return None
    if len(name) > SKILL_NAME_MAX:
        name = name[:SKILL_NAME_MAX].rstrip("_- ")
    if _DATE_TASK_SUFFIX_RE.search(name):
        return None
    return name


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 when either is zero)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class SkillWriteDecision:
    """Outcome of evaluating a proposed skill write against the Q3-E guard.

    ``outcome`` is one of:
      - ``"patch"``   — land as a version bump on an existing skill.
      - ``"create"``  — new skill (passed all CREATE guards).
      - ``"reject"``  — blocked; ``reason`` explains why and, when the
        block was a similarity hit, ``suggested_action`` = ``"patch"``.
    """

    outcome: str
    reason: str
    skill_name: str | None
    existing_version: int | None = None
    suggested_action: str | None = None


async def evaluate_skill_write(
    *,
    raw_name: str,
    action: str,
    existing_names: list[str],
    per_workspace_count: int,
    description: str = "",
    existing_descriptions: list[str] | None = None,
    embed_fn: Callable[[list[str]], Any] | None = None,
    cap: int = SKILL_PER_WORKSPACE_CAP,
    threshold: float = CREATE_SIMILARITY_THRESHOLD,
) -> SkillWriteDecision:
    """Pure (DB-free) evaluation of a skill write against the Q3-E guard.

    ``embed_fn`` is an optional callable taking a list of texts and
    returning a list of equal-length vectors (aligned). When provided, a
    CREATE whose embedding is within ``threshold`` cosine of an existing
    skill's embedding is rejected in favour of a PATCH. When ``None``, only
    the exact-name / regex / cap guards apply (still a hard block).

    This is the unit-test seam — callers can inject a deterministic
    ``embed_fn`` without a live embedding model or Redis.
    """
    name = normalize_skill_name(raw_name)
    if name is None:
        return SkillWriteDecision(
            outcome="reject",
            reason="skill name is empty or carries a date/task suffix (Q3-E)",
            skill_name=None,
        )

    # PATCH if the class-level name already exists (regardless of the
    # reviewer's stated action — ADD on an existing name is a PATCH).
    if name in existing_names:
        return SkillWriteDecision(
            outcome="patch",
            reason="skill name already exists in workspace — applying as PATCH",
            skill_name=name,
            existing_version=None,
        )

    # CREATE path — apply hard guards.
    if per_workspace_count >= cap:
        return SkillWriteDecision(
            outcome="reject",
            reason=f"per-workspace skill cap reached ({cap})",
            skill_name=name,
        )

    if embed_fn is not None and existing_names:
        query = f"{name}. {description}".strip()
        try:
            all_texts = [query] + [
                f"{n}. {(existing_descriptions or [])[i] if existing_descriptions else ''}".strip()
                for i, n in enumerate(existing_names)
            ]
            raw_vectors = embed_fn(all_texts)
            if inspect.isawaitable(raw_vectors):
                vectors = await raw_vectors
            else:
                vectors = raw_vectors
            if vectors and len(vectors) == len(all_texts):
                q_vec = vectors[0]
                for i, n in enumerate(existing_names):
                    sim = cosine_similarity(q_vec, vectors[i + 1])
                    if sim >= threshold:
                        return SkillWriteDecision(
                            outcome="reject",
                            reason=(f"proposed skill too similar to existing '{n}' (cosine={sim:.3f} >= {threshold})"),
                            skill_name=name,
                            suggested_action="patch",
                        )
        except Exception as exc:  # best-effort: never block a write on embed failure
            logger.warning("evaluate_skill_write: embedding similarity check failed: %s", exc)

    return SkillWriteDecision(
        outcome="create",
        reason="passed all CREATE guards",
        skill_name=name,
    )


def trust_tier_for_provenance(provenance: str) -> str:
    """Map a skill's provenance to its initial trust tier (GOV-1.2).

    Human-authored skills start at ``curated`` (highest trust). Everything
    the reviewer or an external source produced starts ``unverified`` —
    they must be promoted by a human (HITL) before being trusted. This
    mirrors how ``PersonalMemoryClaim`` provenance drives the approval gate.
    """
    if provenance == "user":
        return "curated"
    if provenance in {"agent", "fetched", "tool_output", "third_party"}:
        return "unverified"
    return "unverified"


class SkillsService:
    """CRUD + progressive disclosure for the ``skills`` table.

    Async-first (``AsyncSession``). Top-level methods own their row writes
    but do NOT commit — the caller (route / background task) owns the
    transaction, per ``backend/app/services/AGENTS.md`` rule 3.
    """

    def __init__(
        self,
        db: Any,
        *,
        embed_fn: Callable[[list[str]], Any] | None = None,
    ) -> None:
        self.db = db
        self._embed_fn = embed_fn

    # ── Progressive disclosure (Q3-D) ──

    async def skills_list(
        self,
        *,
        workspace_id: str,
        user_id: int,
    ) -> list[dict[str, Any]]:
        """Return name + description only (~small, cacheable). No ``body``.

        Progressive disclosure: the expensive ``body`` column is never
        loaded here. Use ``skill_view`` to fetch a full skill on demand.
        """
        try:
            rows = (
                (
                    await self.db.execute(
                        select(Skill).where(
                            Skill.workspace_id == workspace_id,
                            Skill.user_id == user_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            out: list[dict[str, Any]] = []
            for s in rows:
                fm = s.frontmatter or {}
                out.append(
                    {
                        "name": s.name,
                        "description": fm.get("description", ""),
                        "trust_tier": s.trust_tier,
                        "version": s.version,
                        "provenance": s.provenance,
                    }
                )
            return out
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("SkillsService.skills_list failed: %s", exc)
            return []

    async def skill_view(
        self,
        *,
        workspace_id: str,
        user_id: int,
        name: str,
    ) -> dict[str, Any] | None:
        """Return a single skill's full body on demand (after cache boundary)."""
        norm = normalize_skill_name(name)
        if norm is None:
            return None
        try:
            row = (
                await self.db.execute(
                    select(Skill).where(
                        Skill.workspace_id == workspace_id,
                        Skill.user_id == user_id,
                        Skill.name == norm,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "name": row.name,
                "body": row.body,
                "frontmatter": row.frontmatter or {},
                "trust_tier": row.trust_tier,
                "version": row.version,
                "provenance": row.provenance,
                "agent_id": row.agent_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("SkillsService.skill_view failed: %s", exc)
            return None

    # ── Write path (Q3-B/C/E) ──

    async def apply_skill_write(
        self,
        *,
        workspace_id: str,
        user_id: int,
        raw_name: str,
        body: str,
        frontmatter: dict[str, Any] | None,
        provenance: str,
        agent_id: str | None,
        action: str = "add",
    ) -> str | None:
        """Apply a (already HITL-approved) skill write to the ``skills`` table.

        Enforces the Q3-E guard and GOV-1.2 trust-tier mapping. Returns the
        ``Skill.id`` on success, or ``None`` if the write was rejected or
        failed. Never raises.

        Calls ``scan_for_poison`` on the body as a governance parity check
        (Q3-B / Q3-C) — escalate-only, never blocks.
        """
        if workspace_id is None:
            logger.warning("SkillsService.apply_skill_write: workspace_id is None — refusing (isolation guardrail)")
            return None
        try:
            from app.services.memory.poison_scan import scan_for_poison

            scan = scan_for_poison(body)
            if scan.flagged:
                logger.warning(
                    "SkillsService.apply_skill_write: GOV-1.3a flagged skill=%r hits=%s severity=%s",
                    raw_name,
                    scan.hits,
                    scan.severity,
                )

            if provenance not in ALL_SKILL_TRUST_TIERS and provenance not in {
                "agent",
                "fetched",
                "tool_output",
                "third_party",
                "user",
            }:
                logger.warning(
                    "SkillsService.apply_skill_write: unknown provenance=%r; defaulting to 'agent'",
                    provenance,
                )
                provenance = "agent"

            existing = (
                (
                    await self.db.execute(
                        select(Skill).where(
                            Skill.workspace_id == workspace_id,
                            Skill.user_id == user_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            existing_names = [s.name for s in existing]
            existing_desc = [(s.frontmatter or {}).get("description", "") for s in existing]

            decision = await evaluate_skill_write(
                raw_name=raw_name,
                action=action,
                existing_names=existing_names,
                per_workspace_count=len(existing),
                description=(frontmatter or {}).get("description", ""),
                existing_descriptions=existing_desc,
                embed_fn=self._embed_fn,
            )

            if decision.outcome == "reject":
                logger.warning(
                    "SkillsService.apply_skill_write: rejected skill=%r reason=%s",
                    decision.skill_name,
                    decision.reason,
                )
                return None

            norm_name = decision.skill_name  # type: ignore[assignment]
            trust_tier = trust_tier_for_provenance(provenance)

            if decision.outcome == "patch":
                existing_row = next((s for s in existing if s.name == norm_name), None)
                if existing_row is None:
                    # Race / vanished — fall through to create.
                    pass
                else:
                    # Q3-F: retain prior body in frontmatter.history for rollback.
                    hist = list((existing_row.frontmatter or {}).get("history", []))
                    hist.append(
                        {
                            "version": existing_row.version,
                            "body": existing_row.body,
                            "provenance": existing_row.provenance,
                        }
                    )
                    new_version = existing_row.version + 1
                    existing_row.body = body
                    existing_row.frontmatter = {**(frontmatter or {}), "history": hist[-10:]}
                    existing_row.provenance = provenance
                    existing_row.trust_tier = trust_tier
                    existing_row.version = new_version
                    existing_row.agent_id = agent_id
                    await self.db.flush()
                    logger.info(
                        "SkillsService.apply_skill_write PATCHED name=%s version=%d",
                        norm_name,
                        new_version,
                    )
                    return str(existing_row.id)

            # CREATE (passed all guards).
            skill = Skill(
                name=norm_name,  # type: ignore[arg-type]
                body=body,
                frontmatter=frontmatter or {},
                trust_tier=trust_tier,
                version=1,
                provenance=provenance,
                workspace_id=workspace_id,
                user_id=user_id,
                agent_id=agent_id,
            )
            self.db.add(skill)
            await self.db.flush()
            logger.info(
                "SkillsService.apply_skill_write CREATED name=%s trust=%s",
                norm_name,
                trust_tier,
            )
            return str(skill.id)
        except Exception as exc:
            logger.warning("SkillsService.apply_skill_write failed: %s", exc)
            return None
