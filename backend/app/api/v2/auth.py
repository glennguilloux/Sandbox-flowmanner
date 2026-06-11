"""V2 Auth endpoints — standardized envelope, clean paths."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.account_lockout import record_failed_login, reset_login_attempts
from app.services.auth_rate_limiter import RATE_LIMITS, check_rate_limit
from app.services.auth_service import (
    create_access_token,
    create_refresh_token_value,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    hash_password,
    revoke_all_user_tokens,
    revoke_refresh_token,
    store_refresh_token,
    track_login,
    verify_password,
)
from app.services.totp_service import consume_backup_code, verify_code
from app.utils.password_validation import validate_password_strength

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["v2-auth"])


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _get_device_name(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return ua[:100] if ua else "Unknown"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(
        f"register:{ip}",
        RATE_LIMITS["register"]["max_requests"],
        RATE_LIMITS["register"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    password_errors = validate_password_strength(payload.password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(password_errors),
        )

    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if payload.username:
        existing_username = await get_user_by_username(db, payload.username)
        if existing_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    from app.services.auth_service import create_user as create_user_service

    user = await create_user_service(db, payload.email, payload.password, payload.full_name, payload.username)

    try:
        import re as _re

        from app.models.workspace_models import Workspace, WorkspaceMember

        ws_id = str(uuid.uuid4())
        ws_name = f"{payload.full_name or payload.username or 'My'}'s Workspace"
        ws_slug = _re.sub(r"[^a-z0-9]+", "-", ws_name.lower()).strip("-") or "workspace"
        ws = Workspace(id=ws_id, name=ws_name, slug=ws_slug, owner_id=user.id)
        db.add(ws)
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=user.id, role="owner"))
        await db.flush()
    except Exception:
        logger.debug("register_workspace_create_failed", exc_info=True)

    access = create_access_token(user.id, role=user.role)
    refresh = create_refresh_token_value()
    family_id = str(uuid.uuid4())
    await store_refresh_token(
        db,
        user.id,
        refresh,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        device_name=_get_device_name(request),
        family_id=family_id,
    )

    return ok(TokenResponse(access_token=access, refresh_token=refresh).model_dump())


@router.post("/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    ip = _get_client_ip(request)

    allowed, remaining, retry_after = check_rate_limit(
        f"login:{ip}",
        RATE_LIMITS["login"]["max_requests"],
        RATE_LIMITS["login"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    login_field = None
    password = None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            login_field = body.get("username_or_email") or body.get("username") or body.get("email")
            password = body.get("password")
        except Exception:
            logger.debug("login_json_parse_failed", exc_info=True)
    else:
        try:
            form = await request.form()
            login_field = form.get("username_or_email") or form.get("username") or form.get("email")
            password = form.get("password")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-type must be application/json or form-data",
            )

    if not login_field or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="username_or_email and password are required",
        )

    lockout_key = f"login:{login_field}"
    lockout_status = record_failed_login(lockout_key)
    if lockout_status["locked"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to too many failed attempts. Try again in {lockout_status['lockout_seconds']} seconds.",
            headers={"Retry-After": str(lockout_status["lockout_seconds"])},
        )

    result = await db.execute(select(User).where(or_(User.email == login_field, User.username == login_field)))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    if user.totp_enabled:
        import jwt as _jwt

        from app.config import settings as _settings

        temp_expires = datetime.now(UTC) + timedelta(minutes=5)
        temp_payload = {
            "sub": str(user.id),
            "exp": temp_expires,
            "type": "2fa_temp",
            "role": user.role,
        }
        temp_token = _jwt.encode(temp_payload, _settings.JWT_SECRET_KEY, algorithm="HS256")
        return ok({"requires_2fa": True, "temp_token": temp_token})

    reset_login_attempts(lockout_key)

    access = create_access_token(user.id, role=user.role)
    refresh = create_refresh_token_value()
    family_id = str(uuid.uuid4())
    await store_refresh_token(
        db,
        user.id,
        refresh,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        device_name=_get_device_name(request),
        family_id=family_id,
    )

    await track_login(db, user)

    return ok(TokenResponse(access_token=access, refresh_token=refresh).model_dump())


@router.post("/login/2fa")
async def login_2fa(request: Request, db: AsyncSession = Depends(get_db)):
    ip = _get_client_ip(request)

    allowed, remaining, retry_after = check_rate_limit(
        f"2fa_verify:{ip}",
        RATE_LIMITS["2fa_verify"]["max_requests"],
        RATE_LIMITS["2fa_verify"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many 2FA attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        body = await request.json()
        temp_token = body.get("temp_token")
        code = body.get("code")
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body")

    if not temp_token or not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="temp_token and code are required",
        )

    try:
        import jwt as _jwt

        from app.config import settings as _settings

        payload = _jwt.decode(temp_token, _settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "2fa_temp":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired temp token",
        )

    user = await get_user_by_id(db, int(user_id))
    if not user or not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled for this user",
        )

    code_valid = False
    if user.totp_secret and verify_code(user.totp_secret, code):
        code_valid = True
    elif user.totp_backup_codes:
        success, new_codes = consume_backup_code(code, user.totp_backup_codes)
        if success:
            code_valid = True
            user.totp_backup_codes = new_codes

    if not code_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")

    access = create_access_token(user.id, role=user.role)
    refresh = create_refresh_token_value()
    family_id = str(uuid.uuid4())
    await store_refresh_token(
        db,
        user.id,
        refresh,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        device_name=_get_device_name(request),
        family_id=family_id,
    )

    reset_login_attempts(f"login:{user.email}")
    await track_login(db, user)

    return ok(TokenResponse(access_token=access, refresh_token=refresh).model_dump())


@router.post("/refresh")
async def refresh(payload: RefreshTokenRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from app.services.auth_service import RefreshToken as RTModel

    result = await db.execute(select(RTModel).where(RTModel.token == payload.refresh_token))
    token_record = result.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if token_record.is_revoked:
        await revoke_all_user_tokens(db, token_record.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All sessions revoked for security.",
        )

    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        await revoke_refresh_token(db, token_record.token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = await get_user_by_id(db, token_record.user_id)
    access = create_access_token(token_record.user_id, role=user.role if user else "user")
    new_refresh = create_refresh_token_value()

    await revoke_refresh_token(db, token_record.token)

    family_id = token_record.family_id or str(uuid.uuid4())
    await store_refresh_token(
        db,
        token_record.user_id,
        new_refresh,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        device_name=_get_device_name(request),
        family_id=family_id,
    )

    return ok(TokenResponse(access_token=access, refresh_token=new_refresh).model_dump())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await revoke_refresh_token(db, payload.refresh_token, user.id)


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return ok(
        UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_admin=user.is_admin,
            is_active=user.is_active,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
            onboarding_step=user.onboarding_step,
            onboarding_completed=user.onboarding_completed or False,
            onboarding_completed_at=user.onboarding_completed_at,
            onboarding_data=user.onboarding_data,
            last_login_at=user.last_login_at,
            login_count=user.login_count or 0,
        ).model_dump()
    )


@router.patch("/me")
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        password_errors = validate_password_strength(payload.password)
        if password_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="; ".join(password_errors),
            )
        user.hashed_password = hash_password(payload.password)
    await db.flush()
    await db.refresh(user)
    return ok(
        UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_admin=user.is_admin,
            is_active=user.is_active,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
        ).model_dump()
    )


class PasswordChangeRequest:
    pass
