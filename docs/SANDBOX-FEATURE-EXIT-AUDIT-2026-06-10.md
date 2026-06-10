# Sandbox Feature — Exit Audit & Handoff

**Date:** 2026-06-10  
**Session scope:** Phases 1–4 of the sandbox fix plan (container survival, tool schemas, file APIs, system prompt)  
**Test status:** 69/69 passing, 0 failures  
**Source plan:** `.hermes/plans/SANDBOX-FEATURE-ROOT-CAUSE-PLAN.md`

---

## 1. What was broken (root cause summary)

The sandbox-in-chat feature was completely non-functional. Users asking "build a landing page" would see the LLM paste raw HTML and apologize for a "sandbox infrastructure hiccup." The actual failure chain:

1. **Container dies immediately** — `SANDBOXD_DEFAULT_TEMPLATE="react-standard"` doesn't exist in sandboxd. Fallback to internal API uses `sandboxd-base:1.0.0` with no entrypoint → container exits within seconds.
2. **Tool schema mismatch** — System prompt told LLM to pass `command: ["bash", "-lc", "npx serve"]` but `sandboxd_exec` only accepted `code: str`.
3. **file_write used a base64-via-bash hack** — Bypassed the native `PUT /files` API, shell injection risk, brittle.
4. **file_read and file_list used exec hacks** — `cat`/`ls`/`find` via `exec_command` instead of native APIs.
5. **file_read and file_list NOT registered as chat tools** — LLM couldn't read or list files it wrote.
6. **No preview readiness polling** — Returned "running" before port 3000 was actually listening.
7. **Duplicate URL rewriters** — Two regex implementations that would eventually diverge.
8. **ContextVar isolation** — `sandbox_id` set in one tool call might not persist to the next.
9. **System prompt referenced nonexistent APIs** — `npx serve`, field name mismatches.
10. **No mkdir before file write** — Subdirectory files always failed.
11. **exec_command swallowed error details** — `raise_for_status()` discarded the JSON body.
12. **Hardcoded template default in client** — Shadowed `settings.SANDBOXD_DEFAULT_TEMPLATE`.
13. **Shell injection in base64 file_write** — `echo '{b64}'` with untrusted content.
14. **URL rewriter matched ANY URL** — `https://example.com` → `https://example.com.preview.flowmanner.com`.

---

## 2. What was fixed (14 issues across 10 files)

### Source files modified (8)

| File | Changes |
|------|---------|
| `app/integrations/sandboxd_client.py` | Removed hardcoded `template="react-standard"` default → resolves from settings. `exec_command` returns JSON body on exec failures (not just HTTP errors). `write_file` accepts `str \| bytes`, sets `Content-Type: application/octet-stream`. Added shared `rewrite_sandboxd_url()` function. |
| `app/tools/sandboxd_exec.py` | Added `command: list[str]` field (argv array, takes precedence over `code`). Added `sandbox_id` field. Validates at least one of `command`/`code` is provided. Returns `success=True` with structured `stdout`/`stderr`/`exit_code` for non-zero exits (LLM needs to see the output). |
| `app/tools/sandboxd_file_write.py` | Replaced base64-via-bash hack with native `client.write_file()` API. Added `mkdir -p` for parent directories with warning logging. Added `sandbox_id` field. Removed `import base64`. |
| `app/tools/sandboxd_file_read.py` | Replaced `exec cat` with native `client.read_file()` API. Added `sandbox_id` field. |
| `app/tools/sandboxd_file_list.py` | Replaced `exec ls/find` with native `client.list_files()` API. Added `sandbox_id` field. |
| `app/tools/sandboxd_preview.py` | Added readiness polling (30 × 500ms = 15s max). Imports shared `rewrite_sandboxd_url` from client. Removed `import re`. |
| `app/api/v1/sandbox_preview.py` | Removed duplicate `_rewrite_preview_url`. Imports shared `rewrite_sandboxd_url` from client. |
| `app/services/chat_service.py` | Registered all 5 sandboxd tools (was only 3). Rewrote `_SANDBOXD_SYSTEM_GUIDANCE` with correct field names, `command` array examples, and explicit 5-step workflow. |

### Test files modified (2)

| File | Changes |
|------|---------|
| `tests/test_sandboxd_tools.py` | Updated mocks for native APIs (`read_file`, `write_file`, `list_files`). Updated `rewrite_sandboxd_url` imports to `sandboxd_client`. Fixed patch targets to `app.integrations.sandboxd_client.settings`. Preview tests use `"ready"` status to avoid polling delays. Added 4 new polling tests. Updated `test_execute_invalid_input` assertion. |
| `tests/test_sandbox_preview_api.py` | Updated import from `app.tools.sandboxd_preview` to `app.integrations.sandboxd_client`. |

### New tests added (4)

| Test | What it verifies |
|------|-----------------|
| `test_polls_until_ready` | Polling from `"starting"` → `"ready"` with mocked `asyncio.sleep`, correct `get`/`sleep` call counts |
| `test_polls_until_error` | Polling stops when preview status becomes `"error"` |
| `test_polling_survives_transient_get_errors` | `ConnectionError` inside the polling loop is caught and polling continues |
| `test_skips_polling_when_already_ready` | No polling when status is already `"ready"` (single `get`, zero `sleep`) |

---

## 3. Architecture after the fix

```
sandboxd_client.py          ← integrations layer (HTTP client + shared rewrite_sandboxd_url)
  ↑ imported by
sandboxd_preview.py          ← tools layer (sandboxd_preview tool, uses rewrite_sandboxd_url)
sandboxd_exec.py             ← tools layer (sandboxd_exec tool, command[] + code fields)
sandboxd_file_write.py       ← tools layer (native PUT /files API)
sandboxd_file_read.py        ← tools layer (native GET /files/content API)
sandboxd_file_list.py        ← tools layer (native GET /files API)
sandbox_preview.py           ← API route (imports rewrite_sandboxd_url from client)
chat_service.py              ← service layer (registers all 5 tools, system prompt)
```

**Dependency direction:** tools → integrations → config. API routes → integrations (not tools). No circular imports.

---

## 4. What is NOT done (remaining work)

### Phase 5: Observability (from the plan)

- [ ] Structured log fields on sandboxd tool calls (sandbox_id, tool_name, duration_ms)
- [ ] One log line per tool call with args + truncated result
- [ ] One log line per chat-stream with tool-call sequence
- [ ] `GET /api/sandbox/{id}/health` endpoint (container state vs DB state mismatch)
- [ ] Optional `?debug=1` mode for `stream_message_to_llm`

### Phase 6: Additional test coverage

- [ ] Integration test: create sandbox → write file → exec http.server → poll preview → assert 2xx (mocked sandboxd)
- [ ] Regression test: feed the exact failing transcript back in and assert the LLM gets a working preview URL
- [ ] Test that `command` field in `sandboxd_exec` is actually used as-is (not wrapped)

### Template fix (requires sandboxd access)

- [ ] Build or identify a sandboxd template that keeps the container alive with a static server on port 3000
- [ ] Update `SANDBOXD_DEFAULT_TEMPLATE` in config to use the working template
- [ ] This is the **highest-leverage remaining fix** — without it, the base image still has no entrypoint

### Other

- [ ] The `ContextVar` for `sandbox_id` still has isolation issues between async tasks. The `sandbox_id` field on all tools mitigates this for chat (LLM passes it explicitly), but the mission path still relies on ContextVar.
- [ ] `sandboxd_exec` allows both `command` and `code` to be provided simultaneously (command wins silently). Consider validating exactly one.
- [ ] `rewrite_sandboxd_url` has `from app.config import settings` imported inside the function body (lazy import). When moved to `sandboxd_client.py`, the module-level `settings` is available. Could remove the lazy import.

---

## 5. Verification steps

```bash
# Run all sandbox tests
cd /opt/flowmanner/backend
python -m pytest tests/test_sandboxd_tools.py tests/test_chat_service_sandboxd_prompt.py \
    tests/test_sandbox_preview_api.py tests/test_sandbox_preview_auth.py -v

# Expected: 69 passed, 0 failed

# Syntax check all modified files
python -c "
import py_compile
for f in [
    'app/integrations/sandboxd_client.py',
    'app/tools/sandboxd_exec.py',
    'app/tools/sandboxd_file_write.py',
    'app/tools/sandboxd_file_read.py',
    'app/tools/sandboxd_file_list.py',
    'app/tools/sandboxd_preview.py',
    'app/api/v1/sandbox_preview.py',
    'app/services/chat_service.py',
]:
    py_compile.compile(f, doraise=True)
    print(f'OK: {f}')
"
```

---

## 6. Deployment

```bash
# From homelab:
bash /opt/flowmanner/deploy-backend.sh

# Verify:
curl -s http://localhost:8000/healthz
```

⚠️ **Deploy takes ~2 minutes.** The deploy script handles image backup, health checks, and automatic rollback on failure.

**Note:** The template fix (building a `static-server-3000` image for sandboxd) is NOT included in this deploy. The container will still die if `react-standard` doesn't exist. The fix reduces the blast radius by:
- The v1 API fallback now passes the template to the internal API (no template = base image)
- The system prompt tells the LLM the correct workflow
- The LLM gets clear error messages instead of silent failures

---

## 7. Files touched (for commit)

```
backend/app/integrations/sandboxd_client.py
backend/app/tools/sandboxd_exec.py
backend/app/tools/sandboxd_file_write.py
backend/app/tools/sandboxd_file_read.py
backend/app/tools/sandboxd_file_list.py
backend/app/tools/sandboxd_preview.py
backend/app/api/v1/sandbox_preview.py
backend/app/services/chat_service.py
backend/tests/test_sandboxd_tools.py
backend/tests/test_sandbox_preview_api.py
```

---

## 8. Risk assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Native `PUT /files` has different path semantics than base64 hack | Low | `write_file` in client already existed and was tested |
| LLM passes both `command` and `code` | Low | `command` takes precedence, validated in code |
| Readiness polling adds latency to every preview call | Low | Only polls when status is not `"ready"`, max 15s |
| `sandboxd_file_write` mkdir -p failure → confusing write error | Low | Warning logged, write will fail with HTTP error (clear enough) |
| Template still broken (container dies) | **High** | This is the next fix to do — see §4 "Template fix" |

---

## 9. Next session priorities

1. **Deploy and verify** — `deploy-backend.sh`, then test in a real chat thread
2. **Template fix** — Build/identify a working sandboxd template (highest leverage)
3. **Observability** — Phase 5 logging from the plan
4. **E2E test** — Full chat → LLM → sandbox → preview URL flow
