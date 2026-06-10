# Flowmanner — Session Exit Audit & Handoff

**Date:** 2026-06-10
**Sessions:** 2 sessions (~3 hours + ~2 hours)
**Agent:** Buffy (Codebuff)

---

## Session 1 (Morning) — Previous Agent

### ✅ Bug 1: Sandbox Preview Auth Chain (UUID-vs-JWT)

**Problem:** `_authenticate_preview_request()` passed UUID refresh tokens to `jwt.decode()` → 401.

**Fix:** Added `_is_jwt()` heuristic + DB lookup path for UUID cookies.
**Commit:** `4d8e04d`

---

### ✅ Bug 2: Code Execute 422 (ToolResult Field Mismatches)

**Problem:** `io.py` referenced `result.status.value` and `result.data` but `ToolResult` has `success: bool` and `result: Any` → 422.

**Commit:** `800b670`

---

### ✅ Bug 3: Preview Cookie 401 (refreshToken Not in Session)

**Problem:** `/api/auth/preview-cookie` reads `session.refreshToken` but NextAuth session callback never copied it → 401.

**Fix:** Added `token.refreshToken` → `session.refreshToken` in `frontend/src/auth.ts`.

---

### ✅ Bug 4: Auth Chain Completion

**Problem:** 4 uncommitted files needed deployment together (`auth.py`, `auth_cookies.py`, `mission_executor.py`, `seed_demo_data.py`).

**Commit:** `cd70bb6`

---

### ✅ Documentation Updates

**Commit:** `dcca241` — AGENTS.md + REBUILD-ROADMAP.md updated.

---

## Session 2 (Afternoon) — This Session

### ✅ Fix 1: Forward-Auth 422 (Request Not Injected by FastAPI)

**Problem:** `/api/sandbox/forward-auth` returned 422 `{"detail":[{"type":"missing","loc":["query","request"],"msg":"Field required"}]}`. FastAPI couldn't inject the `Request` object because `from starlette.requests import Request` was under `TYPE_CHECKING` only. With `from __future__ import annotations`, all annotations are strings — FastAPI's `get_type_hints()` couldn't resolve `Request` at runtime, so it treated `request` as a query parameter.

**Fix:** Moved `from starlette.requests import Request` to runtime import with `# noqa: TC002` (FastAPI DI requires it at runtime).

**Commit:** `6f56ac6`
**Files:** `backend/app/api/v1/sandbox_preview.py`
**Verified:** `curl /api/sandbox/forward-auth` now returns 401 (correct) instead of 422.

---

### ✅ Fix 2: Asyncpg "Connection Is Closed" During Chat Streaming

**Problem:** `stream_message_to_llm` (and `send_message_to_llm`) saves the user message via `create_chat_message` which does `db.flush()` — opening a PostgreSQL transaction. The LLM then streams for minutes (tool calls, multiple rounds). PostgreSQL's `idle_in_transaction_session_timeout` (30s) kills the connection. When the assistant message is saved at the end → `InterfaceError: cannot call PreparedStatement.fetch(): the underlying connection is closed`.

**Fix (3 parts):**
1. Both functions now `await db.commit()` immediately after saving the user message — releases the transaction so the connection isn't idle-in-transaction during LLM streaming.
2. Added `create_chat_message_fresh_session()` — a fallback that creates messages using a brand new DB session from `AsyncSessionLocal`. Used when the original session's connection dies.
3. Increased `DATABASE_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS` from 30,000 (30s) to 300,000 (5min) in `config.py` as defense-in-depth.

**Commit:** `6f56ac6`
**Files:** `backend/app/services/chat_service.py`, `backend/app/config.py`
**Verified:** 69 tests pass, backend rebuilt and healthy.

---

### ✅ Fix 3: DeepSeek Passing "NEW" / "NULL" / "NONE" as sandbox_id

**Problem:** Some LLMs (DeepSeek) pass literal strings like `"NEW"`, `"NULL"`, or `"NONE"` as the `sandbox_id` argument instead of omitting the field. These are truthy strings, so the code skips auto-create and passes them to `client.get()` → 404 (`GET /v1/sandboxes/NEW`).

**Fix:** Added guard before the sandbox_id resolution chain: `if raw_id.strip().upper() in ("NEW", "NONE", "NULL"): raw_id = None` — triggers auto-create path.

**Commits:** `6f56ac6` (initial "NEW" guard), `0ea3993` (extended to "NONE"/"NULL")
**Files:** `backend/app/tools/sandboxd_preview.py`
**Verified:** 53 sandbox tests pass.

---

### ✅ Fix 4: Frontend Sandbox Preview URL Path Mismatch

**Problem:** Frontend `lib/api/io.ts` called `/api/v1/sandbox/${sandboxId}/preview` but the backend endpoint is `/api/sandbox/${sandboxId}/preview`. The `api_v1_router` has `prefix="/api"` (not `/api/v1`). Frontend got 404 on every preview poll.

**Fix:** Changed `/api/v1/sandbox/` to `/api/sandbox/` in `getSandboxPreview()`.

**Commit:** `c9413d3` (frontend, master branch)
**Files:** `/home/glenn/FlowmannerV2-frontend/src/lib/api/io.ts`

---

### ✅ Fix 5: Celery Workers extra_hosts (Committed)

**Problem:** `celery-worker` and `celery-beat` containers lacked `extra_hosts: host.docker.internal:host-gateway` — missions couldn't reach sandboxd. Applied in Session 1 but uncommitted.

**Commit:** `6f56ac6` (committed with other fixes)
**Files:** `docker-compose.yml`

---

### ✅ Fix 6: nginx/default.conf Tracking

**Problem:** `nginx/default.conf` contained preview server blocks for `*.preview.flowmanner.com` but was untracked in git.

**Fix:** `git add nginx/default.conf` — now tracked for reproducibility.

**Commit:** `6f56ac6`

---

### ✅ Fix 7: Frontend auth.ts refreshToken (Committed)

**Problem:** Session callback never copied `token.refreshToken` to session object — deployed in Session 1 but uncommitted.

**Commit:** `ceb269e` (frontend, master branch)
**Files:** `/home/glenn/FlowmannerV2-frontend/src/auth.ts`

---

### ✅ Fix 8: Increase Max Tool Rounds

**Problem:** `_MAX_TOOL_ROUNDS = 10` was too low for sandbox workflows (create → write files → start server → get preview = 4+ calls, multi-file projects exceed 10).

**Fix:** Increased to 15.

**Commit:** `6dc705a`
**Files:** `backend/app/services/chat_service.py`

---

### ✅ Ruff Lint Fixes

**Problem:** Pre-commit hooks blocked commits due to ruff errors in modified files.

**Fixes:**
- `sandbox_preview.py`: Added `# noqa: TC002` on `Request` import (needed at runtime for FastAPI DI)
- `chat_service.py`: Replaced `for` loop + `append` with `list.extend` generator expressions (PERF401)

**Applied as part of:** `6f56ac6`

---

## All Commits This Day

### Backend (origin/main)

| Hash | Message |
|------|---------|
| `4d8e04d` | fix(auth): resolve UUID-vs-JWT cookie auth bug in forward-auth |
| `800b670` | fix(io): align ToolResult field names in voice_transcribe, voice_synthesize, code_execute |
| `cd70bb6` | fix(auth): complete preview auth chain — cookie path widening, _auth_response helper, metrics fix |
| `dcca241` | docs: mark sandbox preview auth chain as resolved in AGENTS.md |
| `6f56ac6` | fix: forward-auth 422, asyncpg connection-closed, sandboxd NEW guard, celery extra_hosts |
| `0ea3993` | fix(sandboxd): extend LLM literal-string guard to include NONE and NULL |
| `6dc705a` | chore(chat): increase max tool rounds from 10 to 15 |

### Frontend (master branch)

| Hash | Message |
|------|---------|
| `c9413d3` | fix(api): correct sandbox preview URL path from /api/v1/sandbox to /api/sandbox |
| `ceb269e` | fix(auth): expose refreshToken in session callback for preview-cookie route |

---

## Test Results (End of Day)

| Test Suite | Tests | Status |
|-----------|-------|--------|
| `test_sandbox_preview_auth.py` | 14 | ✅ All pass |
| `test_sandbox_preview_api.py` | 10 | ✅ All pass |
| `test_io_api.py` | 24 | ✅ All pass |
| `test_chat_tool_loop.py` | 26 | ✅ All pass |
| `test_chat_service_sandboxd_prompt.py` | 6 | ✅ All pass |
| `test_sandboxd_tools.py` | 31 | ✅ All pass |
| `test_sandboxd_client.py` | 11 | ✅ All pass |
| `test_sandbox_service.py` | 11 | ✅ All pass |
| **Total** | **133** | **✅ All pass** |

---

## Container Status (as of exit)

```
backend             Up ~15 min (healthy)
celery-worker       Up ~1 hour (healthy)
celery-beat         Up ~1 hour (healthy)
sandboxd-sandboxd-1 Up 18 hours
sandboxd-traefik-1  Up 2 days
workflow-postgres   Up 7 days (healthy)
workflow-redis      Up 7 days (healthy)
workflow-qdrant     Up 7 days (healthy)
workflow-rabbitmq   Up 7 days (healthy)
jaeger              Up 7 days (healthy)
flowmanner-frontend Up <1 min (VPS)
flowmanner-nginx    Up <1 min (VPS)
```

**Backend health:** `ok` — PostgreSQL, Redis, Langfuse, LLM provider all healthy.
**Forward-auth:** `/api/sandbox/forward-auth` → 401 (correct).

---

## Remaining Open Issues

### 🟡 Traefik websecure EntryPoint Missing

Sandbox containers have labels referencing `websecure` entrypoint, but Traefik only has `web` (HTTP). Causes warnings in Traefik logs. Not blocking — VPS nginx handles SSL termination. Labels should be cleaned up in sandboxd template config.

### 🟡 Make _MAX_TOOL_ROUNDS Configurable

Currently hardcoded in `chat_service.py`. Should be moved to `config.py` as `MAX_TOOL_ROUNDS: int = 15` for easier tuning without redeployment.

### ⬜ Phase 0.2 — Live Preview End-to-End

All blockers resolved. The full flow should now work:
1. User asks for HTML in chat
2. DeepSeek calls `sandboxd_preview` → creates sandbox (literal-string guard active)
3. DeepSeek writes files via `sandboxd_file_write` (up to 15 tool rounds)
4. DeepSeek starts dev server via `sandboxd_exec`
5. DeepSeek calls `sandboxd_preview(sandbox_id)` → returns preview URL
6. Frontend polls `/api/sandbox/{id}/preview` (correct path now)
7. User clicks preview URL → forward-auth checks cookie → 200 → VPS nginx → WireGuard → Traefik → sandbox

### ⬜ Phase 0.3 — Firefox Busy Dialog

Depends on 0.2. Once preview works end-to-end, the Firefox busy dialog should resolve.

---

## Key Architecture Notes

- **Router prefix:** `api_v1_router` has `prefix="/api"` (NOT `/api/v1`). All v1 endpoints are at `/api/...`.
- **Sandbox preview URL:** Frontend must use `/api/sandbox/{id}/preview`, NOT `/api/v1/sandbox/{id}/preview`.
- **Forward-auth:** `Request` MUST be imported at runtime (not under `TYPE_CHECKING`) for FastAPI dependency injection.
- **DB sessions:** Long-running generators (streaming responses) must commit user messages before the LLM call to avoid idle-in-transaction kills.
- **Frontend repo:** Branch is `master` (not `main`). Push to `origin master`.
