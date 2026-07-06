# Phase 4 — Browser Sandbox Tile — Handoff

**Status:** Backend complete ✅ | Frontend complete ✅ | Build verified ✅ | Tests pass ✅ (50/50)
**Date:** 2026-07-05
**Commits:** Backend `2e1df29d` → `dbeb9232` (4 commits), Frontend `00cd57e` → `2cfc3ff` (2 commits)
**Spec:** `.specs/tasks/draft/phase-4-browser-sandbox-tile.md`

---

## What was done

### Backend (committed to `/opt/flowmanner/`)

| File | Action | Details |
|------|--------|---------|
| `sandboxd/Dockerfile.browser` | **Created** | Playwright + Chromium + Xvfb + x11vnc + websockify + noVNC. Correct VNC chain (NOT the draft's broken CDP proxy). |
| `sandboxd/browser-entrypoint.sh` | **Created** | Xvfb → Chromium (CDP :9222) → x11vnc (:5900) → websockify (:6080→:5900). CDP readiness check, signal handling. |
| `backend/app/tools/browser_sandbox.py` | **Created** | Unified tool with 7 actions (launch/navigate/click/type/screenshot/snapshot/close). Uses SandboxService for lifecycle, sandboxd exec for Playwright scripts via CDP. Requires `tool:browser-sandbox` scope. |
| `backend/app/services/sandbox_service.py` | Modified | Added `create_browser_sandbox()` and `close_browser_sandbox()`. Removed dead `get_browser_sandbox_status()`. |
| `backend/app/services/chat_service.py` | Modified | (1) `browser_sandbox` in `sandboxd_ids` (gated by `SANDBOXD_ENABLED`). (2) `_CANVAS_UPDATE_TOOLS` registry + `_build_canvas_update()` for `canvas_update` SSE events. (3) `isinstance(result, dict)` guard fix. |
| `backend/tests/test_browser_sandbox.py` | **Created** | 25 tests: input validation, metadata, action dispatch, error handling, SandboxService delegation. |
| `backend/tests/test_canvas_update.py` | **Created** | 25 tests: registry lookup, JSON parsing, action filtering, error handling, extensibility. |

### Frontend (committed to `/home/glenn/FlowmannerV2-frontend/`)

| File | Action | Details |
|------|--------|---------|
| `src/components/chat/BrowserSandboxTile.tsx` | **Created** | noVNC iframe with `?token=` auth, browser chrome bar, collapsible agent action thread with expandable cards. |
| `src/components/chat/Canvas.tsx` | Modified | Import `BrowserSandboxTile`, wire `browser-sandbox` case in `TileContent`, remove `stubMessage` from `TILE_KIND_META`. |
| `src/hooks/useStreaming.ts` | Modified | Added `onCanvasUpdate` callback, `canvas_update` event handler at correct nesting level, destructured param, dependency array entry. |
| `src/components/chat/SSEChat.tsx` | Modified | Added `TileKind` import, wired `onCanvasUpdate` to `useChatStore.getState().addCanvasTile()`. |
| `src/lib/slash-commands.ts` | Modified | Replaced `/browse` stub with real handler that opens `browser-sandbox` tile. |

---

## Architecture decisions made

1. **`python:3.12-slim` base image** instead of extending `sandboxd-base:latest`. The browser sandbox doesn't need `runtimed`, `entrypoint-wrapper.sh`, or the `RUNTIMED_DIR`/`RUNTIMED_DEV_CMD` infrastructure. This is a conscious divergence from the spec — document it.

2. **SandboxService delegation.** `_launch()` delegates to `SandboxService.create_browser_sandbox()` and `_close()` delegates to `SandboxService.close_browser_sandbox()`. This reuses the sandboxd client singleton and preview URL logic rather than calling the raw client directly.

3. **Playwright scripts executed via `sandboxd exec_command`.** Each browser action (navigate, click, type, screenshot, snapshot) runs a standalone Python script inside the container that connects to Chromium via CDP (`localhost:9222`). This avoids running a long-lived Playwright server process.

4. **`isinstance(sandbox_id, ToolResult)` instead of truthiness check.** `_require_sandbox_id()` returns `str | ToolResult`. Since `ToolResult` is truthy, `if not sandbox_id` would miss error results. All 6 action methods use `isinstance` to properly detect error returns.

5. **`_CANVAS_UPDATE_TOOLS` registry pattern.** A dict mapping tool names to tile configs. Only `browser_sandbox` is registered now, but the pattern is extensible for future tile types (e.g., code-sandbox auto-open, image-gen tiles).

6. **`canvas_update` SSE event emitted after `tool_call_result`.** The backend yields `canvas_update` with `action: "open_tile"` when a registered tool produces a successful launch result. The frontend handles it in `useStreaming.ts` at the same nesting level as `agent_step_start`.

7. **`getAuthToken()` for iframe auth.** `BrowserSandboxTile` fetches the JWT via `getAuthToken()` from `@/lib/get-auth-token` (same caching pattern as `SandboxPreviewButton`) and appends it as `?token=` to the noVNC URL.

8. **`browser_sandbox` gated by `SANDBOXD_ENABLED`.** Moved from `phase2_readonly_ids` (always exposed) to `sandboxd_ids` (only when sandboxd is enabled). Without this gate, the tool would be exposed to the LLM but fail at runtime.

---

## What was NOT done (deferred to Phase 5+)

| Item | Phase | Notes |
|------|-------|-------|
| Build `sandboxd-browser` Docker image | Manual | `docker build -t sandboxd-browser:latest -f sandboxd/Dockerfile.browser .` — needs to be run on homelab |
| `permission_request` SSE / HITL interrupt | 5 | When user lacks `tool:browser-sandbox` scope, the tool returns an error JSON. No inline PermissionCard UI yet. |
| Extract inline Playwright scripts to files | 5+ | 6 Python scripts as string constants in `browser_sandbox.py`. Could be `sandboxd/browser_scripts/`. |
| Container auto-expiry config | 5 | sandboxd may handle this automatically; not explicitly configured. |
| Frontend `Canvas.test.tsx` update | 5 | Phase 3 tests don't cover browser-sandbox tile. Add test for auto-open via `canvas_update`. |
| Mobile canvas | 5+ | Browser tile is desktop-only (same as all canvas tiles). |
| Backend `canvas_tiles` table | 5+ | localStorage only. Cross-device sync deferred. |
| Tile resize | 3b | Deferred from Phase 3. |
| `onBranchFromMessage` through Canvas | 3b | Deferred from Phase 3. |

---

## Key files for context

| File | Why it matters |
|------|---------------|
| `backend/app/tools/browser_sandbox.py` | The browser sandbox tool — all 7 actions, Playwright scripts, SandboxService delegation |
| `backend/app/services/sandbox_service.py` | Container lifecycle — `create_browser_sandbox()`, `close_browser_sandbox()` |
| `backend/app/services/chat_service.py` | `_build_canvas_update()`, `_CANVAS_UPDATE_TOOLS`, `sandboxd_ids` allowlist |
| `backend/tests/test_browser_sandbox.py` | 25 tests — run with `pytest backend/tests/test_browser_sandbox.py` |
| `backend/tests/test_canvas_update.py` | 25 tests — run with `pytest backend/tests/test_canvas_update.py` |
| `sandboxd/Dockerfile.browser` | Browser container image — correct VNC chain |
| `sandboxd/browser-entrypoint.sh` | Container entrypoint — Xvfb → x11vnc → websockify → noVNC |
| `src/components/chat/BrowserSandboxTile.tsx` | Frontend tile component — noVNC iframe + action thread |
| `src/hooks/useStreaming.ts` | `canvas_update` event handler, `onCanvasUpdate` callback |
| `src/components/chat/SSEChat.tsx` | Wires `onCanvasUpdate` to `addCanvasTile` |
| `src/lib/slash-commands.ts` | `/browse` command handler |

---

## Verification steps for next agent

```bash
# 1. Backend tests
cd /opt/flowmanner
python3 -m pytest backend/tests/test_browser_sandbox.py backend/tests/test_canvas_update.py -v
# Expected: 50 passed

# 2. Frontend build
cd /home/glenn/FlowmannerV2-frontend
pnpm build
# Expected: Build succeeded

# 3. All backend commits pushed
cd /opt/flowmanner
git fetch origin && git log --oneline origin/main..main
# Expected: empty (all pushed)

# 4. Build the browser sandbox Docker image (manual — not yet done)
docker build -t sandboxd-browser:latest -f sandboxd/Dockerfile.browser .
# Expected: image builds successfully

# 5. Manual verification (requires Docker image)
# - Type /browse https://example.com in chat
# - Browser sandbox tile opens with noVNC iframe
# - Agent can call browser_sandbox(action='launch') → tile auto-opens via canvas_update
# - Agent navigate/click/type actions render as cards in tile header
# - noVNC iframe shows live browser (NOT blank — confirms correct VNC chain)
```

---

## Gotchas

- **Docker image not built.** The `Dockerfile.browser` and `browser-entrypoint.sh` are committed but the `sandboxd-browser` image has not been built. Run `docker build` before testing end-to-end.
- **`_build_canvas_update` title shows preview_url**, not user-facing URL. The tile title will be something like "Browse: https://s-sbx_abc-6080.preview.flowmanner.com" rather than the URL the user asked to browse. Cosmetic issue.
- **Inline Playwright scripts are fragile.** The 6 Python scripts as string constants have no syntax checking until runtime. If a script has a bug, it will only surface when the agent calls that action.
- **`_sandbox_context` module exists** at `backend/app/tools/_sandbox_context.py`. It's a `ContextVar`-based store for mission-scoped sandbox IDs. The `browser_sandbox` tool reads it in `_require_sandbox_id()` as a fallback.
- **Frontend has uncommitted changes** from prior work (not Phase 4). These are in `package.json`, `pnpm-lock.yaml`, and various page components. Do not commit them as part of Phase 4.
- **The `canvas_update` handler in `useStreaming.ts` uses `as Record<string, unknown>` casts** — this is the established pattern in the codebase (same as `agent_step_start` handler). TypeScript doesn't have a typed `canvas_update` event in the `SSEEvent` union yet.
