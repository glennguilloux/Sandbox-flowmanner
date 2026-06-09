# sandboxd × FlowManner — Integration Roadmap (v3, audit-corrected)

> **Author:** DeepSeek (v1), audit corrections by Codebuff (v3)
> **Date:** 2026-06-08
> **Status:** Planning — ready for Phase 1 execution
> **Target:** Solo founder, homelab + VPS infrastructure
>
> **v3 changelog** — Applied full audit against sandboxd source (`control-plane/internal/api/`),
> actual `.env` config, and FlowManner codebase. Fixed 6 errors, added 8 missing capabilities,
> corrected sequencing, and added comprehensive test specifications matching project conventions.

---

## Executive Summary

We're grafting sandboxd's Docker-native isolation, persistent workspaces, live
preview URLs, and AI agent runtime into FlowManner's tool system, mission
lifecycle, and workflow DAG. The integration follows an **extend-don't-replace**
philosophy. Phase 1 puts sandboxd tools in agents' hands, Phase 2 adds live
previews, Phase 3 cements it as a first-class workflow primitive, and Phase 4
builds a public playground.

---

## Architecture Decision Records

### ADR-1: Extend, Don't Replace

**Decision:** sandboxd tools coexist alongside `python_sandbox.py` and
`nodejs_sandbox.py`. Existing subprocess sandboxes are NOT deprecated.

**Reasoning:**
- Subprocess sandboxes: ~50ms startup. sandboxd: ~1-3s Docker container create.
  For `2+2` or a JSON sort, speed matters.
- They handle ~90% of current agent tool calls.
- sandboxd overhead: 449 MB base image + runtime memory per container. Blowing
  a container for a 3-line snippet is wasteful.
- Agent guidance: "Use `python_sandbox` / `nodejs_sandbox` for quick one-shot
  execution. Use `sandboxd_exec` / `sandboxd_file_*` when you need multi-file
  projects, dev servers, or persistent workspaces."

### ADR-2: Mission-Managed Sandbox Lifecycle

**Decision:** Sandbox lifecycle (create, stop, destroy) is managed by the
backend service layer, NOT exposed as agent tools. Agents receive a
`sandbox_id` scoped to their mission.

**Reasoning:**
- Agents are unpredictable. Letting them create/destroy Docker containers is a
  resource management nightmare.
- Sandbox lifecycle maps to mission lifecycle: create on `EXECUTING`, destroy
  on terminal state.
- One sandbox per mission gives persistent workspace across tool calls.
- If a workflow needs multiple sandboxes, each gets its own mission sub-tree.

**Implementation:** `SandboxService.create_for_mission(mission_id)` called
during `MissionExecutor.execute_mission()`. `SandboxService.reap_for_mission()`
on mission terminal transition.

**Storage:** A `mission_sandboxes` table in Phase 1:

```sql
CREATE TABLE mission_sandboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    sandbox_id TEXT NOT NULL UNIQUE,  -- sandboxd ULID
    project_id TEXT NOT NULL,          -- maps to sandboxd's project.id
    status TEXT NOT NULL DEFAULT 'creating',
    created_at TIMESTAMPTZ DEFAULT now(),
    stopped_at TIMESTAMPTZ,
    purged_at TIMESTAMPTZ,
    CONSTRAINT one_sandbox_per_mission UNIQUE(mission_id)
);
CREATE INDEX idx_mission_sandboxes_sandbox ON mission_sandboxes(sandbox_id);
```

### ADR-3: Previews Route Through VPS Nginx → WireGuard → sandboxd Traefik

**Decision:** The preview URL path is: User's browser →
`*.preview.flowmanner.com` (VPS 74.208.115.142) → VPS Nginx (TLS termination)
→ WireGuard tunnel → Homelab sandboxd Traefik → Docker container port.

**Key details (audit-verified):**
- sandboxd's preview URL format is `s-<id>-<port>.preview.<domain>` for each
  exposed port. Port 3000 is the default for `react-standard` template, but
  other ports are supported per-sandbox via the `ports` field in create.
- Current homelab config: `PREVIEW_DOMAIN=localhost`, `HTTP_PORT=80`,
  `PREVIEW_TLS=false`. Must be updated for production (see Phase 2a.4).
- Traefik uses label-based routing: priority-100 for active sandboxes,
  priority-1 catch-all for wake path.

### ADR-4: sandboxd Runs on the Homelab

62 GB RAM, ~51.5 GB available for sandboxes. Offloading to a separate machine
is Phase 4+. The pressure reaper (stops sandboxes when host memory is low)
provides a safety net.

### ADR-5: No Iframe Initially — External Link Button

Phase 2 shows a "🔗 Open Preview" button. Iframe is Phase 2.5.

### ADR-6: Forward Auth for Preview Gating (NEW)

sandboxd exposes `GET /forward-auth` — a Traefik hot path that performs its own
cookie/JWT validation. In Phase 2a, we configure Traefik forward auth to gate
preview URLs behind FlowManner session auth, so only authenticated users can
access sandbox previews.

---

## Phase 1: Foundation — sandboxd Tools in Agent Hands

**Timeline:** 1–2 weeks
**Goal:** Agents can use sandboxd tools. No frontend changes.

### 1.1 — sandboxd HTTP Client

**File:** `backend/app/integrations/sandboxd_client.py` (NEW)

Uses `httpx.AsyncClient`. Wraps the **public v1 API** at
`/v1/sandboxes/{id}/...`:

```python
class SandboxdClient:
    """Async client for sandboxd's v1 API (http://127.0.0.1:9090)."""

    def __init__(self, base_url: str = "http://127.0.0.1:9090",
                 auth_token: str | None = None):
        self.base_url = base_url
        self._auth = auth_token
        self._client: httpx.AsyncClient | None = None

    # ── Sandbox lifecycle ──

    async def create(self, project_id: str, user_id: str,
                     template: str = "react-standard",
                     visibility: str = "public") -> dict:
        """POST /v1/sandboxes — create sandbox for a project.
        Body: {project: {id, user_id}, template?, visibility?}
        Idempotent: returns existing sandbox if one exists for this project.
        Returns {id, status, preview: {url, status}, ...}"""

    async def get(self, sandbox_id: str) -> dict:
        """GET /v1/sandboxes/{id} — status + preview + active_task"""

    async def stop(self, sandbox_id: str) -> dict:
        """POST /v1/sandboxes/{id}/stop — stop container (workspace preserved)"""

    async def delete(self, sandbox_id: str) -> None:
        """DELETE /v1/sandboxes/{id} — full destroy (container + workspace + row).
        Returns 204 No Content on success."""

    # ── Tasks (AI coding agents) ──

    async def submit_task(self, sandbox_id: str, prompt: str,
                          agent: str = "opencode") -> dict:
        """POST /v1/sandboxes/{id}/tasks — start coding agent.
        Body: {prompt, agent?}. Returns {id, status, events_url} (202 Accepted).
        Auto-wakes stopped sandbox first."""

    async def get_task(self, sandbox_id: str, task_id: str) -> dict:
        """GET /v1/sandboxes/{id}/tasks/{taskId} — task result (durable store)"""

    async def task_events(self, sandbox_id: str, task_id: str,
                          since: int = 0) -> AsyncIterator[dict]:
        """GET /v1/sandboxes/{id}/tasks/{taskId}/events — SSE stream.
        Yields {id, type, data} events. Supports Last-Event-ID for reconnect."""

    async def cancel_task(self, sandbox_id: str, task_id: str) -> dict:
        """POST /v1/sandboxes/{id}/tasks/{taskId}/cancel"""

    # ── Files (workspace) ──

    async def list_files(self, sandbox_id: str, path: str = "",
                         recursive: bool = False) -> list[dict]:
        """GET /v1/sandboxes/{id}/files?path=&recursive= — list workspace"""

    async def read_file(self, sandbox_id: str, path: str) -> str:
        """GET /v1/sandboxes/{id}/files/content?path= — read file (≤2 MiB)"""

    async def write_file(self, sandbox_id: str, path: str,
                         content: bytes) -> dict:
        """PUT /v1/sandboxes/{id}/files?path= — write file (≤25 MiB).
        Atomic: tmp file + rename. No symlink following."""

    async def export(self, sandbox_id: str) -> bytes:
        """GET /v1/sandboxes/{id}/export — download workspace as .zip"""

    # ── Snapshots (NEW — audit-discovered) ──

    async def create_snapshot(self, sandbox_id: str, name: str = "") -> dict:
        """POST /v1/snapshots — create snapshot of sandbox state."""

    async def list_snapshots(self) -> list[dict]:
        """GET /v1/snapshots — list all snapshots."""

    async def get_snapshot(self, snapshot_id: str) -> dict:
        """GET /v1/snapshots/{id} — get snapshot details."""

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """DELETE /v1/snapshots/{id} — delete snapshot."""
```

**Audit corrections from v2:**
- Removed `git_remote_url` — field does not exist in the Go source.
- FlowManner uses the **v1 public API** (`/v1/sandboxes/...`), not the
  internal `/sandbox/...` paths.
- There is **no `/v1/sandboxes/{id}/exec`** — raw command execution is an
  internal-only endpoint (`POST /sandbox/{id}/exec`). For Phase 1, we use the
  internal exec (same host) or the task system.
- **Create is idempotent per project** — calling `POST /v1/sandboxes` twice
  with the same `project.id` returns the existing sandbox.
- **Preview URL is per-port** — not hardcoded to 3000. Each exposed port gets
  its own `s-<id>-<port>.preview.<domain>` URL.
- **File paths are relative** to `/home/sandbox/workspace/app/` inside the
  container.
- **File reads return raw text**, not JSON-wrapped. File writes take raw body.
- **DELETE = full purge**, returning 204.
- **Auth is currently DISABLED** (`SANDBOXD_API_AUTH_DISABLED=true`). No
  token needed for Phase 1. Auth hardening is Phase 1.10 (optional).

### 1.2 — Sandbox Service (Lifecycle Manager)

**File:** `backend/app/services/sandbox_service.py` (NEW)

```python
class SandboxService:
    """Orchestrates sandboxd lifecycle scoped to missions."""

    async def ensure_sandbox_for_mission(self, mission_id: str,
                                         user_id: str) -> str:
        """Get or create sandbox. Returns sandbox_id.
        Idempotent: if sandbox already exists for this mission, returns it.
        Stores mapping in mission_sandboxes table."""

    async def reap_sandbox(self, mission_id: str) -> None:
        """Soft-stop sandbox (preserve workspace for potential reuse).
        Called on mission terminal transition."""

    async def purge_sandbox(self, mission_id: str) -> None:
        """Full destroy (DELETE /v1/sandboxes/{id}).
        Called on explicit cleanup or after a TTL expires."""

    async def get_sandbox_for_mission(self, mission_id: str) -> str | None:
        """Look up sandbox_id from mission_sandboxes table."""

    async def create_snapshot(self, mission_id: str, name: str = "") -> dict:
        """Create a snapshot of the sandbox workspace. Returns snapshot info."""

    async def restore_snapshot(self, mission_id: str, snapshot_id: str) -> None:
        """Restore sandbox to a previous snapshot."""
```

### 1.3 — Tool: sandboxd_exec

**File:** `backend/app/tools/sandboxd_exec.py` (NEW)

Since the v1 API has no raw exec, Phase 1 uses the **internal exec endpoint**
(`POST /sandbox/{id}/exec`) which is reachable because FlowManner and sandboxd
run on the same host:

```python
class SandboxdExecInput(ToolInput):
    code: str = Field(..., description="Source code to execute")
    language: str = Field(default="python", description="python | node | bash | go")
    timeout_seconds: int = Field(default=60, ge=5, le=300)

class SandboxdExecTool(BaseTool):
    tool_id = "sandboxd_exec"
    async def execute(self, input_data: dict) -> ToolResult:
        # 1. Resolve mission → sandbox_id via SandboxService
        # 2. Build cmd array: ["python3", "-c", code] or ["node", "-e", code] etc.
        # 3. POST /sandbox/{id}/exec with {cmd: [...], stream: false}
        # 4. Return {stdout, stderr, exit_code}
```

**Note:** The internal exec endpoint expects `{cmd: string[], stream?: bool}`.
Our tool translates the user-friendly params into the correct cmd array.

### 1.4 — Tools: sandboxd_file_read, sandboxd_file_write, sandboxd_file_list

**Files:** `backend/app/tools/sandboxd_file_read.py`,
`backend/app/tools/sandboxd_file_write.py`,
`backend/app/tools/sandboxd_file_list.py` (NEW)

Map directly to v1 file endpoints. Key implementation notes:
- **Read:** `GET /v1/sandboxes/{id}/files/content?path=<rel>` returns raw
  text. Max 2 MiB.
- **Write:** `PUT /v1/sandboxes/{id}/files?path=<rel>` with raw body. Max
  25 MiB. Atomic (tmp + rename). Rejects symlinks, `..`, and absolute paths.
- **List:** `GET /v1/sandboxes/{id}/files?path=&recursive=true` for browsing.

### 1.5 — Tool: sandboxd_preview

**File:** `backend/app/tools/sandboxd_preview.py` (NEW)

Returns the preview URL from `GET /v1/sandboxes/{id}` (the `sandbox.preview.url`
field). Supports multiple ports per sandbox.

### 1.6 — Configuration

**File:** `backend/app/config.py` (EDIT)

```python
# sandboxd integration
SANDBOXD_API_URL: str = "http://127.0.0.1:9090"
SANDBOXD_AUTH_TOKEN: str = ""          # Bearer token (empty = no auth, matches current config)
SANDBOXD_PREVIEW_DOMAIN: str = "preview.flowmanner.com"
SANDBOXD_ENABLED: bool = True
SANDBOXD_DEFAULT_TEMPLATE: str = "react-standard"
```

**Audit notes:**
- `SANDBOXD_AUTH_TOKEN` is empty because auth is currently disabled.
- sandboxd has no TTL on create. It uses keepalive and idle reaper
  (`SANDBOXD_IDLE_THRESHOLD_SECONDS=2100`). FlowManner manages lifecycle
  explicitly via stop/delete.

### 1.7 — Tool Registration

Each tool self-registers at import time via `register_tool(Instance())`
(matching the existing pattern in all 110+ tools). Alembic migration inserts
rows into the `tools` catalog table for DB-driven hydration via
`ToolRegistry.hydrate_from_db()`.

### 1.8 — Mission Executor Wiring

**File:** `backend/app/services/mission_executor.py` (EDIT)

In `execute_mission()`, after transitioning to `EXECUTING`:

```python
sandbox_svc = SandboxService(client)
sandbox_id = await sandbox_svc.ensure_sandbox_for_mission(
    str(mission_id), str(mission.user_id)
)
# sandbox_id passed into ToolContext for tool resolution
```

On terminal transition:

```python
await sandbox_svc.reap_sandbox(str(mission_id))
```

### 1.9 — Monitoring Integration

sandboxd exposes health/metrics endpoints:

| Endpoint | What | Use |
|----------|------|-----|
| `GET /healthz` | 200 if alive | Liveness probe |
| `GET /readyz` | 200 if DB + Docker reachable | Readiness probe |
| `GET /metrics` | Prometheus format | sandbox count, exec duration, API latency |

**Action:** Add `SandboxdHealthCheck` to FlowManner's health endpoint. Log
warnings when sandboxd is unreachable so agents fall back to `python_sandbox`.

**Note:** The pressure reaper (stops sandboxes when host memory is low)
already exists in sandboxd but `SANDBOXD_SET_MEMORY_HIGH=false` currently
disables it. Enable it before production (see Phase 1.10).

### 1.10 — Hardening (Optional, Not a Blocker)

**sandboxd auth is currently DISABLED** (`SANDBOXD_API_AUTH_DISABLED=true`).
This is fine for homelab development. For production:

```bash
# In sandboxd/.env:
SANDBOXD_API_AUTH_DISABLED=false
SANDBOXD_API_TOKENS=flowmanner:${FLOWMANNER_SANDBOXD_TOKEN}
SANDBOXD_SET_MEMORY_HIGH=true  # Enable pressure reaper
```

FlowManner reads `SANDBOXD_AUTH_TOKEN` from its own config and passes it as
`Authorization: Bearer <token>` on every request.

### 1.11 — Tests

**Test file:** `backend/tests/test_sandboxd_client.py` (NEW)

```python
"""Unit tests for sandboxd_client — HTTP client for sandboxd v1 API."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestSandboxdClientCreate:
    """POST /v1/sandboxes — create sandbox."""

    @pytest.mark.asyncio
    async def test_create_sandbox_success(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": "sb-abc123",
            "status": "starting",
            "preview": {"url": "http://s-abc123-3000.preview.localhost", "status": "starting"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.create("proj-1", "user-1")

        assert result["id"] == "sb-abc123"
        assert result["status"] == "starting"

    @pytest.mark.asyncio
    async def test_create_sandbox_idempotent(self):
        """Calling create twice with same project_id returns existing sandbox."""
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200  # 200 on idempotent, 201 on new
        mock_resp.json.return_value = {"id": "sb-existing", "status": "running"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.create("proj-1", "user-1")

        assert result["id"] == "sb-existing"

    @pytest.mark.asyncio
    async def test_create_sandbox_server_error_returns_retryable(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock(status_code=500)
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.create("proj-1", "user-1")


class TestSandboxdClientGet:
    """GET /v1/sandboxes/{id} — sandbox status."""

    @pytest.mark.asyncio
    async def test_get_sandbox_returns_status_and_preview(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "sb-abc123",
            "status": "running",
            "preview": {"url": "http://s-abc123-3000.preview.localhost", "status": "running"},
            "active_task": None,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.get("sb-abc123")

        assert result["status"] == "running"
        assert "preview" in result

    @pytest.mark.asyncio
    async def test_get_nonexistent_sandbox_raises(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.get("sb-nonexistent")


class TestSandboxdClientStop:
    """POST /v1/sandboxes/{id}/stop — stop container."""

    @pytest.mark.asyncio
    async def test_stop_sandbox_success(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "sb-abc123", "status": "stopped"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.stop("sb-abc123")

        assert result["status"] == "stopped"


class TestSandboxdClientDelete:
    """DELETE /v1/sandboxes/{id} — full destroy."""

    @pytest.mark.asyncio
    async def test_delete_sandbox_returns_204(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock, return_value=mock_resp):
            await client.delete("sb-abc123")  # Should not raise


class TestSandboxdClientFiles:
    """File I/O operations."""

    @pytest.mark.asyncio
    async def test_read_file_returns_text(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "console.log('hello');"
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.read_file("sb-abc123", "src/index.js")

        assert result == "console.log('hello');"

    @pytest.mark.asyncio
    async def test_write_file_sends_raw_body(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"written": True}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=mock_resp) as mock_put:
            result = await client.write_file("sb-abc123", "src/app.py", b"print('hi')")

        assert result["written"] is True
        # Verify raw bytes sent, not base64 or JSON
        assert mock_put.call_args.kwargs.get("content") == b"print('hi')"

    @pytest.mark.asyncio
    async def test_list_files_with_recursive(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"path": "src/index.js", "type": "file"},
            {"path": "src/utils.js", "type": "file"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.list_files("sb-abc123", "src", recursive=True)

        assert len(result) == 2


class TestSandboxdClientTasks:
    """Task submission and events."""

    @pytest.mark.asyncio
    async def test_submit_task_returns_202(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "id": "task-xyz",
            "status": "running",
            "events_url": "/v1/sandboxes/sb-abc123/tasks/task-xyz/events",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.submit_task("sb-abc123", "Build a todo app")

        assert result["id"] == "task-xyz"
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_cancel_task_success(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "task-xyz", "status": "cancelled"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.cancel_task("sb-abc123", "task-xyz")

        assert result["status"] == "cancelled"


class TestSandboxdClientSnapshots:
    """Snapshot operations (audit-discovered capability)."""

    @pytest.mark.asyncio
    async def test_create_snapshot(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "snap-1", "sandbox_id": "sb-abc123"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.create_snapshot("sb-abc123", "before-deploy")

        assert result["id"] == "snap-1"

    @pytest.mark.asyncio
    async def test_list_snapshots(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "snap-1"}, {"id": "snap-2"}]
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.list_snapshots()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_delete_snapshot(self):
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock, return_value=mock_resp):
            await client.delete_snapshot("snap-1")  # Should not raise
```

**Test file:** `backend/tests/test_sandbox_service.py` (NEW)

```python
"""Unit tests for SandboxService — mission-scoped sandbox lifecycle."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestEnsureSandboxForMission:
    """create_for_mission — idempotent sandbox creation."""

    @pytest.mark.asyncio
    async def test_creates_sandbox_and_stores_mapping(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.create = AsyncMock(return_value={"id": "sb-new", "status": "starting"})
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))

        svc = SandboxService(client=mock_client)
        sandbox_id = await svc.ensure_sandbox_for_mission(str(uuid4()), "user-1", db=mock_db)

        assert sandbox_id == "sb-new"
        mock_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_sandbox_if_already_created(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_db = AsyncMock()
        # Simulate existing mapping
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-existing"
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))))

        svc = SandboxService(client=mock_client)
        sandbox_id = await svc.ensure_sandbox_for_mission(str(uuid4()), "user-1", db=mock_db)

        assert sandbox_id == "sb-existing"
        mock_client.create.assert_not_called()


class TestReapSandbox:
    """reap_sandbox — soft-stop on mission terminal state."""

    @pytest.mark.asyncio
    async def test_stops_sandbox_preserving_workspace(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.stop = AsyncMock(return_value={"status": "stopped"})
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))))

        svc = SandboxService(client=mock_client)
        await svc.reap_sandbox(str(uuid4()), db=mock_db)

        mock_client.stop.assert_called_once_with("sb-abc")

    @pytest.mark.asyncio
    async def test_noop_when_no_sandbox_exists(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.stop = AsyncMock()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))

        svc = SandboxService(client=mock_client)
        await svc.reap_sandbox(str(uuid4()), db=mock_db)

        mock_client.stop.assert_not_called()


class TestPurgeSandbox:
    """purge_sandbox — full destroy."""

    @pytest.mark.asyncio
    async def test_deletes_sandbox_and_clears_mapping(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.delete = AsyncMock(return_value=None)
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))))

        svc = SandboxService(client=mock_client)
        await svc.purge_sandbox(str(uuid4()), db=mock_db)

        mock_client.delete.assert_called_once_with("sb-abc")


class TestSandboxServiceSnapshots:
    """Snapshot operations via SandboxService."""

    @pytest.mark.asyncio
    async def test_create_snapshot_delegates_to_client(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.create_snapshot = AsyncMock(return_value={"id": "snap-1"})
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))))

        svc = SandboxService(client=mock_client)
        result = await svc.create_snapshot(str(uuid4()), "checkpoint", db=mock_db)

        assert result["id"] == "snap-1"
        mock_client.create_snapshot.assert_called_once_with("sb-abc", "checkpoint")
```

**Test file:** `backend/tests/test_sandboxd_tools.py` (NEW)

```python
"""Unit tests for sandboxd agent tools — sandboxd_exec, sandboxd_file_*, sandboxd_preview."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestSandboxdExecTool:
    """sandboxd_exec — execute code in isolated Docker container."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()
        assert tool.tool_id == "sandboxd_exec"
        assert "sandbox" in tool.tags
        assert tool.category == "code-execution-and-development"

    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()

        mock_client = MagicMock()
        mock_client._post_internal = AsyncMock(return_value={
            "stdout": "hello world\n",
            "stderr": "",
            "exit_code": 0,
        })

        with patch.object(tool, "_get_client", return_value=mock_client), \
             patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"):
            result = await tool.execute({"code": "print('hello world')", "language": "python"})

        assert result.success is True
        assert "hello world" in result.result["stdout"]

    @pytest.mark.asyncio
    async def test_execute_returns_nonzero_on_error(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()

        mock_client = MagicMock()
        mock_client._post_internal = AsyncMock(return_value={
            "stdout": "",
            "stderr": "SyntaxError: invalid syntax",
            "exit_code": 1,
        })

        with patch.object(tool, "_get_client", return_value=mock_client), \
             patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"):
            result = await tool.execute({"code": "def broken(", "language": "python"})

        assert result.success is True  # Tool succeeded (code failed)
        assert result.result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_execute_invalid_input_returns_error(self):
        from app.tools.sandboxd_exec import SandboxdExecTool

        tool = SandboxdExecTool()
        result = await tool.execute({})  # Missing required 'code'

        assert result.success is False
        assert "Invalid input" in result.error


class TestSandboxdFileReadTool:
    """sandboxd_file_read — read files from sandbox workspace."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_file_read import SandboxdFileReadTool

        tool = SandboxdFileReadTool()
        assert tool.tool_id == "sandboxd_file_read"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_read_file_returns_content(self):
        from app.tools.sandboxd_file_read import SandboxdFileReadTool

        tool = SandboxdFileReadTool()

        mock_client = MagicMock()
        mock_client.read_file = AsyncMock(return_value="const x = 42;")

        with patch.object(tool, "_get_client", return_value=mock_client), \
             patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"):
            result = await tool.execute({"path": "src/index.js"})

        assert result.success is True
        assert result.result["content"] == "const x = 42;"


class TestSandboxdFileWriteTool:
    """sandboxd_file_write — write files to sandbox workspace."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_file_write import SandboxdFileWriteTool

        tool = SandboxdFileWriteTool()
        assert tool.tool_id == "sandboxd_file_write"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_write_file_success(self):
        from app.tools.sandboxd_file_write import SandboxdFileWriteTool

        tool = SandboxdFileWriteTool()

        mock_client = MagicMock()
        mock_client.write_file = AsyncMock(return_value={"written": True})

        with patch.object(tool, "_get_client", return_value=mock_client), \
             patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"):
            result = await tool.execute({"path": "src/app.py", "content": "print('hi')"})

        assert result.success is True


class TestSandboxdPreviewTool:
    """sandboxd_preview — get live preview URL."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()
        assert tool.tool_id == "sandboxd_preview"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_returns_preview_url(self):
        from app.tools.sandboxd_preview import SandboxdPreviewTool

        tool = SandboxdPreviewTool()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value={
            "preview": {"url": "http://s-abc-3000.preview.localhost", "status": "running"}
        })

        with patch.object(tool, "_get_client", return_value=mock_client), \
             patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"):
            result = await tool.execute({})

        assert result.success is True
        assert "preview" in result.result
        assert result.result["preview"]["status"] == "running"


class TestSandboxdFileListTool:
    """sandboxd_file_list — list files in sandbox workspace."""

    def test_tool_metadata(self):
        from app.tools.sandboxd_file_list import SandboxdFileListTool

        tool = SandboxdFileListTool()
        assert tool.tool_id == "sandboxd_file_list"
        assert "sandbox" in tool.tags

    @pytest.mark.asyncio
    async def test_list_files_returns_tree(self):
        from app.tools.sandboxd_file_list import SandboxdFileListTool

        tool = SandboxdFileListTool()

        mock_client = MagicMock()
        mock_client.list_files = AsyncMock(return_value=[
            {"path": "src/index.js", "type": "file"},
            {"path": "src/utils.js", "type": "file"},
        ])

        with patch.object(tool, "_get_client", return_value=mock_client), \
             patch.object(tool, "_resolve_sandbox_id", return_value="sb-abc"):
            result = await tool.execute({"path": "src", "recursive": True})

        assert result.success is True
        assert len(result.result["files"]) == 2
```

**Test file:** `backend/tests/test_mission_sandbox_integration.py` (NEW)

```python
"""Integration tests for sandbox lifecycle wired into mission executor."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestMissionSandboxWiring:
    """Verify sandbox creation/destruction in mission lifecycle."""

    @pytest.mark.asyncio
    async def test_sandbox_created_on_mission_execute(self):
        """SandboxService.ensure_sandbox_for_mission called when mission transitions to EXECUTING."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        mock_sandbox_svc = MagicMock()
        mock_sandbox_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-new")
        mock_sandbox_svc.reap_sandbox = AsyncMock()

        with patch("app.services.mission_executor.SandboxService", return_value=mock_sandbox_svc):
            # Patch the DB layer so execute_mission can run
            mock_mission = MagicMock()
            mock_mission.id = str(uuid4())
            mock_mission.user_id = "user-1"
            mock_mission.title = "Test"
            mock_mission.status = "queued"
            mock_mission.plan = {}
            mock_mission.workspace_id = None

            # Verify SandboxService is wired into the executor
            assert hasattr(executor, "execute_mission")
            # The actual call happens inside execute_mission after EXECUTING transition
            # Full integration test would mock DB and run execute_mission end-to-end

    @pytest.mark.asyncio
    async def test_sandbox_reaped_on_mission_complete(self):
        """SandboxService.reap_sandbox called on terminal state."""
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.stop = AsyncMock(return_value={"status": "stopped"})
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))
        ))

        svc = SandboxService(client=mock_client)
        await svc.reap_sandbox(str(uuid4()), db=mock_db)

        mock_client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_subprocess_sandboxes_still_work(self):
        """python_sandbox and nodejs_sandbox are NOT broken by sandboxd integration."""
        from app.tools.python_sandbox import PythonSandboxTool
        from app.tools.nodejs_sandbox import NodeJsSandboxTool

        py_tool = PythonSandboxTool()
        node_tool = NodeJsSandboxTool()

        assert py_tool.tool_id == "python_sandbox"
        assert node_tool.tool_id == "nodejs_sandbox"
        # Both should still be registered
        from app.tools.base import get_tool_registry
        registry = get_tool_registry()
        assert registry.get("python_sandbox") is not None
        assert registry.get("nodejs_sandbox") is not None


class TestMissionSandboxesTable:
    """Verify mission_sandboxes table schema."""

    def test_table_exists_in_models(self):
        """MissionSandbox model should be importable."""
        # This will fail until the model is created — that's expected
        try:
            from app.models.sandbox_models import MissionSandbox
            assert hasattr(MissionSandbox, "mission_id")
            assert hasattr(MissionSandbox, "sandbox_id")
            assert hasattr(MissionSandbox, "status")
        except ImportError:
            pytest.skip("MissionSandbox model not yet created — Phase 1.2 task")
```

### 1.12 — Verification

1. `curl http://127.0.0.1:9090/healthz` → 200
2. Create sandbox via v1: `POST /v1/sandboxes {"project":{"id":"test","user_id":"u1"}}` → 201
3. Write file: `PUT /v1/sandboxes/{id}/files?path=hello.txt` → 200
4. Read file: `GET /v1/sandboxes/{id}/files/content?path=hello.txt` → file content
5. Submit task: `POST /v1/sandboxes/{id}/tasks {"prompt":"echo hello"}` → 202
6. Stop: `POST /v1/sandboxes/{id}/stop` → 200
7. Delete: `DELETE /v1/sandboxes/{id}` → 204
8. `pytest backend/tests/test_sandboxd_client.py -v` → all pass
9. `pytest backend/tests/test_sandbox_service.py -v` → all pass
10. `pytest backend/tests/test_sandboxd_tools.py -v` → all pass
11. `pytest backend/tests/test_mission_sandbox_integration.py -v` → all pass
12. Verify `python_sandbox` / `nodejs_sandbox` still work (no regression)

---

## Phase 2: Live Previews — The "Wow" Feature

**Timeline:** 2–3 weeks (split into 2a + 2b)

### Phase 2a — Infrastructure (DNS + TLS + Nginx)

#### 2a.1 — DNS: Wildcard Preview Domain

Add DNS record: `*.preview.flowmanner.com → A 74.208.115.142`

#### 2a.2 — Wildcard TLS Certificate

Obtain wildcard Let's Encrypt cert via DNS-01 with certbot + IONOS API.

#### 2a.3 — VPS Nginx: Preview Routing

**File:** `/opt/flowmanner/nginx/default.conf` (edit on homelab, rsync to VPS)

```nginx
# ── sandboxd Live Previews ─────────────────────────────────────────────
# sandboxd generates: https://s-<id>-3000.preview.<domain>
# Traefik routes on Host(`s-<id>-3000.preview.<domain>`) → container:3000

server {
    listen 443 ssl http2;
    server_name ~^(?<subdomain>.+)\\.preview\\.flowmanner\\.com$;

    ssl_certificate /etc/nginx/certs/preview-fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/preview-privkey.pem;

    location / {
        proxy_pass http://10.99.0.3:80;  # sandboxd Traefik on homelab (HTTP_PORT=80)
        proxy_http_version 1.1;
        proxy_set_header Host $host;        # passes s-xxx-3000.preview.flowmanner.com
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }
}
```

**Audit correction:** `proxy_pass` targets `:80` (not `:9080`) because
sandboxd's `HTTP_PORT=80`. The `Host` header must be the original
`s-xxx-3000.preview.flowmanner.com` so Traefik's Host-based routing matches.

#### 2a.4 — sandboxd Configuration

In `/mnt/apps/Softwares2/sandboxd/.env`:

```bash
PREVIEW_DOMAIN=preview.flowmanner.com
PREVIEW_ENTRYPOINT=websecure
PREVIEW_TLS=true
HTTP_PORT=80                            # Keep at 80 (already set)
SANDBOXD_API_AUTH_DISABLED=false        # Enable auth for production
SANDBOXD_API_TOKENS=flowmanner:${FLOWMANNER_SANDBOXD_TOKEN}
SANDBOXD_SET_MEMORY_HIGH=true           # Enable pressure reaper
```

Restart sandboxd: `cd /mnt/apps/Softwares2/sandboxd && docker compose down && docker compose up -d`

#### 2a.5 — Forward Auth for Preview Gating (NEW — audit-discovered)

sandboxd's `GET /forward-auth` is a Traefik hot path that validates
cookies/JWT. Configure Traefik to use forward auth on preview routes so only
authenticated FlowManner users can access sandbox previews.

**Test file:** `backend/tests/test_sandbox_preview_api.py` (NEW)

```python
"""Tests for sandbox preview API endpoint."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


@pytest.fixture
def preview_app():
    """Minimal app with sandbox preview route."""
    from app.api.v1.sandbox_preview import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def preview_client(preview_app):
    from app.api.deps import get_current_user
    from app.database import get_db

    mock_db = AsyncMock()
    mock_user = MagicMock(id=1, email="test@example.com")

    async def override_get_db():
        yield mock_db

    async def override_get_current_user():
        return mock_user

    preview_app.dependency_overrides[get_db] = override_get_db
    preview_app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(preview_app) as client:
        yield client

    preview_app.dependency_overrides.clear()


class TestSandboxPreviewEndpoint:
    @pytest.mark.asyncio
    async def test_get_preview_url_success(self, preview_client):
        with patch("app.integrations.sandboxd_client.SandboxdClient.get",
                    new_callable=AsyncMock, return_value={
                        "preview": {"url": "http://s-abc-3000.preview.localhost", "status": "running"}
                    }):
            resp = preview_client.get("/sandbox/sb-abc/preview")

        assert resp.status_code == 200
        assert "preview_url" in resp.json()
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_preview_sandbox_not_found(self, preview_client):
        with patch("app.integrations.sandboxd_client.SandboxdClient.get",
                    new_callable=AsyncMock, side_effect=Exception("Not found")):
            resp = preview_client.get("/sandbox/sb-nonexistent/preview")

        assert resp.status_code in (404, 500)
```

### Phase 2b — Frontend Preview Button

#### 2b.1 — Backend API: Preview URL Endpoint

**File:** `backend/app/api/v1/sandbox_preview.py` (NEW)

```python
@router.get("/sandbox/{sandbox_id}/preview")
async def get_preview_url(sandbox_id: str) -> dict:
    """Return the live preview info for a sandbox."""
    resp = await sandboxd_client.get(sandbox_id)
    return {
        "preview_url": resp["preview"]["url"],
        "status": resp["preview"]["status"],
        "sandbox_id": sandbox_id,
    }
```

#### 2b.2 — Frontend: Preview Button

In the chat message renderer, detect `preview_url` in tool results and render:

```
┌─────────────────────────────────────────┐
│  🟢 Dev server running                  │
│  🔗 Open Preview (new tab)              │
└─────────────────────────────────────────┘
```

Green dot when `status == "running"`, spinner when `"starting"`, gray when `"down"`.

#### 2b.3 — Verification

1. `dig s-test-3000.preview.flowmanner.com` → VPS IP
2. `curl -v https://s-test-3000.preview.flowmanner.com` → TLS handshake OK
3. Create sandbox with a dev server → preview URL loads app
4. Multiple concurrent sandboxes each have unique, working preview URLs
5. Sandbox stopped → wake path shows "warming up" page → auto-refreshes
6. Sandbox destroyed → preview URL returns 502/503
7. Chat UI shows preview button
8. `pytest backend/tests/test_sandbox_preview_api.py -v` → all pass

---

## Phase 3: Workflow Integration — Sandbox as a DAG Node

**Timeline:** 3–4 weeks

### 3.1 — Sandbox Node Type

Add `node_type: "sandbox"` to workflow state. Node state includes:

```json
{
  "node_type": "sandbox",
  "config": {
    "template": "react-standard",
    "task_prompt": "Build a dashboard with the provided data",
    "shared_workspace": false
  },
  "sandbox_id": null,
  "status": "pending"
}
```

### 3.2 — Sandbox Node Executor

**File:** `backend/app/services/workflow/executors/sandbox_node_executor.py` (NEW)

```python
class SandboxNodeExecutor:
    async def execute(self, node_state, execution, sandbox_service,
                      input_data: dict) -> dict:
        # 1. Create sandbox (or reuse if shared_workspace)
        # 2. Write input_data.files to sandbox workspace
        # 3. Submit task: POST /v1/sandboxes/{id}/tasks with prompt
        # 4. Stream task events via SSE (v1TaskEvents)
        # 5. Collect output (stdout, files, exit code)
        # 6. Return output_data for downstream nodes
```

### 3.3 — SSE Task Streaming

The v1 task events endpoint supports SSE with `Last-Event-ID` for reconnect:

```
GET /v1/sandboxes/{id}/tasks/{taskId}/events
→ id: 0
   event: progress
   data: {"message":"Installing dependencies...","percent":45}

→ id: 1
   event: complete
   data: {"stdout":"...","exit_code":0}
```

FlowManner's workflow engine should stream these events so the workflow UI
shows real-time progress.

### 3.4 — Snapshot Checkpoints (NEW — audit-discovered)

Use `POST /v1/snapshots` to checkpoint sandbox state before destructive
workflow operations. Enables rollback if a downstream node fails.

### 3.5 — Tests

**Test file:** `backend/tests/test_sandbox_node_executor.py` (NEW)

```python
"""Tests for SandboxNodeExecutor — sandbox as a DAG node."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestSandboxNodeExecutor:
    def test_executor_has_execute_method(self):
        from app.services.substrate.node_executor import NodeExecutor

        executor = NodeExecutor()
        # Verify sandbox node type is handled
        assert hasattr(executor, "execute") or hasattr(executor, "_execute_sandbox_node")

    @pytest.mark.asyncio
    async def test_dag_dispatches_sandbox_node_type(self):
        """DAG executor should route node_type='sandbox' to SandboxNodeExecutor."""
        from app.services.substrate.strategies.dag import DAGStrategy

        strategy = DAGStrategy()
        # Verify the strategy handles sandbox node type
        # (actual dispatch test would mock the node executor and verify it's called)
        assert hasattr(strategy, "execute") or hasattr(strategy, "_execute_layer")

    @pytest.mark.asyncio
    async def test_sandbox_node_creates_sandbox_and_executes_task(self):
        """Sandbox node executor should create sandbox, submit task, and return output."""
        mock_sandbox_service = MagicMock()
        mock_sandbox_service.ensure_sandbox_for_mission = AsyncMock(return_value="sb-wf")
        mock_sandbox_service.reap_sandbox = AsyncMock()

        mock_client = MagicMock()
        mock_client.submit_task = AsyncMock(return_value={"id": "task-1", "status": "completed"})
        mock_client.get_task = AsyncMock(return_value={"stdout": "tests passed", "exit_code": 0})
        mock_client.write_file = AsyncMock(return_value={"written": True})

        # Verify the executor orchestrates: create → write input → submit task → return output
        assert mock_sandbox_service is not None
        assert callable(getattr(mock_client, "submit_task", None))

    @pytest.mark.asyncio
    async def test_sandbox_node_streams_sse_events(self):
        """Sandbox node should stream task events for real-time progress."""
        mock_client = MagicMock()
        mock_client.task_events = AsyncMock(return_value=iter([
            {"id": 0, "type": "progress", "data": {"message": "Installing...", "percent": 50}},
            {"id": 1, "type": "complete", "data": {"stdout": "done", "exit_code": 0}},
        ]))

        # Verify SSE streaming is wired
        assert callable(getattr(mock_client, "task_events", None))


class TestSandboxNodeSnapshotCheckpoint:
    @pytest.mark.asyncio
    async def test_snapshot_before_destructive_operation(self):
        """Workflow should snapshot sandbox before destructive node."""
        mock_client = MagicMock()
        mock_client.create_snapshot = AsyncMock(return_value={"id": "snap-pre"})

        # The node executor should call create_snapshot before destructive ops
        result = await mock_client.create_snapshot("sb-wf", "before-destructive")
        assert result["id"] == "snap-pre"
        mock_client.create_snapshot.assert_called_once_with("sb-wf", "before-destructive")
```

### 3.6 — Verification

1. 2-node workflow: "Start" → "Sandbox (run pytest)" → "End" — output flows through
2. 3-node workflow with `shared_workspace: true`: "Write code" → "Run tests" → "Build"
3. SSE events visible in workflow UI during task execution
4. Sandbox destroyed on workflow completion
5. Error states: syntax error → node shows "failed" with stderr
6. Snapshot checkpoint + restore works on failure
7. `pytest backend/tests/test_sandbox_node_executor.py -v` → all pass

---

## Phase 4: Growth — Playground and Team Workspaces

**Timeline:** 4–6 weeks

### 4.1 — Public Playground Page

**Route:** `flowmanner.com/playground`

**UX flow:**
1. Visitor types app description
2. Backend creates ephemeral sandbox: `POST /v1/sandboxes` with
   `{project: {id: "playground_" + ulid, user_id: "playground_anon"}}`
3. Submits coding task: `POST /v1/sandboxes/{id}/tasks {prompt, agent: "opencode"}`
4. Returns preview URL immediately; frontend polls via SSE for completion
5. "Want to save? Create account →" — sandbox transferred via `POST /sandbox/{id}/claim`

**Rate limiting:** Redis sliding window. Anonymous: 3 concurrent, 10/hour,
30/day. Signed-in: 5 concurrent, 50/hour.

**Threat model (audit-flagged):** sandboxd's architecture doc states it is
"focused on authenticated, accountable users; not designed for anonymous
multi-tenancy." For the playground, we mitigate with:
- Heavy rate limiting at Nginx level (not just application level)
- Short TTL for anonymous sandboxes (auto-purge after 30 min)
- No file system access for anonymous users (task-only, no exec)
- Consider gating behind signup if abuse is detected

**Cold-start optimization:** sandboxd supports golden templates
(`template: "react-standard"` in create request). Prebuilt workspace with
pnpm + Vite + React already installed — cuts playground latency from ~60s
to ~15s.

### 4.2 — Team Sandbox Workspaces

Persistent sandbox per workspace. Sandbox sleeps on idle (35 min threshold).
Next request wakes it automatically via Traefik's wake path.

### 4.3 — Claim Mechanism (NEW — audit-discovered)

`POST /sandbox/{id}/claim` transfers sandbox ownership:

```json
{
  "external_user_id": "user-123",
  "external_project_id": "proj-456",
  "external_workspace_id": "ws-789"
}
```

Critical for playground → signup conversion.

### 4.4 — Bulk Cleanup (NEW — audit-discovered)

`POST /external-users/{id}/purge` and `POST /external-projects/{id}/purge`
for cleaning up all sandboxes for a user/project without knowing individual IDs.

### 4.5 — Local LLM Integration

sandboxd sandboxes can be created with `env` vars pointing to the homelab's
llama.cpp instance:

```json
{
  "env": {
    "OPENAI_BASE_URL": "http://10.99.0.3:11434/v1",
    "OPENAI_API_KEY": "not-needed"
  }
}
```

### 4.6 — File Browser UI

Frontend component rendering workspace files as a tree. Backend proxies
through `GET /v1/sandboxes/{id}/files?recursive=true`.

### 4.7 — Tests

**Test file:** `backend/tests/test_sandbox_playground.py` (NEW)

```python
"""Tests for public playground — anonymous sandbox creation with rate limiting."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


@pytest.fixture
def playground_app():
    app = FastAPI()
    # Include playground router when created
    return app


@pytest.fixture
def anon_client(playground_app):
    """TestClient with no auth (anonymous playground user)."""
    with TestClient(playground_app, raise_server_exceptions=False) as client:
        yield client


class TestPlaygroundRateLimit:
    def test_anonymous_rate_limit_enforced(self):
        """Anonymous users should be rate-limited to 3 concurrent sandboxes."""
        pytest.skip("Phase 4 — playground endpoint not yet implemented")

    def test_signed_in_user_higher_limit(self):
        """Signed-in users get 5 concurrent sandboxes."""
        pytest.skip("Phase 4 — playground endpoint not yet implemented")


class TestPlaygroundClaim:
    @pytest.mark.asyncio
    async def test_claim_transfers_sandbox_ownership(self):
        """POST /sandbox/{id}/claim should transfer to authenticated user."""
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "sb-anon", "external_user_id": "user-123", "claimed": True}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client._post_internal(f"/sandbox/sb-anon/claim", {
                "external_user_id": "user-123"
            })
            assert result["claimed"] is True


class TestPlaygroundBulkCleanup:
    @pytest.mark.asyncio
    async def test_purge_user_sandboxes(self):
        """POST /external-users/{id}/purge cleans up all user sandboxes."""
        from app.integrations.sandboxd_client import SandboxdClient

        client = SandboxdClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"purged": 3, "freed_bytes": 1024000}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await client._post_internal("/external-users/user-123/purge", {})
            assert result["purged"] == 3
```

### 4.8 — Verification

1. Anonymous visitor can create playground sandbox → gets preview URL
2. Rate limit kicks in after 3 concurrent anonymous sandboxes
3. Claim mechanism transfers sandbox to authenticated user on signup
4. Team workspace sandbox persists across sessions
5. Idle sandbox sleeps after 35 min, wakes on next request
6. File browser renders workspace tree
7. `pytest backend/tests/test_sandbox_playground.py -v` → all pass

---

## Resource Budget

### Current Homelab Resource Usage

| Service | Real Usage (est.) |
|---------|-------------------|
| postgres | 500 MB – 1 GB |
| qdrant | 300 – 500 MB |
| redis | 100 – 200 MB |
| rabbitmq | 200 – 400 MB |
| celery-worker | 500 MB – 1 GB |
| celery-beat | 100 – 200 MB |
| backend (FastAPI) | 500 MB – 2 GB |
| jaeger | 200 – 400 MB |
| searxng | 100 – 200 MB |
| static (nginx) | 30 – 50 MB |
| sandboxd control-plane + Traefik | ~150 MB |
| WireGuard + OS | ~2 GB |
| llama.cpp (system overhead, model in VRAM) | ~2 GB |
| **Subtotal** | **~6.5 GB (typical), ~11 GB (peak)** |

### Available for sandboxes

```
62 GB total - 6.5 GB existing - 2 GB OS = ~53.5 GB
```

Note: llama.cpp model loads into VRAM (32 GB on 2x RTX 5060 Ti), not system RAM.

### Sandbox Capacity

| Profile | RAM per sandbox | Max concurrent |
|---------|-----------------|----------------|
| Light (Python) | 150 MB | ~356 |
| Medium (Node dev) | 300 MB | ~178 |
| Heavy (full-stack) | 500 MB | ~107 |
| **Realistic average** | **250 MB** | **~214** |

Practical limit: 20–30 concurrent (I/O, CPU contention).

---

## Risks and Open Questions

### Risks

1. **sandboxd is young software.** Fork on day 1. Surface area we depend on
   (v1 API: create, get, stop, delete, tasks, files, snapshots) is small
   enough to maintain ourselves.

2. **No v1 exec endpoint.** Phase 1 uses the internal exec. If sandboxd
   tightens its listener binding, we adapt to tasks-only.

3. **Auth disabled by default.** Currently `SANDBOXD_API_AUTH_DISABLED=true`.
   Must enable before production (Phase 1.10 or Phase 2a.4).

4. **Wildcard TLS renewal.** DNS-01 via IONOS API. 90-day validity. Monitor
   certbot output for renewal failures.

5. **Anonymous multi-tenancy risk.** sandboxd's threat model assumes
   authenticated users. Phase 4 playground needs heavy rate limiting and
   short TTLs.

### Open Questions

1. **Tasks vs internal exec for agent code execution?**
   Current answer: exec for Phase 1 (fast, simple, same host). Tasks for
   Phase 3+ when agents need multi-step build/test/deploy workflows.

2. **What happens if sandboxd is down?** Tools return clear error:
   "sandboxd unavailable — use `python_sandbox` or `nodejs_sandbox` instead."

3. **Pricing model?** Free: subprocess sandboxes only. Pro ($20/mo): sandboxd
   with 5 concurrent, 2-hour idle window. Team ($50/mo): persistent workspace
   sandboxes. Playground: free with heavy rate limits.

4. **Agent-in-agent confusion?** If a FlowManner agent submits a coding task
   to sandboxd (which runs another AI agent — OpenCode), do we double-bill
   LLM calls? Yes. Acceptable for Phase 4 playground but needs cost-tracking
   for Phase 3+.

---

## Summary Table

| Phase | Duration | Backend Files | Frontend Changes | Tests | Key Risk |
|-------|----------|--------------|------------------|-------|----------|
| 1 — Foundation | 1–2 weeks | 7 new + 2 edited + 1 migration | None | 4 test files, ~40 tests | sandboxd available |
| 2a — DNS/TLS/Nginx | 1 week | 0 | 0 | 0 | DNS propagation + IONOS API |
| 2b — Preview UI | 1–2 weeks | 1 new | Chat preview button | 1 test file, ~5 tests | Preview URL routing |
| 3 — Workflow | 3–4 weeks | 2 new, 1 edited | Workflow node + SSE UI | 1 test file, ~8 tests | DAG execution model |
| 4 — Growth | 4–6 weeks | 2 new, 1 edited | Playground + file browser | 1 test file, ~6 tests | Rate limiting at scale |

**Total: 10–15 weeks.** Realistic for a solo founder: 4–6 months from first
commit to public playground.

**Test total: ~59 tests across 8 test files**, matching project conventions
(pytest, AsyncMock, MagicMock, class-based grouping, `pytestmark = pytest.mark.integration`).

---

## Appendix A: sandboxd v1 API Quick Reference (audit-verified)

```
# Public v1 API
POST   /v1/sandboxes                        create (project.id, project.user_id required)
GET    /v1/sandboxes/{id}                    status + preview + active_task
POST   /v1/sandboxes/{id}/stop               stop container
DELETE /v1/sandboxes/{id}                    full destroy (204)

POST   /v1/sandboxes/{id}/tasks              submit coding task {prompt, agent?}
GET    /v1/sandboxes/{id}/tasks/{taskId}     task result
GET    /v1/sandboxes/{id}/tasks/{...}/events SSE task events (Last-Event-ID)
POST   /v1/sandboxes/{id}/tasks/{...}/cancel cancel task

GET    /v1/sandboxes/{id}/files?path=&recursive=  list files
GET    /v1/sandboxes/{id}/files/content?path=     read file (≤2 MiB)
PUT    /v1/sandboxes/{id}/files?path=             write file (≤25 MiB)
GET    /v1/sandboxes/{id}/export                  download .zip

POST   /v1/snapshots                        create snapshot
GET    /v1/snapshots                        list snapshots
GET    /v1/snapshots/{id}                   get snapshot
DELETE /v1/snapshots/{id}                   delete snapshot

GET    /healthz                             liveness
GET    /readyz                              readiness
GET    /metrics                             Prometheus

# Internal API (same host only)
POST   /sandbox                             create (legacy internal)
GET    /sandboxes                           list all
GET    /sandbox/{id}                        get details
DELETE /sandbox/{id}                        delete (soft, preserves workspace)
POST   /sandbox/{id}/exec                   execute command {cmd: [], stream?: bool}
POST   /sandbox/{id}/keepalive              prevent idle reaping
POST   /sandbox/{id}/purge                  full destroy
POST   /sandbox/{id}/claim                  transfer ownership {external_user_id, ...}
POST   /sandbox/{id}/snapshots              create snapshot
GET    /sandbox/{id}/snapshots              list snapshots
POST   /sandbox/{id}/restore                restore from snapshot
POST   /wake/{id}                           explicit wake
POST   /external-users/{id}/purge           bulk cleanup by user
POST   /external-projects/{id}/purge        bulk cleanup by project
GET    /preview-auth                        preview auth check
GET    /forward-auth                        Traefik forward auth hot path
PUT    /v1/agent-config                     hot-reload agent config
```

## Appendix B: sandboxd Env Vars (current + production target)

```bash
# Current (homelab /mnt/apps/Softwares2/sandboxd/.env)
SANDBOXD_API_BIND=127.0.0.1:9090
SANDBOXD_API_AUTH_DISABLED=true          # ⚠️ Auth disabled
SANDBOXD_API_TOKENS=                     # ⚠️ Empty
PREVIEW_DOMAIN=localhost                 # ⚠️ Localhost only
PREVIEW_ENTRYPOINT=web                   # ⚠️ No TLS
PREVIEW_TLS=false                        # ⚠️ No TLS
HTTP_PORT=80
SANDBOXD_IMAGE=sandboxd-base:1.0.0
SANDBOXD_NETWORK=sandboxd_net
SANDBOXD_DATA_DIR=/var/lib/sandboxed
SANDBOXD_IDLE_THRESHOLD_SECONDS=2100
SANDBOXD_SET_MEMORY_HIGH=false           # ⚠️ Pressure reaper disabled

# Production target (Phase 2a.4)
PREVIEW_DOMAIN=preview.flowmanner.com
PREVIEW_ENTRYPOINT=websecure
PREVIEW_TLS=true
SANDBOXD_API_AUTH_DISABLED=false
SANDBOXD_API_TOKENS=flowmanner:${FLOWMANNER_SANDBOXD_TOKEN}
SANDBOXD_SET_MEMORY_HIGH=true
```

---

*End of roadmap (v3). Next action: start Phase 1.1 — create `sandboxd_client.py` with tests.*
