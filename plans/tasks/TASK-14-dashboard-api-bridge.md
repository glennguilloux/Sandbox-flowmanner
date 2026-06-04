# DEEPSEEK TASK 14: Hermes Dashboard — API Server Bridge Layer

## Context

The Hermes Dashboard (`hermes dashboard`, FastAPI :9119) and the Hermes API Server (aiohttp :8642) are two separate servers. The dashboard has the UI and session auth; the API server has the run lifecycle engine (submit/stop/approve, SSE events, detailed health). **The gap is that the dashboard never connects to the API server.**

This is the foundational task. Without it, Run Inspector, Ops Health, and capabilities-driven rendering can't reach the API server.

## Files

- **PRIMARY:** `~/.hermes/hermes-agent/hermes_cli/web_server.py` (4671 lines, FastAPI)
- Config: `~/.hermes/config.yaml` (for `platforms.api_server.extra`)

The dashboard web server is a **FastAPI** app defined in `web_server.py`. Routes are registered with `@app.get(...)`, `@app.post(...)`, `@app.websocket(...)` decorators. The file is organized:

```
lines 1-98:   imports, lazy dep install, FastAPI app creation
lines 99-108: CORS config
lines 109+:   helper functions and route handlers
lines 3396-3620: WebSocket endpoints (/api/pty, /api/ws, /api/pub, /api/events)
lines 4602-4671: start_server() function
```

## Step 1: Add streaming imports

At line 53-58, add `StreamingResponse` to the imports:

```python
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
```

`sse-starlette` is already a project dependency (in uv.lock) so `EventSourceResponse` is available, but for a simple SSE passthrough, a raw `StreamingResponse` with `text/event-stream` content-type works fine and has zero additional dep risk.

## Step 2: Add API server config helper

After the CORS middleware setup (around line 109), add a helper to resolve the API server address and auth token:

```python
# ── API Server Bridge ──────────────────────────────────────────────
_API_SERVER_HOST: Optional[str] = None
_API_SERVER_PORT: Optional[int] = None
_API_SERVER_KEY: Optional[str] = None

def _resolve_api_server_config():
    """Read API server host/port/key from config or env vars.
    
    Config path: platforms.api_server.extra.{host,port,key}
    Env overrides: API_SERVER_HOST, API_SERVER_PORT, API_SERVER_KEY
    Defaults: 127.0.0.1, 8642, empty string
    """
    global _API_SERVER_HOST, _API_SERVER_PORT, _API_SERVER_KEY
    try:
        cfg = load_config()
        extra = (cfg.get("platforms", {})
                   .get("api_server", {})
                   .get("extra", {}))
    except Exception:
        extra = {}
    
    _API_SERVER_HOST = extra.get("host", os.getenv("API_SERVER_HOST", "127.0.0.1"))
    raw_port = extra.get("port", os.getenv("API_SERVER_PORT", "8642"))
    try:
        _API_SERVER_PORT = int(raw_port)
    except (TypeError, ValueError):
        _API_SERVER_PORT = 8642
    _API_SERVER_KEY = extra.get("key", os.getenv("API_SERVER_KEY", ""))


_api_server_config_loaded = False

def _api_server_base() -> str:
    global _api_server_config_loaded
    if not _api_server_config_loaded:
        _resolve_api_server_config()
        _api_server_config_loaded = True
    return f"http://{_API_SERVER_HOST}:{_API_SERVER_PORT}"


def _api_server_headers() -> dict:
    """Return auth headers for API server requests."""
    if not _api_server_config_loaded:
        _resolve_api_server_config()
    if _API_SERVER_KEY:
        return {"Authorization": f"Bearer {_API_SERVER_KEY}"}
    return {}


def _api_server_offline_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "status": "offline",
            "message": "API server is not running. Start it with `hermes gateway run` "
                       "with api_server platform enabled, or configure in config.yaml.",
        },
    )
```

## Step 3: Add proxy endpoints

These follow the exact same pattern as the existing 69+ routes in web_server.py — `@app.get(...)` / `@app.post(...)` / `@app.delete(...)` async handlers directly on the module-level `app` object.

Place them after the existing `/api/config` routes (after line ~900) or at the end before the WebSocket section — conventions anywhere that keeps them grouped with the other API routes. Use a section comment:

```python
# ── API Server Proxy Endpoints ─────────────────────────────────────

@app.get("/api/server/health")
async def proxy_server_health():
    """Proxy /health/detailed from the API server."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{_api_server_base()}/health/detailed",
                headers=_api_server_headers(),
            )
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return _api_server_offline_response()


@app.get("/api/server/capabilities")
async def proxy_server_capabilities():
    """Proxy /v1/capabilities from the API server."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{_api_server_base()}/v1/capabilities",
                headers=_api_server_headers(),
            )
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return {"api_server": False, "message": "API server offline"}


@app.get("/api/runs")
async def proxy_list_runs():
    """List runs from the API server."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_api_server_base()}/v1/runs",
                headers=_api_server_headers(),
            )
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return _api_server_offline_response()


@app.post("/api/runs")
async def proxy_create_run(request: Request):
    """Submit a new run to the API server."""
    import httpx
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_api_server_base()}/v1/runs",
                json=body,
                headers={
                    **_api_server_headers(),
                    "Content-Type": "application/json",
                },
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return _api_server_offline_response()


@app.get("/api/runs/{run_id}")
async def proxy_get_run(run_id: str):
    """Get a single run's status."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_api_server_base()}/v1/runs/{run_id}",
                headers=_api_server_headers(),
            )
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return _api_server_offline_response()


@app.delete("/api/runs/{run_id}")
async def proxy_stop_run(run_id: str):
    """Stop a running agent."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_api_server_base()}/v1/runs/{run_id}/stop",
                headers=_api_server_headers(),
            )
            # API server returns 200 on success
            if resp.status_code == 200:
                return {"status": "stopped", "run_id": run_id}
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return _api_server_offline_response()


@app.post("/api/runs/{run_id}/approve")
async def proxy_approve_run(run_id: str, request: Request):
    """Approve or deny a pending run action."""
    import httpx
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_api_server_base()}/v1/runs/{run_id}/approval",
                json=body,
                headers={
                    **_api_server_headers(),
                    "Content-Type": "application/json",
                },
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return _api_server_offline_response()
```

**IMPORTANT:** Use `import httpx` inside each handler (lazy import), not at the top of the file. This matches the existing pattern at lines 1831 and 1927 where httpx is imported lazily inside async handlers. It avoids startup failures when httpx isn't installed.

## Step 4: SSE Passthrough for run events

This is the most important endpoint — it enables live streaming of run events to the browser dashboard's EventSource API. The API server at `:8642/v1/runs/{id}/events` emits an SSE stream of structured events (thinking, tool_call, tool_result, approval_request, error, complete).

The existing streaming pattern in web_server.py uses WebSocket (`@app.websocket("/api/events")` at line 3578 with a subscriber model via `_broadcast_event`). For the API server bridge we need HTTP SSE with `StreamingResponse` — a different transport that the browser's native `EventSource` API can consume.

```python
@app.get("/api/runs/{run_id}/events")
async def proxy_run_events(run_id: str):
    """SSE passthrough for run event stream.
    
    The browser's EventSource API connects here. We relay the SSE stream
    from the API server's /v1/runs/{id}/events endpoint byte-for-byte.
    """
    import httpx
    api_url = f"{_api_server_base()}/v1/runs/{run_id}/events"
    
    async def event_stream():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "GET",
                    api_url,
                    headers=_api_server_headers(),
                ) as response:
                    if response.status_code != 200:
                        yield f"event: error\ndata: {json.dumps({'error': 'API server returned ' + str(response.status_code)})}\n\n"
                        return
                    async for raw_line in response.aiter_lines():
                        yield f"{raw_line}\n"
                    # Final SSE event to signal stream end
                    yield f"event: complete\ndata: {json.dumps({'type': 'stream_closed'})}\n\n"
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            yield f"event: error\ndata: {json.dumps({'error': 'API server unreachable', 'detail': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

**Note:** The `/api/events` WebSocket endpoint (`@app.websocket("/api/events")` at line 3578 of web_server.py) uses a broadcast pattern for the chat tab's structured metadata. This SSE endpoint is different — it's a direct HTTP SSE stream, not a WebSocket. Don't confuse the two. The existing WebSocket pattern subscribes to a channel; this new endpoint is a simple HTTP passthrough.

## Step 5: CORS config

The existing CORS config at lines 99-108 already allows all methods and headers from localhost origins:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This is sufficient — the SSE endpoint is on the same origin (`:9119`) as the React frontend, so no CORS changes needed for the bridge itself. The API server (`:8642`) has its own CORS config.

## Step 6: Startup config loading

The `_resolve_api_server_config()` helper is called lazily on first proxy request (via `_api_server_base()` and `_api_server_headers()`). Alternatively, call it once at the top of `start_server()` (line 4602):

```python
def start_server(host="127.0.0.1", port=9119, open_browser=True, *, embedded_chat=False):
    import uvicorn
    global _DASHBOARD_EMBEDDED_CHAT_ENABLED
    _DASHBOARD_EMBEDDED_CHAT_ENABLED = embedded_chat
    
    _resolve_api_server_config()  # ← ADD THIS
    ...
```

This ensures config is loaded before the first request arrives. Lazy fallback in the helper handles the edge case where this isn't called.

## Verification

1. Start the Hermes gateway (with API server platform enabled):
   ```
   hermes gateway run &
   ```
   Or manually start just the API server: verify it's listening on :8642.

2. Start the Hermes dashboard:
   ```
   hermes dashboard --port 9119
   ```

3. Test each proxy endpoint with curl:
   ```
   # Health
   curl http://127.0.0.1:9119/api/server/health
   # → health/detailed JSON from API server

   # Capabilities
   curl http://127.0.0.1:9119/api/server/capabilities
   # → capabilities JSON with run_submission, auth type, etc.

   # List runs
   curl http://127.0.0.1:9119/api/runs
   # → [] or list of runs

   # Submit a run
   curl -X POST http://127.0.0.1:9119/api/runs \
     -H "Content-Type: application/json" \
     -d '{"prompt":"say hello","max_turns":3}'
   # → 202 with run_id

   # SSE event stream (replace run_id)
   curl -N http://127.0.0.1:9119/api/runs/<run_id>/events
   # → SSE stream of events (thinking, tool_call, tool_result, complete)
   ```

4. Test graceful degradation: kill the API server, then:
   ```
   curl http://127.0.0.1:9119/api/server/health
   # → 503 {"status": "offline", ...}
   ```

## Pitfalls

- **Lazy httpx import** — `import httpx` goes inside each handler, NOT at the top of the file. Matches existing pattern (lines 1831, 1927, 2001) and avoids startup failures if httpx is missing.
- **SSE vs WebSocket** — The existing `/api/events` at line 3578 uses WebSocket with `_broadcast_event`. Don't modify that. This is a new HTTP SSE endpoint using `StreamingResponse`, which is what browser `EventSource` expects.
- **Server-Sent Events buffering** — Without `X-Accel-Buffering: no` header, nginx/reverse proxies may buffer the SSE stream. Add it to the SSE response headers.
- **Timeout** — The SSE stream uses `timeout=None` to stay open indefinitely. Non-SSE proxy endpoints use short timeouts (3-5s) so the dashboard doesn't hang if the API server is down.
- **No caching** — Run data is time-sensitive. Don't add caching headers to proxy responses.
- **API key mismatch** — If the API server is configured without a key (empty `extra.key`), the `_api_server_headers()` function returns a blank dict and no auth header is sent. This is correct for the no-auth case.
- **Config not the original `config.yaml` reference** — The user's own `~/.hermes/config.yaml` may not have `platforms.api_server.extra` set. The helper falls back to defaults and env vars (`API_SERVER_HOST`, `API_SERVER_PORT`, `API_SERVER_KEY`).
