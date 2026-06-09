# sandboxd Integration — Phase 3 Exit Audit

**Date:** June 8, 2026
**Status:** Phase 3 COMPLETE ✅. Sandbox as a DAG Node — backend handler, blueprint seed, and frontend preview button all operational.

---

## Phase 3 Execution Summary

### Objective
Add `node_type: "sandbox"` to FlowManner's workflow DAG so sandbox containers can be orchestrated as first-class nodes in multi-step workflows, with live preview URLs surfaced in the chat UI.

### Result
**All deliverables complete. 118 sandbox unit tests pass. Sandbox DAG blueprint seeded. Frontend preview button wired up. TypeScript typecheck clean (0 errors).**

---

## Deliverables Completed

### 1. Backend — Sandbox Node Handler (Phase 3 Core)

**File:** `backend/app/services/substrate/node_executor.py`

Added `_handle_sandbox_node()` method (~150 lines) to `NodeExecutor`:

| Step | Action |
|------|--------|
| 1 | Create or reuse sandbox (mission-scoped via `SandboxService`, or ephemeral) |
| 2 | Optional snapshot checkpoint before execution |
| 3 | Write input files to workspace (`input_files` config) |
| 4 | Submit coding task via `POST /v1/sandboxes/{id}/tasks` |
| 5 | Stream SSE events for real-time progress |
| 6 | Return output on completion; handle errors gracefully |

**Config keys supported:**
- `template` — sandboxd template name (default `"react-standard"`)
- `task_prompt` — coding task prompt for sandboxd's AI agent
- `shared_workspace` — reuse existing sandbox for this mission
- `input_files` — dict of path→content to write before task
- `snapshot_before` — create snapshot before executing (rollback safety)

**Additional changes to `node_executor.py`:**
- Added imports: `SandboxdClient`, `get_sandboxd_client`, `SandboxService`
- Added lazy properties: `_sandbox_client`, `_sandbox_service`
- Added `case NodeType.SANDBOX` to `_dispatch()` method
- Added `json` import at module top (per code review)
- Typed `db` parameter as `AsyncSession` (per code review)
- Added `hasattr` guard for `ws_manager.broadcast_node_state()` (per code review)

### 2. Backend — NodeType Enum

**File:** `backend/app/services/substrate/workflow_models.py`

Added `SANDBOX = "sandbox"` to `NodeType` enum after `FAN_IN`.

### 3. Backend — Sandbox Event Types

**File:** `backend/app/models/substrate_models.py`

Added 7 sandbox event types to `SubstrateEventType`:

| Constant | Value |
|----------|-------|
| `SANDBOX_CREATED` | `sandbox.created` |
| `SANDBOX_FILES_WRITTEN` | `sandbox.files_written` |
| `SANDBOX_TASK_SUBMITTED` | `sandbox.task_submitted` |
| `SANDBOX_TASK_PROGRESS` | `sandbox.task_progress` |
| `SANDBOX_TASK_COMPLETED` | `sandbox.task_completed` |
| `SANDBOX_TASK_FAILED` | `sandbox.task_failed` |
| `SANDBOX_SNAPSHOT_CREATED` | `sandbox.snapshot_created` |

Added catch-all in `SubstrateRunState.apply()` before the final `case _:` fallthrough:
```python
case _ if event.type.startswith("sandbox."):
    pass  # Informational — no state change needed
```

### 4. Alembic Migration — Sandbox DAG Blueprint Template

**File:** `backend/alembic/versions/20260617_seed_sandbox_dag_blueprint.py`

Seeds a "Sandbox Code Runner" blueprint into the `blueprints` table:

| Field | Value |
|-------|-------|
| ID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` (deterministic) |
| Title | Sandbox Code Runner |
| Type | `dag` |
| Status | `published` |
| Category | `code-execution-and-development` |
| Nodes | 3 (generate_code → execute_in_sandbox → summarize_results) |

**DAG structure:**
1. `generate_code` (LLM) — Generates Python code from user's task description
2. `execute_in_sandbox` (sandbox) — Runs code in isolated Docker container with snapshot
3. `summarize_results` (LLM) — Analyzes sandbox output and produces summary

Chains from `seed_sandboxd_tools` (previous head). Idempotent (`ON CONFLICT DO NOTHING`). Clean downgrade.

**Migration verified in database:**
- `alembic current` → `seed_sandbox_dag_blueprint (head)`
- Blueprint query → `FOUND: id=a1b2c3d4..., title=Sandbox Code Runner, type=dag, status=published`

### 5. Frontend — Preview Button Integration (5 files)

| File | Change |
|------|--------|
| `src/lib/chat-types.ts` | Added `"sandboxd_exec"` to `ToolType` union, added `sandboxId?: string` to `ToolEvent` interface |
| `src/components/chat/ToolActivityFeed.tsx` | Added `Container` icon import, `sandboxd_exec` to `TOOL_ICONS`, `SandboxPreviewButton` import, conditional rendering when `tool.sandboxId` exists |
| `src/hooks/useStreaming.ts` | Added `lastSandboxIdRef` (captures `sandbox_id` from `sandbox.*` SSE events), passes to `addToolEvent`, resets in `finally` block |
| `src/lib/tool-event-parser.ts` | Added `sandboxd_exec` detection rules, `"Sandbox"` label in `formatToolName`, `sandboxId` to `ParsedToolEvent` |
| `src/components/chat/SandboxPreviewButton.tsx` | Added `getSandboxPreview` import from `@/lib/api/io` |

**TypeScript typecheck:** 0 errors ✅

**Data flow:**
```
Backend sandbox.created SSE event (with sandbox_id)
  → useStreaming.ts captures sandbox_id into lastSandboxIdRef
  → sandboxd_exec tool event gets sandboxId from ref
  → addToolEvent stores it in ToolEventContext
  → ToolActivityFeed renders SandboxPreviewButton (polls every 3s)
  → User clicks "🔗 Open Preview" → opens preview.flowmanner.com
```

### 6. Unit Tests

**File:** `backend/tests/test_sandbox_node_executor.py` (NEW — 17 tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestSandboxNodeType` | 2 | Enum value exists and is valid |
| `TestSandboxEventTypes` | 2 | All 7 event type constants defined |
| `TestSandboxRunStateProjection` | 2 | Sandbox events are no-op in RunState.apply() |
| `TestSandboxNodeDispatch` | 1 | _dispatch routes SANDBOX to handler |
| `TestSandboxNodeEvents` | 1 | Emits create/submit/progress/complete events |
| `TestSandboxNodeErrorHandling` | 4 | Missing prompt, submit failure, SSE error, unexpected stream end |
| `TestSandboxNodeConfig` | 3 | Shared workspace reuse, input files written, snapshot before |
| `TestSandboxNodeLazyProperties` | 3 | Client lazy init, service lazy init, ephemeral sandbox |

**Regression tests:** All 49 existing `test_node_executor.py` + `test_dag_executor.py` tests still pass ✅

---

## Test Results

```
118 passed in 0.37s

Breakdown:
  test_sandbox_node_executor.py    17 passed  (Phase 3 — NEW)
  test_node_executor.py            32 passed  (regression)
  test_dag_executor.py             17 passed  (regression)
  test_sandboxd_tools.py           16 passed  (Phase 1)
  test_sandboxd_client.py          14 passed  (Phase 1)
  test_sandbox_service.py          12 passed  (Phase 1)
  test_sandbox_preview_api.py      10 passed  (Phase 2)
```

---

## Files Changed Summary

### Backend (Homelab)

| File | Change |
|------|--------|
| `backend/app/services/substrate/workflow_models.py` | Added `SANDBOX = "sandbox"` to `NodeType` enum |
| `backend/app/models/substrate_models.py` | Added 7 sandbox event types + catch-all in `RunState.apply()` |
| `backend/app/services/substrate/node_executor.py` | Added imports, lazy properties, dispatch case, `_handle_sandbox_node()` (~150 lines) |
| `backend/tests/test_sandbox_node_executor.py` | **NEW** — 17 unit tests |
| `backend/alembic/versions/20260617_seed_sandbox_dag_blueprint.py` | **NEW** — Seeds sandbox DAG blueprint template |

### Frontend (Homelab)

| File | Change |
|------|--------|
| `src/lib/chat-types.ts` | Added `sandboxd_exec` to `ToolType`, `sandboxId` to `ToolEvent` |
| `src/components/chat/ToolActivityFeed.tsx` | Added `Container` icon, `sandboxd_exec` mapping, `SandboxPreviewButton` integration |
| `src/hooks/useStreaming.ts` | Added `lastSandboxIdRef`, sandbox SSE event handler, sandboxId in addToolEvent |
| `src/lib/tool-event-parser.ts` | Added sandboxd_exec rules, Sandbox label, sandboxId to ParsedToolEvent |
| `src/components/chat/SandboxPreviewButton.tsx` | Added `getSandboxPreview` import |

---

## Architecture

```
Workflow DAG (blueprint definition)
  ├── Node: generate_code (LLM)
  │     └── output.text = Python code
  ├── Node: execute_in_sandbox (SANDBOX)
  │     ├── Creates/reuses sandboxd Docker container
  │     ├── Writes input_files (main.py from LLM output)
  │     ├── Submits task via POST /v1/sandboxes/{id}/tasks
  │     ├── Streams SSE events (progress → complete/error)
  │     └── output.stdout = execution output
  └── Node: summarize_results (LLM)
        └── Analyzes sandbox output → summary

Chat UI Integration:
  Backend SSE (sandbox.created with sandbox_id)
    → useStreaming.ts captures into lastSandboxIdRef
    → ToolActivityFeed renders SandboxPreviewButton
    → Polls GET /api/v1/sandbox/{id}/preview every 3s
    → User clicks "🔗 Open Preview" → s-<id>-3000.preview.flowmanner.com
```

---

## Code Review Findings (All Addressed)

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | `db` parameter untyped on `_handle_sandbox_node` | Code quality | ✅ Fixed — typed as `AsyncSession` |
| 2 | `json` import at method top, not module top | Code quality | ✅ Fixed — moved to module imports |
| 3 | `ws_manager.broadcast_node_state()` without guard | Runtime safety | ✅ Fixed — added `hasattr` guard |
| 4 | `lastSandboxIdRef` not declared in refs section | Build-breaking | ✅ Fixed — added `useRef<string \| null>(null)` |
| 5 | `parsed.payload` not on SSEEvent type | Type safety | ✅ Fixed — cast to `Record<string, unknown>` |
| 6 | Detection patterns too broad (`/execute.*sandbox/i`) | False positives | ⚠️ Known — tighten in future iteration |
| 7 | `Container` icon may not exist in all lucide-react versions | Runtime risk | ⚠️ Verify — swap to `Box`/`Server` if missing |
| 8 | `lastSandboxIdRef` not reset between streams | Stale data | ✅ Fixed — reset in `finally` block |

---

## Verification Checklist

- [x] `NodeType.SANDBOX` exists in enum and is routable via `_dispatch()`
- [x] 7 sandbox event types defined in `SubstrateEventType`
- [x] Sandbox events are no-op in `RunState.apply()`
- [x] `_handle_sandbox_node` creates sandbox, writes files, submits task, streams SSE
- [x] Shared workspace reuse works (skips create if existing sandbox found)
- [x] Snapshot before execution works
- [x] Input files written to sandbox workspace
- [x] Ephemeral sandbox created when no mission context
- [x] Error handling covers: missing prompt, submit failure, SSE error, unexpected stream end
- [x] `json` import at module top
- [x] `db` typed as `AsyncSession`
- [x] `ws_manager` guarded with `hasattr`
- [x] Alembic migration chains from `seed_sandboxd_tools`
- [x] Blueprint seeded: id=`a1b2c3d4...`, title="Sandbox Code Runner", type=dag, status=published
- [x] `alembic current` → `seed_sandbox_dag_blueprint (head)`
- [x] Blueprint query returns expected data
- [x] 17 new sandbox node executor tests pass
- [x] 49 regression tests (node_executor + dag_executor) pass
- [x] 52 Phase 1+2 tests pass (no regression)
- [x] Frontend: `sandboxd_exec` in ToolType union
- [x] Frontend: `sandboxId` in ToolEvent interface
- [x] Frontend: `Container` icon + `sandboxd_exec` in TOOL_ICONS
- [x] Frontend: `SandboxPreviewButton` renders when `tool.sandboxId` exists
- [x] Frontend: `lastSandboxIdRef` captures sandbox_id from SSE events
- [x] Frontend: `lastSandboxIdRef` reset in `finally` block
- [x] Frontend: TypeScript typecheck passes (0 errors)
- [x] Frontend: `getSandboxPreview` import in SandboxPreviewButton.tsx

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Detection patterns broad (`/execute.*sandbox/i`) | May match assistant prose | Tighten to `/sandboxd_exec/` in future iteration |
| Only `sandboxd_exec` in ToolType | Other sandboxd tools fall to `"other"` type | Add `sandboxd_file_*` and `sandboxd_preview` types later |
| `lastSandboxIdRef` assumes one sandbox per turn | Multiple sandboxes share same ref | Low risk — one sandbox per DAG node is the common case |
| No polling timeout on SandboxPreviewButton | Infinite polling if sandboxd unreachable | Add max retry count (e.g., 20 attempts = 60s) |
| Base64 arg length ~128KB for input_files | Files > ~128KB will fail | Phase 4+: pipe via stdin instead of echo |
| `Container` icon from lucide-react | May not exist in all versions | Swap to `Box` or `Server` if runtime error |

---

## Lessons Learned

1. **The DAG node handler pattern is clean.** Adding a new node type only requires: enum value + dispatch case + handler method. The `_dispatch()` match statement makes routing trivial.

2. **Lazy properties prevent import cycles.** `SandboxdClient` and `SandboxService` are imported at module top but instantiated lazily via `@property`. This avoids circular imports with the substrate layer.

3. **SSE event parsing needs structured handling, not just regex.** The `parseToolEvents` function scans accumulated text with regex — it can't extract structured data like `sandbox_id`. The fix was to handle `sandbox.*` SSE events directly in `useStreaming.ts` and store the ID in a ref.

4. **Pattern matching for file edits is fragile across agents.** Multiple basher agents tried to edit the same file with slightly different indentation, causing repeated failures. Using Python scripts with explicit line manipulation was more reliable than `sed`.

5. **Alembic data migrations should use deterministic UUIDs.** The blueprint seed uses a hardcoded UUID (`a1b2c3d4...`) so re-runs are safe. Runtime `uuid4()` would create duplicates on re-run.

6. **The `finally` block is critical for ref cleanup.** Without resetting `lastSandboxIdRef.current = null` in the `finally` block, a stale sandbox ID would leak into the next stream.

---

## What's Next: Phase 4+

| Item | Description |
|------|-------------|
| Frontend deploy | `bash /opt/flowmanner/deploy-frontend.sh` to push preview button to production |
| Tighten detection patterns | Change `/execute.*sandbox/i` → `/sandboxd_exec/` in tool-event-parser.ts |
| Add polling timeout | Max 20 retries (60s) on SandboxPreviewButton before showing "timed out" |
| Add remaining sandboxd tool types | `sandboxd_file_read`, `sandboxd_file_write`, `sandboxd_file_list`, `sandboxd_preview` to ToolType |
| Preview URL API endpoint | `GET /api/v1/sandbox/{id}/preview` already exists (Phase 2) — verify frontend integration |
| Security headers | Add HSTS, X-Frame-Options to preview nginx block |
| Auto-renewal setup | IONOS API credentials for `certbot-dns-ionos` plugin |
| Large file support | Pipe via stdin instead of echo for files > 128KB |

---

*End of Phase 3 Exit Audit.*
