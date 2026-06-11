"""Custom roles CRUD + permission management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.database import get_db
from app.models.auth_models import CustomRole, RolePermission, UserCustomRole
from app.models.user import User
from app.schemas.roles import (
    PermissionAdd,
    PermissionKeyResponse,
    RoleCreate,
    RoleListResponse,
    RoleResponse,
    RoleUpdate,
)

router = APIRouter(prefix="/roles", tags=["roles"])

# Canonical permission key catalogue
PERMISSION_CATALOGUE: list[PermissionKeyResponse] = [
    PermissionKeyResponse(key="admin.all", description="Full administrative access"),
    PermissionKeyResponse(key="missions.create", description="Create missions"),
    PermissionKeyResponse(key="missions.read", description="View missions"),
    PermissionKeyResponse(key="missions.update", description="Edit missions"),
    PermissionKeyResponse(key="missions.delete", description="Delete missions"),
    PermissionKeyResponse(key="team.manage", description="Manage team settings"),
    PermissionKeyResponse(key="team.invite", description="Invite team members"),
    PermissionKeyResponse(key="team.remove", description="Remove team members"),
    PermissionKeyResponse(key="billing.view", description="View billing info"),
    PermissionKeyResponse(key="billing.manage", description="Manage billing"),
    PermissionKeyResponse(key="roles.create", description="Create custom roles"),
    PermissionKeyResponse(key="roles.manage", description="Edit/delete custom roles"),
    PermissionKeyResponse(key="delegations.create", description="Create delegations"),
    PermissionKeyResponse(key="delegations.manage", description="Manage delegations"),
]


# ── helpers ─────────────────────────────────────────────────────────────


async def _get_role_or_404(role_id: str, db: AsyncSession, workspace_id: str | None = None) -> CustomRole:
    q = select(CustomRole).where(CustomRole.id == role_id)
    if workspace_id is not None:
        # Allow access to workspace-scoped roles AND global system roles
        q = q.where((CustomRole.workspace_id == workspace_id) | (CustomRole.workspace_id.is_(None)))
    role = (await db.execute(q)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def _resolve_workspace(user: User) -> str | None:
    """Derive workspace_id from user context. Falls back to None for global roles."""
    return getattr(user, "primary_workspace_id", None)


# ── endpoints ───────────────────────────────────────────────────────────


@router.get("", response_model=RoleListResponse)
async def list_roles(
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """List roles for the current workspace (system + custom)."""
    wid = workspace_id or _resolve_workspace(user)
    q = select(CustomRole).where((CustomRole.workspace_id == wid) | (CustomRole.workspace_id.is_(None)))
    result = await db.execute(q)
    roles = result.scalars().all()
    return RoleListResponse(
        roles=[RoleResponse.model_validate(r) for r in roles],
        total=len(roles),
    )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.create")),
):
    """Create a custom role with optional initial permissions."""
    wid = workspace_id or _resolve_workspace(user)

    # Check uniqueness within workspace
    existing = (
        await db.execute(
            select(CustomRole).where(
                CustomRole.workspace_id == wid,
                CustomRole.name == payload.name,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Role '{payload.name}' already exists")

    role = CustomRole(
        workspace_id=wid,
        name=payload.name,
        description=payload.description,
        created_by=user.id,
        is_system=False,
    )
    db.add(role)
    await db.flush()

    for pk in payload.permission_keys:
        db.add(RolePermission(role_id=role.id, permission_key=pk))
    await db.flush()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.get("/permissions", response_model=list[PermissionKeyResponse])
async def list_permission_keys(
    user: User = Depends(get_current_user),
):
    """List all available permission keys (reference catalogue)."""
    return PERMISSION_CATALOGUE


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: str,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get role details with permissions."""
    wid = workspace_id or _resolve_workspace(user)
    role = await _get_role_or_404(role_id, db, wid)
    return RoleResponse.model_validate(role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str,
    payload: RoleUpdate,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """Update a custom role's name/description.  System roles are immutable."""
    wid = workspace_id or _resolve_workspace(user)
    role = await _get_role_or_404(role_id, db, wid)
    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot modify system roles")

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    await db.flush()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: str,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """Delete a custom role.  System roles cannot be deleted."""
    wid = workspace_id or _resolve_workspace(user)
    role = await _get_role_or_404(role_id, db, wid)
    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system roles")
    await db.delete(role)
    await db.flush()


@router.post("/{role_id}/permissions", response_model=RoleResponse)
async def add_permission(
    role_id: str,
    payload: PermissionAdd,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """Add a permission key to a custom role."""
    wid = workspace_id or _resolve_workspace(user)
    role = await _get_role_or_404(role_id, db, wid)
    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot modify system roles")

    # Check for duplicate
    existing = (
        await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_key == payload.permission_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Permission already exists on role")

    db.add(RolePermission(role_id=role_id, permission_key=payload.permission_key))
    await db.flush()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.delete(
    "/{role_id}/permissions/{permission_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_permission(
    role_id: str,
    permission_key: str,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """Remove a permission key from a custom role."""
    wid = workspace_id or _resolve_workspace(user)
    role = await _get_role_or_404(role_id, db, wid)
    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot modify system roles")

    rp = (
        await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_key == permission_key,
            )
        )
    ).scalar_one_or_none()
    if not rp:
        raise HTTPException(status_code=404, detail="Permission not found on role")

    await db.delete(rp)
    await db.flush()


@router.post("/{role_id}/assign/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role_to_user(
    role_id: str,
    user_id: int,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """Assign a custom role to a user within the workspace."""
    wid = workspace_id or _resolve_workspace(user)
    if not wid:
        raise HTTPException(status_code=400, detail="workspace_id required")

    role = await _get_role_or_404(role_id, db, wid)
    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot assign system roles via this endpoint")

    # Check for existing assignment
    existing = (
        await db.execute(
            select(UserCustomRole).where(
                UserCustomRole.user_id == user_id,
                UserCustomRole.role_id == role_id,
                UserCustomRole.workspace_id == wid,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Role already assigned to user")

    db.add(
        UserCustomRole(
            user_id=user_id,
            role_id=role_id,
            workspace_id=wid,
            assigned_by=user.id,
        )
    )
    await db.flush()


@router.delete("/{role_id}/assign/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_role_from_user(
    role_id: str,
    user_id: int,
    workspace_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
):
    """Remove a custom role assignment from a user."""
    wid = workspace_id or _resolve_workspace(user)
    if not wid:
        raise HTTPException(status_code=400, detail="workspace_id required")

    ucr = (
        await db.execute(
            select(UserCustomRole).where(
                UserCustomRole.user_id == user_id,
                UserCustomRole.role_id == role_id,
                UserCustomRole.workspace_id == wid,
            )
        )
    ).scalar_one_or_none()
    if not ucr:
        raise HTTPException(status_code=404, detail="Role assignment not found")

    await db.delete(ucr)
    await db.flush()
