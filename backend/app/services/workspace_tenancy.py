"""Data-layer tenancy backstop — single source of truth for "can this caller see this row?".

This is the FIRST DRAFT of the shared membership helper proposed in
``docs/adr/ADR-003-tenancy-backstop.md``. It is **additive** — no call
site is migrated by this card. It exists so the regression suite
(``tests/test_tenancy_backstop_pg.py``) can pin its behaviour, and so a
later migration card has a ready-made, tested primitive to route existing
``require_*`` guards through.

Design rules (fail-closed):
  * Absence of an explicit membership confirmation is a DENIAL.
  * ``workspace_id`` set  -> caller must be an active member (or hold a
    cross-workspace read grant).
  * ``is_global=True``    -> explicitly public; allowed (auditable opt-out).
  * ``workspace_id IS NULL`` and not ``is_global`` -> ambiguous legacy
    state. Default is DENIED. The legacy user-ownership fallback is an
    *explicit* opt-in via ``allow_legacy_owner_fallback`` so it can never
    be silently assumed.

The helper raises :class:`TenancyError`. Downstream call sites map that to
a 404 (never a 403 that would confirm existence to an attacker — see ADR).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TenancyError(Exception):
    """Raised when a caller is not permitted to access a tenant-scoped entity.

    Call sites should map this to HTTP 404 (not 403) so an unauthorized
    caller cannot distinguish "exists but denied" from "does not exist".
    """

    def __init__(
        self,
        *,
        entity_type: str,
        entity_id: str | int,
        workspace_id: str | None,
        user_id: int,
        reason: str,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.reason = reason
        super().__init__(
            f"tenancy_denied entity_type={entity_type} entity_id={entity_id} "
            f"workspace_id={workspace_id} user_id={user_id} reason={reason}"
        )


async def _is_active_member(
    db: AsyncSession, workspace_id: str, user_id: int
) -> bool:
    """Return True iff ``user_id`` is an active member of ``workspace_id``."""
    from app.models.workspace_models import WorkspaceMember

    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none() is not None


async def _has_cross_workspace_grant(
    db: AsyncSession,
    *,
    user_id: int,
    target_workspace_id: str,
    entity_type: str,
    entity_id: str | int,
) -> bool:
    """Check cross-workspace read grants the caller's workspaces hold for this entity."""
    from app.services.cross_workspace_service import (
        check_entity_access,
        find_user_workspaces,
    )

    user_workspaces = await find_user_workspaces(db, user_id)
    for ws_id in user_workspaces:
        if ws_id == target_workspace_id:
            continue  # already checked direct membership above
        grant = await check_entity_access(
            db,
            user_id=user_id,
            target_workspace_id=ws_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            required_permission="read",
        )
        if grant:
            return True
    return False


async def verify_entity_tenancy(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str | int,
    workspace_id: str | None,
    user_id: int,
    owner_user_id: int | None = None,
    is_global: bool = False,
    allow_legacy_owner_fallback: bool = False,
) -> bool:
    """Enforce that ``user_id`` may access the entity described by the args.

    Returns ``True`` if access is permitted. Raises :class:`TenancyError`
    (fail-closed) otherwise.

    Parameters
    ----------
    entity_type:
        Logical type, e.g. ``"mission"``, ``"chat_thread"``, ``"memory"``.
    entity_id:
        The row's primary key (for audit logging only — never trusted for
        the access decision; the decision comes from ``workspace_id``).
    workspace_id:
        The row's ``workspace_id`` (read from the entity, not caller input).
    user_id:
        The authenticated caller.
    owner_user_id:
        For legacy ``workspace_id IS NULL`` rows: the row's owning user id.
        Only consulted when ``allow_legacy_owner_fallback=True``.
    is_global:
        Row is explicitly public/non-tenant (e.g. a system entity).
    allow_legacy_owner_fallback:
        Explicit opt-in to permit ``workspace_id IS NULL`` rows when the
        caller *is* the owner. Default ``False`` = deny. This flag exists so
        the insecure fallback can never be the implicit default.
    """
    # 1. Explicitly global entities are readable by anyone.
    if is_global:
        return True

    # 2. Workspace-scoped entities require active membership (or a grant).
    if workspace_id:
        if await _is_active_member(db, workspace_id, user_id):
            return True
        if await _has_cross_workspace_grant(
            db,
            user_id=user_id,
            target_workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id=entity_id,
        ):
            return True
        logger.warning(
            "tenancy_denied user_id=%s entity_type=%s entity_id=%s "
            "workspace_id=%s reason=no_membership",
            user_id,
            entity_type,
            entity_id,
            workspace_id,
        )
        raise TenancyError(
            entity_type=entity_type,
            entity_id=entity_id,
            workspace_id=workspace_id,
            user_id=user_id,
            reason="no_membership",
        )

    # 3. Ambiguous legacy state: workspace_id IS NULL and not global.
    #    Fail closed unless the caller explicitly opts into owner fallback
    #    AND actually owns the row.
    if allow_legacy_owner_fallback and owner_user_id is not None:
        if owner_user_id == user_id:
            return True
        logger.warning(
            "tenancy_denied user_id=%s entity_type=%s entity_id=%s "
            "workspace_id=None reason=legacy_owner_mismatch",
            user_id,
            entity_type,
            entity_id,
        )
        raise TenancyError(
            entity_type=entity_type,
            entity_id=entity_id,
            workspace_id=None,
            user_id=user_id,
            reason="legacy_owner_mismatch",
        )

    logger.warning(
        "tenancy_denied user_id=%s entity_type=%s entity_id=%s "
        "workspace_id=None reason=no_scope_is_null",
        user_id,
        entity_type,
        entity_id,
    )
    raise TenancyError(
        entity_type=entity_type,
        entity_id=entity_id,
        workspace_id=None,
        user_id=user_id,
        reason="no_scope_is_null",
    )


def workspace_scoped_stmt(
    stmt,
    workspace_column,
    caller_workspace_ids: Iterable[str],
    *,
    is_global_column=None,
):
    """AND tenant scoping onto a SELECT so a forgotten join returns *no* rows.

    Parameters
    ----------
    stmt:
        A SQLAlchemy ``select(...)`` (or select-compatible) statement.
    workspace_column:
        The entity's ``workspace_id`` column expression.
    caller_workspace_ids:
        Workspaces the caller belongs to. Rows must belong to one of them.
    is_global_column:
        Optional column; when provided, rows where this is true are also
        permitted (explicit public entities).

    Returns the mutated statement. A caller that omits this helper gets all
    rows (current unsafe default); a caller that applies it but passes an
    empty workspace list gets ZERO rows (safe default — fail closed).
    """
    ids = list(caller_workspace_ids)
    if is_global_column is not None:
        predicate = (workspace_column.in_(ids)) | (is_global_column == True)  # noqa: E712
    else:
        predicate = workspace_column.in_(ids)
    return stmt.where(predicate)
