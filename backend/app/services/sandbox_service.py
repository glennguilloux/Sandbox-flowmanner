"""Sandbox Service — orchestrates sandboxd lifecycle scoped to missions.

Sandbox lifecycle (create → stop → purge) maps to the mission lifecycle.
One sandbox per mission, stored in the ``mission_sandboxes`` table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.integrations.sandboxd_client import SandboxdClient, get_sandboxd_client
from app.models.playground_models import PlaygroundSandbox, PlaygroundSandboxStatus
from app.models.sandbox_models import MissionSandbox

logger = logging.getLogger(__name__)


class SandboxService:
    """Orchestrates sandboxd lifecycle scoped to missions."""

    def __init__(self, client: SandboxdClient | None = None) -> None:
        self._client = client or get_sandboxd_client()

    # ── Core lifecycle ─────────────────────────────────────────────────

    async def ensure_sandbox_for_mission(
        self,
        mission_id: str,
        user_id: str,
        *,
        db,
        template: str | None = None,
    ) -> str:
        """Get or create sandbox. Returns sandbox_id.

        Idempotent: if sandbox already exists for this mission, returns it.
        Stores mapping in mission_sandboxes table.
        """
        # 1. Check for existing mapping
        existing = await self.get_sandbox_for_mission(mission_id, db=db)
        if existing:
            logger.info(
                "Sandbox %s already exists for mission %s", existing, mission_id
            )
            return existing

        # 2. Create sandbox via sandboxd
        project_id = f"mission_{mission_id}"
        tmpl = template or settings.SANDBOXD_DEFAULT_TEMPLATE

        logger.info(
            "Creating sandbox for mission %s (project=%s, template=%s)",
            mission_id,
            project_id,
            tmpl,
        )

        resp = await self._client.create(
            project_id=project_id,
            user_id=user_id,
            template=tmpl,
        )
        sandbox_id = resp["id"]

        # 3. Store mapping
        row = MissionSandbox(
            mission_id=mission_id,
            sandbox_id=sandbox_id,
            project_id=project_id,
            status=resp.get("status", "creating"),
        )
        db.add(row)
        await db.commit()

        logger.info("Sandbox %s created for mission %s", sandbox_id, mission_id)
        return sandbox_id

    async def reap_sandbox(self, mission_id: str, *, db) -> None:
        """Soft-stop sandbox (preserve workspace for potential reuse).

        Called on mission terminal transition (completed/failed/aborted).
        """
        sandbox_id = await self.get_sandbox_for_mission(mission_id, db=db)
        if not sandbox_id:
            logger.debug("No sandbox for mission %s — noop", mission_id)
            return

        try:
            result = await self._client.stop(sandbox_id)
            new_status = result.get("status", "stopped")

            # Update row
            stmt = select(MissionSandbox).where(MissionSandbox.sandbox_id == sandbox_id)
            row_result = await db.execute(stmt)
            row = row_result.scalars().first()
            if row:
                row.status = new_status
                row.stopped_at = datetime.now(UTC)
                await db.commit()

            logger.info("Sandbox %s stopped for mission %s", sandbox_id, mission_id)
        except Exception:
            logger.exception(
                "Failed to stop sandbox %s for mission %s",
                sandbox_id,
                mission_id,
            )

    async def purge_sandbox(self, mission_id: str, *, db) -> None:
        """Full destroy (DELETE /v1/sandboxes/{id}).

        Called on explicit cleanup or after a TTL expires.
        """
        sandbox_id = await self.get_sandbox_for_mission(mission_id, db=db)
        if not sandbox_id:
            logger.debug("No sandbox for mission %s — noop", mission_id)
            return

        try:
            await self._client.delete(sandbox_id)

            # Update row
            stmt = select(MissionSandbox).where(MissionSandbox.sandbox_id == sandbox_id)
            row_result = await db.execute(stmt)
            row = row_result.scalars().first()
            if row:
                row.status = "purged"
                row.purged_at = datetime.now(UTC)
                await db.commit()

            logger.info("Sandbox %s purged for mission %s", sandbox_id, mission_id)
        except Exception:
            logger.exception(
                "Failed to purge sandbox %s for mission %s",
                sandbox_id,
                mission_id,
            )

    # ── Lookup ─────────────────────────────────────────────────────────

    async def get_sandbox_for_mission(self, mission_id: str, *, db) -> str | None:
        """Look up sandbox_id from mission_sandboxes table."""
        stmt = select(MissionSandbox).where(
            MissionSandbox.mission_id == mission_id,
            MissionSandbox.status.notin_(["purged"]),
        )
        result = await db.execute(stmt)
        row = result.scalars().first()
        return row.sandbox_id if row else None

    # ── Snapshots ──────────────────────────────────────────────────────

    async def create_snapshot(
        self, mission_id: str, name: str = "", *, db
    ) -> dict[str, Any]:
        """Create a snapshot of the sandbox workspace."""
        sandbox_id = await self.get_sandbox_for_mission(mission_id, db=db)
        if not sandbox_id:
            raise ValueError(f"No sandbox for mission {mission_id}")
        return await self._client.create_snapshot(sandbox_id, name)

    async def restore_snapshot(self, mission_id: str, snapshot_id: str, *, db) -> None:
        """Restore sandbox to a previous snapshot."""
        sandbox_id = await self.get_sandbox_for_mission(mission_id, db=db)
        if not sandbox_id:
            raise ValueError(f"No sandbox for mission {mission_id}")
        await self._client.restore_snapshot(sandbox_id, snapshot_id)

    # ── Workspace-scoped sandboxes (Phase 4) ─────────────────────────

    async def create_workspace_sandbox(
        self,
        workspace_id: str,
        user_id: str,
        *,
        db,
        template: str = "react-standard",
    ) -> str:
        """Create a persistent sandbox for a team workspace."""
        import secrets
        from datetime import timedelta

        result = await self._client.create(
            project_id=f"ws-{workspace_id[:12]}",
            user_id=user_id,
            template=template,
        )
        sandbox_id = result["id"]

        now = datetime.now(UTC)
        pg = PlaygroundSandbox(
            sandbox_id=sandbox_id,
            session_token=f"ws-{secrets.token_urlsafe(32)}",
            user_id=int(user_id),
            workspace_id=workspace_id,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=30),  # Long-lived for workspaces
            status=PlaygroundSandboxStatus.RUNNING.value,
            template=template,
            is_persistent=True,
            last_active_at=now,
        )
        db.add(pg)
        await db.commit()
        return sandbox_id

    async def get_workspace_sandboxes(
        self,
        workspace_id: str,
        *,
        db,
    ) -> list[dict]:
        """List all sandboxes in a workspace."""
        result = await db.execute(
            select(PlaygroundSandbox).where(
                PlaygroundSandbox.workspace_id == workspace_id,
                PlaygroundSandbox.status != PlaygroundSandboxStatus.PURGED.value,
            )
        )
        sandboxes = result.scalars().all()
        return [
            {
                "sandbox_id": s.sandbox_id,
                "status": s.status,
                "template": s.template,
                "created_at": s.created_at.isoformat(),
                "last_active_at": (
                    s.last_active_at.isoformat() if s.last_active_at else None
                ),
            }
            for s in sandboxes
        ]

    async def wake_workspace_sandbox(
        self,
        sandbox_id: str,
        *,
        db,
    ) -> None:
        """Wake up an idle workspace sandbox."""
        result = await db.execute(
            select(PlaygroundSandbox).where(
                PlaygroundSandbox.sandbox_id == sandbox_id,
            )
        )
        pg = result.scalar_one_or_none()
        if pg:
            pg.last_active_at = datetime.now(UTC)
            pg.status = PlaygroundSandboxStatus.RUNNING.value
            pg.updated_at = datetime.now(UTC)
            await db.commit()

    # ── Health ─────────────────────────────────────────────────────────

    async def is_sandboxd_healthy(self) -> bool:
        """Check if sandboxd is reachable."""
        try:
            await self._client.health_check()
            return True
        except Exception:
            return False
