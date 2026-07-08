"""Auth v3 service — session management, API key encryption, token hashing.

Business logic for the v3 auth API. Handles:
- Session creation, refresh, revocation (with token reuse detection)
- API key generation with AES-256 encryption at rest
- Scope validation for API keys
- Token hashing utilities
- OIDC provider PKCE flows
- Webhook dispatch for auth events
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

import bcrypt as _bcrypt
import jwt
from sqlalchemy import select, text

from app.config import settings
from app.models.auth_v3_models import (
    ApiKey,
    AuthSession,
)
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ──────────────────────────────────────────────────────────────
# Scope validation
# ──────────────────────────────────────────────────────────────

_VALID_SCOPES: set[str] = {
    "missions:read",
    "missions:write",
    "sessions:read",
    "sessions:write",
    "api_keys:read",
    "api_keys:write",
    "webhooks:read",
    "webhooks:write",
    "workspaces:read",
    "workspaces:write",
    "agents:read",
    "agents:write",
    "chat:read",
    "chat:write",
}

_VALID_ROLES: set[str] = {"viewer", "member", "admin", "owner"}


def validate_api_key_scopes(scopes: list[str]) -> bool:
    """Check that all requested scopes are valid v3 scopes."""
    if not scopes:
        return False
    return all(s in _VALID_SCOPES for s in scopes)


def validate_role(role: str) -> bool:
    """Check that a role string is one of the valid workspace roles."""
    return role in _VALID_ROLES


# ──────────────────────────────────────────────────────────────
# Datetime normalization
# ──────────────────────────────────────────────────────────────


def _to_utc_aware(dt: datetime | None) -> datetime | None:
    """Re-attach UTC tzinfo to a datetime that came from a naive-UTC column.

    The legacy ``refresh_tokens`` table stores ``expires_at`` as
    ``timestamp without time zone`` (see ``app.services.auth_service`` — the
    writer strips tzinfo via ``.replace(tzinfo=None)`` before insert, on
    purpose for pre-v3 client compatibility). When the v3 refresh path
    reads one of these rows back through asyncpg, the value comes back as
    a *naive* datetime, and a direct comparison to ``datetime.now(UTC)``
    (which is aware) raises ``TypeError: can't compare offset-naive and
    offset-aware datetimes``. This helper bridges the two representations
    by assuming the naive value is UTC — which is the convention used
    throughout the v1 code path. Returns ``None`` unchanged.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    """Strip tzinfo from a datetime so it can be written to a naive-UTC column.

    The v1 schema stores ``last_used_at`` as ``timestamp without time zone``,
    which asyncpg refuses to accept with tzinfo set. The v1 codebase writes
    to it with ``datetime.now(UTC).replace(tzinfo=None)`` (see
    ``auth_service.py``); the v3 migration path has to do the same when
    it touches v1 columns. Returns ``None`` unchanged.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is None else dt.replace(tzinfo=None)


# ──────────────────────────────────────────────────────────────
# Token hashing utilities
# ──────────────────────────────────────────────────────────────


def hash_refresh_token(token: str) -> str:
    """SHA-256 the refresh token for storage. Never store plaintext."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_invite_token() -> str:
    """Generate a cryptographically random invitation token (64 hex chars = 256 bits)."""
    return secrets.token_hex(32)


# ──────────────────────────────────────────────────────────────
# Session management
# ──────────────────────────────────────────────────────────────


def create_access_token(
    user_id: int,
    session_id: str,
    tenant_id: int | None = None,
    role: str = "user",
    scopes: list[str] | None = None,
) -> str:
    """Create a JWT access token with v3 claims (includes session_id and scopes).

    tenant_id is DEPRECATED (H4 Phase 2) — kept for backward compat but
    no longer included in the JWT payload. Workspace context is resolved
    via WorkspaceMember at request time instead.
    """
    expires = datetime.now(UTC) + timedelta(seconds=settings.JWT_ACCESS_TOKEN_EXPIRES)
    payload: dict = {
        "sub": str(user_id),
        "session_id": session_id,
        "exp": expires,
        "type": "access",
        "role": role,
    }
    if scopes:
        payload["scopes"] = scopes
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    """Decode JWT access token and return full payload. Returns None on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def create_temp_token(user_id: int, role: str, tenant_id: int | None = None) -> str:
    """Create a short-lived temp token for 2FA verification (5 min TTL).

    tenant_id is DEPRECATED (H4 Phase 2) — kept for backward compat but
    no longer included in the JWT payload.
    """
    expires = datetime.now(UTC) + timedelta(minutes=5)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "type": "2fa_temp",
        "role": role,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def decode_temp_token(token: str) -> dict | None:
    """Decode a 2FA temp token. Returns None on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "2fa_temp":
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def create_session(
    db: AsyncSession,
    user: User,
    ip_address: str | None = None,
    device_name: str | None = None,
    device_os: str | None = None,
    browser: str | None = None,
) -> tuple[AuthSession, str]:
    """Create a new auth session. Returns (session, refresh_token).

    The refresh token is returned in plaintext for the response.
    Only its SHA-256 hash is stored in auth_sessions.
    """
    refresh_token = AuthSession.generate_refresh_token()
    token_hash = AuthSession.make_refresh_token_hash(refresh_token)
    family_id = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.JWT_REFRESH_TOKEN_EXPIRES)

    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=token_hash,
        device_name=device_name,
        device_os=device_os,
        browser=browser,
        ip_address=ip_address,
        is_active=True,
        expires_at=expires_at,
        family_id=family_id,
        family_generation=0,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session, refresh_token


async def _try_migrate_v1_token(
    db: AsyncSession,
    refresh_token: str,
    ip_address: str | None = None,
    device_name: str | None = None,
) -> tuple[AuthSession, str] | None:
    """Try to validate a v1 refresh token and migrate it to v3 AuthSession format.

    v1 stores plaintext tokens in the ``refresh_tokens`` table.  v3 stores
    SHA-256 hashes in ``auth_sessions``.  When a v1 token is presented to the
    v3 refresh endpoint, this function looks it up, validates it, and creates
    a new ``AuthSession`` entry so subsequent refreshes use the v3 path.

    Returns ``(new_session, new_refresh_token)`` on success, ``None`` on failure.
    The caller (``refresh_session``) returns this tuple directly — it does NOT
    fall through to the revoke-and-recreate path.
    """
    from app.services.auth_service import RefreshToken

    result = await db.execute(select(RefreshToken).where(RefreshToken.token == refresh_token))
    v1_token = result.scalar_one_or_none()

    if v1_token is None:
        return None

    if v1_token.is_revoked:
        return None

    # ``refresh_tokens.expires_at`` is stored as naive UTC (the v1 schema
    # is ``timestamp without time zone`` by design), so we normalize to
    # aware-UTC before comparing against ``datetime.now(UTC)``.
    v1_expires = _to_utc_aware(v1_token.expires_at)
    if v1_expires and v1_expires < datetime.now(UTC):
        v1_token.is_revoked = True
        await db.flush()
        return None

    # Migrate: create an AuthSession from the v1 token
    family_id = v1_token.family_id or str(uuid.uuid4())
    new_refresh_token = AuthSession.generate_refresh_token()
    new_token_hash = AuthSession.make_refresh_token_hash(new_refresh_token)
    new_expires_at = datetime.now(UTC) + timedelta(seconds=settings.JWT_REFRESH_TOKEN_EXPIRES)

    new_session = AuthSession(
        user_id=v1_token.user_id,
        refresh_token_hash=new_token_hash,
        device_name=device_name or v1_token.device_name,
        ip_address=ip_address or v1_token.ip_address,
        is_active=True,
        expires_at=new_expires_at,
        family_id=family_id,
        family_generation=0,
    )
    db.add(new_session)

    # Revoke the v1 token so it cannot be reused
    v1_token.is_revoked = True
    # ``refresh_tokens.last_used_at`` is ``timestamp without time zone``;
    # asyncpg refuses aware datetimes on insert. The v1 codebase always
    # writes this column with tzinfo stripped — see auth_service.py:135.
    v1_token.last_used_at = _to_utc_naive(datetime.now(UTC))

    await db.flush()
    await db.refresh(new_session)
    new_session.last_used_at = datetime.now(UTC)
    await db.flush()

    logger.info(
        "migrated v1 refresh token to v3 auth session for user_id=%s",
        v1_token.user_id,
    )
    return new_session, new_refresh_token


async def refresh_session(
    db: AsyncSession,
    refresh_token: str,
    ip_address: str | None = None,
    device_name: str | None = None,
) -> tuple[AuthSession, str] | None:
    """Refresh a session: validate token, revoke old, create new in same family.

    Returns (new_session, new_refresh_token) or None if token invalid/expired/revoked.

    Token reuse detection: if a revoked token is presented, the entire family is
    revoked and None is returned.
    """
    token_hash = hash_refresh_token(refresh_token)

    result = await db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()

    if session is None:
        # v1 backward compat: check legacy refresh_tokens table for plaintext match.
        # If found, migrate the token to v3 AuthSession format transparently.
        # Returns (session, token) directly — does NOT fall through to the
        # revoke-and-recreate path below.
        return await _try_migrate_v1_token(db, refresh_token, ip_address, device_name)

    # Token reuse detection — if the token was already revoked, revoke the whole family
    if not session.is_active:
        await revoke_token_family(db, session.family_id)
        return None

    # Check expiry (normalize to UTC-aware — see _to_utc_aware for the
    # why; the v1 ``refresh_tokens`` schema is naive-UTC, and a stray
    # ``TIMESTAMP`` column in ``auth_sessions`` would have the same
    # problem. Defending the v3 hot path too is cheap.)
    session_expires = _to_utc_aware(session.expires_at)
    if session_expires is None or session_expires < datetime.now(UTC):
        session.is_active = False
        session.revoked_at = datetime.now(UTC)
        session.revoke_reason = "expired"
        await db.flush()
        return None

    # Revoke old session
    session.is_active = False
    session.revoked_at = datetime.now(UTC)

    # Create new session in the same family with incremented generation
    new_refresh_token = AuthSession.generate_refresh_token()
    new_token_hash = AuthSession.make_refresh_token_hash(new_refresh_token)
    new_expires_at = datetime.now(UTC) + timedelta(seconds=settings.JWT_REFRESH_TOKEN_EXPIRES)

    new_session = AuthSession(
        user_id=session.user_id,
        refresh_token_hash=new_token_hash,
        device_name=device_name or session.device_name,
        device_os=session.device_os,
        browser=session.browser,
        ip_address=ip_address or session.ip_address,
        is_active=True,
        expires_at=new_expires_at,
        family_id=session.family_id,
        family_generation=(session.family_generation or 0) + 1,
    )
    db.add(new_session)
    await db.flush()
    await db.refresh(new_session)

    # Update last_used_at on the NEW session (tracking happens on refresh, not on access)
    new_session.last_used_at = datetime.now(UTC)
    await db.flush()

    return new_session, new_refresh_token


async def revoke_session(
    db: AsyncSession,
    session_id: str,
    user_id: int,
    reason: str = "user_logout",
) -> bool:
    """Revoke a specific session by ID. Returns True if session was found and revoked."""
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.is_active == True,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False

    session.is_active = False
    session.revoked_at = datetime.now(UTC)
    session.revoke_reason = reason
    await db.flush()
    return True


async def revoke_all_user_sessions(
    db: AsyncSession,
    user_id: int,
    reason: str = "password_change",
) -> int:
    """Revoke all active sessions for a user. Returns count of revoked sessions."""
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.is_active == True,
        )
    )
    sessions = result.scalars().all()
    count = 0
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.now(UTC)
        session.revoke_reason = reason
        count += 1
    await db.flush()
    return count


async def revoke_token_family(db: AsyncSession, family_id: str | None) -> int:
    """Revoke all active sessions in a token family (reuse detection). Returns count."""
    if not family_id:
        return 0

    result = await db.execute(
        select(AuthSession).where(
            AuthSession.family_id == family_id,
            AuthSession.is_active == True,
        )
    )
    sessions = result.scalars().all()
    count = 0
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.now(UTC)
        session.revoke_reason = "reuse_detected"
        count += 1
    await db.flush()
    return count


async def get_active_sessions(db: AsyncSession, user_id: int) -> list[AuthSession]:
    """Get all active sessions for a user, ordered by creation time descending."""
    result = await db.execute(
        select(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.is_active == True)
        .order_by(AuthSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_session_by_id(db: AsyncSession, session_id: str) -> AuthSession | None:
    """Get a session by ID (active or not)."""
    result = await db.execute(select(AuthSession).where(AuthSession.id == session_id))
    return result.scalar_one_or_none()


# ──────────────────────────────────────────────────────────────
# API key management
# ──────────────────────────────────────────────────────────────


async def create_api_key(
    db: AsyncSession,
    user_id: int,
    name: str,
    scopes: list[str],
    workspace_id: str | None = None,
    expires_in_days: int | None = None,
) -> tuple[ApiKey, str]:
    """Create a new scoped API key. Returns (api_key_record, full_key).

    The full_key is returned ONCE — only the SHA-256 hash is stored.
    """
    if not validate_api_key_scopes(scopes):
        raise ValueError("Invalid scopes")

    full_key, prefix, key_hash = ApiKey.generate_api_key()

    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

    api_key = ApiKey(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=json.dumps(scopes),
        is_active=True,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)
    return api_key, full_key


async def get_user_api_keys(db: AsyncSession, user_id: int) -> list[ApiKey]:
    """List all API keys for a user (active or inactive)."""
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, key_id: str, user_id: int) -> bool:
    """Revoke an API key. Returns True if found and revoked."""
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return False

    api_key.is_active = False
    await db.flush()
    return True


# ──────────────────────────────────────────────────────────────
# Feature flag resolution
# ──────────────────────────────────────────────────────────────


async def is_auth_v3_enabled(db: AsyncSession) -> bool:
    """Check if the master Auth v3 endpoints flag is globally enabled."""
    result = await db.execute(text("SELECT enabled_globally FROM feature_flags WHERE key = 'AUTH_V3_ENDPOINTS'"))
    flag = result.scalar()
    return bool(flag)


# ──────────────────────────────────────────────────────────────
# Password hashing (reuses existing bcrypt pattern)
# ──────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return _bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ──────────────────────────────────────────────────────────────
# User management
# ──────────────────────────────────────────────────────────────


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Find a user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Find a user by username."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """Find a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def backfill_session_from_v1(
    db: AsyncSession,
    user_id: int,
    ip_address: str | None = None,
    device_name: str | None = None,
) -> AuthSession:
    """Lazily create an AuthSession for a user authenticating via v1 JWT.

        Called by ``get_current_user`` when it encounters a valid v1 access token
        (no ``session_id`` claim) and no active AuthSession exists.  This is the
        single-write bridge: every identity resolution that lands here produces an
        AuthSession row so the v3 system becomes authoritative over time.

        The backfilled session has a long-lived refresh token that is NOT returned
    to the caller — the v1 caller already has its own refresh token.  The session
        is only used for tracking and future v3-resolution.
    """
    # Check for existing active session to avoid duplicates
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.is_active == True,
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        return existing

    # Use a deterministic sentinel hash — this session is for tracking only,
    # not for refresh.  A real random token would waste entropy and create
    # an unvalidatable hash in the DB.
    token_hash = hashlib.sha256(f"backfill:v1:{user_id}".encode()).hexdigest()
    family_id = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.JWT_REFRESH_TOKEN_EXPIRES)

    session = AuthSession(
        user_id=user_id,
        refresh_token_hash=token_hash,
        device_name=device_name,
        ip_address=ip_address,
        is_active=True,
        expires_at=expires_at,
        family_id=family_id,
        family_generation=0,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    logger.info(
        "backfilled v3 auth session from v1 token for user_id=%s session_id=%s",
        user_id,
        session.id,
    )
    return session


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str | None = None,
    username: str | None = None,
) -> User:
    """Create a new user account."""
    username = username or email.split("@")[0]
    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_admin=False,
        onboarding_step="welcome",
        onboarding_completed=False,
        onboarding_data="{}",
        login_count=0,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
