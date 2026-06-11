"""Auth v3 route handlers — sessions, users, API keys, OIDC, webhooks.

All endpoints under /api/v3/auth. Replaces the v2 auth flow with:
- httpOnly cookie for refresh tokens (not localStorage)
- Explicit session management (list, revoke per-session)
- Scoped API keys with AES-256 encryption at rest
- Granular scope-based authorization
- trace_id in error responses for log correlation
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from app.api.deps import get_current_user
from app.api.utils import get_client_ip, get_device_name, parse_browser, parse_os
from app.api.v3.auth_cookies import (
    clear_refresh_cookie,
    get_refresh_from_request,
    set_refresh_cookie,
)
from app.api.v3.base import ok
from app.database import get_db
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember
from app.schemas.auth_v3 import (
    ApiKeyListResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    LoginRequest,
    RefreshSessionRequest,
    RegisterRequest,
    SessionListResponse,
    SessionResponse,
    TempTokenResponse,
    UpdateUserRequest,
    UserResponse,
    UserSummary,
    Verify2FARequest,
)
from app.services.auth_rate_limiter import RATE_LIMITS, check_rate_limit
from app.services.auth_v3_service import (
    create_access_token,
    create_api_key,
    create_session,
    create_temp_token,
    create_user,
    decode_access_token,
    decode_temp_token,
    get_active_sessions,
    get_user_api_keys,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    hash_password,
    is_auth_v3_enabled,
    refresh_session,
    revoke_all_user_sessions,
    revoke_api_key,
    revoke_session,
    verify_password,
)
from app.services.totp_service import consume_backup_code, verify_code
from app.utils.password_validation import validate_password_strength

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["v3-auth"])


async def _require_v3_enabled(db: AsyncSession) -> None:
    """Raise 404 if Auth v3 feature flag is disabled."""
    if not await is_auth_v3_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )


def _build_user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        avatar_url=user.avatar_url,
        totp_enabled=user.totp_enabled,
    )


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account and create an initial session.

    Returns:
        201: { data: SessionResponse, meta, error: null }
        409: Email or username conflict
        422: Password validation failure
    """
    await _require_v3_enabled(db)

    ip = get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(
        f"v3_register:{ip}",
        RATE_LIMITS["register"]["max_requests"],
        RATE_LIMITS["register"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Password strength validation
    password_errors = validate_password_strength(payload.password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(password_errors),
        )

    # Check email uniqueness
    existing_email = await get_user_by_email(db, payload.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Check username uniqueness
    if payload.username:
        existing_username = await get_user_by_username(db, payload.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )

    # Create user
    user = await create_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        username=payload.username,
    )

    # Auto-create a personal workspace
    try:
        import re as _re

        ws_id = str(uuid.uuid4())
        ws_name = f"{payload.full_name or payload.username or user.username}'s Workspace"
        ws_slug = _re.sub(r"[^a-z0-9]+", "-", ws_name.lower()).strip("-") or "workspace"
        ws = Workspace(id=ws_id, name=ws_name, slug=ws_slug, owner_id=user.id)
        db.add(ws)
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=user.id, role="owner"))
        await db.flush()
    except Exception:
        logger.debug("register_workspace_create_failed", exc_info=True)

    # Create initial session
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    session, refresh_token = await create_session(
        db,
        user,
        ip_address=ip,
        device_name=get_device_name(request),
        device_os=parse_os(ua),
        browser=parse_browser(ua),
    )

    # Create access token
    access_token = create_access_token(
        user.id,
        session_id=session.id,
        role=user.role,
    )

    # Build response
    response_data = SessionResponse(
        access_token=access_token,
        session_id=session.id,
        expires_at=session.expires_at,
        user=_build_user_summary(user),
    )

    resp = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=ok(response_data.model_dump(mode="json")),
    )
    set_refresh_cookie(resp, refresh_token)
    return resp


# ═══════════════════════════════════════════════
# POST /auth/sessions — Login
# ═══════════════════════════════════════════════


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session_handler(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and create a new session.

    Returns:
        201: { data: SessionResponse, meta, error: null }
        401: Invalid credentials
        200: { data: { requires_2fa: true, temp_token: "..." } } — 2FA required
        423: Account locked
    """
    await _require_v3_enabled(db)

    ip = get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(
        f"v3_login:{ip}",
        RATE_LIMITS["login"]["max_requests"],
        RATE_LIMITS["login"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Find user by email or username
    result = await db.execute(select(User).where(or_(User.email == payload.login, User.username == payload.login)))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    # 2FA challenge if TOTP is enabled
    if user.totp_enabled:
        temp_token = create_temp_token(
            user.id,
            role=user.role,
        )
        temp_response = TempTokenResponse(temp_token=temp_token)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=ok(temp_response.model_dump(mode="json")),
        )

    # Create session
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    session, refresh_token = await create_session(
        db,
        user,
        ip_address=ip,
        device_name=get_device_name(request),
        device_os=parse_os(ua),
        browser=parse_browser(ua),
    )

    # Update login tracking
    user.login_count = (user.login_count or 0) + 1
    user.last_login_at = datetime.now(UTC)
    await db.flush()

    # Create access token
    access_token = create_access_token(
        user.id,
        session_id=session.id,
        role=user.role,
    )

    response_data = SessionResponse(
        access_token=access_token,
        session_id=session.id,
        expires_at=session.expires_at,
        user=_build_user_summary(user),
    )

    resp = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=ok(response_data.model_dump(mode="json")),
    )
    set_refresh_cookie(resp, refresh_token)
    return resp


# ═══════════════════════════════════════════════
# POST /auth/sessions/verify — 2FA Verification
# ═══════════════════════════════════════════════


@router.post("/sessions/verify", status_code=status.HTTP_200_OK)
async def verify_session_2fa(
    payload: Verify2FARequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Complete 2FA verification after login challenge.

    Returns:
        200: { data: SessionResponse } — session created
        401: Invalid 2FA code or expired temp token
    """
    await _require_v3_enabled(db)

    ip = get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(
        f"v3_2fa:{ip}",
        RATE_LIMITS["2fa_verify"]["max_requests"],
        RATE_LIMITS["2fa_verify"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Decode temp token
    token_payload = decode_temp_token(payload.temp_token)
    if not token_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired temp token",
        )

    user_id = int(token_payload["sub"])
    user = await get_user_by_id(db, user_id)
    if not user or not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled for this user",
        )

    # Verify TOTP code or backup code
    code_valid = False
    if user.totp_secret and verify_code(user.totp_secret, payload.code):
        code_valid = True
    elif user.totp_backup_codes:
        success, new_codes = consume_backup_code(payload.code, user.totp_backup_codes)
        if success:
            code_valid = True
            user.totp_backup_codes = new_codes

    if not code_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code",
        )

    # Create session
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    session, refresh_token = await create_session(
        db,
        user,
        ip_address=ip,
        device_name=get_device_name(request),
        device_os=parse_os(ua),
        browser=parse_browser(ua),
    )

    # Update login tracking
    user.login_count = (user.login_count or 0) + 1
    user.last_login_at = datetime.now(UTC)
    await db.flush()

    access_token = create_access_token(
        user.id,
        session_id=session.id,
        role=user.role,
    )

    response_data = SessionResponse(
        access_token=access_token,
        session_id=session.id,
        expires_at=session.expires_at,
        user=_build_user_summary(user),
    )

    resp = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ok(response_data.model_dump(mode="json")),
    )
    set_refresh_cookie(resp, refresh_token)
    return resp


# ═══════════════════════════════════════════════
# POST /auth/sessions/refresh — Refresh Token
# ═══════════════════════════════════════════════


@router.post("/sessions/refresh", status_code=status.HTTP_200_OK)
async def refresh_session_handler(
    request: Request,
    payload: RefreshSessionRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Refresh an access token using the refresh token.

    Refresh token is read from:
    1. httpOnly cookie (primary — extracted by AuthCookieMiddleware)
    2. Request body (fallback for non-browser clients)

    Returns:
        200: { data: SessionResponse }
        401: Invalid/expired/revoked refresh token
        401: Token reuse detected (entire family revoked)
    """
    await _require_v3_enabled(db)

    # Get refresh token from cookie or body
    refresh_token = get_refresh_from_request(request)

    if not refresh_token and payload and payload.refresh_token:
        refresh_token = payload.refresh_token

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided (cookie or body)",
        )

    # Refresh the session
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    result = await refresh_session(
        db,
        refresh_token,
        ip_address=ip,
        device_name=get_device_name(request),
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    new_session, new_refresh_token = result

    # Get the user
    user = await get_user_by_id(db, new_session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Create new access token
    access_token = create_access_token(
        user.id,
        session_id=new_session.id,
        role=user.role,
    )

    response_data = SessionResponse(
        access_token=access_token,
        session_id=new_session.id,
        expires_at=new_session.expires_at,
        user=_build_user_summary(user),
    )

    resp = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ok(response_data.model_dump(mode="json")),
    )
    set_refresh_cookie(resp, new_refresh_token)
    return resp


# ═══════════════════════════════════════════════
# GET /auth/sessions — List Sessions
# ═══════════════════════════════════════════════


@router.get("/sessions", status_code=status.HTTP_200_OK)
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the authenticated user.

    Returns:
        200: { data: [SessionListResponse], meta, error: null }
    """
    await _require_v3_enabled(db)

    sessions = await get_active_sessions(db, user.id)

    # Get the current session from the access token to mark it
    current_session_id: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload:
            current_session_id = payload.get("session_id")

    session_list = []
    for s in sessions:
        session_list.append(
            SessionListResponse(
                id=s.id,
                device_name=s.device_name,
                device_os=s.device_os,
                browser=s.browser,
                ip_address=s.ip_address,
                location=s.location,
                is_current=(s.id == current_session_id),
                last_used_at=s.last_used_at,
                created_at=s.created_at,
                expires_at=s.expires_at,
            ).model_dump(mode="json")
        )

    return ok(session_list)


# ═══════════════════════════════════════════════
# DELETE /auth/sessions/{session_id} — Revoke Session
# ═══════════════════════════════════════════════


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session_handler(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session.

    Returns:
        204: No content (success)
        404: Session not found or not owned by user
    """
    await _require_v3_enabled(db)

    success = await revoke_session(db, session_id, user.id, reason="user_logout")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # If revoking the current session, clear the cookie
    current_session_id: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload:
            current_session_id = payload.get("session_id")

    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    if current_session_id == session_id:
        clear_refresh_cookie(resp)
    return resp


# ═══════════════════════════════════════════════
# GET /auth/users/me — Current User Profile
# ═══════════════════════════════════════════════


@router.get("/users/me", status_code=status.HTTP_200_OK)
async def get_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get current user profile.

    Returns:
        200: { data: UserResponse, meta, error: null }
    """
    await _require_v3_enabled(db)

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
            totp_enabled=user.totp_enabled,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            onboarding_step=user.onboarding_step,
            onboarding_completed=user.onboarding_completed,
        ).model_dump(mode="json")
    )


# ═══════════════════════════════════════════════
# PATCH /auth/users/me — Update Current User
# ═══════════════════════════════════════════════


@router.patch("/users/me", status_code=status.HTTP_200_OK)
async def update_me(
    payload: UpdateUserRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile.

    Returns:
        200: { data: UserResponse, meta, error: null }
    """
    await _require_v3_enabled(db)

    changed = False

    if payload.full_name is not None:
        user.full_name = payload.full_name
        changed = True

    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url
        changed = True

    if payload.password is not None:
        password_errors = validate_password_strength(payload.password)
        if password_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="; ".join(password_errors),
            )
        user.hashed_password = hash_password(payload.password)
        # Revoke all existing sessions on password change
        await revoke_all_user_sessions(db, user.id, reason="password_change")
        changed = True

    if changed:
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
            totp_enabled=user.totp_enabled,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            onboarding_step=user.onboarding_step,
            onboarding_completed=user.onboarding_completed,
        ).model_dump(mode="json")
    )


# ═══════════════════════════════════════════════
# POST /auth/api-keys — Create API Key
# ═══════════════════════════════════════════════


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key_handler(
    payload: CreateApiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a scoped API key.

    The full key is returned ONCE in this response. It is not stored in plaintext —
    only the SHA-256 hash and prefix are persisted.

    Returns:
        201: { data: ApiKeyResponse }
        400: Invalid scopes
    """
    await _require_v3_enabled(db)

    try:
        api_key, full_key = await create_api_key(
            db,
            user_id=user.id,
            name=payload.name,
            scopes=payload.scopes,
            workspace_id=payload.workspace_id,
            expires_in_days=payload.expires_in_days,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    import json

    scopes_list = json.loads(api_key.scopes) if api_key.scopes else []

    return ok(
        ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=full_key,  # Full key — shown ONCE
            key_prefix=api_key.key_prefix,
            scopes=scopes_list,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
        ).model_dump(mode="json")
    )


# ═══════════════════════════════════════════════
# GET /auth/api-keys — List API Keys
# ═══════════════════════════════════════════════


@router.get("/api-keys", status_code=status.HTTP_200_OK)
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the authenticated user.

    The full key is NEVER returned in list endpoints — only key_prefix is shown.

    Returns:
        200: { data: [ApiKeyListResponse], meta, error: null }
    """
    await _require_v3_enabled(db)

    import json

    api_keys = await get_user_api_keys(db, user.id)
    key_list = []
    for k in api_keys:
        scopes_list = json.loads(k.scopes) if k.scopes else []
        key_list.append(
            ApiKeyListResponse(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                scopes=scopes_list,
                is_active=k.is_active,
                last_used_at=k.last_used_at,
                expires_at=k.expires_at,
                created_at=k.created_at,
            ).model_dump(mode="json")
        )

    return ok(key_list)


# ═══════════════════════════════════════════════
# DELETE /auth/api-keys/{key_id} — Revoke API Key
# ═══════════════════════════════════════════════


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key_handler(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key.

    Returns:
        204: No content (success)
        404: Key not found or not owned by user
    """
    await _require_v3_enabled(db)

    success = await revoke_api_key(db, key_id, user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
