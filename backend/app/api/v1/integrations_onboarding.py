"""Integration Onboarding API — Phase 6: TTFC Optimization.

Provides pre-built workflow templates that use integrations out of the box,
reducing Time to First Connection from ~15-30 min to <5 min.

Endpoints:
    GET /api/integrations/onboarding/templates
        List available template workflows, optionally filtered by integration slugs.

    POST /api/integrations/onboarding/create-from-template
        Create a mission from a template workflow definition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.mission_models import Mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/integrations/onboarding",
    tags=["integrations-onboarding"],
)


# ── Template Workflow Definitions ────────────────────────────────────────────
# Pre-built templates that use integrations out of the box.
# Each template defines a complete mission with tasks that leverage
# connected integrations.

TEMPLATE_WORKFLOWS: list[dict] = [
    {
        "id": "star-your-repos",
        "name": "Star Your Repos",
        "description": "Automatically star repositories in a GitHub organization. Great for keeping track of active projects.",
        "icon": "⭐",
        "required_integrations": ["github"],
        "category": "development",
        "difficulty": "beginner",
        "estimated_time": "2 min",
        "default_mission": {
            "title": "Star repos in organization",
            "description": "Browse repositories in a GitHub organization and star the most relevant ones based on activity and relevance.",
            "mission_type": "automation",
            "priority": "medium",
        },
        "steps": [
            {
                "order": 1,
                "title": "List organization repositories",
                "description": "Fetch all repositories from the connected GitHub organization.",
            },
            {
                "order": 2,
                "title": "Evaluate repository activity",
                "description": "Score repos by recent commits, open issues, and contributor count.",
            },
            {
                "order": 3,
                "title": "Star top repositories",
                "description": "Star the top-scoring repositories automatically.",
            },
        ],
    },
    {
        "id": "slack-daily-digest",
        "name": "Slack Daily Digest",
        "description": "Post a daily summary of pull request activity to a Slack channel. Never miss a PR review again.",
        "icon": "📊",
        "required_integrations": ["slack", "github"],
        "category": "communication",
        "difficulty": "beginner",
        "estimated_time": "3 min",
        "default_mission": {
            "title": "Daily PR digest to Slack",
            "description": "Gather pull request activity from GitHub and post a formatted daily summary to a Slack channel.",
            "mission_type": "automation",
            "priority": "medium",
        },
        "steps": [
            {
                "order": 1,
                "title": "Fetch PR activity",
                "description": "Pull recent pull request events (opened, merged, reviewed) from GitHub.",
            },
            {
                "order": 2,
                "title": "Format digest",
                "description": "Summarize PR activity into a readable Slack message with status indicators.",
            },
            {
                "order": 3,
                "title": "Post to Slack",
                "description": "Send the formatted digest to the configured Slack channel.",
            },
        ],
    },
    {
        "id": "notion-meeting-notes",
        "name": "Notion Meeting Notes",
        "description": "Create a Notion page from a Google Calendar event. Automatically populate attendee list and agenda.",
        "icon": "📝",
        "required_integrations": ["notion", "google"],
        "category": "productivity",
        "difficulty": "intermediate",
        "estimated_time": "4 min",
        "default_mission": {
            "title": "Create meeting notes page",
            "description": "When a Google Calendar event starts, create a structured Notion page with attendees, agenda, and action items section.",
            "mission_type": "automation",
            "priority": "medium",
        },
        "steps": [
            {
                "order": 1,
                "title": "Read calendar event",
                "description": "Fetch upcoming Google Calendar event details including attendees and description.",
            },
            {
                "order": 2,
                "title": "Create Notion page",
                "description": "Create a new page in the designated Notion database with event metadata.",
            },
            {
                "order": 3,
                "title": "Populate template",
                "description": "Fill in the meeting notes template with attendees, agenda items, and empty action items.",
            },
        ],
    },
    {
        "id": "error-alert-to-slack",
        "name": "Error Alert to Slack",
        "description": "Get instant Slack notifications when CI/CD runs fail on GitHub. Catch failures before they block your team.",
        "icon": "🚨",
        "required_integrations": ["github", "slack"],
        "category": "development",
        "difficulty": "beginner",
        "estimated_time": "2 min",
        "default_mission": {
            "title": "CI failure alerts to Slack",
            "description": "Monitor GitHub Actions workflow runs and send immediate Slack alerts when builds or tests fail.",
            "mission_type": "automation",
            "priority": "high",
        },
        "steps": [
            {
                "order": 1,
                "title": "Monitor workflow runs",
                "description": "Watch for GitHub Actions workflow completion events.",
            },
            {
                "order": 2,
                "title": "Filter failures",
                "description": "Identify workflow runs that ended with a failure or cancelled status.",
            },
            {
                "order": 3,
                "title": "Alert Slack channel",
                "description": "Post an alert message with failure details, commit info, and a link to the failed run.",
            },
        ],
    },
]


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class TemplateWorkflowStep(BaseModel):
    order: int
    title: str
    description: str


class TemplateWorkflow(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    required_integrations: list[str]
    category: str
    difficulty: str
    estimated_time: str
    steps: list[TemplateWorkflowStep]


class TemplateListResponse(BaseModel):
    templates: list[TemplateWorkflow]
    total: int


class CreateFromTemplateRequest(BaseModel):
    template_id: str


class CreateFromTemplateResponse(BaseModel):
    mission_id: str
    title: str
    status: str
    template_id: str


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/templates", response_model=TemplateListResponse)
async def list_onboarding_templates(
    integrations: str | None = Query(
        None,
        description="Comma-separated list of connected integration slugs to filter by.",
    ),
    user: User = Depends(get_current_user),
):
    """List available integration onboarding template workflows.

    When ``integrations`` is provided, only templates whose required
    integrations are a subset of the connected set are returned.
    This powers the "filtered by your tools" step in the onboarding wizard.
    """
    templates = TEMPLATE_WORKFLOWS

    if integrations:
        connected = {s.strip() for s in integrations.split(",") if s.strip()}
        templates = [t for t in TEMPLATE_WORKFLOWS if set(t["required_integrations"]).issubset(connected)]

    return TemplateListResponse(
        templates=[TemplateWorkflow(**t) for t in templates],
        total=len(templates),
    )


@router.post("/create-from-template", response_model=CreateFromTemplateResponse)
async def create_mission_from_template(
    payload: CreateFromTemplateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a mission from a template workflow definition.

    Looks up the template by ID, instantiates a new Mission with the
    template's default configuration, and returns the created mission.
    """
    # Find template
    template = next(
        (t for t in TEMPLATE_WORKFLOWS if t["id"] == payload.template_id),
        None,
    )
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{payload.template_id}' not found.",
        )

    mission_data = template["default_mission"]

    # Create the mission
    mission = Mission(
        user_id=user.id,
        title=mission_data["title"],
        description=mission_data["description"],
        mission_type=mission_data.get("mission_type", "automation"),
        priority=mission_data.get("priority", "medium"),
        status="pending",
        constraints={
            "template_id": template["id"],
            "required_integrations": template["required_integrations"],
            "steps": template["steps"],
        },
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)

    logger.info(
        "Mission created from onboarding template",
        mission_id=str(mission.id),
        template_id=template["id"],
        user_id=user.id,
    )

    return CreateFromTemplateResponse(
        mission_id=str(mission.id),
        title=mission.title,
        status=mission.status,
        template_id=template["id"],
    )
