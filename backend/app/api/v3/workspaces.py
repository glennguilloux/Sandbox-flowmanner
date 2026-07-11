"""v3 workspace routes — membership-scoped, NOT scope-middleware-scoped.

Authorization model (see backend/app/api/v3/AGENTS.md):
  * every endpoint is gated first by the WORKSPACES_V3_ENDPOINTS
    feature flag (`_require_workspaces_v3`), then by explicit
    WorkspaceMember membership (`_check_workspace_access`).
  * destructive / management endpoints additionally require an
    owner / admin..owner role subset (see `required_roles`).

Why NOT ScopeValidationMiddleware (app/middleware/scope_validator.py):
  that middleware is a per-route OAuth2-style scope gate that only fires
  for routes registered via `register_scope_requirement(...)`. As of this
  writing NO route in the repo registers a scope requirement, so the
  middleware enforces nothing for /api/v3/*. These workspace routes are
  intentionally membership-scoped (workspace ownership / role), which is a
  different and stricter contract than a bearer-token scope subset. Adding
  scope registration here would be redundant defense-in-depth (admin/owner
  already short-circuit the middleware at scope_validator.py:40) and is
  deliberately out of scope. If scope gating is ever desired for v3, that
  is a separate design decision tracked outside this file.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import UUID as SA_UUID
from sqlalchemy import MetaData, select, text

from app.api.deps import get_current_user
from app.api.middleware.audit import log_event
from app.api.v3.base import ok
from app.database import get_db
from app.models.agent import Agent
from app.models.blueprint_models import Blueprint
from app.models.chat import ChatThread
from app.models.hitl_models import InboxItem
from app.models.memory_models import MemoryEntry, PendingWrite
from app.models.mission_models import Mission
from app.models.playground_models import PlaygroundSandbox
from app.models.user import User
from app.models.workspace_models import Workspace, WorkspaceMember
from app.schemas.workspace_v3 import (
    WorkspaceCreateRequest,
    WorkspaceListItem,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.services.background_task_manager import background_task_manager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/workspaces", tags=["v3-workspaces"])


async def _require_workspaces_v3(db: AsyncSession) -> None:
    result = await db.execute(
        __import__("sqlalchemy").text(
            "SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_ENDPOINTS'"
        )
    )
    if not result.scalar():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


async def _check_workspace_access(
    db: AsyncSession,
    workspace_id: str,
    user_id: int,
    required_roles: list[str] | None = None,
) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if required_roles and membership.role not in required_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return membership


@router.get("", status_code=status.HTTP_200_OK)
async def list_workspaces(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)

    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
    memberships = result.scalars().all()

    workspaces = []
    for m in memberships:
        ws_result = await db.execute(select(Workspace).where(Workspace.id == m.workspace_id))
        ws = ws_result.scalar_one_or_none()
        if ws and ws.is_active:
            workspaces.append(
                WorkspaceListItem(
                    id=ws.id,
                    name=ws.name,
                    slug=ws.slug,
                    plan=ws.plan,
                    member_count=0,
                    logo_url=ws.logo_url,
                    role=m.role,
                    created_at=ws.created_at,
                ).model_dump(mode="json")
            )

    return ok(workspaces)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)

    ws_id = str(uuid.uuid4())
    slug = payload.slug or payload.name.lower().replace(" ", "-").replace("_", "-")

    existing = await db.execute(select(Workspace).where(Workspace.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")

    ws = Workspace(id=ws_id, name=payload.name, slug=slug, owner_id=user.id)
    db.add(ws)
    db.add(WorkspaceMember(workspace_id=ws_id, user_id=user.id, role="owner"))
    await db.flush()
    await db.refresh(ws)

    # Tenant-scoped audit trail (fire-and-forget, consistent with deps.py:408).
    # Records the workspace that was created, scoped by its workspace_id.
    background_task_manager.spawn(
        log_event(
            user_id=user.id,
            action="workspace.create",
            details={
                "workspace_id": ws.id,
                "name": ws.name,
                "slug": ws.slug,
                "owner_id": user.id,
            },
        ),
        label="audit.workspace.create",
    )

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=1,
            member_limit=ws.member_limit or 5,
            logo_url=ws.logo_url,
            settings=ws.settings or {},
            storage_used_bytes=ws.storage_used_bytes or 0,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        ).model_dump(mode="json")
    )


@router.get("/{workspace_id}", status_code=status.HTTP_200_OK)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id)

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    member_count_result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    member_count = len(member_count_result.scalars().all())

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=member_count,
            member_limit=ws.member_limit or 5,
            logo_url=ws.logo_url,
            settings=ws.settings or {},
            storage_used_bytes=ws.storage_used_bytes or 0,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        ).model_dump(mode="json")
    )


@router.patch("/{workspace_id}", status_code=status.HTTP_200_OK)
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id, ["admin", "owner"])

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if payload.name is not None:
        ws.name = payload.name
    if payload.logo_url is not None:
        ws.logo_url = payload.logo_url
    if payload.settings is not None:
        ws.settings = payload.settings

    await db.flush()
    await db.refresh(ws)

    # Tenant-scoped audit trail (fire-and-forget). Records the workspace that was
    # mutated, scoped by its workspace_id. Only the fields present in the payload
    # are noted in the audit details.
    changed = {}
    if payload.name is not None:
        changed["name"] = payload.name
    if payload.logo_url is not None:
        changed["logo_url"] = payload.logo_url
    if payload.settings is not None:
        changed["settings"] = payload.settings

    background_task_manager.spawn(
        log_event(
            user_id=user.id,
            action="workspace.update",
            details={
                "workspace_id": ws.id,
                "name": ws.name,
                **changed,
            },
        ),
        label="audit.workspace.update",
    )

    return ok(
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            member_count=0,
            member_limit=ws.member_limit or 5,
            logo_url=ws.logo_url,
            settings=ws.settings or {},
            storage_used_bytes=ws.storage_used_bytes or 0,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        ).model_dump(mode="json")
    )


# Tables that must never be pruned by a workspace delete. ``workspaces`` is
# the target row itself; these others are global/root system tables that
# carry a (nullable) workspace_id but must survive a workspace removal.
_PURGE_PROTECTED_TABLES = frozenset({"workspaces"})


def _ws_param_type(tables: dict, table_name: str) -> type:
    """Python type to bind ``:ws`` with for a table that owns workspace data.

    ``workspace_id`` columns are NOT uniformly typed across the schema: most
    are ``varchar`` (matching ``workspaces.id``), but a handful (e.g.
    ``episodes``, ``memory_action_events``) are ``uuid``. Binding the string
    workspace id against a uuid column raises a DataError, so we must coerce
    the value to the column's actual python type before executing.

    Pure inspection of the reflected metadata — no IO — so this is a plain
    (synchronous) function.
    """
    col = tables[table_name].columns["workspace_id"]
    if isinstance(col.type, SA_UUID):
        return uuid.UUID
    return str


async def _purge_workspace_children(db: AsyncSession, workspace_id: str) -> None:
    """Explicitly delete EVERY workspace-owned row BEFORE removing the workspace.
    ---------------------
    Several workspace-child tables declare their FK to ``workspaces.id`` with
    ``ondelete="SET NULL"`` (or, worse, NO ACTION / RESTRICT) rather than
    ``CASCADE`` (verified against the live schema). A bare ``db.delete(ws)``
    therefore either 500s with an integrity violation (NO ACTION) or, worse,
    silently orphans the child rows (SET NULL) — leaking the tenant's content
    into a workspace-less void. Some tables (``chat_threads``) have NO FK to
    ``workspaces`` at all and would be fully orphaned.

    Why a static table list is wrong (root cause)
    ----------------------------------------------
    An earlier implementation hard-coded the list of tables to purge. That list
    is incomplete (it missed e.g. ``user_api_keys``, ``agent_versions``,
    ``mission_sandboxes``, ``workflow_states``, ``program_runs``,
    ``role_permissions``, ``swarm_agents`` …) and silently DRIFTS whenever the
    schema gains a new workspace-owned table — precisely the orphan-leak class
    this card forbids. The correct fix is to derive the purge set from the
    LIVE schema itself.

    Schema-driven purge (no migration, no drift)
    ---------------------------------------------
    ``_compute_purge_plan`` reflects the foreign-key graph and returns a
    child-first ordered list of ``(table, predicate)`` pairs covering every
    table that owns workspace data. A table with its own ``workspace_id`` column
    is deleted with ``WHERE workspace_id = :ws``; a table that has NO
    ``workspace_id`` but references a parent that is itself being purged (e.g.
    ``mission_tasks`` via ``mission_id``) is deleted with an FK-join predicate
    ``WHERE <fk> IN (SELECT <parent.pk> FROM <parent> WHERE workspace_id = :ws)``.
    Children are always emitted before their parents so the parents' deletes are
    never blocked.

    Result: no surviving row references this workspace, the final
    ``db.delete(ws)`` is never blocked, and the fix stays correct across
    schema changes WITHOUT any Alembic migration (see card t_d043d05e: schema is
    Alembic-ONLY and we delete rows in code instead of changing ``ondelete``).
    Correctness against the live schema is asserted by
    ``app/tests/test_ws_delete_purge.py``.
    """
    tables = (await _reflect_tables(db)).tables
    for table, predicate, ws_owner in await _compute_purge_plan(db):
        # Coerce the bound value to the column's python type. ``workspace_id``
        # is ``varchar`` on most tables but ``uuid`` on a few (episodes,
        # memory_action_events); binding the raw string against a uuid column
        # raises a DataError, so type it per-table. ``ws_owner`` is the table
        # whose ``workspace_id`` column actually receives the bound :ws — for
        # FK-joined (grandchild) deletes this is the root ancestor, not the
        # row being deleted.
        param_type = _ws_param_type(tables, ws_owner)
        await db.execute(
            text(f"DELETE FROM {table} WHERE {predicate}"),
            {"ws": param_type(workspace_id)},
        )


async def _reflect_tables(db: AsyncSession) -> MetaData:
    """Reflect the live schema (reusing the session's engine) once.

    Shared by ``_compute_purge_plan`` (which signs the graph) and
    ``_purge_workspace_children`` (which needs the per-table ``workspace_id``
    column type to bind ``:ws`` correctly). Reflecting once avoids paying the
    introspection cost twice and keeps the two views of the schema consistent.
    """
    engine = db.bind
    meta = MetaData()
    async with engine.connect() as conn:
        await conn.run_sync(lambda sc: meta.reflect(bind=sc))
    return meta


async def _compute_purge_plan(db: AsyncSession) -> list[tuple[str, str, str]]:
    """Return ``(table, sql_predicate)`` pairs to purge, child-first.

    Reflects the live schema (reusing the session's engine) and computes the
    set of tables that own workspace data:

    * directly — they carry a ``workspace_id`` column, or
    * transitively — they FK into a table that is itself being purged.

    Grandchildren with no ``workspace_id`` column (e.g. ``mission_tasks`` via
    ``mission_id``) are reached through their parent (which has ``workspace_id``)
    and ordered BEFORE that parent. Their predicate joins through the FK.
    """
    meta = await _reflect_tables(db)

    if "workspaces" not in meta.tables:
        return []

    tables = meta.tables

    # child_table -> set of (parent_table, child_col, parent_col) FK edges.
    # `fk.parent` is the FK column on the child table; `fk.column` is the
    # referenced column (PK) on the parent table.
    fk_edges: dict[str, set[tuple[str, str, str]]] = {t: set() for t in tables}
    for table in tables.values():
        for fk in table.foreign_keys:
            target = fk.column.table
            if target.name in tables and target.name != table.name:
                child_col = fk.parent.name
                parent_col = fk.column.name
                fk_edges[table.name].add((target.name, child_col, parent_col))

    # Seed: tables whose ``workspace_id`` column is the SAME type as
    # ``workspaces.id`` (a varchar-36 string). A bare ``workspace_id`` column
    # is NOT sufficient on its own — the schema reuses the name for columns
    # that reference entirely DIFFERENT entities:
    #   * ``episodes`` / ``memory_action_events`` declare ``workspace_id`` as
    #     ``uuid`` — they point at some other (uuid) entity, NOT this
    #     workspace. Deleting those by this workspace's id would silently wipe
    #     unrelated rows. We must NOT seed them.
    #   * ``chat_templates`` declares ``workspace_id`` as ``int4`` (a real
    #     ``templates_workspaces`` FK, NOT ``workspaces.id``). Same hazard.
    # Only tables whose ``workspace_id`` type matches ``workspaces.id`` are
    # genuinely "owned by this workspace"; seed those. ``chat_threads`` is
    # included here (varchar, no FK) and is reached by the purge even though
    # it has no referential integrity to ``workspaces``.
    ws_id_col = tables["workspaces"].columns["id"]
    seeds = {
        t
        for t, table in tables.items()
        if "workspace_id" in table.columns and isinstance(table.columns["workspace_id"].type, type(ws_id_col.type))
    }

    # Closure: any table that references a table already in the set joins the
    # set (it belongs to a workspace being deleted). This pulls in
    # grandchildren (mission_tasks -> missions) and their children
    # (agent_capabilities -> agents) without needing a workspace_id.
    in_set: set[str] = set(seeds)
    changed = True
    while changed:
        changed = False
        for child, edges in fk_edges.items():
            if child in in_set:
                continue
            if {p for (p, _, _) in edges} & in_set:
                in_set.add(child)
                changed = True

    purge = in_set - _PURGE_PROTECTED_TABLES

    # Topological order: a child must be emitted BEFORE its parent. We compute
    # indegree by counting how many in-set *children* each table has (i.e. how
    # many tables reference it); a table with no in-set children is a leaf and
    # goes first. We then emit zero-indegree tables, decrementing parents.
    indegree: dict[str, int] = dict.fromkeys(purge, 0)
    children: dict[str, set[str]] = {t: set() for t in purge}
    for t in purge:
        for p, _, _ in fk_edges[t]:
            if p in purge and p != t:
                indegree[t] += 1  # t depends on p (t is a child of p)
                children[p].add(t)

    order: list[str] = []
    emitted: set[str] = set()
    # Leaf children (no in-set children of their own) emitted first.
    queue = deque(sorted(t for t in purge if indegree[t] == 0))
    while queue:
        t = queue.popleft()
        if t in emitted:
            continue
        order.append(t)
        emitted.add(t)
        for parent in sorted(children[t]):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)
    order.extend(sorted(purge - emitted))  # break any cycle deterministically
    # The topological walk above emits PARENT-first (a table before its
    # children). For a delete we need CHILD-first so a child is removed before
    # the parent it references. Reverse the order.
    order.reverse()

    # Emit (table, predicate).
    #   * A table that carries its own workspace_id is filtered directly.
    #   * Otherwise walk the FK graph from this table up to the nearest
    #     workspace_id-bearing ancestor and build a multi-hop EXISTS clause,
    #     e.g. ``trigger_logs`` -> ``mission_triggers`` -> ``missions`` becomes
    #         ``EXISTS (SELECT 1 FROM mission_triggers mt
    #                   JOIN missions m ON m.id = mt.mission_id
    #                  WHERE mt.id = trigger_logs.trigger_id
    #                    AND m.workspace_id = :ws)``.
    #     BFS guarantees the path terminates at a workspace-scoped root (the
    #     closure proved such a root exists) and never fabricates a
    #     workspace_id column on an intermediate table.
    plan: list[tuple[str, str, str]] = []
    for t in order:
        if "workspace_id" in tables[t].columns:
            # The bound :ws targets THIS table's own workspace_id column.
            plan.append((t, "workspace_id = :ws", t))
            continue
        # BFS over the in-set FK edges to find the path to a workspace_id root.
        path: list[tuple[str, str, str]] | None = None
        visited = {t}
        frontier: list[tuple[str, list[tuple[str, str, str]]]] = [(t, [])]
        while frontier and path is None:
            node, acc = frontier.pop(0)
            for p, child_col, parent_col in fk_edges[node]:
                if p not in purge or p in visited:
                    continue
                step = (p, child_col, parent_col)
                new_acc = [*acc, step]
                if "workspace_id" in tables[p].columns:
                    path = new_acc
                    break
                visited.add(p)
                frontier.append((p, new_acc))
        if path is None:
            # Defensive: should be unreachable (closure guarantees a root).
            continue
        # Build a multi-hop EXISTS that walks the FK graph from this table
        # up to the nearest workspace_id-bearing ancestor, JOINing each hop
        # explicitly. An earlier version emitted the join predicate into the
        # WHERE against a table that was never added to the FROM, which
        # raised "missing FROM-clause entry for table <parent>":
        #   EXISTS (
        #     SELECT 1 FROM <p0>
        #     JOIN <p1> ON <p1>.<pk1> = <p0>.<fk1>
        #     ...
        #     WHERE <p0>.<pk0> = <t>.<fk0>
        #       AND <root>.workspace_id = :ws
        #   )
        # where each (p_i, fk_i, pk_i) is one FK edge along the BFS path and
        # <root> is the last node (the workspace_id-bearing ancestor).
        first_p, first_child, first_parent = path[0]
        from_clause = f"FROM {first_p}"
        where = [f"{first_p}.{first_parent} = {t}.{first_child}"]
        chain_alias = first_p
        for i in range(1, len(path)):
            p, _cc, pc = path[i]
            prev_child_col = path[i][1]
            from_clause += f" JOIN {p} ON {p}.{pc} = {chain_alias}.{prev_child_col}"
            chain_alias = p
        root = path[-1][0]
        where.append(f"{root}.workspace_id = :ws")
        predicate = f"EXISTS (SELECT 1 {from_clause} WHERE {' AND '.join(where)})"
        # The bound :ws targets the ROOT ancestor's workspace_id column (not
        # this table's — FK-joined tables have no workspace_id of their own).
        plan.append((t, predicate, root))
    return plan


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id, ["owner"])

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Tenant-scoped audit trail (fire-and-forget). Capture the workspace_id and
    # name BEFORE the row is deleted so the event records the workspace that was
    # removed. Captured here (ahead of the purge) so the audit line survives
    # the deletion.
    deleted_workspace_id = ws.id
    deleted_name = ws.name

    # Purge workspace-owned children first (SET NULL / NO ACTION / orphaned
    # FKs) so the final workspace delete is unblocked and no tenant data
    # survives. Runs in the SAME db session / transaction as the delete.
    await _purge_workspace_children(db, workspace_id)
    await db.delete(ws)
    await db.flush()

    background_task_manager.spawn(
        log_event(
            user_id=user.id,
            action="workspace.delete",
            details={
                "workspace_id": deleted_workspace_id,
                "name": deleted_name,
            },
        ),
        label="audit.workspace.delete",
    )


@router.get("/{workspace_id}/members", status_code=status.HTTP_200_OK)
async def list_members(
    workspace_id: str,
    include: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_workspaces_v3(db)
    await _check_workspace_access(db, workspace_id, user.id)

    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    members = result.scalars().all()

    member_list = []
    for m in members:
        entry = {
            "user_id": m.user_id,
            "role": m.role,
            "joined_at": m.joined_at.isoformat(),
        }
        if include and "user" in include:
            user_result = await db.execute(select(User).where(User.id == m.user_id))
            u = user_result.scalar_one_or_none()
            if u:
                entry["email"] = u.email
                entry["full_name"] = u.full_name
                entry["avatar_url"] = u.avatar_url
        member_list.append(entry)

    return ok(member_list)
