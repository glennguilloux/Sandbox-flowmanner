# Task: Phase 4 — Browser Sandbox Tile

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P4 — advanced agent capability
**Estimated effort:** 2 sessions
**Created:** 2026-07-05
**Depends on:** Phase 3 (canvas v1) ✅ complete
**Blocks:** Phase 5 (permissions + metering)
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §Phase 4, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

1. **The existing `browser_*` tools are NOT in the backend container by default.** The draft says "Playwright runs in the backend container" — but the existing `app/tools/browser_navigate.py`, `browser_click.py`, `browser_screenshot.py`, `browser_snapshot.py` are thin tool wrappers. The actual Playwright runtime lives where the chat loop executes it, which means inside the existing backend Docker container. The draft is correct in substance but sloppy — the existing browser tools depend on Playwright being installed in the backend image, which it currently is (per the workspace doc's note that "browser_task_runner.py" exists in the mission executor cluster). Verify by reading `backend/requirements.txt` and the existing `browser_*` tool files before designing the sandbox image.

2. **`browser_task_runner.py` already exists in the mission cluster** (per `services/AGENTS.md` §1 — the task dispatch by `task_type`). The browser task runner is the existing pattern for "browser tasks in missions." Phase 4 should read it to model the new `browser_sandbox` tool on the same dispatch shape, rather than inventing a parallel implementation.

3. **The Dockerfile in the draft is sketch-grade.** `pip install playwright && playwright install --with-deps chromium` is the right sequence, but the draft's noVNC + websockify setup omits the VNC server that has to run between Chromium and noVNC. The correct chain is: **Chromium (headless, remote-debugging-port=9222) → Xvfb → x11vnc (binds to a VNC display) → websockify (translates VNC TCP to WebSocket for the browser's noVNC client)**. The draft's `websockify --web /usr/share/novnc 6080 localhost:9222` proxies noVNC to the CDP port, which is **NOT how noVNC works** — noVNC talks VNC, not Chrome DevTools Protocol. Without Xvfb + x11vnc between them, the noVNC iframe will be blank. The Phase 4 Dockerfile and entrypoint must be corrected.

4. **`sandbox_service.py` is confirmed to exist** (per the workspace doc and `services/AGENTS.md` §11 "Sandbox / playground / preview"). Reuse its container lifecycle for the browser variant — don't write a parallel container orchestrator.

5. **`playwright_controller.py` exists** in `app/tools/` per the workspace doc. Don't conflate it with the per-tool files (`browser_navigate.py` etc.) — it may be a higher-level controller. Read it first to see whether Phase 4 can delegate to it inside the sandbox rather than re-implementing dispatch.

---

## 🔴 Reference prototype patterns (from `.sisyphus/src/`)

### A. `SandboxTile.tsx` — the tile UX template

The prototype's `SandboxTile` (123 lines) is the exact component template for the browser sandbox tile:
- **Output/Preview tab switcher:** two buttons with icons (Terminal for Output, ExternalLink for Preview), active state styling
- **Status badge:** `running` → green pill, else gray
- **Output tab:** monospace terminal-style output block
- **Preview tab:** browser-chrome-styled frame with traffic-light dots (red/yellow/green circles), URL bar showing `previewUrl`, "open in new tab" button
- **Header controls:** reload (RotateCw icon), close (X icon)

The browser sandbox tile should reuse this exact layout — the Preview tab becomes the noVNC iframe.

### B. The `sandboxes` table schema (migration reference)

From `db/schema.ts:206-227`:
```
id, sandbox_type ("code" | "browser"), language, thread_id (FK SET NULL),
message_id (FK SET NULL), container_id, preview_url, preview_token,
status ("creating" | "running" | "stopped" | "expired"), files (JSONB),
expires_at, created_at
INDEX: (thread_id)
```

The `sandbox_type` column distinguishes code sandboxes from browser sandboxes — both share the same table. `preview_url` and `preview_token` are the forward-auth pair reused from the existing sandboxd pattern.

### C. `sandbox_event` SSE events drive tile lifecycle

From the mock stream (`chat/stream/route.ts:194-203`):
```json
{
  "type": "sandbox_event",
  "data": {
    "sandboxId": "sbx_demo_001",
    "status": "running",
    "previewUrl": "/sandbox-preview/demo",
    "language": "python",
    "timestamp": 1234567890
  }
}
```

These events are collected into `streaming.sandboxEvents[]` and the `SandboxTile` auto-appears when the array is non-empty. Phase 4's `browser_sandbox` tool must emit these events as it launches and navigates.

### D. Backend-driven tile opening via `canvas_update`

When a sandbox is launched, the backend sends:
```json
{
  "type": "canvas_update",
  "data": {
    "action": "open_tile",
    "tileKind": "browser_sandbox",
    "config": { "url": "https://example.com", "sandboxId": "..." }
  }
}
```

This means the `/browse <url>` slash command flow is: user types `/browse` → frontend calls backend tool → backend creates container → backend emits `sandbox_event` + `canvas_update` → frontend auto-opens the browser tile.

---

## Problem

The existing browser tools (`browser_navigate.py`, `browser_click.py`, `browser_screenshot.py`, `browser_snapshot.py`) run Playwright inside the backend container — no isolation, no live visual preview. The user can't watch the agent browse. There's no way to see what the agent is doing in a browser in real time.

**Goal:** An isolated Playwright container with a noVNC iframe preview, dockable as a canvas tile. The agent's browser actions stream as tool-invocation cards in the tile header while the user watches the live browser in the iframe.

---

## Acceptance Criteria

- [ ] New sandboxd Docker image variant (`sandboxd/Dockerfile.browser`) with Playwright + Chromium + Xvfb + x11vnc + websockify + noVNC (the correct VNC chain, not the draft's broken direct-CDP proxy)
- [ ] `browser_sandbox` tool with: `launch`, `navigate`, `click`, `type`, `screenshot`, `snapshot`
- [ ] Tool requires `tool:browser-sandbox` capability scope
- [ ] Browser sandbox tile in canvas with noVNC iframe + tool invocation thread
- [ ] `?token=` forward-auth works for the noVNC iframe (reuses existing `SandboxPreviewButton` pattern)
- [ ] Agent's `navigate`/`click`/`type` calls render as `ToolInvocation` cards in tile header
- [ ] `pnpm lint && pnpm build` passes
- [ ] Backend tests pass: `test_browser_sandbox.py`
- [ ] `/browse <url>` slash command works (was stubbed in Phase 3 — wire it up here)

---

## Sub-tasks

### 4.1 — Build sandboxd browser image (correct VNC chain)

**Create:** `sandboxd/Dockerfile.browser`

Extends the existing sandboxd base image pattern. The correct chain is:

```dockerfile
FROM sandboxd-base:latest

# Install Playwright + Chromium (with OS deps)
RUN pip install playwright && playwright install --with-deps chromium

# VNC stack: Xvfb (virtual framebuffer), x11vnc (VNC server), websockify (VNC↔WS), noVNC (JS client)
RUN apt-get update && apt-get install -y \
    xvfb x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*

# Expose noVNC web client on 6080, VNC server on 5900 (internal), CDP on 9222
EXPOSE 6080 9222

COPY browser-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

**Create:** `sandboxd/browser-entrypoint.sh`

```bash
#!/bin/bash
# 1. Start Xvfb on display :99
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# 2. Launch Chromium headless with remote debugging
chromium --remote-debugging-port=9222 --no-sandbox --disable-gpu --disable-dev-shm-usage &

# 3. Start x11vnc server bound to display :99, port 5900
x11vnc -display :99 -forever -shared -rfbport 5900 -nopw &

# 4. Start websockify proxying noVNC's WebSocket client to the VNC server
#    (websockify --web serves the noVNC HTML/JS client on :6080, proxies to VNC :5900)
websockify --web /usr/share/novnc 6080 localhost:5900 &

wait
```

**⚠ The DeepSeek draft's `websockify 6080 localhost:9222` was wrong** — noVNC cannot speak Chrome DevTools Protocol. The correct target is the VNC server (`localhost:5900`), not the CDP port (`9222`).

### 4.2 — Create browser_sandbox tool (backend)

**Create:** `backend/app/tools/browser_sandbox.py`

Before coding, read `app/tools/playwright_controller.py` (the existing higher-level Playwright controller) and `app/services/mission_executor.py`'s `browser_task_runner.py` (existing browser task dispatch). The new tool can delegate to the controller's code path — the change is that the browser runs inside the sandboxd container, not the backend.

```python
class BrowserSandboxTool(BaseTool):
    """Isolated browser environment with live preview."""

    def __init__(self):
        super().__init__(metadata=ToolMetadata(
            tool_id="browser_sandbox",
            name="Browser Sandbox",
            description="Launch an isolated browser with live preview. Navigate, click, type, and screenshot.",
            category="browser",
            input_schema={...},
            required_scopes=["tool:browser-sandbox"],
            requires_sandbox=True,
        ))

    async def execute(self, input_data: dict) -> ToolResult:
        action = input_data.get("action")
        sandbox_id = input_data.get("sandbox_id")

        if action == "launch":
            # Spin up sandboxd browser container
            # Return { sandbox_id, preview_url }
        elif action == "navigate":
            # Proxy to Playwright inside container (via CDP port 9222)
        elif action == "click":
            # ...
        elif action == "type":
            # ...
        elif action == "screenshot":
            # Return base64 screenshot
        elif action == "snapshot":
            # Return accessibility tree snapshot
```

**Sub-actions:** `launch`, `navigate`, `click`, `type`, `screenshot`, `snapshot`, `close`

**Read first:** `app/tools/browser_navigate.py`, `browser_click.py`, `browser_screenshot.py`, `browser_snapshot.py`, and `playwright_controller.py` to reuse existing Playwright call shapes (the args schema and result format). Don't invent a different return shape per action.

### 4.3 — Wire to sandboxd container management (backend)

**File:** `backend/app/services/sandbox_service.py`

Reuse existing sandboxd container lifecycle:
- `launch` → create container from `sandboxd-browser` image, expose via Traefik
- Preview URL: `https://s-{sandbox_id}-6080.preview.flowmanner.com`
- Same forward-auth chain as code sandbox previews (the fix at commit `b6012d1b` already parses `X-Forwarded-Uri` tokens; reuse it for port 6080)
- Container auto-expires after 35 minutes (existing pattern)

### 4.4 — Browser sandbox tile (frontend)

**Create:** `frontend/src/components/chat/BrowserSandboxTile.tsx`

Canvas tile for browser sandbox:
- **Top section:** noVNC iframe using `SandboxPreviewButton`'s `?token=` auth pattern
- **Bottom section:** scrollable thread of `ToolInvocation` cards for the agent's browser actions
- **Header:** sandbox status (launching → ready → expired), URL bar showing current page

```tsx
const BrowserSandboxTile: React.FC<{ tile: CanvasTile }> = ({ tile }) => {
  const { sandbox_id, preview_url } = tile.payload;
  const { accessToken } = useAuth();

  return (
    <div className="flex flex-col h-full">
      {/* noVNC iframe */}
      <div className="flex-1">
        <iframe
          src={`${preview_url}?token=${accessToken}`}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-same-origin"
        />
      </div>

      {/* Agent action thread */}
      <div className="h-48 overflow-y-auto border-t">
        {tile.payload.actions?.map(action => (
          <ToolCallCard key={action.call_id} invocation={action} />
        ))}
      </div>
    </div>
  );
};
```

### 4.5 — Wire browser_sandbox to agent tool calling

**File:** `backend/app/services/chat_service.py`

Update `_get_chat_openai_tools()` to include `browser_sandbox` in the allowed tool set (read the Phase 1 allowlist comment from `phase-1` — by Phase 4, browser-sandbox is in the allowlist; document the change in a comment block).

### 4.6 — Capability gating

The tool has `required_scopes=["tool:browser-sandbox"]`. When the LLM tries to call it without the scope:
1. Backend `_execute_tool_call` (Phase 1's capability check) returns a `permission_request` SSE event (Phase 2 pattern)
2. Frontend renders an inline `PermissionCard` with Approve/Deny
3. On approve: capability token issued, tool call retried

### 4.7 — Wire `/browse` slash command (was stubbed in Phase 3)

**File:** `frontend/src/lib/slash-commands.ts`

Replace the Phase 3 stub for `/browse` with a real handler:
```typescript
{ command: 'browse', handler: (args) => addTile({ kind: 'browser-sandbox', title: `Browse: ${args}`, payload: { url: args } }) }
```

### 4.8 — Tests

**Backend:** Create `backend/tests/test_browser_sandbox.py`
- Test container launches and preview URL returns 200 with valid token
- Test Playwright commands proxy correctly (navigate, click, type)
- Test container auto-expires after timeout
- Test capability token required (403 without scope)

**Frontend:** Manual test:
- `/browse https://example.com` in chat
- Browser sandbox tile opens, page loads in iframe
- Agent clicks render as tool-invocation cards in tile header

### 4.9 — Verification gate

```bash
# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/test_browser_sandbox.py -v

# Frontend
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build

# Manual: /browse https://example.com → live preview in tile
# Verify noVNC iframe is NOT blank (it would be with the draft's broken websockify config)
```

---

## File Map

| File | Action |
|------|--------|
| `sandboxd/Dockerfile.browser` | **NEW** — Playwright + Xvfb + x11vnc + websockify + noVNC (correct VNC chain) |
| `sandboxd/browser-entrypoint.sh` | **NEW** — container startup script (Xvfb → x11vnc → websockify, not direct CDP proxy) |
| `backend/app/tools/browser_sandbox.py` | **NEW** — browser sandbox tool (delegate to existing Playwright tool shapes) |
| `backend/app/services/sandbox_service.py` | Extend for browser container lifecycle (reuse existing) |
| `backend/app/services/chat_service.py` | Add `browser_sandbox` to chat tool set (Phase 1 allowlist update) |
| `backend/tests/test_browser_sandbox.py` | **NEW** — browser sandbox tests |
| `frontend/src/components/chat/BrowserSandboxTile.tsx` | **NEW** — noVNC tile component |
| `frontend/src/lib/slash-commands.ts` | Wire `/browse` (was stubbed in Phase 3) |

---

## Risks

| Risk | Mitigation |
|------|------------|
| noVNC performance over WireGuard | Test with real network conditions. Fall back to screenshot-only mode if too slow. |
| Chromium memory usage in sandbox | Limit to 1 concurrent browser sandbox per workspace. |
| Container startup time | Pre-pull image. Accept 5-10s cold start. Show "Launching..." state in tile. |
| Cross-origin iframe restrictions | Same forward-auth pattern as code sandbox. `sandbox="allow-scripts allow-same-origin"`. |
| Draft's broken noVNC config ships blank iframe | 4.1 explicitly corrects the VNC chain (`Chromium → Xvfb → x11vnc → websockify → noVNC`); 4.9 verification gate checks the iframe is not blank. |
| `playwright_controller.py` exists and Phase 4 reinvents it | Read it before coding; delegate where possible. |
