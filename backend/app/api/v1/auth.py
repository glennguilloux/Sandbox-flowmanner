"""Authentication API endpoints with 2FA, rate limiting, and account lockout."""

import contextlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi import File as FastAPIFile
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, considering proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _get_device_name(request: Request) -> str:
    """Extract a human-readable device name from User-Agent."""
    ua = request.headers.get("user-agent", "")
    if not ua:
        return "Unknown"
    # Simple extraction — just use first 100 chars of UA
    return ua[:100]


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    # Rate limiting
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

    # Password strength validation
    password_errors = validate_password_strength(payload.password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(password_errors),
        )

    logger.info("[REGISTER] email=%s", payload.email)
    existing = await get_user_by_email(db, payload.email)
    if existing:
        logger.warning("[REGISTER] Email already registered: %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    # Check username uniqueness if provided
    if payload.username:
        existing_username = await get_user_by_username(db, payload.username)
        if existing_username:
            logger.warning("[REGISTER] Username already taken: %s", payload.username)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
            )

    from app.services.auth_service import create_user as create_user_service

    user = await create_user_service(
        db, payload.email, payload.password, payload.full_name, payload.username
    )

    # Auto-create a default workspace for the new user
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
        logger.exception(
            "[REGISTER] Failed to auto-create workspace for user %s", user.id
        )

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

    # Track analytics event — fire-and-forget, never crashes
    try:
        from app.services.analytics_service import EventType, track_event

        await track_event(db, str(user.id), EventType.ACCOUNT_CREATED)
    except Exception:
        logger.debug("analytics_register_track_failed", exc_info=True)

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    """Login with optional 2FA step."""
    ip = _get_client_ip(request)

    # Rate limiting
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

    try:
        login_field = None
        password = None

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                login_field = (
                    body.get("username_or_email")
                    or body.get("username")
                    or body.get("email")
                )
                password = body.get("password")
            except Exception:
                logger.debug("login_json_parse_failed", exc_info=True)
        else:
            try:
                form = await request.form()
                login_field = (
                    form.get("username_or_email")
                    or form.get("username")
                    or form.get("email")
                )
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

        # Account lockout check
        lockout_key = f"login:{login_field}"
        lockout_status = record_failed_login(lockout_key)
        if lockout_status["locked"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account temporarily locked due to too many failed attempts. Try again in {lockout_status['lockout_seconds']} seconds.",
                headers={"Retry-After": str(lockout_status["lockout_seconds"])},
            )

        # Find user
        result = await db.execute(
            select(User).where(
                or_(User.email == login_field, User.username == login_field)
            )
        )
        user = result.scalar_one_or_none()

        if (
            not user
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled"
            )

        # Check if 2FA is enabled
        if user.totp_enabled:
            # Return temp token for 2FA step
            temp_token = create_access_token(
                user.id,
                role=user.role,
            )
            # Override the expiry to 5 minutes for temp token
            import jwt as _jwt

            from app.config import settings as _settings

            temp_expires = datetime.now(UTC) + timedelta(minutes=5)
            temp_payload = {
                "sub": str(user.id),
                "exp": temp_expires,
                "type": "2fa_temp",
                "role": user.role,
            }
            temp_token = _jwt.encode(
                temp_payload, _settings.JWT_SECRET_KEY, algorithm="HS256"
            )

            return {
                "requires_2fa": True,
                "temp_token": temp_token,
            }

        # No 2FA — complete login
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

        return TokenResponse(access_token=access, refresh_token=refresh)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[LOGIN] Unhandled error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred. Please try again later.",
        )


@router.post("/login/2fa", response_model=TokenResponse)
async def login_2fa(request: Request, db: AsyncSession = Depends(get_db)):
    """Complete login with 2FA code."""
    ip = _get_client_ip(request)

    # Rate limiting
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body"
        )

    if not temp_token or not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="temp_token and code are required",
        )

    # Decode temp token
    user_id = decode_access_token(temp_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired temp token",
        )

    # Verify it's a 2fa_temp token
    try:
        import jwt as _jwt

        from app.config import settings as _settings

        payload = _jwt.decode(
            temp_token, _settings.JWT_SECRET_KEY, algorithms=["HS256"]
        )
        if payload.get("type") != "2fa_temp":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
            )
    except _jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    user = await get_user_by_id(db, user_id)
    if not user or not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled for this user",
        )

    # Verify TOTP code
    code_valid = False
    if user.totp_secret and verify_code(user.totp_secret, code):
        code_valid = True
    # Also accept backup codes
    elif user.totp_backup_codes:
        success, new_codes = consume_backup_code(code, user.totp_backup_codes)
        if success:
            code_valid = True
            user.totp_backup_codes = new_codes

    if not code_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code"
        )

    # Complete login
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

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    # First check if token exists (active or revoked)
    from app.services.auth_service import RefreshToken as RTModel

    result = await db.execute(
        select(RTModel).where(RTModel.token == payload.refresh_token)
    )
    token_record = result.scalar_one_or_none()

    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    # Token exists but is revoked — potential theft/reuse!
    if token_record.is_revoked:
        # Grace period: if token was revoked within the last REUSE_GRACE_SECONDS,
        # treat as a race condition (parallel refresh), not theft
        REUSE_GRACE_SECONDS = 5
        grace_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            seconds=REUSE_GRACE_SECONDS
        )
        recently_revoked = (
            token_record.last_used_at is not None
            and token_record.last_used_at > grace_cutoff
        )
        if recently_revoked:
            logger.warning(
                "Refresh token reuse within %ss grace period for user %s — treating as race condition, not theft",
                REUSE_GRACE_SECONDS,
                token_record.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token already used"
            )
        # Outside grace period — potential theft: revoke ALL tokens
        await revoke_all_user_tokens(db, token_record.user_id)
        logger.warning(
            "Refresh token reuse detected for user %s — all tokens revoked",
            token_record.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All sessions revoked for security.",
        )

    # Check expiry
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        await revoke_refresh_token(db, token_record.token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
        )

    # Get user for tenant claims
    user = await get_user_by_id(db, token_record.user_id)
    access = create_access_token(
        token_record.user_id, role=user.role if user else "user"
    )
    new_refresh = create_refresh_token_value()

    # Revoke old token
    await revoke_refresh_token(db, token_record.token)

    # Store new token in same family
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

    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await revoke_refresh_token(db, payload.refresh_token, user.id)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
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
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        # Validate new password strength
        password_errors = validate_password_strength(payload.password)
        if password_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="; ".join(password_errors),
            )
        user.hashed_password = hash_password(payload.password)
    await db.flush()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_admin=user.is_admin,
        is_active=user.is_active,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


@router.put("/me", response_model=UserResponse)
async def put_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await update_me(payload, db, user)


@router.patch("/settings")
async def update_settings(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update user settings (theme, language, email_notifications)."""
    from sqlalchemy import select

    from app.models.phase4_models import UserSettings

    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user.id)
        db.add(settings)

    if "theme" in data:
        settings.theme = data["theme"]
    if "language" in data:
        settings.language = data["language"]
    if "email_notifications" in data:
        settings.email_notifications = data["email_notifications"]
    # Store any extra fields as JSON
    import json

    extra = {
        k: v
        for k, v in data.items()
        if k not in ("theme", "language", "email_notifications")
    }
    if extra:
        existing = {}
        if settings.settings_json:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                existing = json.loads(settings.settings_json)
        existing.update(extra)
        settings.settings_json = json.dumps(existing)

    await db.flush()
    await db.refresh(settings)
    return {
        "status": "updated",
        "settings": {
            "theme": settings.theme,
            "language": settings.language,
            "email_notifications": settings.email_notifications,
        },
    }


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get current user's settings."""
    from sqlalchemy import select

    from app.models.phase4_models import UserSettings

    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        return {"theme": "dark", "language": "en", "email_notifications": True}
    return {
        "theme": settings.theme,
        "language": settings.language,
        "email_notifications": settings.email_notifications,
    }


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/password")
async def change_password(
    payload: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change the current user's password."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    password_errors = validate_password_strength(payload.new_password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(password_errors),
        )
    user.hashed_password = hash_password(payload.new_password)
    await db.flush()
    return {"status": "password_changed"}


class SocialTokenRequest(BaseModel):
    provider: str
    access_token: str


@router.post("/social/token", response_model=TokenResponse)
async def social_token_exchange(
    payload: SocialTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a social provider's access_token for backend JWT tokens.

    Used by NextAuth's signIn callback after GitHub / Google OAuth completes.
    Fetches the user's profile from the provider's API, creates or
    finds the local user, and returns a backend access/refresh pair.
    """
    # Rate limiting per IP (5 requests per minute)
    ip = _get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(
        f"social_token:{ip}",
        RATE_LIMITS["social_token"]["max_requests"],
        RATE_LIMITS["social_token"]["window_seconds"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many social token requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if payload.provider not in ("github", "google"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {payload.provider}",
        )

    # Fetch the social profile
    social = await _fetch_social_profile(payload.provider, payload.access_token)

    # Ensure an OIDCProvider row exists (or create it lazily)
    from app.models.auth_models import UserOIDCAccount

    provider_id = await _ensure_oidc_provider(
        db, payload.provider, social["display_name"], social["issuer_url"]
    )

    # Find user by OIDC account link (scoped to provider + subject)
    result = await db.execute(
        select(UserOIDCAccount).where(
            UserOIDCAccount.provider_id == provider_id,
            UserOIDCAccount.subject == social["id"],
        )
    )
    oidc_account = result.scalar_one_or_none()

    if oidc_account:
        user_result = await db.execute(
            select(User).where(User.id == oidc_account.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            if social["avatar"] and user.avatar_url != social["avatar"]:
                user.avatar_url = social["avatar"]
                await db.flush()
            _complete_login(user)
            return TokenResponse(
                access_token=create_access_token(user.id, role=user.role),
                refresh_token=await _issue_refresh_token(db, user.id, request),
            )

    # Find by email (link existing account)
    user = await get_user_by_email(db, social["email"])
    if user:
        _link_oidc_account(
            db,
            user.id,
            provider_id,  # type: ignore[arg-type]
            social["id"],
            social["login"],
            social["email"],
            social["name"],
        )
        if social["avatar"] and not user.avatar_url:
            user.avatar_url = social["avatar"]
        await db.flush()
        _complete_login(user)
        return TokenResponse(
            access_token=create_access_token(user.id, role=user.role),
            refresh_token=await _issue_refresh_token(db, user.id, request),
        )

    # Create new user
    import secrets

    from app.services.auth_service import create_user as create_user_service

    username = social["login"]
    # Avoid username collisions — append a suffix if taken
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        username = f"{social['login']}_{social['id'][:6]}"
    user = await create_user_service(
        db,
        email=social["email"],
        password=secrets.token_urlsafe(32),
        full_name=social["name"],
        username=username,
    )
    if social["avatar"]:
        user.avatar_url = social["avatar"]
        await db.flush()

    _link_oidc_account(
        db,
        user.id,
        provider_id,  # type: ignore[arg-type]
        social["id"],
        social["login"],
        social["email"],
        social["name"],
    )
    await db.flush()

    # Auto-create default workspace
    try:
        import re as _re

        from app.models.workspace_models import Workspace, WorkspaceMember

        ws_id = str(uuid.uuid4())
        ws_name = f"{social['name'] or social['login']}'s Workspace"
        ws_slug = _re.sub(r"[^a-z0-9]+", "-", ws_name.lower()).strip("-") or "workspace"
        ws = Workspace(id=ws_id, name=ws_name, slug=ws_slug, owner_id=user.id)
        db.add(ws)
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=user.id, role="owner"))
        await db.flush()
    except Exception:
        logger.exception("Failed to auto-create workspace for OAuth user %s", user.id)

    _complete_login(user)
    return TokenResponse(
        access_token=create_access_token(user.id, role=user.role),
        refresh_token=await _issue_refresh_token(db, user.id, request),
    )


async def _fetch_social_profile(provider: str, access_token: str) -> dict:
    """Fetch a normalized profile dict from a social provider.

    Returns keys: id, login, email, name, avatar, display_name, issuer_url
    """
    import httpx

    if provider == "github":
        async with httpx.AsyncClient(timeout=10.0) as client:
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                logger.warning("GitHub /user returned %s", user_resp.status_code)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid GitHub access token",
                )
            gh = user_resp.json()

            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            emails = emails_resp.json() if emails_resp.status_code == 200 else []

        gh_id = str(gh.get("id"))
        gh_login = gh.get("login", "")
        gh_name = gh.get("name") or gh_login
        gh_avatar = gh.get("avatar_url")

        primary_email = gh.get("email")
        if not primary_email and isinstance(emails, list):
            for e in emails:
                if e.get("primary") and e.get("verified"):
                    primary_email = e["email"]
                    break
            if not primary_email:
                for e in emails:
                    if e.get("verified"):
                        primary_email = e["email"]
                        break
        if not primary_email:
            primary_email = f"{gh_login}@github.local"
            logger.warning(
                "No public email for GitHub user %s, using synthetic", gh_login
            )

        return {
            "id": gh_id,
            "login": gh_login,
            "email": primary_email,
            "name": gh_name,
            "avatar": gh_avatar,
            "display_name": "GitHub",
            "issuer_url": "https://github.com",
        }

    elif provider == "google":
        async with httpx.AsyncClient(timeout=10.0) as client:
            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                logger.warning("Google userinfo returned %s", user_resp.status_code)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google access token",
                )
            g = user_resp.json()

        google_id = str(g.get("id"))
        google_email = g.get("email", "")
        google_name = g.get("name") or google_email.split("@")[0]
        google_avatar = g.get("picture")
        google_login = google_email.split("@")[0] if google_email else google_id

        if not google_email:
            google_email = f"{google_login}@google.local"
            logger.warning("No email for Google user %s, using synthetic", google_id)

        return {
            "id": google_id,
            "login": google_login,
            "email": google_email,
            "name": google_name,
            "avatar": google_avatar,
            "display_name": "Google",
            "issuer_url": "https://accounts.google.com",
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported provider: {provider}",
    )


async def _ensure_oidc_provider(
    db: AsyncSession, name: str, display_name: str, issuer_url: str
) -> int:
    """Look up or lazily create an OIDCProvider row, returning its id."""
    from app.models.auth_models import OIDCProvider

    result = await db.execute(select(OIDCProvider).where(OIDCProvider.name == name))
    provider = result.scalar_one_or_none()
    if not provider:
        provider = OIDCProvider(
            name=name,
            display_name=display_name,
            issuer_url=issuer_url,
            client_id="",
            client_secret="",
            is_active=True,
        )
        db.add(provider)
        await db.flush()
    return provider.id


def _link_oidc_account(
    db: AsyncSession,
    user_id: int,
    provider_id: str,
    subject: str,
    login: str,
    email: str,
    name: str | None,
) -> None:
    """Create an OIDC account link (GitHub ID, Google ID, etc.)."""
    from app.models.auth_models import UserOIDCAccount

    db.add(
        UserOIDCAccount(
            user_id=user_id,
            provider_id=provider_id,
            subject=subject,
            email=email,
            name=name or login,
        )
    )


async def _issue_refresh_token(db: AsyncSession, user_id: int, request: Request) -> str:
    """Issue and store a refresh token, returning the token value."""
    refresh = create_refresh_token_value()
    family_id = str(uuid.uuid4())
    await store_refresh_token(
        db,
        user_id,
        refresh,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        device_name=_get_device_name(request),
        family_id=family_id,
    )
    return refresh


def _complete_login(user: User) -> None:
    """Bump login counter and timestamp."""
    try:
        user.login_count = (user.login_count or 0) + 1
        user.last_login_at = datetime.now(UTC)
    except Exception:
        logger.debug("login_counter_update_failed", exc_info=True)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = FastAPIFile(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a new avatar image."""
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}",
        )
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File too large. Max 5MB."
        )

    import os
    import uuid as _uuid

    ext = (
        file.filename.rsplit(".", 1)[-1]
        if file.filename and "." in file.filename
        else "png"
    )
    filename = f"avatar_{user.id}_{_uuid.uuid4().hex[:8]}.{ext}"
    static_dir = os.getenv("STATIC_FILES_DIR", "/opt/flowmanner/static/avatars")
    os.makedirs(static_dir, exist_ok=True)

    filepath = os.path.join(static_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    base_url = os.getenv("STATIC_BASE_URL", "/static/avatars")
    avatar_url = f"{base_url}/{filename}"

    user.avatar_url = avatar_url
    await db.flush()
    await db.refresh(user)

    return {"status": "uploaded", "avatar_url": avatar_url}


def decode_access_token(token: str) -> str | None:
    """Decode a JWT access token and return the subject (user ID)."""
    try:
        import jwt as _jwt

        from app.config import settings as _settings

        payload = _jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        return None
