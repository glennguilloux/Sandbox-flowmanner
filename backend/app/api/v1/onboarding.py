"""Onboarding state management — per-user, DB-backed."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_current_user
from app.database import AsyncSessionLocal

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ONBOARDING_STEPS = [
    {"id": "welcome", "title": "Welcome", "required": True},
    {"id": "create_mission", "title": "Create a Mission", "required": True},
    {"id": "add_byok", "title": "Add an API Key", "required": False},
    {"id": "run_mission", "title": "Run Your Mission", "required": True},
    {"id": "explore", "title": "Explore Features", "required": False},
]


async def _get_or_create_state(user_id: int) -> dict:
    """Get existing onboarding state or create a default one."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "SELECT id, user_id, current_step, milestones, is_completed, completed_at FROM onboarding_state WHERE user_id = :uid"
            ),
            {"uid": user_id},
        )
        row = result.mappings().first()

        if row:
            return dict(row)

        # Create default state
        now = datetime.now(UTC)
        result = await db.execute(
            text(
                """
                INSERT INTO onboarding_state (user_id, current_step, milestones, is_completed, created_at, updated_at)
                VALUES (:uid, 'welcome', '{}', false, :now, :now)
                RETURNING id, user_id, current_step, milestones, is_completed, completed_at
            """
            ),
            {"uid": user_id, "now": now},
        )
        await db.commit()
        return dict(result.mappings().first())


@router.get("/status")
async def get_status(user=Depends(get_current_user)):
    """Get current user's onboarding state."""
    state = await _get_or_create_state(user.id)
    step_ids = [s["id"] for s in ONBOARDING_STEPS]
    current_idx = step_ids.index(state["current_step"]) if state["current_step"] in step_ids else 0

    return {
        "currentStep": state["current_step"],
        "currentStepIndex": current_idx,
        "isCompleted": state["is_completed"],
        "completedAt": (state["completed_at"].isoformat() if state["completed_at"] else None),
        "milestones": state["milestones"],
        "steps": ONBOARDING_STEPS,
    }


class StepUpdate(BaseModel):
    step: str


@router.put("/step")
async def advance_step(update: StepUpdate, user=Depends(get_current_user)):
    """Advance to a specific onboarding step."""
    valid_ids = {s["id"] for s in ONBOARDING_STEPS}
    if update.step not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Invalid step: {update.step}. Valid: {valid_ids}")

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE onboarding_state SET current_step = :step, updated_at = :now WHERE user_id = :uid"),
            {"step": update.step, "now": now, "uid": user.id},
        )
        await db.commit()

    return {"success": True, "currentStep": update.step}


@router.post("/complete")
async def complete_onboarding(user=Depends(get_current_user)):
    """Mark onboarding as completed."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "UPDATE onboarding_state SET is_completed = true, completed_at = :now, updated_at = :now WHERE user_id = :uid"
            ),
            {"now": now, "uid": user.id},
        )
        await db.commit()

    return {"success": True, "isCompleted": True}


@router.post("/skip")
async def skip_onboarding(user=Depends(get_current_user)):
    """Skip onboarding entirely."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO onboarding_state (user_id, current_step, is_completed, completed_at, created_at, updated_at)
                VALUES (:uid, 'skipped', true, :now, :now, :now)
                ON CONFLICT (user_id) DO UPDATE SET current_step = 'skipped', is_completed = true, completed_at = :now, updated_at = :now
            """
            ),
            {"uid": user.id, "now": now},
        )
        await db.commit()

    return {"success": True, "isCompleted": True, "currentStep": "skipped"}


@router.get("/steps")
async def get_steps():
    """Return static step definitions."""
    return {"steps": ONBOARDING_STEPS}


@router.post("/sample-data")
async def generate_sample_data(user=Depends(get_current_user)):
    """Generate sample missions for new users using built-in templates."""
    import json
    import uuid
    from datetime import datetime as dt

    now = dt.now(UTC)
    missions_created = 0

    # Sample missions to create — pre-completed so dashboard has data
    sample_missions = [
        {
            "title": "Sample: Deep Research",
            "description": "A sample research mission demonstrating multi-step AI analysis. This mission was pre-completed to show you how Flowmanner works.",
            "mission_type": "research",
            "results": {
                "summary": "Research completed successfully. Key findings include improved workflow efficiency through AI-assisted task decomposition and parallel execution.",
                "tasks_completed": 4,
                "total_tokens": 2450,
            },
        },
        {
            "title": "Sample: Content Creation",
            "description": "A sample content creation mission showing how Flowmanner can generate and refine written content using AI agents.",
            "mission_type": "content",
            "results": {
                "summary": "Content generated and reviewed. The AI pipeline produced a draft, refined it for clarity, and delivered a polished final version.",
                "tasks_completed": 3,
                "total_tokens": 1800,
            },
        },
    ]

    async with AsyncSessionLocal() as db:
        for mission_data in sample_missions:
            mission_id = str(uuid.uuid4())
            await db.execute(
                text(
                    """
                    INSERT INTO missions (id, user_id, title, description, mission_type, status, results, tokens_used, started_at, completed_at, created_at, updated_at)
                    VALUES (:id, :uid, :title, :desc, :type, 'completed', :results, :tokens, :now, :now, :now, :now)
                """
                ),
                {
                    "id": mission_id,
                    "uid": user.id,
                    "title": mission_data["title"],
                    "desc": mission_data["description"],
                    "type": mission_data["mission_type"],
                    "results": json.dumps(mission_data["results"]),
                    "tokens": mission_data["results"]["total_tokens"],
                    "now": now,
                },
            )
            missions_created += 1

        await db.commit()

    return {
        "success": True,
        "message": f"Created {missions_created} sample missions",
        "items_created": {
            "missions": missions_created,
            "graphs": 0,
            "chat_threads": 0,
        },
    }
