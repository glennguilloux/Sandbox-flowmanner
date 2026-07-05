"""Async HTTP client for sandboxd v1 API (http://127.0.0.1:9090).

Wraps the public v1 endpoints for sandbox lifecycle, file I/O, coding
agent tasks, and snapshot management.  Uses ``httpx.AsyncClient`` with
optional Bearer token auth (currently disabled in sandboxd config).

FlowManner and sandboxd run on the same homelab host, so the internal
exec endpoint (``POST /sandbox/{id}/exec``) is also available for
Phase 1 code execution via ``SandboxdClient.exec_command``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ── Shared URL rewriter (used by tools, API routes, and playground) ──


def rewrite_sandboxd_url(url: str, domain: str | None = None) -> str:
    """Rewrite sandboxd localhost URLs to the public preview domain.

    Transforms ``http://s-xxx-3000.preview.localhost`` into
    ``https://s-xxx-3000.preview.flowmanner.com`` — fixing both
    the domain and the scheme (public domain has TLS).

    Only rewrites URLs whose host contains ``.preview.`` — plain URLs
    (e.g. ``https://example.com/page``) pass through unchanged.
    """
    if not url:
        return ""

    effective_domain = domain or settings.SANDBOXD_PREVIEW_DOMAIN

    # Only rewrite sandboxd preview URLs (must contain '.preview.' in host)
    match = re.search(r"://([^/]+)", url)
    if match and ".preview." in match.group(1):
        host = match.group(1).split(":")[0]
        subdomain = re.sub(r"\.preview.*$", "", host)
        if effective_domain:
            result = f"https://{subdomain}.{effective_domain}"
            # ── Debug: trace port through rewrite ──────────────────
            _port_match = re.search(r"-(\d+)\.preview", url)
            _port = _port_match.group(1) if _port_match else "(none)"
            logger.debug(
                "rewrite_sandboxd_url: %r → %r (extracted_port=%s, domain=%s)",
                url,
                result,
                _port,
                effective_domain,
            )
            return result

    # Fallback: string replacement for .preview.localhost
    if effective_domain and ".preview.localhost" in url:
        url = url.replace(".preview.localhost", f".{effective_domain}")
    if url.startswith("http://") and effective_domain and effective_domain in url:
        url = "https://" + url[len("http://") :]
    logger.debug("rewrite_sandboxd_url (fallback): → %r", url)
    return url


class SandboxdClient:
    """Async client for sandboxd's v1 and internal APIs."""

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.SANDBOXD_API_URL).rstrip("/")
        self._auth = auth_token or settings.SANDBOXD_AUTH_TOKEN or None
        self._client: httpx.AsyncClient | None = None

    # ── Client lifecycle ───────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._auth:
                headers["Authorization"] = f"Bearer {self._auth}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Sandbox lifecycle (v1 public API) ──────────────────────────────

    async def create(
        self,
        project_id: str,
        user_id: str,
        template: str | None = None,
        visibility: str = "private",
    ) -> dict[str, Any]:
        """Create sandbox for a project.

        Tries the v1 public API first (``POST /v1/sandboxes``). If the
        template is rejected (400), falls back to the internal API
        (``POST /sandbox``) which is available because FlowManner and
        sandboxd run on the same host.

        Returns ``{id, status, ...}``
        """
        client = await self._get_client()

        # Resolve template: explicit arg > settings default > empty (no template)
        effective_template = template if template is not None else settings.SANDBOXD_DEFAULT_TEMPLATE

        # Try v1 public API first
        payload: dict[str, Any] = {
            "project": {"id": project_id, "user_id": user_id},
            "visibility": visibility,
        }
        if effective_template:
            payload["template"] = effective_template

        resp = await client.post("/v1/sandboxes", json=payload)

        if resp.status_code == 400:
            # Fallback: internal API (same-host, no template validation)
            logger.warning(
                "v1 create rejected (%s), falling back to internal /sandbox",
                resp.text[:200],
            )
            resp = await client.post(
                "/sandbox",
                json={
                    "project_id": project_id,
                    "user_id": user_id,
                },
            )

        resp.raise_for_status()
        data = resp.json()
        # Normalize: internal API uses 'state' instead of 'status',
        # and lacks 'preview'. Ensure callers always see 'id' and 'status'.
        if "state" in data and "status" not in data:
            data["status"] = data["state"]
        return data

    async def get(self, sandbox_id: str) -> dict[str, Any]:
        """GET /v1/sandboxes/{id} — status + preview + active_task.

        Falls back to internal ``GET /sandbox/{id}`` if v1 is unavailable.
        The internal API wraps the response in ``{"row": {...}}`` —
        this method unwraps it automatically.
        """
        client = await self._get_client()
        resp = await client.get(f"/v1/sandboxes/{sandbox_id}")
        if resp.status_code == 404 or resp.status_code >= 500:
            # Fallback: internal API
            resp = await client.get(f"/sandbox/{sandbox_id}")
        resp.raise_for_status()
        data = resp.json()
        # Internal API wraps in {"row": {...}} — unwrap if needed
        if "row" in data and isinstance(data["row"], dict):
            data = data["row"]
        # Normalize state → status
        if "state" in data and "status" not in data:
            data["status"] = data["state"]

        # ── Debug: trace raw sandboxd preview response ─────────────
        _preview = data.get("preview") or {}
        _raw_preview_url = _preview.get("url", "")
        _port_m = re.search(r"-(\d+)\.preview", _raw_preview_url)
        _port = _port_m.group(1) if _port_m else "(none)"
        logger.debug(
            "SandboxdClient.get(%s): status=%s preview.status=%s " "preview.url=%r preview_port=%s",
            sandbox_id,
            data.get("status"),
            _preview.get("status"),
            _raw_preview_url,
            _port,
        )
        if _port not in ("8081", "(none)"):
            logger.warning(
                "SandboxdClient.get(%s): sandboxd returned port %s "
                "(not 8081) in preview.url=%r — this will be "
                "forwarded to the frontend as-is",
                sandbox_id,
                _port,
                _raw_preview_url,
            )

        return data

    async def get_internal(self, sandbox_id: str) -> dict[str, Any]:
        """GET /sandbox/{id} — internal API with live Docker state.

        Unlike ``get()`` (which prefers the v1 API and normalizes away
        ``live_state``), this method calls the **internal** API directly
        and returns the raw response including the Docker container's
        ``live_state`` field.  Used for fast-fail detection of dead
        containers before entering a readiness polling loop.
        """
        client = await self._get_client()
        resp = await client.get(f"/sandbox/{sandbox_id}")
        resp.raise_for_status()
        data = resp.json()
        if "row" in data and isinstance(data["row"], dict):
            data = data["row"]
        return data

    async def stop(self, sandbox_id: str) -> dict[str, Any]:
        """POST /v1/sandboxes/{id}/stop — stop container (workspace preserved)."""
        client = await self._get_client()
        resp = await client.post(f"/v1/sandboxes/{sandbox_id}/stop")
        resp.raise_for_status()
        return resp.json()

    async def delete(self, sandbox_id: str) -> None:
        """DELETE /v1/sandboxes/{id} — full destroy (204 No Content)."""
        client = await self._get_client()
        resp = await client.delete(f"/v1/sandboxes/{sandbox_id}")
        resp.raise_for_status()

    # ── Tasks (AI coding agents) ───────────────────────────────────────

    async def submit_task(
        self,
        sandbox_id: str,
        prompt: str,
        agent: str = "opencode",
    ) -> dict[str, Any]:
        """POST /v1/sandboxes/{id}/tasks — start coding agent (202 Accepted).

        Auto-wakes stopped sandbox first.
        """
        client = await self._get_client()
        resp = await client.post(
            f"/v1/sandboxes/{sandbox_id}/tasks",
            json={"prompt": prompt, "agent": agent},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_task(self, sandbox_id: str, task_id: str) -> dict[str, Any]:
        """GET /v1/sandboxes/{id}/tasks/{taskId} — task result (durable)."""
        client = await self._get_client()
        resp = await client.get(f"/v1/sandboxes/{sandbox_id}/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()

    async def task_events(
        self,
        sandbox_id: str,
        task_id: str,
        since: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        """GET /v1/sandboxes/{id}/tasks/{taskId}/events — SSE stream.

        Yields ``{id, type, data}`` events. Supports ``Last-Event-ID``
        for reconnect.
        """
        client = await self._get_client()
        url = f"/v1/sandboxes/{sandbox_id}/tasks/{task_id}/events"
        headers = {}
        if since:
            headers["Last-Event-ID"] = str(since)

        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            current_event: dict[str, Any] = {}
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("id:"):
                    current_event["id"] = line[3:].strip()
                elif line.startswith("event:"):
                    current_event["type"] = line[6:].strip()
                elif line.startswith("data:"):
                    current_event["data"] = line[5:].strip()
                elif line == "" and current_event:
                    yield current_event
                    current_event = {}

    async def cancel_task(self, sandbox_id: str, task_id: str) -> dict[str, Any]:
        """POST /v1/sandboxes/{id}/tasks/{taskId}/cancel."""
        client = await self._get_client()
        resp = await client.post(f"/v1/sandboxes/{sandbox_id}/tasks/{task_id}/cancel")
        resp.raise_for_status()
        return resp.json()

    # ── Files (workspace) ──────────────────────────────────────────────

    async def list_files(
        self,
        sandbox_id: str,
        path: str = "",
        recursive: bool = False,
    ) -> list[dict[str, Any]]:
        """GET /v1/sandboxes/{id}/files — list workspace files."""
        client = await self._get_client()
        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        if recursive:
            params["recursive"] = "true"
        resp = await client.get(f"/v1/sandboxes/{sandbox_id}/files", params=params)
        resp.raise_for_status()
        return resp.json()

    async def read_file(self, sandbox_id: str, path: str) -> str:
        """GET /v1/sandboxes/{id}/files/content?path= — read file (≤2 MiB)."""
        client = await self._get_client()
        resp = await client.get(
            f"/v1/sandboxes/{sandbox_id}/files/content",
            params={"path": path},
        )
        resp.raise_for_status()
        return resp.text

    async def write_file(self, sandbox_id: str, path: str, content: str | bytes) -> dict[str, Any]:
        """PUT /v1/sandboxes/{id}/files?path= — write file (≤25 MiB).

        Atomic: tmp file + rename. No symlink following.
        Accepts both ``str`` (auto-encoded to UTF-8) and ``bytes``.
        """
        if isinstance(content, str):
            content = content.encode("utf-8")
        client = await self._get_client()
        resp = await client.put(
            f"/v1/sandboxes/{sandbox_id}/files",
            params={"path": path},
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()
        return resp.json()

    async def export(self, sandbox_id: str) -> bytes:
        """GET /v1/sandboxes/{id}/export — download workspace as .zip."""
        client = await self._get_client()
        resp = await client.get(f"/v1/sandboxes/{sandbox_id}/export")
        resp.raise_for_status()
        return resp.content

    # ── Internal exec (same-host only) ─────────────────────────────────

    async def exec_command(
        self,
        sandbox_id: str,
        cmd: list[str],
        stream: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """POST /sandbox/{id}/exec — execute command inside sandbox.

        Uses the **internal** API (not v1) because raw exec is internal-only.
        Same-host access only (FlowManner and sandboxd share the homelab).

        Returns the JSON body directly (including ``stdout``, ``stderr``,
        ``exit_code``) even when the exec itself failed — callers check
        ``exit_code`` rather than relying on HTTP status.

        Args:
            timeout: Per-request timeout in seconds.  Overrides the
                client default (30 s) so long-running commands like
                ``npm install`` don't time out prematurely.
        """
        client = await self._get_client()
        # Use per-request timeout if provided; build a new Timeout object
        # so we keep the 5 s connect timeout but extend the read/write.
        req_timeout = httpx.Timeout(timeout, connect=5.0) if timeout else None
        resp = await client.post(
            f"/sandbox/{sandbox_id}/exec",
            json={"cmd": cmd, "stream": stream},
            timeout=req_timeout,
        )
        # Return the body regardless of HTTP status — the exec may have
        # "succeeded" at the HTTP level (200) but the command inside the
        # container failed (exit_code != 0).  Only raise for transport
        # errors (e.g. sandbox not found at all → 404).
        try:
            body = resp.json()
        except Exception:
            resp.raise_for_status()
            return {}
        if resp.status_code >= 400 and "exit_code" not in body:
            # True transport error (not an exec-in-container failure)
            resp.raise_for_status()
        return body

    # ── Snapshots ──────────────────────────────────────────────────────

    async def create_snapshot(self, sandbox_id: str, name: str = "") -> dict[str, Any]:
        """POST /v1/snapshots — create snapshot of sandbox state."""
        client = await self._get_client()
        body: dict[str, Any] = {"sandbox_id": sandbox_id}
        if name:
            body["name"] = name
        resp = await client.post("/v1/snapshots", json=body)
        resp.raise_for_status()
        return resp.json()

    async def list_snapshots(self) -> list[dict[str, Any]]:
        """GET /v1/snapshots — list all snapshots."""
        client = await self._get_client()
        resp = await client.get("/v1/snapshots")
        resp.raise_for_status()
        return resp.json()

    async def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """GET /v1/snapshots/{id} — get snapshot details."""
        client = await self._get_client()
        resp = await client.get(f"/v1/snapshots/{snapshot_id}")
        resp.raise_for_status()
        return resp.json()

    async def delete_snapshot(self, snapshot_id: str) -> None:
        """DELETE /v1/snapshots/{id} — delete snapshot."""
        client = await self._get_client()
        resp = await client.delete(f"/v1/snapshots/{snapshot_id}")
        resp.raise_for_status()

    async def restore_snapshot(self, sandbox_id: str, snapshot_id: str) -> None:
        """POST /sandbox/{id}/restore — restore sandbox to a snapshot.

        Uses the internal API (same-host only).
        """
        client = await self._get_client()
        resp = await client.post(
            f"/sandbox/{sandbox_id}/restore",
            json={"snapshot_id": snapshot_id},
        )
        resp.raise_for_status()

    # ── Health ─────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """GET /healthz — sandboxd liveness probe."""
        client = await self._get_client()
        resp = await client.get("/healthz")
        resp.raise_for_status()
        return {"status": "ok", "status_code": resp.status_code}


# ── Module-level singleton ─────────────────────────────────────────────

_sandboxd_client: SandboxdClient | None = None


def get_sandboxd_client() -> SandboxdClient:
    """Get or create the SandboxdClient singleton."""
    global _sandboxd_client
    if _sandboxd_client is None:
        _sandboxd_client = SandboxdClient()
    return _sandboxd_client
