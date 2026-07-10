# Task: Phase 5 — Permissions + Metering for Tool Calls

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P5 — production safety + billing
**Estimated effort:** 2 sessions
**Created:** 2026-07-05
**Depends on:** Phase 1 (tool registry) + Phase 4 (browser sandbox) ✅ complete
**Blocks:** Phase 6 (evals + prompt versioning)
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §Phase 5, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

1. **Capability tokens already exist in the substrate.** The draft invents a `require_tool_scope` factory as if authz doesn't exist. Per `substrate/AGENTS.md` rule #5: "All tool calls go through `CapabilityEngine.issue()` + `verify_and_require()`. `NodeExecutor._handle_tool` is the canonical implementation." Phase 5's authz wiring should reuse `CapabilityEngine` (already used by Phase 1's `_execute_tool_call` capability check), not invent a new `require_tool_scope` Dependency that bypasses it. The per-route `Depends(require_tool_scope(tool_name))` pattern from the draft is fine for HTTP routes but should delegate to the same scope-resolution logic — do not fork two authz paths.

2. **`require_scope(*required_scopes)` exists in `deps.py:358`** (verified). The `tool:call` scope can be added to this existing dependency rather than inventing a new factory. Read `deps.py:358` before writing `require_tool_scope`.

3. **`cost_tracker.py` already exists** in the `services/` cluster (per `services/AGENTS.md` §1 — "cost_tracker: Cost estimation + LLMCallRecord writes + Prometheus metrics. `record_llm_call()`. **No `db.commit()`.**"). The Phase 5 "cost_event per tool invocation" should extend the **existing** `cost_tracker.py` pattern — `record_tool_call_cost` follows `record_llm_call` shape. Do not write a separate `cost_tracker_tool.py`. Do NOT call `db.commit()` inside cost tracking — the calling route owns the transaction (services AGENTS.md rule #3).

4. **`analytics_service.py` exists** (per Phase 5's reference to `analytics.py`; verify the exact filename — `services/analytics_service.py` vs `services/analytics.py` via `ls` before coding). The rollup extension goes in the existing file, not a new module.

5. **The workspace `tool:call` scope lives in v3 cookies** by default — `deps.py:358 require_scope` is wired for the v3 `get_current_session` path. Phase 5 routes use v2 (`get_current_user`, JWT). Make sure the capability token verification references the v2 auth context, not v3 — the two have different session shapes.

---

## 🔴 Reference prototype patterns (from `.sisyphus/src/`)

### A. `tool_definitions` table — the Phase 1 + Phase 5 migration reference

From `db/schema.ts:174-187`:
```
id, name (UNIQUE), display_name, description, category (default 'utility'),
input_schema (JSONB), required_scopes (JSONB string[]), rate_limit_per_min (INTEGER),
requires_sandbox (BOOLEAN), requires_approval (BOOLEAN), is_enabled (BOOLEAN),
created_at
```

Note: the prototype has `requires_approval` as a separate boolean — this is the HITL flag. Phase 1's `ToolMetadata` additions should include `requires_approval` alongside `required_scopes`, `requires_sandbox`, `rate_limit_key`. The prototype also uses `rate_limit_per_min` (numeric ceiling) not `rate_limit_key` (grouping key) — Phase 1 should add both since they serve different purposes.

### B. `workspace_tool_permissions` table — the allowlist

From `db/schema.ts:189-202`:
```
id, workspace_id (TEXT), tool_id (UUID FK → tool_definitions.id CASCADE),
is_allowed (BOOLEAN DEFAULT TRUE), granted_by (TEXT), granted_at (TIMESTAMPTZ)
INDEX: (workspace_id, tool_id)
```

This is the exact shape for Phase 5's `workspace_tool_allowlist` migration. Note: the prototype uses `tool_id` as a UUID FK to `tool_definitions`, while the drafts' version uses `tool_name` as a string. The FK approach is cleaner (referential integrity) but requires the `tool_definitions` table to exist first. If the production backend keeps tools in the in-memory `ToolRegistry` (not a DB table), use `tool_name` as a string with an application-level check instead.

### C. Tool discovery endpoint with workspace filtering

`app/api/tools/route.ts:6-41` — the prototype's tool discovery endpoint:
1. Fetches all enabled tools from `tool_definitions`
2. Fetches workspace permissions from `workspace_tool_permissions`
3. Builds a set of allowed tool IDs
4. Returns tools with an `isAllowed` boolean per tool

This is the exact shape for Phase 1's `GET /api/v2/tools/discover` endpoint, extended in Phase 5 to enforce the allowlist during tool execution (not just discovery).

### D. `WorkspaceTool` type — the frontend contract

From `lib/types.ts:116-118`:
```typescript
export interface WorkspaceTool extends ToolDefinition {
  isAllowed: boolean;
}
```

The frontend receives the tool list with an `isAllowed` flag — tools that aren't allowed are hidden from the LLM's available tool set and from the workspace settings UI.

---

## Problem

Today, any tool call from the LLM executes without authorization checks or billing. The tool registry has `requires_auth` (a coarse boolean) and Phase 1 added `required_scopes: list[str]`, but the per-workspace allowlist doesn't exist. There's no per-workspace tool allowlist, no cost tracking per tool invocation, and no way for a workspace admin to control which tools are available.

**Goal:** Every tool call is authorized, scoped, metered, and billable. Workspace admins can toggle tools on/off. Blocked tool calls show a "Request access" card in chat.

---

## Acceptance Criteria

- [ ] `tool:call` scope added to `deps.py` auth system (extends existing `require_scope`, not a new factory)
- [ ] `workspace_tool_allowlist` table created via Alembic migration (sentinel `UPDATE` pattern per `backend/AGENTS.md` migration rules — never `DELETE`)
- [ ] Tool registry filters tools by workspace allowlist
- [ ] `cost_event` row created per tool invocation (extends `cost_tracker.py`, not a new file)
- [ ] `analytics_service.py` rollup includes tool-call counts and costs (extends existing file)
- [ ] Frontend workspace settings page has tool allowlist toggle UI
- [ ] Blocked tool calls render as "Request access" card in chat
- [ ] `pnpm lint && pnpm build` passes
- [ ] Backend tests pass: `test_workspace_tool_allowlist.py`, `test_tool_call_billing.py`

---

## Sub-tasks

### 5.1 — Add tool:call scope (backend)

**File:** `backend/app/api/deps.py:358`

Add `tool:call` to the scope system by extending the existing `require_scope(*required_scopes: str)`:

```python
TOOL_CALL_SCOPE = "tool:call"

def require_tool_scope(tool_name: str):
    """Dependency that checks if the calling user has permission to invoke a specific tool.
    Uses the existing require_scope() path — does NOT fork a second authz flow."""
    async def _check(user = Depends(get_current_user), db = Depends(get_db)):
        # Check workspace allowlist (5.3)
        allowlist = await get_workspace_tool_allowlist(db, user.workspace_id)
        if tool_name not in allowlist:
            raise HTTPException(403, f"Tool '{tool_name}' not enabled for this workspace")
        return user
    return _check
```

**⚠ Read `deps.py:358` first** to confirm the existing `require_scope` shape and avoid forking two authz paths. The new dependency delegates to the same scope-resolution logic as `require_scope`, then adds the workspace-allowlist check on top.

### 5.2 — Create workspace_tool_allowlist table (backend)

**Create model:** add to `backend/app/models/workspace_models.py` (or whatever the existing workspace models file is — read `backend/app/models/` first):

```python
class WorkspaceToolAllowlist(Base):
    __tablename__ = "workspace_tool_allowlist"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    tool_name = Column(String, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
    granted_by = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "tool_name", name="uq_workspace_tool"),
    )
```

**Migration:** `backend/alembic/versions/xxx_workspace_tool_allowlist.py`

```python
def upgrade():
    op.create_table(
        "workspace_tool_allowlist",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workspace_id", sa.String, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("tool_name", sa.String, nullable=False),
        sa.Column("granted_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("granted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.UniqueConstraint("workspace_id", "tool_name", name="uq_workspace_tool"),
    )

def downgrade():
    op.drop_table("workspace_tool_allowlist")
```

**Pre-flight:** `SELECT COUNT(*) FROM workspaces` to assess impact. No data migration needed (default: no entries → all tools permitted, see 5.3).

### 5.3 — Wire allowlist to tool registry (backend)

**File:** `backend/app/tools/base.py`

Add filtering method to `ToolRegistry`:

```python
def get_permitted_tools(self, allowed_tool_names: list[str] | None = None) -> list[BaseTool]:
    """Return tools filtered by workspace allowlist. If allowlist is None, return all."""
    if allowed_tool_names is None:
        return self.list_all()
    return [t for t in self.list_all() if t.tool_id in allowed_tool_names]
```

**File:** `backend/app/services/chat_service.py`

Update `_get_chat_openai_tools()` to accept `workspace_id` and filter by allowlist (this changes the existing function shape at `chat_service.py:1352` — update both the non-streaming and streaming call sites):

```python
async def _get_chat_openai_tools(db: AsyncSession, workspace_id: str | None = None) -> list[dict] | None:
    if not settings.SANDBOXD_ENABLED:
        return None
    try:
        from app.tools.base import get_tool_registry
        registry = get_tool_registry()
        if workspace_id:
            allowlist = await get_workspace_tool_allowlist(db, workspace_id)
            tools = registry.get_permitted_tools(allowlist)
        else:
            tools = registry.list_all()
        # Existing Phase 1 sandboxd_ids + Phase 4 browser_sandbox filter goes here
        return [t.to_openai_schema() for t in tools if t.tool_id in _CHAT_TOOL_ALLOWLIST] or None
    except Exception:
        logger.debug("Failed to get chat tools from registry", exc_info=True)
        return None
```

**Default behavior:** if no allowlist entries exist for a workspace, **all** tools are permitted (returns `None` from `get_workspace_tool_allowlist` → `get_permitted_tools(None)` → `list_all()`). This is backwards compatible — only restrict when explicitly configured.

### 5.4 — Add cost_event per tool invocation (backend)

**File:** `backend/app/services/cost_tracker.py`

Add `record_tool_call_cost()` following the existing `record_llm_call` pattern (read `cost_tracker.py` first to match the convention; rule #3 from `services/AGENTS.md`: no `db.commit()` inside the tracker):

```python
async def record_tool_call_cost(
    user_id: int,
    tool_name: str,
    duration_ms: float,
    workspace_id: str | None = None,
    db: AsyncSession = None,
):
    """Record a tool call as a billable cost event. Do NOT commit — caller owns the transaction."""
    cost_event = CostEvent(
        user_id=user_id,
        event_type="tool_call",
        tool_name=tool_name,
        duration_ms=duration_ms,
        workspace_id=workspace_id,
        cost_usd=_calculate_tool_cost(tool_name, duration_ms),
    )
    db.add(cost_event)
    # No db.commit() — per services/AGENTS.md rule #3
```

**File:** `backend/app/services/chat_service.py`

After each tool call in the streaming loop:

```python
# In stream_message_to_llm, after tool execution:
from app.services.cost_tracker import record_tool_call_cost
import asyncio

# Fire-and-forget (cost tracking must not block the tool result):
asyncio.create_task(record_tool_call_cost(
    user_id=user_id,
    tool_name=tool_name,
    duration_ms=duration_ms,
    workspace_id=workspace_id,
    db=fresh_session,  # fire-and-forget needs its own session
))
```

⚠ Fire-and-forget cost tracking needs its own `AsyncSessionLocal` (not the request's session, which closes when the response ends). Follow the `_schedule_fire_and_forget()` pattern in `_mission_cqrs/base.py` if available.

### 5.5 — Analytics rollup (backend)

**File:** `backend/app/services/analytics_service.py` (verify exact filename via `ls backend/app/services/analytics*`)

Extend rollup queries to include tool-call counts and costs:

```sql
-- Add to existing analytics rollup
SELECT
    tool_name,
    COUNT(*) as call_count,
    AVG(duration_ms) as avg_duration,
    SUM(cost_usd) as total_cost
FROM cost_events
WHERE event_type = 'tool_call'
GROUP BY tool_name
```

### 5.6 — Tool allowlist management UI (frontend)

**Create:** `frontend/src/components/settings/ToolAllowlist.tsx`

Workspace settings page:
- List all available tools (from `GET /api/v2/tools/discover` — Phase 1)
- Toggle switch per tool
- Shows: tool name, description, category, required scopes
- Bulk enable/disable by category
- Save button → `PUT /api/v2/workspaces/{id}/tools`

### 5.7 — Add workspace tool management endpoint (backend)

**File:** `backend/app/api/v2/workspaces.py` (already exists — extend it)

```python
@router.get("/workspaces/{workspace_id}/tools")
async def list_workspace_tools(workspace_id: str, ...):
    """List all tools and their enabled status for this workspace."""
    registry = get_tool_registry()
    allowlist = await get_workspace_tool_allowlist(db, workspace_id)
    return ok({
        "tools": [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "enabled": t.tool_id in allowlist,
                "required_scopes": t.metadata.required_scopes,
            }
            for t in registry.list_all()
        ]
    })

@router.put("/workspaces/{workspace_id}/tools")
async def update_workspace_tools(workspace_id: str, body: UpdateToolsRequest, ...):
    """Update the tool allowlist for this workspace."""
    # Upsert into workspace_tool_allowlist (sentinel pattern — INSERT, not DELETE)
```

### 5.8 — Request access card (frontend)

**File:** `frontend/src/components/chat/PermissionCard.tsx` (already created in Phase 2)

Extend for blocked tool calls (403 from allowlist):

```tsx
// When a tool call returns 403 (tool not in allowlist):
{step.tool_invocation?.status === 'error' && step.tool_invocation?.error?.includes('not enabled') && (
  <div className="border-amber-500 bg-amber-50 p-4 rounded-lg">
    <p className="font-medium">Tool not available: {step.name}</p>
    <p className="text-sm text-muted-foreground">
      This tool is not enabled for your workspace.
    </p>
    <Button onClick={() => requestToolAccess(step.name)}>
      Request Access
    </Button>
  </div>
)}
```

`Request Access` → `POST /api/v2/workspaces/{id}/tools/request` → notifies workspace admins.

### 5.9 — Tests

**Backend:**
- `test_workspace_tool_allowlist.py`: CRUD operations, filtering, unique constraint
- `test_tool_call_billing.py`: cost event recording, analytics rollup, fire-and-forget session independence

**Frontend:**
- Manual: workspace without `tool:browser-sandbox` → agent tries to browse → request-access card appears

### 5.10 — Verification gate

```bash
# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/test_workspace_tool_allowlist.py -v
docker compose exec backend pytest app/tests/test_tool_call_billing.py -v

# Frontend
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build

# Manual: toggle a tool off in workspace settings, try to use it in chat →
#        request-access card appears
```

---

## File Map

| File | Action |
|------|--------|
| `backend/app/api/deps.py` | Extend `require_scope` with `tool:call` + `require_tool_scope` (no fork) |
| `backend/app/models/workspace_models.py` | Add `WorkspaceToolAllowlist` model |
| `backend/alembic/versions/xxx_workspace_tool_allowlist.py` | **NEW** — migration (sentinel INSERT, no DELETE) |
| `backend/app/tools/base.py` | Add `get_permitted_tools()` method |
| `backend/app/services/chat_service.py` | Wire allowlist + cost tracking into the tool dispatch path |
| `backend/app/services/cost_tracker.py` | Add `record_tool_call_cost()` (no `db.commit()`) |
| `backend/app/services/analytics_service.py` | Extend rollup with tool-call metrics |
| `backend/app/api/v2/workspaces.py` | Add tool allowlist CRUD endpoints |
| `backend/tests/test_workspace_tool_allowlist.py` | **NEW** — allowlist tests |
| `backend/tests/test_tool_call_billing.py` | **NEW** — billing tests |
| `frontend/src/components/settings/ToolAllowlist.tsx` | **NEW** — toggle UI |

---

## Migration Notes

- The `workspace_tool_allowlist` table uses a sentinel `INSERT` pattern (not `DELETE`) per `backend/AGENTS.md` migration rules.
- Pre-flight: `SELECT COUNT(*) FROM workspaces` to assess impact.
- Default behavior: if no allowlist entries exist for a workspace, **ALL** tools are permitted (backwards compatible — `get_permitted_tools(None)` returns `list_all()`).
- The migration is a pure `CREATE TABLE` — no data mutation, no sentinel UPDATE needed for new tables.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Breaking existing tool calls with new auth checks | Default: no allowlist entries → all tools permitted. Only restrict when explicitly configured. |
| Performance: allowlist query on every tool call | Cache allowlist in Redis per workspace (TTL 5min). |
| Cost tracking adds latency to tool calls | Fire-and-forget: `asyncio.create_task(record_tool_call_cost(...))` — don't block the tool result. Use its own `AsyncSessionLocal`. |
| Forking two authz paths (one for routes, one for the substrate) | `require_tool_scope` delegates to `require_scope` for the scope check, then adds the allowlist check on top. Same CapabilityEngine is the substrate's source of truth — no second verify path. |
| `record_tool_call_cost` accidentally commits the request's session | Follow `services/AGENTS.md` rule #3 — no `db.commit()` inside cost tracking; fire-and-forget opens its own session. |
