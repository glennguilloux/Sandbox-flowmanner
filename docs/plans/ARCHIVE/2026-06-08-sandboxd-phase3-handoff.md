# sandboxd Integration — Phase 3 Handoff

**Date:** June 8, 2026
**Prerequisite:** Phase 1 + Phase 2 complete ✅ (see `docs/plans/2026-06-08-sandboxd-phase1-exit-audit.md` and `docs/plans/2026-06-08-sandboxd-phase2-exit-audit.md`)

---

## Copy-Paste Prompt for New Session

```
I need to do post-Phase 3 cleanup and deploy for the sandboxd integration.

CONTEXT:
- Phase 3 is complete: sandbox node handler in NodeExecutor, 7 sandbox event types, Alembic migration seeding a "Sandbox Code Runner" DAG blueprint, and frontend SandboxPreviewButton integration.
- 118 sandbox tests pass. TypeScript typecheck clean (0 errors).
- Backend deployed with migrations (alembic current = seed_sandbox_dag_blueprint).
- Frontend changes are on the homelab but NOT yet deployed to VPS.

PHASE 3 COMPLETED DELIVERABLES:

1. BACKEND — SANDBOX NODE HANDLER (backend/app/services/substrate/node_executor.py):
   - _handle_sandbox_node() method: create/reuse sandbox → write files → submit task → stream SSE → return output
   - Lazy properties: _sandbox_client, _sandbox_service
   - Dispatch case: NodeType.SANDBOX → _handle_sandbox_node
   - Config: template, task_prompt, shared_workspace, input_files, snapshot_before

2. BACKEND — NODE TYPE ENUM (backend/app/services/substrate/workflow_models.py):
   - Added SANDBOX = "sandbox" to NodeType enum

3. BACKEND — EVENT TYPES (backend/app/models/substrate_models.py):
   - 7 sandbox event types: sandbox.created, sandbox.files_written, sandbox.task_submitted, sandbox.task_progress, sandbox.task_completed, sandbox.task_failed, sandbox.snapshot_created
   - Catch-all in RunState.apply() for sandbox.* events

4. BACKEND — BLUEPRINT SEED (backend/alembic/versions/20260617_seed_sandbox_dag_blueprint.py):
   - "Sandbox Code Runner" DAG blueprint: generate_code (LLM) → execute_in_sandbox (sandbox) → summarize_results (LLM)
   - Deterministic UUID, idempotent, clean downgrade

5. BACKEND — TESTS (backend/tests/test_sandbox_node_executor.py):
   - 17 tests: dispatch routing, event emission, error handling, config options, lazy properties

6. FRONTEND — PREVIEW BUTTON (5 files in /home/glenn/FlowmannerV2-frontend/):
   - src/lib/chat-types.ts: sandboxd_exec in ToolType, sandboxId in ToolEvent
   - src/components/chat/ToolActivityFeed.tsx: Container icon, sandboxd_exec in TOOL_ICONS, SandboxPreviewButton import + conditional rendering
   - src/hooks/useStreaming.ts: lastSandboxIdRef captures sandbox_id from sandbox.* SSE events, passed to addToolEvent, reset in finally
   - src/lib/tool-event-parser.ts: sandboxd_exec detection rules, Sandbox label, sandboxId in ParsedToolEvent
   - src/components/chat/SandboxPreviewButton.tsx: getSandboxPreview import from @/lib/api/io

REMAINING WORK (Phase 4+):
1. Deploy frontend: bash /opt/flowmanner/deploy-frontend.sh (~4 minutes)
2. Tighten detection patterns: /execute.*sandbox/i → /sandboxd_exec/ in tool-event-parser.ts
3. Add polling timeout: max 20 retries (60s) on SandboxPreviewButton
4. Add remaining sandboxd tool types to ToolType (sandboxd_file_read, sandboxd_file_write, sandboxd_file_list, sandboxd_preview)
5. Security headers on preview nginx block (HSTS, X-Frame-Options)
6. Auto-renewal: IONOS API credentials for certbot-dns-ionos plugin

KEY FILES TO READ FIRST:
- backend/app/services/substrate/node_executor.py (sandbox node handler)
- backend/app/services/substrate/workflow_models.py (NodeType enum)
- backend/app/models/substrate_models.py (sandbox event types)
- backend/tests/test_sandbox_node_executor.py (17 tests)
- backend/alembic/versions/20260617_seed_sandbox_dag_blueprint.py (blueprint seed)
- /home/glenn/FlowmannerV2-frontend/src/components/chat/ToolActivityFeed.tsx (preview button integration)
- /home/glenn/FlowmannerV2-frontend/src/hooks/useStreaming.ts (sandboxId SSE pipeline)

ARCHITECTURE:
Workflow DAG → NodeExecutor._dispatch() → _handle_sandbox_node()
  → SandboxService.ensure_sandbox_for_mission()
  → SandboxdClient.submit_task()
  → SandboxdClient.task_events() (SSE stream)
  → EventLog.append() (sandbox.* events)

Chat UI:
  Backend SSE (sandbox.created) → useStreaming.lastSandboxIdRef → addToolEvent(sandboxId) → ToolActivityFeed → SandboxPreviewButton

FRONTEND SOURCE: /home/glenn/FlowmannerV2-frontend/ on the homelab (deployed to VPS via deploy-frontend.sh)
BACKEND SOURCE: /opt/flowmanner/backend/ on the homelab

START WITH: Read the key files above, then deploy the frontend with bash /opt/flowmanner/deploy-frontend.sh.
```

---

## Phase 3 Current State Assessment

### What Exists (from Phase 1 + 2 + 3)

| Component | Status | Notes |
|-----------|--------|-------|
| `SandboxdClient` | ✅ Working | Create, get, stop, delete, exec, snapshots, tasks, SSE events |
| `SandboxService` | ✅ Working | Mission-scoped lifecycle (ensure/reap/purge/snapshots) |
| 5 sandboxd tools | ✅ Registered | Exec, file_read, file_write, file_list, preview |
| Preview API | ✅ Working | `GET /api/v1/sandbox/{id}/preview` + forward auth |
| Wildcard TLS | ✅ Working | `*.preview.flowmanner.com` cert valid until Sep 6, 2026 |
| VPS nginx routing | ✅ Working | HTTPS proxy → homelab sandboxd Traefik |
| `NodeType.SANDBOX` | ✅ Working | Enum value + dispatch routing |
| `_handle_sandbox_node` | ✅ Working | Full lifecycle: create → files → task → SSE → output |
| 7 sandbox event types | ✅ Defined | Emitted during sandbox node execution |
| Sandbox DAG blueprint | ✅ Seeded | "Sandbox Code Runner" in blueprints table |
| Frontend preview button | ✅ Wired | SandboxPreviewButton in ToolActivityFeed |
| Frontend SSE pipeline | ✅ Wired | lastSandboxIdRef captures sandbox_id from SSE events |

### What's Remaining (Phase 4+)

| Component | Status | Blocker? |
|-----------|--------|----------|
| Frontend deploy to VPS | 🔴 Not deployed | Yes — changes only on homelab |
| Detection pattern tightening | ⚠️ Broad patterns | No — false positives possible but not breaking |
| Polling timeout on preview button | ⚠️ No timeout | No — infinite polling if sandboxd unreachable |
| Remaining sandboxd tool types | ⚠️ Only sandboxd_exec | No — others fall to "other" type |
| Security headers | ⚠️ Missing | No — Traefik handles access control |
| Auto-renewal for wildcard cert | ⚠️ Manual process | No — cron monitor warns at 30 days |

---

## Key Technical Details

### Sandbox Node Config Schema

```json
{
  "task_prompt": "Build a React todo app",
  "template": "react-standard",
  "shared_workspace": false,
  "input_files": {
    "src/index.tsx": "console.log('hello')",
    "package.json": "{\"name\":\"test\"}"
  },
  "snapshot_before": true
}
```

### Sandbox Node Output Schema

```json
{
  "sandbox_id": "sb-abc123",
  "task_id": "task-xyz",
  "stdout": "...",
  "exit_code": 0
}
```

### SSE Event Flow (Frontend)

```
1. Backend emits: data: {"type":"sandbox.created","payload":{"sandbox_id":"sb-abc"}}
2. useStreaming.ts: lastSandboxIdRef.current = "sb-abc"
3. Backend emits: data: {"type":"tool.call","tool_name":"sandboxd_exec",...}
4. tool-event-parser.ts: detects sandboxd_exec in accumulated text
5. addToolEvent({ type: "sandboxd_exec", ..., sandboxId: "sb-abc" })
6. ToolActivityFeed: renders SandboxPreviewButton(sandboxId="sb-abc")
7. SandboxPreviewButton: polls GET /api/v1/sandbox/sb-abc/preview every 3s
8. User clicks "🔗 Open Preview" → opens s-abc-3000.preview.flowmanner.com
```

### Blueprint DAG Definition

```
generate_code (LLM)
  │
  ▼
execute_in_sandbox (SANDBOX)
  │  ├── snapshot_before: true
  │  ├── input_files: { main.py: {{generate_code.output.text}} }
  │  └── task_prompt: "Run the following Python script..."
  │
  ▼
summarize_results (LLM)
  └── Analyzes sandbox output → summary
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `Container` icon missing in lucide-react | Low | Medium | Swap to `Box` or `Server` at runtime |
| Detection patterns cause false positives | Medium | Low | Tighten to `/sandboxd_exec/` in future |
| Stale sandboxId across streams | Low | Low | Ref reset in `finally` block |
| Frontend not deployed yet | Certain | Medium | Run `deploy-frontend.sh` |
| Wildcard cert expires Sep 6 | Certain | High | Cron monitor + renewal helper script |

---

## Verification Checklist (Phase 3)

- [x] `NodeType.SANDBOX` in enum
- [x] 7 sandbox event types defined
- [x] `_handle_sandbox_node` method working
- [x] Sandbox creation (mission-scoped + ephemeral)
- [x] File writing to sandbox workspace
- [x] Task submission and SSE streaming
- [x] Snapshot before execution
- [x] Shared workspace reuse
- [x] Error handling (missing prompt, submit failure, SSE error)
- [x] Alembic migration applied (seed_sandbox_dag_blueprint)
- [x] Blueprint in database (verified via psql)
- [x] 17 new tests pass
- [x] 49 regression tests pass
- [x] 52 Phase 1+2 tests pass
- [x] Frontend: sandboxd_exec in ToolType
- [x] Frontend: sandboxId in ToolEvent
- [x] Frontend: SandboxPreviewButton in ToolActivityFeed
- [x] Frontend: lastSandboxIdRef in useStreaming
- [x] Frontend: TypeScript 0 errors
- [ ] Frontend deployed to VPS (pending)

---

*End of Phase 3 Handoff.*
