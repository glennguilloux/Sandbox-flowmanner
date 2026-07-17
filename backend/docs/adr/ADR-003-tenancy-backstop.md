# ADR-003: Data-layer tenancy backstop (mandatory workspace scoping)

**Status:** Proposed (RFC — requires human approval before rollout)
**Date:** 2026-07-17
**Decision-maker:** Security Engineer (R7 swarm audit, §3 H3)
**Supersedes:** none — augments existing opt-in `workspace_id` checks

---

## Context

Tenant isolation in Flowmanner is **opt-in per call site**. An audit
(`REPORT.md` §3 H3) found the following:

- `backend/app/services/mission_service.py:53-92` (`require_mission_access`)
  falls back to `user_id` ownership when `workspace_id` is `null`.
- `get_workspace_id` (`backend/app/api/deps.py:366`) is **caller-supplied**
  from the `X-Workspace-Id` header / `workspace_id` query param and only
  *validates* membership — it does not *enforce* scoping downstream.
- Every entity read (`Mission`, `MemoryEntry`, `ChatThread`, …) currently
  relies on the individual endpoint/ handler remembering to AND the
  caller's workspace membership into its query, or to call the right
  `require_*` guard.

There is **no data-layer backstop**. Any endpoint that forgets the
membership join — or that scopes by `user_id` alone — silently exposes
another workspace's rows (classic BOLA / IDOR, OWASP A01 / A04). The blast
radius is every tenant's missions, memory, and chat history.

### Why this is hard to fix all at once

- ~60+ mission endpoints + memory + chat read paths.
- `workspace_id` is `nullable=True` on every entity (legacy user-scoped
  data predates workspaces).
- A full migration (making `workspace_id` non-nullable, backfilling,
  rewriting every query) is high-risk and must be staged.

This ADR therefore proposes a **backstop + incremental migration path**,
not a big-bang refactor. R7 implements only the design + a safe slice
(helper draft + regression tests). Full rollout is explicitly out of scope
for this card and requires human sign-off.

---

## Decision

### 1. Every tenant-scoped entity gets an explicit tenancy declaration

Add a non-nullable `workspace_id` **OR** an explicit `is_global` flag.

- New rows created inside a workspace MUST set `workspace_id`.
- Rows that legitimately belong to no workspace (system/global data) MUST
  set `is_global = True` instead of leaving `workspace_id = NULL`.
- `workspace_id IS NULL AND is_global IS FALSE` becomes an **invalid**
  state that the data layer refuses to return to a scoped caller.

This is the long-term goal achieved via a *later* migration card
(out of scope here). This ADR only locks the convention.

### 2. One shared membership helper — used by every read path

A single module, `app/services/workspace_tenancy.py`, owns the
"is this caller allowed to see this row?" decision. It **fails closed**:
absence of an explicit membership confirmation is a denial.

```python
# The only correct way to scope an entity read to a caller.
from app.services.workspace_tenancy import verify_entity_tenancy

entity = await verify_entity_tenancy(
    db,
    entity_type="mission",
    entity_id=mission_id,
    workspace_id=mission.workspace_id,   # from the row itself
    user_id=caller.id,
    owner_user_id=mission.user_id,        # for legacy null-workspace fallback
    is_global=getattr(mission, "is_global", False),
)
# returns the entity, or raises TenancyError (→ mapped to 404 downstream)
```

The helper encodes the policy **once**:

1. If `is_global` → allow (explicit opt-out, auditable).
2. If `workspace_id` is set → caller must be an **active** member of that
   workspace, OR hold a cross-workspace `read` grant
   (`cross_workspace_service.check_entity_access`).
3. If `workspace_id` is `NULL` and **not** `is_global` → this is ambiguous
   legacy state. The helper **treats it as denied by default** unless the
   caller passes `allow_legacy_owner_fallback=True` **and** `owner_user_id`
   matches. The default (fail-closed) is the security backstop; the
   fallback flag is an explicit, per-call-site opt-in for incremental
   migration.

### 3. A query-builder helper for list endpoints

```python
from app.services.workspace_tenancy import workspace_scoped_stmt

stmt = workspace_scoped_stmt(
    select(Mission), Mission.workspace_id, caller_workspace_ids
)
```

`workspace_scoped_stmt` ANDs `workspace_id IN (...)` (or `is_global`) onto
the statement so a list query **cannot** accidentally return cross-tenant
rows. A caller who forgets to apply it gets *no rows*, not *all rows*.

### 4. Migration strategy (future cards — NOT this one)

| Phase | Work | Risk |
|-------|------|------|
| 0 (this card) | ADR + helper draft + regression tests | none — additive |
| 1 | Route every *new* read path through the helper | low |
| 2 | Migrate high-value entities (`Mission`, `ChatThread`, `MemoryEntry`) one at a time, each behind its own PR + regression test | medium |
| 3 | Backfill `workspace_id` / set `is_global` on legacy null rows | medium |
| 4 | Make `workspace_id` `nullable=False` + DB constraint | high — separate card |

---

## Options considered

### Option A: Per-call-site hardening only (status quo + patch each bug)
Manually fix each endpoint as IDORs are found.

- Pro: no new abstraction.
- Con: **never converges** — 60+ paths, new ones added weekly; the next
  forgotten join is the next breach. Defense-in-depth absent.

### Option B: DB-level row security policy (Postgres RLS)
Enforce tenancy in the database via RLS, keyed on a session GUC.

- Pro: truly cannot be bypassed at the app layer.
- Con: requires a stable per-request `workspace_id` GUC, breaks multi-
  tenant admin/report queries, hard to test, large blast radius. Better
  as a *future* layer 2, not the first move.

### Option C (chosen): Shared fail-closed helper + incremental migration
App-layer backstop, one policy function, additive, testable per entity.

- Pro: converges (every path routed through one function), fails closed,
  no big-bang migration, each step independently reviewable + tested.
- Con: relies on developers actually calling the helper (mitigated by
  regression tests + future lint rule). Does not protect paths that
  bypass the service layer (mitigated in phase 4 by RLS as layer 2).

---

## Consequences

### Positive
- Single, auditable source of truth for "can this caller see this row?".
- Missing join → **denied**, not **exposed** (fail-closed).
- Each entity migration is independently testable; regressions caught by
  the suite added in this card.
- Cross-workspace grants and `is_global` handled uniformly.

### Negative / accepted trade-offs
- New abstraction to learn; lint/code-review discipline needed to ensure
  adoption (future: a CI check that every `*_by_id` handler calls the
  helper).
- Legacy `NULL workspace_id` rows need a backfill (phase 3) before the
  column can become non-nullable (phase 4).
- Helper adds one membership lookup per read (mitigated: cached /
  index-backed on `workspace_members(workspace_id, user_id)`).

### Risk if we do nothing
Continued IDOR exposure across all tenant data; any single forgotten join
is a full cross-tenant disclosure. Severity: **High** (OWASP A01/BOLA).

---

## References
- `REPORT.md` §3 H3 (Swarm audit — Security Engineer finding)
- `backend/app/services/mission_service.py:53` `require_mission_access`
- `backend/app/api/deps.py:366` `get_workspace_id`
- `backend/app/services/cross_workspace_service.py` (grant model)
- Regression suite: `backend/tests/test_tenancy_backstop_pg.py`
- Helper draft: `backend/app/services/workspace_tenancy.py`
