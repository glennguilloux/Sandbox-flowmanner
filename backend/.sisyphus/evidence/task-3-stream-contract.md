# Mission Stream Endpoint Contract

## Decision: SSE status event stream (matches existing app patterns)

### Rationale
- Chat uses SSE via `StreamingResponse` with `media_type="text/event-stream"` (chat.py:214-221)
- Flow compat uses SSE with JSON-encoded `data:` lines (flow_compat.py:30-46)
- Mission stream should follow the same pattern for consistency

### Contract

**Route**: `GET /api/missions/{mission_id}/stream` and `GET /api/missions/{mission_id}/stream/`

**Auth**: Requires authenticated user via `get_current_user`; mission must pass `_require_owner()` check (404 if not found/not owned)

**Response**: `StreamingResponse` with `media_type="text/event-stream"`

**Event format**: JSON-encoded SSE lines:
```
data: {"type": "status", "mission_id": "...", "status": "pending", "total_tasks": 3, "completed_tasks": 0, "failed_tasks": 0}

data: {"type": "task_update", "task_id": "...", "task_title": "...", "status": "running"}

data: {"type": "complete", "mission_id": "...", "status": "completed", "total_tasks": 3, "completed_tasks": 3, "failed_tasks": 0}

data: [DONE]
```

**Error behavior**:
- Unauthenticated: 403 (standard auth middleware)
- Mission not found / not owned: 404 (via `_require_owner()`)
- Mission in terminal state: stream sends final status event then `[DONE]`

**Headers**: Same as chat stream:
```python
{
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
```

### Implementation approach
Poll mission status at intervals (matching flow_compat pattern of using `asyncio.sleep`) and emit SSE events as the mission progresses. For a completed/pending mission, emit the current state and close.
