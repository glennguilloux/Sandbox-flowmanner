"""Episodic Memory API — Q2-Q3 Chunk 2.

Provides:
- POST /episodes/retrieve — hybrid BM25+vector retrieval, returns max 5
- GET /missions/{mission_id}/episodes — list episodes that influenced a mission
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.database import get_db
from app.services.episodic_memory_service import (
    EpisodicMemoryService,
    get_episodic_memory_service,
)

router = APIRouter(tags=["episodic-memory"])


# ── Request / Response models ─────────────────────────────────────


class RetrieveRequest(BaseModel):
    """Request body for POST /episodes/retrieve."""

    query: str = Field(..., min_length=1, max_length=2000, description="Search query text")
    workspace_id: str = Field(..., description="Workspace UUID to scope results")
    k: int = Field(default=5, ge=1, le=5, description="Max results (hard cap: 5)")


class EpisodeResponse(BaseModel):
    """Single episode in a response."""

    id: str
    mission_id: str | None = None
    step_type: str | None = None
    outcome: str | None = None
    cost_bucket: str | None = None
    hitl_outcome: str | None = None
    retrieval_text: str | None = None
    combined_score: float | None = None
    created_at: str | None = None


class RetrieveResponse(BaseModel):
    """Response for POST /episodes/retrieve."""

    episodes: list[EpisodeResponse]
    count: int
    capped: bool = Field(description="True if results were capped at k=5")


class MissionEpisodesResponse(BaseModel):
    """Response for GET /missions/{mission_id}/episodes."""

    episodes: list[EpisodeResponse]
    count: int


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/episodes/retrieve", response_model=RetrieveResponse)
async def retrieve_episodes(
    body: RetrieveRequest,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
    service: EpisodicMemoryService | None = Depends(get_episodic_memory_service),
) -> RetrieveResponse:
    """Retrieve the most relevant prior episodes for a query.

    Uses hybrid BM25 + vector search with a hard cap of 5 results.
    All results are scoped to the requesting user's workspace.
    """
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Cross-mission memory is disabled (FLOWMANNER_CROSS_MISSION_MEMORY=off)",
        )

    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    results = await service.retrieve_relevant(
        db,
        query_text=body.query,
        workspace_id=body.workspace_id,
        user_id=user_id,
        k=body.k,
    )

    # Record which episodes were retrieved in the event log (best-effort)
    episode_ids = [r.get("id") for r in results if r.get("id")]
    if episode_ids:
        with contextlib.suppress(Exception):
            await service.mark_used(db, episode_ids=episode_ids, mission_id="retrieve_query")

    episodes = [
        EpisodeResponse(
            id=r.get("id", ""),
            mission_id=r.get("mission_id"),
            step_type=r.get("step_type"),
            outcome=r.get("outcome"),
            cost_bucket=r.get("cost_bucket"),
            hitl_outcome=r.get("hitl_outcome"),
            retrieval_text=r.get("retrieval_text"),
            combined_score=r.get("combined_score"),
            created_at=r.get("created_at"),
        )
        for r in results
    ]

    return RetrieveResponse(
        episodes=episodes,
        count=len(episodes),
        capped=len(episodes) >= body.k,
    )


@router.get("/missions/{mission_id}/episodes", response_model=MissionEpisodesResponse)
async def get_mission_episodes(
    mission_id: str,
    workspace_id: str,
    db: Any = Depends(get_db),
    current_user: Any = Depends(get_current_user),
    service: EpisodicMemoryService | None = Depends(get_episodic_memory_service),
) -> MissionEpisodesResponse:
    """List episodes that influenced a specific mission.

    Returns all episode records associated with the given mission,
    scoped to the requesting user's workspace.
    """
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Cross-mission memory is disabled (FLOWMANNER_CROSS_MISSION_MEMORY=off)",
        )

    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    results = await service.get_episodes_for_mission(
        db,
        mission_id=mission_id,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    episodes = [
        EpisodeResponse(
            id=r.get("id", ""),
            mission_id=r.get("mission_id"),
            step_type=r.get("step_type"),
            outcome=r.get("outcome"),
            cost_bucket=r.get("cost_bucket"),
            hitl_outcome=r.get("hitl_outcome"),
            retrieval_text=r.get("retrieval_text"),
            created_at=r.get("created_at"),
        )
        for r in results
    ]

    return MissionEpisodesResponse(
        episodes=episodes,
        count=len(episodes),
    )
