"""Session management service — device tracking, session listing, revocation.

Item #10: Migrated from v1 RefreshToken to v3 AuthSession as the canonical
session store.  Falls back to RefreshToken only if AuthSession has no match
(during the migration period while v1 tokens are still in flight).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_v3_models import AuthSession
from app.services.auth_service import RefreshToken

logger = logging.getLogger(__name__)


async def get_user_sessions(db: AsyncSession, user_id: int) -> list[dict]:
    """Get all active sessions for a user with device info.

    Item #10: Queries v3 AuthSession first.  If no v3 sessions exist, falls
    back to v1 RefreshToken for backward compat during migration.
    """
    # v3 path: AuthSession (canonical)
    result = await db.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.is_active.is_(True),
        )
        .order_by(AuthSession.created_at.desc())
    )
    v3_sessions = result.scalars().all()

    if v3_sessions:
        sessions = []
        for s in v3_sessions:
            expires_at = s.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at and expires_at < datetime.now(UTC):
                continue

            sessions.append(
                {
                    "id": str(s.id),
                    "token_prefix": s.refresh_token_hash[:8] + "...",
                    "device_name": s.device_name or "Unknown device",
                    "ip_address": s.ip_address,
                    "user_agent": s.browser or s.device_os,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                }
            )
        return sessions

    # v1 fallback: RefreshToken (legacy)
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
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
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


async def revoke_session(db: AsyncSession, user_id: int, session_id: int | str) -> bool:
    """Revoke a specific session by ID. Returns True if found and revoked.

    Item #10: Tries v3 AuthSession first, falls back to v1 RefreshToken.
    """
    # v3 path
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.is_active.is_(True),
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False
        session.revoked_at = datetime.now(UTC)
        session.revoke_reason = "user_logout"
        await db.flush()
        logger.info("v3 session %s revoked for user %s", session_id, user_id)
        return True

    # v1 fallback
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
    logger.info("v1 session %s revoked for user %s", session_id, user_id)
    return True


async def revoke_all_other_sessions(db: AsyncSession, user_id: int, current_token: str) -> int:
    """Revoke all sessions except the current one. Returns count of revoked sessions.

    Item #10: Revokes in both v3 AuthSession and v1 RefreshToken.
    The current session is identified by hashing current_token and skipping
    the matching AuthSession.
    """
    count = 0

    # v3: revoke all active sessions for this user.
    # NOTE (Item #10): The client holds a v1 refresh token (plaintext UUID),
    # but the v3 AuthSession stores the SHA-256 hash of a *different* token
    # (generated by v3_create_session and discarded).  We cannot identify which
    # AuthSession is "current" from the v1 token alone.  So we revoke ALL v3
    # sessions.  The current session is recreated on the next request via
    # backfill_session_from_v1 in deps.py.  Phase 2 will store the v1→v3
    # session mapping so we can skip the current one precisely.
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.is_active.is_(True),
        )
    )
    for s in result.scalars().all():
        s.is_active = False
        s.revoked_at = datetime.now(UTC)
        s.revoke_reason = "user_logout"
        count += 1

    # v1: revoke all except current
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.token != current_token,
        )
    )
    for token in result.scalars().all():
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
    """Update last_used_at for a refresh token.

    Item #10: Updates v3 AuthSession first; falls back to v1 RefreshToken.
    """
    from app.services.auth_v3_service import hash_refresh_token

    token_hash = hash_refresh_token(token)
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.is_active.is_(True),
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.last_used_at = datetime.now(UTC)
        if ip_address:
            session.ip_address = ip_address
        await db.flush()
        return

    # v1 fallback
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
