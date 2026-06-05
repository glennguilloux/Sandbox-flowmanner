"""Authentication service - JWT tokens, password hashing, user management, session tracking."""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
import jwt
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models import Base
from app.models.user import User


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    # Session/device tracking fields
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Token family for reuse detection
    family_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    family_generation: Mapped[int] = mapped_column(Integer, default=0)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: int, tenant_id: int | None = None, role: str = "user") -> str:
    """Create a JWT access token.

    tenant_id is DEPRECATED (H4 Phase 2) — kept for backward compat but
    no longer included in the JWT payload. Workspace context is resolved
    via WorkspaceMember at request time instead.
    """
    expires = datetime.now(UTC) + timedelta(seconds=settings.JWT_ACCESS_TOKEN_EXPIRES)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "type": "access",
        "role": role,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def create_refresh_token_value() -> str:
    return str(uuid.uuid4())


async def store_refresh_token(
    db: AsyncSession,
    user_id: int,
    token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_name: str | None = None,
    family_id: str | None = None,
) -> RefreshToken:
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=settings.JWT_REFRESH_TOKEN_EXPIRES)

    # Determine family generation
    generation = 0
    if family_id:
        # Find the highest generation in this family
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == family_id,
                RefreshToken.is_revoked == False,
            ).order_by(RefreshToken.family_generation.desc())
        )
        latest = result.scalar_one_or_none()
        if latest:
            generation = (latest.family_generation or 0) + 1

    rt = RefreshToken(
        token=token,
        user_id=user_id,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
        device_name=device_name,
        last_used_at=datetime.now(UTC).replace(tzinfo=None),
        family_id=family_id,
        family_generation=generation,
    )
    db.add(rt)
    await db.flush()
    return rt


async def get_refresh_token(db: AsyncSession, token: str) -> RefreshToken | None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == token, RefreshToken.is_revoked == False))
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token: str, user_id: int | None = None) -> None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == token))
    rt = result.scalar_one_or_none()
    if rt is None:
        return
    if user_id is not None and rt.user_id != user_id:
        return
    rt.is_revoked = True
    rt.last_used_at = datetime.now(UTC).replace(tzinfo=None)  # revocation timestamp for grace period
    await db.flush()


async def revoke_all_user_tokens(db: AsyncSession, user_id: int) -> int:
    """Revoke all refresh tokens for a user. Returns count of revoked tokens."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        )
    )
    tokens = result.scalars().all()
    count = 0
    for token in tokens:
        token.is_revoked = True
        token.last_used_at = datetime.now(UTC).replace(tzinfo=None)
        count += 1
    await db.flush()
    return count


async def revoke_token_family(db: AsyncSession, family_id: str) -> int:
    """Revoke all tokens in a family (for reuse detection). Returns count."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.is_revoked == False,
        )
    )
    tokens = result.scalars().all()
    count = 0
    for token in tokens:
        token.is_revoked = True
        token.last_used_at = datetime.now(UTC).replace(tzinfo=None)
        count += 1
    await db.flush()
    return count


async def check_token_reuse(db: AsyncSession, token: str) -> bool:
    """Check if a refresh token has been reused (theft indicator).

    Returns True if the token was already revoked (potential reuse/theft).
    """
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == token))
    rt = result.scalar_one_or_none()
    if rt is None:
        return False
    return rt.is_revoked


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int | str) -> User | None:
    result = await db.execute(select(User).where(User.id == int(user_id)))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession, email: str, password: str, full_name: str | None = None, username: str | None = None
) -> User:
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

    # Send welcome email (non-blocking)
    try:
        from app.services.onboarding_email_service import send_onboarding_email
        await send_onboarding_email(db, user, "welcome")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to send welcome email: {e}")

    return user


async def track_login(db: AsyncSession, user: User) -> None:
    """Track user login: increment count and update last_login_at."""
    user.login_count = (user.login_count or 0) + 1
    user.last_login_at = datetime.now(UTC)
    await db.flush()
