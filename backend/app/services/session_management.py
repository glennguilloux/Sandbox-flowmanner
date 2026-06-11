"""Session management service — device tracking, session listing, revocation."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import RefreshToken

logger = logging.getLogger(__name__)


async def get_user_sessions(db: AsyncSession, user_id: int) -> list[dict]:
    """Get all active sessions for a user with device info."""
    result = await db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        )
        .order_by(RefreshToken.created_at.desc())
    )
    tokens = result.scalars().all()

    sessions = []
    for token in tokens:
        # Check expiry
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        is_expired = expires_at < datetime.now(UTC)

        if is_expired:
            continue

        sessions.append(
            {
                "id": token.id,
                "token_prefix": (token.token[:8] + "..." if len(token.token) > 8 else token.token),
                "device_name": token.device_name or "Unknown device",
                "ip_address": token.ip_address,
                "user_agent": token.user_agent,
                "created_at": (token.created_at.isoformat() if token.created_at else None),
                "last_used_at": (token.last_used_at.isoformat() if token.last_used_at else None),
                "expires_at": (token.expires_at.isoformat() if token.expires_at else None),
            }
        )

    return sessions


async def revoke_session(db: AsyncSession, user_id: int, session_id: int) -> bool:
    """Revoke a specific session by ID. Returns True if found and revoked."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.id == session_id,
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        return False

    token.is_revoked = True
    await db.flush()
    logger.info("Session %s revoked for user %s", session_id, user_id)
    return True


async def revoke_all_other_sessions(db: AsyncSession, user_id: int, current_token: str) -> int:
    """Revoke all sessions except the current one. Returns count of revoked sessions."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
            RefreshToken.token != current_token,
        )
    )
    tokens = result.scalars().all()
    count = 0
    for token in tokens:
        token.is_revoked = True
        count += 1

    await db.flush()
    logger.info("Revoked %s other sessions for user %s", count, user_id)
    return count


async def update_session_activity(
    db: AsyncSession,
    token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Update last_used_at for a refresh token."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.is_revoked == False,
        )
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.last_used_at = datetime.now(UTC)
        if ip_address:
            rt.ip_address = ip_address
        if user_agent:
            rt.user_agent = user_agent
        await db.flush()
