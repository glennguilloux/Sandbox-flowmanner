# Exit Audit — 2026-06-10 Session 3

**Session scope:** Fix sandbox preview URL showing "Spinning up your app!" template placeholder instead of user's files
**Agent:** Buffy (deepseek/deepseek-v4-pro)
**Test status:** 77 sandbox tests passing (44 tools + 21 preview-auth + 12 prompt)

---

## WHAT CHANGED (surviving changes — 5 files, +111 / -50)

### `backend/app/tools/sandboxd_preview.py` (+40 / -21)
- **Removed `preview_url` from the result** — returns only `sandbox_id`, `status`, `preview_status`. The sandbox runtime URL on port 3000 shows an empty directory listing; exposing it as `preview_url` tricked the LLM into showing it to users.
- **Removed `preview` raw dict** from result — raw sandboxd response not useful to the LLM.
- **Updated tool description** with `WARNING: NEVER show the sandboxd_preview URL to the user` and `sandboxd_serve is the ONLY source of the app preview URL`.
- **Removed dead import** `rewrite_sandboxd_url` (no longer called).
- **Port references**: 8080 → 8081 in descriptions and comments.

### `backend/app/tools/sandboxd_serve.py` (+33 / -21)
- **Default port changed 8080 → 8081** — avoids conflict with the sandbox template's built-in dev server on port 8080 (which shows "Spinning up your app!" and can't be safely killed without crashing the container if it's the entrypoint).
- **Removed `_kill_port`** entirely — `fuser` and `ss` are not available in the sandbox container, and `/proc`-based killing crashed the container when the template server was PID 1.
- **Reverted to simple check-then-start flow**: `_check_port` → if not serving, `_start_fallback_server` → poll.
- **Retained `bash -c` fix** (was `bash -lc`) in `_check_port`.
- Tool descriptions updated to reference port 8081.

### `backend/app/tools/sandboxd_file_write.py` (+50)
- **Added `_ensure_server_8081`** — auto-starts python3 http.server on port 8081 from `/home/sandbox/` after each successful file write.
- **Fire-and-forget**: uses `asyncio.create_task()` to avoid blocking the file write response (non-blocking curl check + nohup start).
- **Idempotent**: checks if port 8081 is already serving before starting.
- This is the key fix — the LLM consistently skips calling `sandboxd_serve`, but now `sandboxd_file_write` starts the server automatically.

### `backend/app/services/chat_service.py` (+10 / -2)
- **Strengthened `_SANDBOXD_SYSTEM_GUIDANCE`** with ⚠️ CRITICAL warnings:
  - "sandboxd_preview returns sandbox metadata ONLY — do NOT show its URL to the user"
  - "sandboxd_serve is the ONLY tool that returns the app preview URL"
  - "ALWAYS call it after writing files, and ALWAYS present its returned URL to the user"
- Port references updated: 8080 → 8081 in URL format and workflow description.

### `backend/tests/test_sandboxd_tools.py` (+28 / -6)
- Updated test names and assertions for new output schema (no `preview_url` in results).
- Updated port assertions 8080 → 8081 in serve tests.
- Removed all kill-related test expectations.
- All 44 tests passing.

---

## WHAT WAS TRIED AND REVERTED (DANGEROUS — do not re-attempt)

| Attempt | What | Why reverted |
|---------|------|-------------|
| `_kill_port` via `fuser -k` + `ss` fallback | Kill template server before starting fallback on 8080 | `fuser` and `ss` unavailable in sandbox container — kill silently failed, fallback crashed with `OSError [Errno 98] Address already in use` |
| `/proc`-based self-kill in serve.py script | Scan `/proc/*/net/tcp` for port 8080 LISTEN state, SIGKILL the process | **Killed the template's entrypoint (PID 1), crashing the entire sandbox container.** Template server IS the entrypoint — killing it kills the container |
| Auto-serve in `sandboxd_preview` | Start server on port 8080 after sandbox auto-creation | Same entrypoint-kill problem; also, `sandboxd_serve` would later kill the auto-serve server and fail to restart |

**Lesson:** The template's dev server on port 8080 is the Docker entrypoint. Killing any process on port 8080 can kill the container. The only safe approach is to use a **different port** (8081) and **never kill anything**.

---

## STATUS

### git status
```
Changes not staged for commit:
  backend/app/services/chat_service.py
  backend/app/tools/sandboxd_file_write.py
  backend/app/tools/sandboxd_preview.py
  backend/app/tools/sandboxd_serve.py
  backend/tests/test_sandboxd_tools.py

Untracked files (pre-existing, do NOT commit without Glenn):
  backend/validate_constraints.py
  docs/HOMELAB-SERVICES-REFERENCE.md
  docs/PORTFOLIO-BRAINSTORM-IDEAS.md
  docs/PORTFOLIO-PROMOTION-PLAN.md
  docs/PROFESSIONALIZATION-PLAN.md
  docs/blog-how-to-run-ai-agents-without-going-bankrupt.md
  sandboxd/
  scripts/apply_attr_defined_fixes.py
  scripts/apply_sentry_none_guards.py
  scripts/debug_converter_splice.py
```

### git log --oneline -5
```
36c1d64 docs: add exit audit for 2026-06-10 session 2
517fb26 fix(sandbox): fix port check always-false and serve returning false success
8b4cb7d fix(unified_tools): correct model imports to fix startup warning
3cc3a28 fix(sandbox): harden preview auth, serve tool, and cleanup stale refs
ce542f1 chore: working-tree whitespace fixes + SESSION-RITUAL pointer in AGENTS.md
```

### alembic current
```
cleanup_stale_handler_refs_001 (head)
```

### Tests
```
77 passed (44 sandboxd_tools + 21 sandbox_preview_auth + 12 chat_service_sandboxd_prompt)
```
Full suite not run (docker-compose exec backend pytest fails with ModuleNotFoundError inside container — host-side tests work fine).

### Container status
```
backend          Up ~1 min (healthy)
celery-beat      Up 9 hours (healthy)
celery-worker    Up 9 hours (healthy)
jaeger           Up 8 days (healthy)
searxng          Up 8 days (healthy)
workflow-postgres Up 8 days (healthy)
workflow-qdrant  Up 8 days (healthy)
workflow-rabbitmq Up 8 days (healthy)
workflow-redis   Up 8 days (healthy)
workflows-static Up 8 days (healthy)
```

---

## NEXT SESSION HANDOFF

### What works
1. `sandboxd_preview` no longer returns `preview_url` — LLM can't show the wrong URL
2. `sandboxd_file_write` auto-starts server on port 8081 after write (non-blocking, fire-and-forget)
3. `sandboxd_serve` serves on port 8081 (doesn't conflict with template on 8080)
4. System prompt has CRITICAL warnings about workflow
5. No kill logic anywhere — safe baseline, containers stay alive

### What still needs attention
1. **E2E re-test** — The auto-serve-in-file-write fix was deployed at the very end. Open a new chat, ask the LLM to build a landing page, verify port 8081 URL shows the actual landing page (not template placeholder). If the LLM still shows port 3000 or 8080 URL, tell it to use sandboxd_serve.
2. **The sandbox template itself** — The template's built-in dev server on port 8080 shows "Spinning up your app!" and can't be killed (it's the entrypoint). Consider switching to a simpler template that doesn't start a dev server, or one that serves from `/home/sandbox/` by default. Check `settings.SANDBOXD_DEFAULT_TEMPLATE` in `backend/app/config.py`.
3. **Commit these changes** — 5 modified files, uncommitted. Needs a descriptive commit message covering all the sandbox preview fixes.
4. **Code duplication** — `_start_fallback_server` is now duplicated between `sandboxd_serve.py` and `sandboxd_file_write.py` (the serve script generation logic). Could be extracted to a shared helper.
5. **Full test suite** — Only sandbox tests were verified (77 passed). The full 912-test suite should be run from the host.

### Gotchas for the next agent
- **Port 8080 = TEMPLATE, Port 8081 = OURS.** Never serve on port 8080. Never kill anything on port 8080.
- **`fuser`, `ss`, `lsof` are NOT available** in the sandbox container. Any kill logic must use Python + `/proc`.
- **The template's entrypoint IS the dev server** on port 8080. Killing it kills the container.
- **`bash -lc` with `%` in curl format strings is always wrong** — use `bash -c`. The `%` gets interpreted as a job-control specifier in login shells.
- **Auto-serve must be fire-and-forget** (`asyncio.create_task`) — blocking the file write response causes hangs.
- The `/proc/net/tcp` hex port format: 8080 = `1F90`, 8081 = `1F91`. LISTEN state = `0A`.
- **Deploy takes ~2 minutes** with 5-7 health check retries. Use `timeout=300`.
- **Untracked files** in the working tree are Glenn's personal files — do NOT commit without approval.

---

## END
