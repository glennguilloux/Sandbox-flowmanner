"""Shared versioning utility — Phase 3.1 Entity Versioning.

Provides a generic ``create_version_snapshot()`` function that any service
can call to persist an immutable version snapshot of an entity.

The pattern is identical across all versioned entities:
1. Read current entity state → serialize to JSONB snapshot
2. Increment the entity's ``version`` column
3. Insert a row into the ``*_versions`` table
4. Return the new version number

This module is the single code path for version creation.  Direct
INSERT into ``*_versions`` tables is discouraged — use this utility.
"""

from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Entity → (model_class, version_model_class, pk_field, snapshot_fn) ──

def _snapshot_agent(agent) -> dict:
    """Serialize an Agent to a JSONB-safe dict."""
    return {
        "id": agent.id,
        "name": agent.name,
        "owner_id": agent.owner_id,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "model_preference": agent.model_preference,
        "config": agent.config,
        "state": agent.state,
    }


def _snapshot_workspace(ws) -> dict:
    """Serialize a Workspace to a JSONB-safe dict."""
    return {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "owner_id": ws.owner_id,
        "plan": ws.plan,
        "is_active": ws.is_active,
        "logo_url": ws.logo_url,
        "settings": ws.settings,
        "member_limit": ws.member_limit,
        "subscription_tier_id": ws.subscription_tier_id,
    }


def _snapshot_mission(mission) -> dict:
    """Serialize a Mission to a JSONB-safe dict."""
    return {
        "id": str(mission.id),
        "user_id": mission.user_id,
        "title": mission.title,
        "description": mission.description,
        "mission_type": mission.mission_type,
        "context_files": mission.context_files,
        "context_urls": mission.context_urls,
        "constraints": mission.constraints,
        "plan": mission.plan,
        "status": mission.status if isinstance(mission.status, str) else mission.status.value,
        "priority": mission.priority,
        "fallback_strategy": mission.fallback_strategy,
        "parent_mission_id": str(mission.parent_mission_id) if mission.parent_mission_id else None,
    }


# Registry: entity_type → (snapshot_fn, version_model_import_path, parent_fk_col)
_ENTITY_REGISTRY: dict[str, tuple] = {
    "agent": (
        _snapshot_agent,
        "app.models.agent.AgentVersion",
        "agent_id",
    ),
    "workspace": (
        _snapshot_workspace,
        "app.models.workspace_models.WorkspaceVersion",
        "workspace_id",
    ),
    "mission": (
        _snapshot_mission,
        "app.models.mission_advanced_models.MissionVersion",
        "mission_id",
    ),
}


async def create_version_snapshot(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    *,
    change_summary: str | None = None,
) -> int:
    """Create an immutable version snapshot of an entity.

    Args:
        db: Async database session (caller is responsible for commit).
        entity_type: One of 'agent', 'workspace', 'mission'.
        entity: The ORM object to snapshot.
        change_summary: Optional human-readable description of what changed.

    Returns:
        The new version number.

    Raises:
        ValueError: If entity_type is unknown.
    """
    if entity_type not in _ENTITY_REGISTRY:
        raise ValueError(
            f"Unknown entity_type '{entity_type}'. "
            f"Supported: {list(_ENTITY_REGISTRY.keys())}"
        )

    snapshot_fn, version_model_path, parent_fk_col = _ENTITY_REGISTRY[entity_type]

    # 1. Increment version on the entity
    old_version = entity.version if entity.version is not None else 0
    new_version = old_version + 1
    entity.version = new_version

    # 2. Build the snapshot
    snapshot = snapshot_fn(entity)
    snapshot["snapshot_version"] = new_version
    snapshot["snapshot_at"] = datetime.now(UTC).isoformat()

    # 3. Import the version model class
    module_path, class_name = version_model_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    VersionModel = getattr(module, class_name)

    # 4. Create the version row
    # MissionVersion uses individual columns instead of a single JSONB snapshot
    if entity_type == "mission":
        version_row = VersionModel(
            id=str(uuid4()),
            **{parent_fk_col: entity.id},
            version=new_version,
            title=snapshot.get("title"),
            description=snapshot.get("description"),
            mission_type=snapshot.get("mission_type"),
            priority=snapshot.get("priority"),
            plan=snapshot.get("plan"),
            constraints=snapshot.get("constraints"),
            change_summary=change_summary,
        )
    else:
        version_row = VersionModel(
            id=str(uuid4()),
            **{parent_fk_col: entity.id},
            version=new_version,
            snapshot=snapshot,
            change_summary=change_summary,
        )
    db.add(version_row)

    logger.debug(
        "Created %s version %d for %s %s",
        entity_type, new_version, entity_type, entity.id,
    )
    return new_version


async def get_version_history(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Retrieve version history for an entity.

    Args:
        db: Async database session.
        entity_type: One of 'agent', 'workspace', 'mission'.
        entity_id: The entity's primary key.
        limit: Max versions to return.
        offset: Pagination offset.

    Returns:
        List of version dicts with id, version, change_summary, created_at.
    """
    if entity_type not in _ENTITY_REGISTRY:
        raise ValueError(f"Unknown entity_type '{entity_type}'")

    _, version_model_path, parent_fk_col = _ENTITY_REGISTRY[entity_type]

    module_path, class_name = version_model_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    VersionModel = getattr(module, class_name)

    fk_col = getattr(VersionModel, parent_fk_col)
    stmt = (
        select(VersionModel)
        .where(fk_col == entity_id)
        .order_by(VersionModel.version.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "id": row.id,
            "version": row.version,
            "change_summary": row.change_summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def get_version_snapshot(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    version_number: int,
) -> dict | None:
    """Retrieve a specific version snapshot.

    Args:
        db: Async database session.
        entity_type: One of 'agent', 'workspace', 'mission'.
        entity_id: The entity's primary key.
        version_number: The version to retrieve.

    Returns:
        The snapshot dict, or None if not found.
    """
    if entity_type not in _ENTITY_REGISTRY:
        raise ValueError(f"Unknown entity_type '{entity_type}'")

    _, version_model_path, parent_fk_col = _ENTITY_REGISTRY[entity_type]

    module_path, class_name = version_model_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    VersionModel = getattr(module, class_name)

    fk_col = getattr(VersionModel, parent_fk_col)
    stmt = (
        select(VersionModel)
        .where(fk_col == entity_id, VersionModel.version == version_number)
    )
    result = await db.execute(stmt)
    row = result.scalars().first()

    if row is None:
        return None

    # MissionVersion has a @property that synthesizes snapshot from individual columns
    return {
        "id": row.id,
        "version": row.version,
        "snapshot": row.snapshot,
        "change_summary": row.change_summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
