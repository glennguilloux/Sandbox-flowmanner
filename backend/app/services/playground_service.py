"""Playground sandbox service — manages anonymous, claimable sandbox lifecycle."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.integrations.sandboxd_client import SandboxdClient, get_sandboxd_client
from app.models.playground_models import PlaygroundSandbox, PlaygroundSandboxStatus

logger = logging.getLogger(__name__)

# Anonymous sandbox TTL: 30 minutes
ANONYMOUS_TTL_MINUTES = 30
# Claimed sandbox TTL: 24 hours (or until explicitly purged)
CLAIMED_TTL_HOURS = 24
# Cooldown between anonymous sandbox creates (per IP): 60 seconds
ANONYMOUS_CREATE_COOLDOWN_SECONDS = 60


class PlaygroundService:
    """Manages playground sandbox lifecycle independent of missions."""

    def __init__(self, client: SandboxdClient | None = None) -> None:
        self._client = client or get_sandboxd_client()

    # ── Create ──────────────────────────────────────────────────────

    async def create_anonymous_sandbox(
        self,
        *,
        db,
        template: str = "react-standard",
        client_ip: str | None = None,
    ) -> PlaygroundSandbox:
        """Create an anonymous sandbox with a 30-minute TTL."""
        session_token = secrets.token_urlsafe(48)

        # Create the sandboxd container (no user_id — anonymous)
        result = await self._client.create(
            project_id=f"playground-{session_token[:12]}",
            user_id="anonymous",
            template=template,
        )
        sandbox_id = result["id"]
        project_id = result.get("project_id")

        now = datetime.now(UTC)
        pg_sandbox = PlaygroundSandbox(
            sandbox_id=sandbox_id,
            session_token=session_token,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=ANONYMOUS_TTL_MINUTES),
            status=PlaygroundSandboxStatus.RUNNING.value,
            template=template,
            project_id=project_id,
            anonymous_ip=client_ip,
        )
        db.add(pg_sandbox)
        await db.commit()
        await db.refresh(pg_sandbox)

        return pg_sandbox

    # ── Get ─────────────────────────────────────────────────────────

    async def get_by_session_token(
        self,
        session_token: str,
        *,
        db,
    ) -> PlaygroundSandbox | None:
        """Look up a playground sandbox by its anonymous session token."""
        result = await db.execute(
            select(PlaygroundSandbox).where(
                PlaygroundSandbox.session_token == session_token,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_sandbox_id(
        self,
        sandbox_id: str,
        *,
        db,
    ) -> PlaygroundSandbox | None:
        """Look up a playground sandbox by the sandboxd container ID."""
        result = await db.execute(
            select(PlaygroundSandbox).where(
                PlaygroundSandbox.sandbox_id == sandbox_id,
            )
        )
        return result.scalar_one_or_none()

    # ── Claim ───────────────────────────────────────────────────────

    async def claim_sandbox(
        self,
        session_token: str,
        user_id: int | str,
        *,
        db,
    ) -> PlaygroundSandbox:
        """Transfer an anonymous sandbox to an authenticated user."""
        pg = await self.get_by_session_token(session_token, db=db)
        if pg is None:
            raise ValueError("Sandbox not found")
        if pg.status == PlaygroundSandboxStatus.PURGED.value:
            raise ValueError("Sandbox has been purged")
        if pg.user_id is not None:
            raise ValueError("Sandbox is already claimed")

        pg.user_id = int(user_id)
        pg.claimed_at = datetime.now(UTC)
        pg.expires_at = datetime.now(UTC) + timedelta(hours=CLAIMED_TTL_HOURS)
        pg.status = PlaygroundSandboxStatus.CLAIMED.value
        pg.is_persistent = True
        pg.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(pg)
        return pg

    # ── Cleanup ─────────────────────────────────────────────────────

    async def purge_sandbox(
        self,
        sandbox_id: str,
        *,
        db,
    ) -> None:
        """Hard-delete a playground sandbox and the sandboxd container."""
        pg = await self.get_by_sandbox_id(sandbox_id, db=db)
        if pg is None:
            return

        try:
            await self._client.delete(pg.sandbox_id)
        except Exception:
            logger.warning("Failed to delete sandboxd container %s", pg.sandbox_id)

        pg.status = PlaygroundSandboxStatus.PURGED.value
        pg.updated_at = datetime.now(UTC)
        await db.commit()

    async def purge_expired(self, *, db) -> int:
        """Purge all playground sandboxes past their TTL. Returns count purged."""
        now = datetime.now(UTC)
        result = await db.execute(
            select(PlaygroundSandbox).where(
                PlaygroundSandbox.expires_at < now,
                PlaygroundSandbox.status.in_(
                    [
                        PlaygroundSandboxStatus.RUNNING.value,
                        PlaygroundSandboxStatus.CREATING.value,
                        PlaygroundSandboxStatus.CLAIMED.value,
                    ]
                ),
            )
        )
        expired = result.scalars().all()
        count = 0
        for pg in expired:
            await self.purge_sandbox(pg.sandbox_id, db=db)
            count += 1
        return count

    # ── Rate-limit check ────────────────────────────────────────────

    async def count_recent_by_ip(
        self,
        ip: str,
        minutes: int = 60,
        *,
        db,
    ) -> int:
        """Count anonymous sandboxes created by an IP in the last N minutes."""
        since = datetime.now(UTC) - timedelta(minutes=minutes)
        result = await db.execute(
            select(PlaygroundSandbox).where(
                PlaygroundSandbox.anonymous_ip == ip,
                PlaygroundSandbox.created_at >= since,
            )
        )
        return len(result.scalars().all())

    # ── File browser ────────────────────────────────────────────────

    async def list_files(
        self,
        sandbox_id: str,
        path: str = "",
        *,
        db,
    ) -> list[dict]:
        """List files in a sandbox workspace directory."""
        pg = await self.get_by_sandbox_id(sandbox_id, db=db)
        if pg is None:
            raise ValueError("Sandbox not found")
        return await self._client.list_files(pg.sandbox_id, path=path)

    async def read_file(
        self,
        sandbox_id: str,
        path: str,
        *,
        db,
    ) -> str:
        """Read a file from a sandbox workspace."""
        pg = await self.get_by_sandbox_id(sandbox_id, db=db)
        if pg is None:
            raise ValueError("Sandbox not found")
        return await self._client.read_file(pg.sandbox_id, path=path)

    async def write_file(
        self,
        sandbox_id: str,
        path: str,
        content: bytes,
        *,
        db,
    ) -> dict:
        """Write a file to a sandbox workspace."""
        pg = await self.get_by_sandbox_id(sandbox_id, db=db)
        if pg is None:
            raise ValueError("Sandbox not found")
        return await self._client.write_file(pg.sandbox_id, path=path, content=content)

    # ── Health ──────────────────────────────────────────────────────

    async def is_sandboxd_healthy(self) -> bool:
        try:
            await self._client.health_check()
            return True
        except Exception:
            return False
