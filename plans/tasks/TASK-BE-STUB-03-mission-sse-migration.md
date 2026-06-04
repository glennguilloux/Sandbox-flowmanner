# TASK-BE-STUB-03 — Migrate Mission SSE Streaming to CQRS

## Current State
`/opt/flowmanner/backend/app/api/_mission_handlers.py` (line 2):
```python
# TODO: DEPRECATED — remove after migrating legacy tests to CQRS handlers.
```
This file is marked DEPRECATED but is still used by:
- `/opt/flowmanner/backend/app/api/_mission_stream.py` — imports `handle_stream_status`
- `/opt/flowmanner/backend/app/api/v2/missions.py:249` — delegates SSE to legacy handler

## Problem
DEPRECATED code is on the **hot path** for mission SSE streaming and async execution. Two parallel implementations (legacy + CQRS) create maintenance overhead and risk of divergence. This is a **CRITICAL** deploy blocker.

## Exact Files
- **Read:** `/opt/flowmanner/backend/app/api/_mission_handlers.py` (lines 296-343: `handle_stream_status`, lines 248-302: `handle_execute_async`)
- **Read:** `/opt/flowmanner/backend/app/api/_mission_stream.py` (entire file)
- **Read:** `/opt/flowmanner/backend/app/api/v2/missions.py` (line 249)
- **Read:** `/opt/flowmanner/backend/app/api/_mission_cqrs/commands.py` (existing CQRS handlers)
- **Read:** `/opt/flowmanner/backend/app/api/_mission_cqrs/queries.py` (existing CQRS queries)
- **Modify:** `/opt/flowmanner/backend/app/api/_mission_stream.py`
- **Modify:** `/opt/flowmanner/backend/app/api/v2/missions.py`
- **Delete:** `/opt/flowmanner/backend/app/api/_mission_handlers.py` (after migration)
- **Modify:** `/opt/flowmanner/backend/app/tests/test_mission_handlers.py` (migrate to test CQRS)
- **Modify:** `/opt/flowmanner/backend/app/tests/test_mission_lifecycle.py` (migrate to test CQRS)

## Exact Implementation Steps
1. Create `handle_stream_status_cqrs()` in `_mission_cqrs/commands.py`:
   - Uses `MissionQueryHandlers.get_mission()` and `get_mission_tasks()`.
   - Implements the same SSE event generator pattern but with CQRS dependencies.
2. Update `_mission_stream.py` to import from CQRS instead of legacy:
   ```python
   from app.api._mission_cqrs.commands import handle_stream_status_cqrs as handle_stream_status
   ```
3. Update `v2/missions.py:249` to use the CQRS path.
4. Migrate `handle_execute_async` to CQRS pattern:
   - Move to `_mission_cqrs/commands.py` as `handle_execute_async_cqrs`.
   - Update `v1/mission.py` to use CQRS version.
5. Run legacy tests; migrate them to CQRS test patterns:
   - `test_mission_handlers.py` → test `_mission_cqrs/` directly.
   - `test_mission_lifecycle.py` → test lifecycle through CQRS handlers.
6. Delete `_mission_handlers.py` after all tests pass.

## Constraints
- SSE streaming must work identically — same event types, same JSON format.
- Must not break the v2 API contract.
- Must maintain owner-authorization checks.

## Verification
```bash
cd /opt/flowmanner/backend
# Run migrated tests
python -m pytest app/tests/test_mission_handlers.py -v
python -m pytest app/tests/test_mission_lifecycle.py -v
# Run all mission tests
python -m pytest app/tests/ -k "mission" -v
# Verify legacy file is gone
test ! -f app/api/_mission_handlers.py && echo "PASS: legacy module removed"
```
