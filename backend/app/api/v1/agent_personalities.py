"""
Agent Personalities API — /api/agent-personalities.

Reads agent personality definitions from the index.json file and exposes
them via REST. Supports listing all, filtering by domain, and lookup by ID.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-personalities", tags=["agent-personalities"])

# Path to the personalities index file — resolved relative to this repo root
_PERSONALITIES_DIR = Path(__file__).resolve().parent.parent.parent / "agent_definitions" / "agent_personalities"
_INDEX_PATH = _PERSONALITIES_DIR / "index.json"


def _load_index() -> dict:
    """Load the personalities index, returning empty dict on failure."""
    if not _INDEX_PATH.exists():
        logger.warning(f"Personalities index not found at {_INDEX_PATH}")
        return {"domains": {}, "agents": []}
    try:
        with open(_INDEX_PATH, "r") as f:
            return json.load(f)
    except Exception:
        logger.exception(f"Failed to load personalities index")
        return {"domains": {}, "agents": []}


def _normalize_personality(entry: dict) -> dict:
    """Ensure every personality entry has consistent fields."""
    return {
        "id": entry.get("id", ""),
        "domain": entry.get("domain", ""),
        "name": entry.get("name", ""),
        "description": entry.get("description", ""),
        "color": entry.get("color", "gray"),
    }


@router.get("")
async def list_personalities(
    domain: str | None = Query(None),
    q: str | None = Query(None, description="Search by name or description"),
):
    """List all agent personalities, optionally filtered by domain."""
    index = _load_index()
    agents: list[dict] = index.get("agents", [])

    if domain:
        agents = [a for a in agents if a.get("domain") == domain]

    if q:
        q_lower = q.lower()
        agents = [
            a
            for a in agents
            if q_lower in a.get("name", "").lower()
            or q_lower in a.get("description", "").lower()
        ]

    return [_normalize_personality(a) for a in agents]


@router.get("/domains")
async def list_domains():
    """List all personality domains with agent counts."""
    index = _load_index()
    domains_dict: dict = index.get("domains", {})
    return [
        {
            "domain": name,
            "label": name.replace("-", " ").title(),
            "count": len(agents),
        }
        for name, agents in domains_dict.items()
    ]


@router.get("/{personality_id:path}")
async def get_personality(personality_id: str):
    """Get a single personality by its full ID (e.g. 'customer-service/chat-support-agent')."""
    index = _load_index()
    agents: list[dict] = index.get("agents", [])

    for a in agents:
        if a.get("id") == personality_id:
            return _normalize_personality(a)

    raise HTTPException(status_code=404, detail=f"Personality '{personality_id}' not found")
