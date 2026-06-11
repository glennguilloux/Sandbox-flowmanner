from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.database import get_db
from app.models.auth_v3_models import AuthSession
from app.services.auth_service import decode_access_token, get_user_by_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode JWT and return the real user from DB."""
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def require_role(*roles: str):
    """Dependency factory that requires the user to have one of the given roles."""

    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {', '.join(roles)}",
            )
        return user

    return role_checker


async def get_workspace_context(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get workspace context for the current user (H4 Phase 2 — replaces Tenant).

    Resolves the user's workspace memberships and picks the primary one
    using explicit role priority: owner(3) > admin(2) > member(1) > viewer(0).
    Uses a single JOIN query instead of N+1.
    """
    from sqlalchemy import case

    from app.models.workspace_models import Workspace, WorkspaceMember

    # Explicit role priority — matches _ROLE_HIERARCHY in permission_service.py
    role_priority = case(
        (WorkspaceMember.role == "owner", 3),
        (WorkspaceMember.role == "admin", 2),
        (WorkspaceMember.role == "member", 1),
        else_=0,
    ).label("priority")

    result = await db.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(role_priority.desc())
    )
    rows = result.all()

    workspaces = [{"workspace": row.Workspace, "role": row.WorkspaceMember.role} for row in rows]

    primary = workspaces[0] if workspaces else None  # highest priority first

    return {
        "user": user,
        "workspaces": workspaces,
        "primary_workspace": primary["workspace"] if primary else None,
        "primary_workspace_id": primary["workspace"].id if primary else None,
        "primary_role": primary["role"] if primary else None,
        "is_workspace_owner": primary["role"] == "owner" if primary else False,
        "is_workspace_admin": (primary["role"] in ("owner", "admin") if primary else False),
        # Deprecated compat keys (H4 Phase 3 will remove)
        "tenant": None,
        "tenant_id": None,
        "member_role": None,
        "is_tenant_owner": False,
        "is_tenant_admin": False,
    }


def require_tenant_admin():
    """Dependency that requires workspace admin or owner role (was: tenant admin).

    H4 Phase 2: now checks workspace membership instead of tenant membership.
    """

    async def checker(
        ctx: dict = Depends(get_workspace_context),
    ) -> dict:
        if not ctx.get("primary_workspace_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No workspace associated with this account",
            )
        if not ctx.get("is_workspace_admin") and not ctx.get("is_workspace_owner"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace admin access required",
            )
        return ctx

    return checker


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of 401 for unauthenticated."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        user_id = decode_access_token(token)
        if user_id is None:
            return None
        user = await get_user_by_id(db, int(user_id))
        if user and user.is_active:
            return user
    except Exception:
        logger.debug("optional_user_decode_failed", exc_info=True)
    return None


def require_permission(permission_key: str) -> Callable:
    """FastAPI dependency factory - checks if the current user has permission_key.

    Resolution order:
    1. Superusers / is_admin -> always pass
    2. System role hierarchy (owner > admin > member > viewer)
    3. Custom role permissions
    4. Active delegations
    """

    async def _check(
        request: Request,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Superuser / admin bypass
        if user.is_superuser or user.is_admin:
            return user

        # Resolve workspace from query param or header (backward compat: also check tenant_id)
        workspace_id = (
            request.query_params.get("workspace_id")
            or request.headers.get("X-Workspace-Id")
            or request.query_params.get("tenant_id")  # H4 Phase 3 backward compat
            or request.headers.get("X-Tenant-Id")  # H4 Phase 3 backward compat
        )

        from app.services.permission_service import PermissionService

        has = await PermissionService.check(db, user.id, workspace_id, permission_key)
        if not has:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )
        return user

    return _check


# ---------------------------------------------------------------------------
# Auth v3 dependencies — session-based auth (httpOnly cookie + Bearer token)
# ---------------------------------------------------------------------------


async def get_current_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthSession:
    """Auth v3 dependency — resolve the authenticated session.

    Resolution order:
    1. httpOnly cookie (set by POST /auth/sessions)
    2. Authorization: Bearer <access_token> header

    Returns the AuthSession ORM object with .user eagerly loaded.
    """
    token_payload: dict | None = None

    # 1. Try httpOnly refresh cookie
    refresh_token = request.cookies.get("fm_refresh_token")
    if refresh_token:
        token_payload = decode_access_token(refresh_token)

    # 2. Fall back to Bearer token header
    if token_payload is None:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_payload = decode_access_token(auth_header[7:])

    if token_payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required — provide a valid session cookie or Bearer token",
        )

    user_id = token_payload.get("sub")
    session_id = token_payload.get("session_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token — missing user ID",
        )

    # Look up the active session — match by session_id if available, else by user_id
    query = select(AuthSession).where(
        AuthSession.user_id == int(user_id),
        AuthSession.is_active == True,
    )
    query = query.where(AuthSession.id == session_id) if session_id else query.where(AuthSession.revoked_at.is_(None))

    query = query.order_by(AuthSession.created_at.desc()).limit(1)
    result = await db.execute(query)
    session = result.scalars().first()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or revoked — please log in again",
        )

    # Eagerly load the user relationship
    user = await get_user_by_id(db, int(session.user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or disabled",
        )

    session.user = user
    return session


async def get_workspace_id(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> str | None:
    """Resolve workspace_id for the current request.

    Resolution order:
    1. X-Workspace-Id header or workspace_id query param
    2. User's primary workspace (highest role priority)
    3. None (no workspace context — caller decides how to handle)
    """
    from sqlalchemy import case

    from app.models.workspace_models import WorkspaceMember

    workspace_id = request.headers.get("X-Workspace-Id") or request.query_params.get("workspace_id")

    if workspace_id:
        # Validate membership
        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.is_active == True,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            return workspace_id
        # Explicit workspace but no membership — return None so caller can decide
        # (endpoint may raise 403, or fall back to user-scoped access)
        logger.warning(
            "workspace_access_denied user_id=%s workspace_id=%s reason=no_membership",
            user.id,
            workspace_id,
        )
        try:
            import asyncio

            from app.api.middleware.audit import log_event

            asyncio.create_task(
                log_event(
                    user_id=user.id,
                    action="workspace.access_denied",
                    details={"workspace_id": workspace_id, "reason": "no_membership"},
                )
            )
        except Exception:
            pass  # audit logging must never break the request
        return None

    # Auto-detect: pick highest-priority workspace
    role_priority = case(
        (WorkspaceMember.role == "owner", 3),
        (WorkspaceMember.role == "admin", 2),
        (WorkspaceMember.role == "member", 1),
        else_=0,
    ).label("priority")

    result = await db.execute(
        select(WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.is_active == True,
        )
        .order_by(role_priority.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


def require_scope(*required_scopes: str):
    """Auth v3 dependency factory — require specific OAuth2-style scopes.

    Usage:
        @router.post("/workspaces")
        async def create_workspace(
            session: AuthSession = Depends(require_scope("workspaces:write")),
        ):
            ...
    """

    async def _check(
        session: AuthSession = Depends(get_current_session),
    ) -> AuthSession:
        if session.scopes is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No scopes assigned to this session",
            )
        granted = set(session.scopes)
        missing = set(required_scopes) - granted
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(sorted(missing))}",
            )
        return session

    return _check
