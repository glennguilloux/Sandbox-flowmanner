"""Permission engine — evaluates access from 4 sources.

Resolution order (first match wins):
1. System role hierarchy: owner > admin > member > viewer
2. Direct tenant member permissions (user_tenants.role → system role perms)
3. Custom role permissions (role_permissions via user_custom_roles junction)
4. Active delegations (role_delegations where now ∈ [starts_at, ends_at])
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_models import (
    RoleDelegation,
    UserCustomRole,
    UserTenant,
)

# System role hierarchy — higher index = more privilege
_ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 0,
    "member": 1,
    "admin": 2,
    "owner": 3,
}

# Permissions granted by each system role (mirrors seed migration)
_SYSTEM_ROLE_PERMS: dict[str, set[str]] = {
    "owner": {"admin.all"},
    "admin": {
        "missions.create",
        "missions.read",
        "missions.update",
        "missions.delete",
        "team.manage",
        "team.invite",
        "team.remove",
        "billing.view",
        "billing.manage",
        "roles.create",
        "roles.manage",
    },
    "member": {
        "missions.create",
        "missions.read",
        "missions.update",
        "missions.delete",
        "team.invite",
        "billing.view",
    },
    "viewer": {"missions.read", "billing.view"},
}


def _expand_system_perms(role_name: str) -> set[str]:
    """Return all permissions for a system role, including inherited ones."""
    level = _ROLE_HIERARCHY.get(role_name, -1)
    perms: set[str] = set()
    for name, lvl in _ROLE_HIERARCHY.items():
        if lvl <= level:
            perms |= _SYSTEM_ROLE_PERMS.get(name, set())
    return perms


class PermissionService:
    """Stateless evaluator — call ``check()`` or ``get_permissions()``."""

    @staticmethod
    async def check(
        db: AsyncSession,
        user_id: int,
        workspace_id: str | None,
        permission_key: str,
    ) -> bool:
        """Return True if *user_id* holds *permission_key* in *workspace_id*."""
        perms = await PermissionService.get_permissions(db, user_id, workspace_id)
        if "admin.all" in perms:
            return True
        return permission_key in perms

    @staticmethod
    async def get_permissions(
        db: AsyncSession,
        user_id: int,
        workspace_id: str | None,
    ) -> set[str]:
        """Collect every permission the user has in the given workspace."""
        perms: set[str] = set()

        # ── 1. Direct workspace membership (system role) ──────────────────
        if workspace_id:
            ut = (
                await db.execute(
                    select(UserTenant).where(
                        UserTenant.user_id == user_id,
                        UserTenant.workspace_id == workspace_id,
                    )
                )
            ).scalar_one_or_none()
            if ut:
                perms |= _expand_system_perms(ut.role)

        # ── 2. Custom roles assigned to this user in this workspace ───────
        if workspace_id:
            assigned = (
                (
                    await db.execute(
                        select(UserCustomRole).where(
                            UserCustomRole.user_id == user_id,
                            UserCustomRole.workspace_id == workspace_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for ucr in assigned:
                for rp in ucr.role.permissions:
                    perms.add(rp.permission_key)

        # ── 3. Active delegations ──────────────────────────────────────
        now = datetime.now(UTC)
        delegations = (
            (
                await db.execute(
                    select(RoleDelegation).where(
                        RoleDelegation.delegatee_id == user_id,
                        RoleDelegation.is_active == True,
                    )
                )
            )
            .scalars()
            .all()
        )
        for d in delegations:
            # Filter by workspace if specified
            if workspace_id and d.workspace_id and d.workspace_id != workspace_id:
                continue
            # Check time window
            if d.starts_at and d.starts_at > now:
                continue
            if d.ends_at and d.ends_at < now:
                continue
            # Grant the delegated role's permissions
            for rp in d.role.permissions:
                perms.add(rp.permission_key)

        return perms

    @staticmethod
    async def user_has_role_at_least(
        db: AsyncSession,
        user_id: int,
        workspace_id: str | None,
        min_role: str,
    ) -> bool:
        """Check if user's system role in workspace is >= min_role."""
        if not workspace_id:
            return False
        ut = (
            await db.execute(
                select(UserTenant).where(
                    UserTenant.user_id == user_id,
                    UserTenant.workspace_id == workspace_id,
                )
            )
        ).scalar_one_or_none()
        if not ut:
            return False
        return _ROLE_HIERARCHY.get(ut.role, -1) >= _ROLE_HIERARCHY.get(min_role, 0)
