"""Scaffold API — proposal management for AutoMem Phase 2.

GET  /api/scaffolds/proposals                → list pending proposals
GET  /api/scaffolds/proposals/{id}            → get proposal detail
POST /api/scaffolds/proposals/{id}/approve    → apply proposal
POST /api/scaffolds/proposals/{id}/reject     → reject proposal
GET  /api/scaffolds/versions                  → list active versions
POST /api/scaffolds/versions/{id}/rollback    → rollback to version
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.scaffold_models import (
    ScaffoldProposal,
    ScaffoldProposalStatus,
    ScaffoldVersion,
)
from app.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scaffolds", tags=["scaffolds"])


# ── Request/Response models ───────────────────────────────────────────


class ApproveRequest(BaseModel):
    notes: str = ""


class RejectRequest(BaseModel):
    reason: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/proposals")
async def list_proposals(
    status: str = "pending",
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List scaffold proposals, optionally filtered by status and agent."""
    stmt = select(ScaffoldProposal).order_by(ScaffoldProposal.created_at.desc())
    if status:
        stmt = stmt.where(ScaffoldProposal.status == status)
    if agent_id:
        stmt = stmt.where(ScaffoldProposal.agent_id == agent_id)
    stmt = stmt.limit(50)

    result = await db.execute(stmt)
    proposals = result.scalars().all()

    return [_proposal_to_dict(p) for p in proposals]


@router.get("/proposals/{proposal_id}")
async def get_proposal(
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single scaffold proposal with full details."""
    proposal = (
        await db.execute(select(ScaffoldProposal).where(ScaffoldProposal.id == str(proposal_id)))
    ).scalar_one_or_none()

    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return _proposal_to_dict(proposal, include_prompt=True)


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: UUID,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve a scaffold proposal and apply it as the active version.

    Creates a new ScaffoldVersion with is_active=True, deactivates
    the previous active version, and updates the proposal status.
    """
    proposal = (
        await db.execute(select(ScaffoldProposal).where(ScaffoldProposal.id == str(proposal_id)))
    ).scalar_one_or_none()

    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status != ScaffoldProposalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is already {proposal.status}, cannot approve",
        )

    # Deactivate current active version for this agent
    await db.execute(
        update(ScaffoldVersion)
        .where(
            ScaffoldVersion.agent_id == proposal.agent_id,
            ScaffoldVersion.is_active == True,
        )
        .values(is_active=False)
    )

    # Get the latest version number for this agent
    latest = (
        await db.execute(
            select(ScaffoldVersion)
            .where(ScaffoldVersion.agent_id == proposal.agent_id)
            .order_by(ScaffoldVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    new_version = (latest.version + 1) if latest else 1

    # Create new active version
    version = ScaffoldVersion(
        agent_id=proposal.agent_id,
        version=new_version,
        prompt_text=proposal.proposed_prompt,
        is_active=True,
        source_proposal_id=proposal.id,
        parent_version_id=latest.id if latest else None,
    )
    db.add(version)
    await db.flush()

    # Update proposal status
    proposal.status = ScaffoldProposalStatus.APPLIED
    proposal.reviewed_at = datetime.now(UTC)
    proposal.reviewed_by = user.id
    proposal.applied_at = datetime.now(UTC)
    proposal.applied_version_id = version.id
    await db.commit()

    logger.info(
        "scaffold_proposal_applied",
        proposal_id=proposal.id,
        agent_id=proposal.agent_id,
        version=new_version,
        user_id=user.id,
    )

    return {
        "proposal_id": str(proposal.id),
        "status": "applied",
        "version_id": str(version.id),
        "version": new_version,
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: UUID,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Reject a scaffold proposal."""
    proposal = (
        await db.execute(select(ScaffoldProposal).where(ScaffoldProposal.id == str(proposal_id)))
    ).scalar_one_or_none()

    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status != ScaffoldProposalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is already {proposal.status}, cannot reject",
        )

    proposal.status = ScaffoldProposalStatus.REJECTED
    proposal.rejection_reason = body.reason or None
    proposal.reviewed_at = datetime.now(UTC)
    proposal.reviewed_by = user.id
    await db.commit()

    logger.info(
        "scaffold_proposal_rejected",
        proposal_id=proposal.id,
        agent_id=proposal.agent_id,
        reason=body.reason,
        user_id=user.id,
    )

    return {"proposal_id": str(proposal.id), "status": "rejected"}


@router.get("/versions")
async def list_versions(
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List scaffold versions, optionally filtered by agent."""
    stmt = select(ScaffoldVersion).order_by(ScaffoldVersion.agent_id, ScaffoldVersion.version.desc())
    if agent_id:
        stmt = stmt.where(ScaffoldVersion.agent_id == agent_id)
    stmt = stmt.limit(50)

    result = await db.execute(stmt)
    versions = result.scalars().all()

    return [
        {
            "id": str(v.id),
            "agent_id": v.agent_id,
            "version": v.version,
            "is_active": v.is_active,
            "source_proposal_id": str(v.source_proposal_id) if v.source_proposal_id else None,
            "parent_version_id": str(v.parent_version_id) if v.parent_version_id else None,
            "prompt_preview": v.prompt_text[:200] + "..." if len(v.prompt_text) > 200 else v.prompt_text,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.post("/versions/{version_id}/rollback")
async def rollback_version(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Rollback to a specific scaffold version.

    Deactivates the current active version for this agent and
    activates the specified version.
    """
    version = (
        await db.execute(select(ScaffoldVersion).where(ScaffoldVersion.id == str(version_id)))
    ).scalar_one_or_none()

    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.is_active:
        raise HTTPException(status_code=400, detail="Version is already active")

    # Deactivate current active version
    await db.execute(
        update(ScaffoldVersion)
        .where(
            ScaffoldVersion.agent_id == version.agent_id,
            ScaffoldVersion.is_active == True,
        )
        .values(is_active=False)
    )

    # Activate this version
    version.is_active = True
    await db.commit()

    logger.info(
        "scaffold_version_rollback",
        version_id=version.id,
        agent_id=version.agent_id,
        version=version.version,
        user_id=user.id,
    )

    return {
        "version_id": str(version.id),
        "agent_id": version.agent_id,
        "version": version.version,
        "status": "active",
    }


# ── Helpers ───────────────────────────────────────────────────────────


def _proposal_to_dict(p: ScaffoldProposal, *, include_prompt: bool = False) -> dict[str, Any]:
    """Convert a ScaffoldProposal to a dict."""
    d: dict[str, Any] = {
        "id": str(p.id),
        "agent_id": p.agent_id,
        "status": p.status,
        "reasoning": p.reasoning,
        "changes_summary": p.changes_summary,
        "expected_impact": p.expected_impact,
        "validation_metrics": p.validation_metrics,
        "trace_count": p.trace_count,
        "meta_model": p.meta_model,
        "current_prompt_hash": p.current_prompt_hash,
        "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        "rejection_reason": p.rejection_reason,
        "applied_at": p.applied_at.isoformat() if p.applied_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if include_prompt:
        d["proposed_prompt"] = p.proposed_prompt
    return d
