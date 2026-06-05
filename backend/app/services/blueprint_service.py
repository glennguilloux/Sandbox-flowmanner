"""Blueprint service — CRUD, versioning, publish lifecycle.

Follows the pattern from mission_service.py with workspace-aware access checks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select

from app.models.blueprint_models import (
    Blueprint,
    BlueprintStatus,
    BlueprintVersion,
)
from app.models.workspace_models import WorkspaceMember

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BlueprintNotFoundError(Exception):
    """Raised when a blueprint is not found or access is denied."""

    pass


class BlueprintValidationError(Exception):
    """Raised when a blueprint operation is invalid."""

    pass


class BlueprintService:
    """Blueprint CRUD + version management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Create ──────────────────────────────────────────────────────

    async def create(
        self,
        user_id: int,
        *,
        title: str,
        description: str = "",
        blueprint_type: str = "solo",
        definition: dict | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        icon: str | None = None,
        workspace_id: str | None = None,
    ) -> Blueprint:
        """Create a new blueprint and its initial version snapshot."""
        bp = Blueprint(
            id=str(uuid4()),
            user_id=user_id,
            title=title,
            description=description,
            blueprint_type=blueprint_type,
            definition=definition or {},
            input_schema=input_schema,
            output_schema=output_schema,
            tags=tags,
            category=category,
            icon=icon,
            workspace_id=workspace_id,
            status=BlueprintStatus.DRAFT.value,
            version=1,
        )
        self.db.add(bp)
        await self.db.flush()

        # Create initial version
        await self._create_version(bp, change_summary="Initial version")

        return bp

    # ── Read ────────────────────────────────────────────────────────

    async def get(self, blueprint_id: str, user_id: int) -> Blueprint:
        """Get blueprint with ownership/workspace check. Raises 404 if not found."""
        result = await self.db.execute(
            select(Blueprint).where(
                Blueprint.id == str(blueprint_id),
                Blueprint.deleted_at.is_(None),
            )
        )
        bp = result.scalar_one_or_none()
        if bp is None:
            raise BlueprintNotFoundError(f"Blueprint {blueprint_id} not found")

        # Access check: owner or workspace member
        await self._check_access(bp, user_id)
        return bp

    async def list(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        workspace_id: str | None = None,
        blueprint_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Blueprint], int]:
        """List blueprints with filtering and pagination."""
        stmt = select(Blueprint).where(Blueprint.deleted_at.is_(None))

        # Access filtering
        if workspace_id is not None:
            stmt = stmt.where(Blueprint.workspace_id == workspace_id)
        else:
            stmt = stmt.where(Blueprint.user_id == user_id)

        if blueprint_type is not None:
            stmt = stmt.where(Blueprint.blueprint_type == blueprint_type)
        if status is not None:
            stmt = stmt.where(Blueprint.status == status)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Paginate
        offset = (page - 1) * per_page
        stmt = stmt.order_by(Blueprint.created_at.desc()).offset(offset).limit(per_page)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # ── Update ──────────────────────────────────────────────────────

    async def update(
        self, blueprint_id: str, user_id: int, **kwargs
    ) -> Blueprint:
        """Update blueprint. If definition changed, creates a new version."""
        bp = await self.get(blueprint_id, user_id)

        definition_changed = False
        for key, value in kwargs.items():
            if value is not None and hasattr(bp, key):
                if key == "definition" and value != bp.definition:
                    definition_changed = True
                setattr(bp, key, value)

        if definition_changed:
            bp.version = (bp.version or 1) + 1
            await self._create_version(bp, change_summary="Definition updated")

        bp.updated_at = datetime.now(UTC)
        await self.db.flush()
        return bp

    # ── Delete (soft) ───────────────────────────────────────────────

    async def delete(self, blueprint_id: str, user_id: int) -> bool:
        """Soft delete blueprint (sets deleted_at + deleted_by)."""
        bp = await self.get(blueprint_id, user_id)
        bp.deleted_at = datetime.now(UTC)
        bp.deleted_by = user_id
        await self.db.flush()
        return True

    # ── Publish ─────────────────────────────────────────────────────

    async def publish(self, blueprint_id: str, user_id: int) -> Blueprint:
        """Publish a draft blueprint."""
        bp = await self.get(blueprint_id, user_id)
        if bp.status != BlueprintStatus.DRAFT.value:
            raise BlueprintValidationError(
                f"Cannot publish blueprint in '{bp.status}' status. Only draft blueprints can be published."
            )
        bp.status = BlueprintStatus.PUBLISHED.value
        bp.updated_at = datetime.now(UTC)
        await self.db.flush()
        return bp

    # ── Version history ─────────────────────────────────────────────

    async def get_versions(self, blueprint_id: str, user_id: int) -> list[BlueprintVersion]:
        """Get version history for a blueprint."""
        await self.get(blueprint_id, user_id)  # ownership check
        result = await self.db.execute(
            select(BlueprintVersion)
            .where(BlueprintVersion.blueprint_id == str(blueprint_id))
            .order_by(BlueprintVersion.version.desc())
        )
        return list(result.scalars().all())

    async def get_by_source_mission_id(
        self, mission_id: str, user_id: int
    ) -> Blueprint | None:
        """Lookup blueprint by source_mission_id in metadata (used during dual-write)."""
        result = await self.db.execute(
            select(Blueprint).where(
                Blueprint.deleted_at.is_(None),
                Blueprint.user_id == user_id,
            )
        )
        for bp in result.scalars().all():
            meta = bp.definition.get("config", {}) if bp.definition else {}
            if meta.get("source_mission_id") == str(mission_id):
                return bp
        return None

    # ── Internal helpers ────────────────────────────────────────────

    async def _create_version(
        self, bp: Blueprint, change_summary: str | None = None
    ) -> BlueprintVersion:
        """Snapshot current definition as a new version."""
        version = BlueprintVersion(
            id=str(uuid4()),
            blueprint_id=str(bp.id),
            version=bp.version or 1,
            snapshot={
                "blueprint_type": bp.blueprint_type,
                "title": bp.title,
                "description": bp.description,
                **(bp.definition or {}),
            },
            description=change_summary,
            created_by=bp.user_id,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    async def _check_access(self, bp: Blueprint, user_id: int) -> None:
        """Check if user has access to the blueprint (owner or workspace member)."""
        if bp.user_id == user_id:
            return

        if bp.workspace_id:
            result = await self.db.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == bp.workspace_id,
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.is_active == True,
                )
            )
            if result.scalar_one_or_none() is not None:
                return

        raise BlueprintNotFoundError(f"Blueprint {bp.id} not found")
