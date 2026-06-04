# TASK-BE-STUB-01 — Fix /api/stats Hardcoded Zeros

## Current State
`/opt/flowmanner/backend/app/main_fastapi.py:333-340`:
```python
@app.get("/api/stats")
async def get_stats():
    return {
        "total_runs": 0,
        "successful_runs": 0,
        "failed_runs": 0,
        "avg_duration_ms": 0,
        "total_tokens": 0,
    }
```
This endpoint returns hardcoded zeros. It is a public, production endpoint.

## Problem
- Production monitoring and dashboards show bogus zero values.
- The function is completely fake — no DB query, no real data.
- This is a **CRITICAL** deploy blocker because it provides misleading information to OPS users.

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/main_fastapi.py` (lines 333-340)
- **Reference:** `/opt/flowmanner/backend/app/services/graph_analytics.py` (has real queries)

## Exact Implementation Steps
1. Import `AsyncSessionLocal` from `app.database` (already imported at top of main_fastapi.py).
2. Import `get_execution_stats` from `app.services.graph_analytics`.
3. Replace the hardcoded dict with an actual async DB query:
   ```python
   @app.get("/api/stats")
   async def get_stats(request: Request):
       try:
           from app.database import AsyncSessionLocal
           from app.services.graph_analytics import get_execution_stats
           async with AsyncSessionLocal() as session:
               stats = await get_execution_stats(session, user_id=0)  # 0 = system-wide
               return {
                   "total_runs": stats["total_runs"],
                   "successful_runs": stats["success"],
                   "failed_runs": stats["failed"],
                   "avg_duration_ms": int(stats["avg_duration_seconds"] * 1000),
                   "total_tokens": 0,  # requires separate query across chat/mission tables
               }
       except Exception:
           return {
               "total_runs": 0,
               "successful_runs": 0,
               "failed_runs": 0,
               "avg_duration_ms": 0,
               "total_tokens": 0,
           }
   ```
4. For total_tokens: add a secondary query across `Mission` or `LLMCallRecord` table, or keep as 0 with a TODO.

## Constraints
- Must not block startup if DB is unavailable (graceful degradation).
- Must not change the response shape (same JSON keys).
- Must be fast (indexed queries only).

## Verification
```bash
# After rebuild, hit the endpoint:
curl http://localhost:8000/api/stats | python -m json.tool
# Verify non-zero values after seeding test data:
cd /opt/flowmanner/backend && python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services.graph_analytics import get_execution_stats
async def main():
    async with AsyncSessionLocal() as s:
        print(await get_execution_stats(s, 1))
asyncio.run(main())
"
```
