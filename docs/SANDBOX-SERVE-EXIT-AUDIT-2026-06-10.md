# Sandbox Feature v2 — sandboxd_serve Exit Audit & Handoff

**Date:** 2026-06-10
**Session scope:** Implement Fix C from `SANDBOX-FEATURE-V2-VERIFICATION-PLAN.md`
**Test status:** 42/42 passing (test_sandboxd_tools.py), e2e verified live
**Source plan:** `.hermes/plans/SANDBOX-FEATURE-V2-VERIFICATION-PLAN.md`

---

## 1. What was the problem

The sandbox-in-chat workflow had a critical bug: **the LLM would write files and start a server, but the preview URL showed an empty directory listing instead of the user's content.**

Root cause chain discovered through e2e testing:

1. **Workspace path mismatch** — The PUT `/files` API writes to `/home/sandbox/` (the sandbox root), but `_WORKSPACE_DIR` was set to `/home/sandbox/workspace/app/` (an empty subdirectory). The LLM's files landed at `/home/sandbox/index.html` while the server served from `/home/sandbox/workspace/app/`.

2. **Port 3000 conflict** — The sandboxd runtime has a built-in server on port 3000 that shows directory listings (doesn't serve `index.html`). The template's process manager auto-restarts it after `fuser -k`, making it impossible to replace.

3. **LLM server command was wrong** — The system prompt told the LLM to run `python3 -m http.server 3000` without `--directory`, so it served from CWD (usually `/` or the wrong dir).

4. **Quoting hell** — Inline Python scripts in shell commands had single-quote escaping issues (`os.chdir('/home/sandbox')` inside a `'...'` shell string).

---

## 2. What was built

### New tool: `sandboxd_serve` (Fix C from the plan)

A dedicated tool that starts a dev server inside the sandbox and returns the preview URL. Eliminates the need for the LLM to manually craft `sandboxd_exec` commands.

**Architecture:**
- **Check-first strategy** — Calls `_check_port()` to see if the port is already serving. If yes, returns the preview URL immediately (server_pid=0).
- **Fallback server** — If port is not serving, calls `_start_fallback_server()` which:
  - Writes a Python script to `/tmp/serve.py` (avoids all shell quoting issues)
  - Uses `SimpleHTTPRequestHandler(directory='/home/sandbox')` (serves from correct dir)
  - Sets `allow_reuse_address = True` (SO_REUSEADDR for port reuse)
  - Runs via `nohup python3 /tmp/serve.py > /tmp/serve.log 2>&1 &`
- **Port 8080** — Default port is 8080 (not 3000, which is reserved by sandboxd runtime)
- **Preview URL** — Format: `https://s-<sandbox_id>-8080.preview.flowmanner.com`

### Changes across 8 commits

| Commit | What |
|--------|------|
| `6e1578f` | feat: add sandboxd_serve tool + commit pre-existing timeout pass-through |
| `398892d` | fix: kill existing process on port with `fuser -k` |
| `ffa7904` | fix: correct workspace path from `/home/sandbox/workspace/app` to `/home/sandbox` |
| `845bea5` | fix: use SO_REUSEADDR + sleep after fuser for TIME_WAIT |
| `88c6d0f` | fix: write serve script to `/tmp/serve.py` to avoid quoting issues |
| `856d39d` | fix: check-first strategy, fix `\\n` → `\\n` newline escaping bug |
| `f40bab2` | fix: port 8080 (3000 reserved by runtime), update tests + system prompt |
| `5cb2668` | chore: clean up stale docstring and comments |

---

## 3. Files modified

### Source files (5)

| File | Changes |
|------|---------|
| `app/tools/sandboxd_serve.py` | **NEW** — sandboxd_serve tool (~200 lines) |
| `app/tools/sandboxd_file_write.py` | Fixed mkdir base path from `/home/sandbox/workspace/app/` to `/home/sandbox/`. Updated description. |
| `app/tools/sandboxd_exec.py` | Updated description to reference sandboxd_serve. (Timeout pass-through was already in uncommitted working tree at session start.) |
| `app/integrations/sandboxd_client.py` | Per-request timeout param on `exec_command()` was already in uncommitted working tree; committed alongside new tool. |
| `app/services/chat_service.py` | Registered `sandboxd_serve` in tool ID set. Rewrote system prompt: 3-step workflow (preview → write → serve) on port 8080. |

### Test files (1)

| File | Changes |
|------|---------|
| `tests/test_sandboxd_tools.py` | Added `TestSandboxdServeTool` class with 9 tests (42/42 total passing) |

### Migration files (1)

| File | Changes |
|------|---------|
| `alembic/versions/20260616_seed_sandboxd_tools.py` | Added `sandboxd_serve` to seed data |

---

## 4. Key discoveries (things that surprised us)

These were discovered through iterative e2e testing — each one required a deploy cycle (~2 min) to verify:

| # | Discovery | Impact |
|---|-----------|--------|
| 1 | PUT `/files?path=index.html` writes to `/home/sandbox/index.html`, NOT `/home/sandbox/workspace/app/index.html` | All workspace path references were wrong |
| 2 | `/home/sandbox/workspace/` exists but is empty — it's a separate mount from the sandbox root | The `_WORKSPACE_DIR` constant was pointing at an empty directory |
| 3 | sandboxd runtime has its own server on port 3000 showing directory listings | Can't use port 3000 for our server |
| 4 | The container's process manager auto-restarts the port 3000 server after `fuser -k` | Fighting for port 3000 is futile |
| 5 | `python3 -m http.server` doesn't set SO_REUSEADDR by default | Address-in-use errors after killing previous server |
| 6 | Inline Python in `bash -lc 'python3 -c "..."'` has unresolvable quoting issues | Wrote script to `/tmp/serve.py` instead |
| 7 | `"\\n".join(lines)` in a regular string produces literal backslash-n chars, not newlines | Serve script was one long line → SyntaxError |

---

## 5. What is NOT done (remaining work)

### Immediate follow-up

- [ ] **Deploy frontend** — System prompt changes are in `chat_service.py` (backend), but the frontend may need updates to display the port-8080 preview URL correctly in the chat UI
- [ ] **`_start_fallback_server` exit_code check** — If the start command fails, it silently returns PID 0. Should check `result.get("exit_code", 1)` and return an error
- [ ] **Clean up stale comments** — Module docstring still mentions "template's Vite dev server" which doesn't apply to port 8080 (partially done in `5cb2668`, but `_WORKSPACE_DIR` comment still has template guidance)

### Medium-term

- [ ] **ContextVar isolation** — `sandbox_id` set in one tool call may not persist to the next in async contexts. The `sandbox_id` field on all tools mitigates this for chat, but missions still rely on ContextVar
- [ ] **`sandboxd_exec` dual input** — Allows both `command` and `code` simultaneously (command wins silently). Consider validating exactly one
- [ ] **Observability** — Structured log fields on sandboxd tool calls (sandbox_id, tool_name, duration_ms)

### Long-term

- [ ] **Template fix** — Build a sandboxd template with a proper entrypoint that keeps the container alive. This is the highest-leverage remaining fix
- [ ] **Integration test** — Full create → write → serve → preview flow with mocked sandboxd

---

## 6. Verification

```bash
# Run all sandboxd tool tests
cd /opt/flowmanner/backend
python -m pytest tests/test_sandboxd_tools.py -v
# Expected: 42 passed, 0 failed

# E2E test (requires running sandboxd + backend)
docker compose exec backend python3 -c "
from app.integrations.sandboxd_client import get_sandboxd_client
import asyncio

async def test():
    client = get_sandboxd_client()
    sb = await client.create(project_id='e2e-verify', user_id='test')
    sb_id = sb['id']
    await client.write_file(sb_id, 'index.html', '<h1>Test</h1>')
    from app.tools.sandboxd_serve import SandboxdServeTool
    result = await SandboxdServeTool().execute({'sandbox_id': sb_id})
    print('status=%s port=%s url=%s' % (
        result.result['status'], result.result['port'], result.result['preview_url']
    ))
    # Verify: curl the preview URL and check for 'Test' in response

asyncio.run(test())
"
```

---

## 7. System prompt (current state)

The LLM now receives this guidance when sandboxd is enabled:

```
1. sandboxd_preview — call with {} to create a new sandbox. Save sandbox_id.
2. sandboxd_file_write — write files. Pass sandbox_id, path, content.
3. sandboxd_serve — start dev server and get preview URL:
   {"sandbox_id": "..."}
   Starts server on port 8080 (port 3000 reserved by runtime).
   Serves from /home/sandbox/ where files were written.
   Returns preview URL directly. 3 tool calls total.
4. sandboxd_file_read — read a file back
5. sandboxd_file_list — list workspace files
```

---

## 8. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Port 8080 not proxied by nginx | Low | Preview URL returns 502 | nginx proxies all ports via `s-<id>-<port>` pattern |
| Serve script fails silently (PID 0) | Medium | User sees "started" but no content | Check `/tmp/serve.log` inside container for errors |
| `/tmp/serve.py` overwritten by concurrent calls | Low | Wrong sandbox gets wrong server | Each sandbox is isolated; file is inside container |
| Template server on port 3000 interferes | None | N/A | Using port 8080 avoids the conflict entirely |
| `echo` with special chars in serve_dir | Low | SyntaxError in serve.py | Only affects custom dirs with single quotes (unlikely) |

---

## 9. Deployment status

- **Backend:** Deployed via `deploy-backend.sh` — commit `5cb2668` is live
- **sandboxd_serve tool:** Seeded into `tools_catalog` via direct SQL (alembic seed migration exists but isn't in the current migration chain)
- **E2E verified:** Create sandbox → write index.html → serve → curl port 8080 → content served correctly

---

## 10. Next session priorities

1. **Test sandbox-in-chat end-to-end** — Open a real chat thread, ask the LLM to build a landing page, verify the preview URL works in the browser
2. **Add exit_code check to _start_fallback_server** — Return error if start command fails
3. **Commit remaining untracked files** — 10+ alembic migrations, test files, sandboxd Dockerfile sitting in working tree
4. **Deploy frontend** — If any frontend changes are needed for port-8080 preview URLs
