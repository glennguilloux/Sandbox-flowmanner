"""Regression report API — compare a run against its template's expected behaviors (Phase 0.6).

Provides:
- GET /regression/{mission_id}/compare — structured regression report
- POST /regression/{mission_id}/freeze-baseline — extract behaviors from a successful run
- GET /regression/{mission_id}/expected-behaviors — list current assertions
- PUT /regression/{mission_id}/expected-behaviors — replace assertions
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v2.base import err, ok
from app.database import get_db
from app.models.mission_advanced_models import MissionTemplate
from app.models.mission_models import Mission
from app.services.substrate.assertion_engine import get_assertion_engine
from app.services.substrate.baseline_extractor import get_baseline_extractor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/regression", tags=["v2-regression"])


# ── Helpers ─────────────────────────────────────────────────────────


async def _get_mission_for_user(
    db: AsyncSession, user: User, mission_id: uuid.UUID
) -> Mission:
    """Get mission or raise 404."""
    result = await db.execute(
        select(Mission).where(
            Mission.id == str(mission_id),
            Mission.user_id == user.id,
            Mission.deleted_at.is_(None),
        )
    )
    mission = result.scalar_one_or_none()
    if mission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {mission_id} not found",
        )
    return mission


async def _get_template_for_mission(
    db: AsyncSession, mission: Mission
) -> MissionTemplate | None:
    """Get the template associated with a mission, if any."""
    template_id = None
    if mission.plan:
        template_id = mission.plan.get("template_id")
    if not template_id:
        return None
    result = await db.execute(
        select(MissionTemplate).where(MissionTemplate.id == str(template_id))
    )
    return result.scalar_one_or_none()


async def _get_run_id(db: AsyncSession, mission: Mission) -> str | None:
    """Get the substrate run_id for a mission."""
    if mission.plan:
        return mission.plan.get("substrate_run_id")
    return None


# ── Compare ─────────────────────────────────────────────────────────


@router.get("/{mission_id}/compare")
async def compare_mission(
    mission_id: uuid.UUID,
    run_id: str | None = Query(
        None, description="Override run_id (defaults to mission's latest)"
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare a run against its template's expected behaviors.

    Returns a structured regression report with pass/fail/warn for each
    assertion, or a "no baseline" message if no expected_behaviors exist.
    """
    mission = await _get_mission_for_user(db, user, mission_id)

    # Resolve run_id
    actual_run_id = run_id or await _get_run_id(db, mission)
    if not actual_run_id:
        return err(
            "no_substrate_run",
            "Mission has no substrate run. Execute it first.",
            status_code=400,
        )

    # Get template + expected behaviors
    template = await _get_template_for_mission(db, mission)
    expected_behaviors = []
    template_version = None
    if template:
        expected_behaviors = template.expected_behaviors or []
        template_version = str(template.id)

    if not expected_behaviors:
        return ok(
            {
                "mission_id": str(mission_id),
                "run_id": actual_run_id,
                "template_version": template_version,
                "evaluated_at": None,
                "results": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "warnings": 0},
                "message": "No baseline set. Use 'Freeze as Baseline' on a successful run first.",
            }
        )

    # Evaluate assertions
    engine = get_assertion_engine()
    results = await engine.evaluate(db, actual_run_id, expected_behaviors)

    # Build summary
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(
            1 for r in results if not r.passed and r.severity.value == "failure"
        ),
        "warnings": sum(
            1 for r in results if not r.passed and r.severity.value == "warning"
        ),
    }

    return ok(
        {
            "mission_id": str(mission_id),
            "run_id": actual_run_id,
            "template_version": template_version,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "results": [r.to_dict() for r in results],
            "summary": summary,
        }
    )


# ── Freeze Baseline ────────────────────────────────────────────────


@router.post("/{mission_id}/freeze-baseline")
async def freeze_baseline(
    mission_id: uuid.UUID,
    run_id: str | None = Query(
        None, description="Override run_id (defaults to mission's latest)"
    ),
    cost_headroom: float = Query(
        1.5, ge=1.0, le=10.0, description="Cost ceiling headroom multiplier"
    ),
    latency_headroom: float = Query(
        2.0, ge=1.0, le=10.0, description="Latency ceiling headroom multiplier"
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract expected behaviors from a successful run and save to the mission's template.

    This is the "record expected behavior" action. Run it on a known-good
    mission to establish the baseline for future regression checks.
    """
    mission = await _get_mission_for_user(db, user, mission_id)

    # Resolve run_id
    actual_run_id = run_id or await _get_run_id(db, mission)
    if not actual_run_id:
        return err(
            "no_substrate_run",
            "Mission has no substrate run. Execute it first.",
            status_code=400,
        )

    # Extract behaviors
    extractor = get_baseline_extractor()
    behaviors = await extractor.extract_from_run(
        db,
        actual_run_id,
        cost_headroom=cost_headroom,
        latency_headroom=latency_headroom,
    )

    # Save to template
    template = await _get_template_for_mission(db, mission)
    if template is None:
        return err(
            "no_template",
            "Mission has no associated template. Create the mission from a template first.",
            status_code=400,
        )

    template.expected_behaviors = behaviors
    await db.flush()

    logger.info(
        "Froze baseline for mission %s → template %s (%d behaviors)",
        mission_id,
        template.id,
        len(behaviors),
    )

    return ok(
        {
            "mission_id": str(mission_id),
            "template_id": str(template.id),
            "run_id": actual_run_id,
            "extracted": behaviors,
            "message": f"Baseline set with {len(behaviors)} assertions. Future runs will be checked against these.",
        }
    )


# ── Expected Behaviors CRUD ─────────────────────────────────────────


@router.get("/{mission_id}/expected-behaviors")
async def get_expected_behaviors(
    mission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the expected behaviors for a mission's template."""
    mission = await _get_mission_for_user(db, user, mission_id)
    template = await _get_template_for_mission(db, mission)

    if template is None:
        return ok(
            {
                "mission_id": str(mission_id),
                "template_id": None,
                "expected_behaviors": [],
                "message": "Mission has no associated template.",
            }
        )

    return ok(
        {
            "mission_id": str(mission_id),
            "template_id": str(template.id),
            "expected_behaviors": template.expected_behaviors or [],
        }
    )


@router.put("/{mission_id}/expected-behaviors")
async def update_expected_behaviors(
    mission_id: uuid.UUID,
    body: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the expected behaviors on a mission's template.

    Body: { "expected_behaviors": [...] }
    """
    mission = await _get_mission_for_user(db, user, mission_id)
    template = await _get_template_for_mission(db, mission)

    if template is None:
        return err(
            "no_template",
            "Mission has no associated template.",
            status_code=400,
        )

    behaviors = body.get("expected_behaviors", [])
    if not isinstance(behaviors, list):
        return err(
            "invalid_payload",
            "expected_behaviors must be a list of assertion objects.",
            status_code=400,
        )

    template.expected_behaviors = behaviors
    await db.flush()

    return ok(
        {
            "mission_id": str(mission_id),
            "template_id": str(template.id),
            "expected_behaviors": behaviors,
            "message": f"Updated {len(behaviors)} assertions.",
        }
    )
