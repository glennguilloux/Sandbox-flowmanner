# TASK-BE-STUB-09 — Remove Legacy TriggerScheduler, Consolidate on TriggerBridge

## Current State
Two trigger dispatch systems exist:
1. **TriggerBridge** (`/opt/flowmanner/backend/app/services/substrate/trigger_bridge.py`): 2s polling, used when `FLOWMANNER_SUBSTRATE_V2=run`.
2. **Legacy TriggerScheduler** (`/opt/flowmanner/backend/app/services/trigger_scheduler.py`): 30s polling, DEPRECATED (H2.4), used when V2 is NOT set.

`/opt/flowmanner/backend/app/lifespan.py:513-530`:
```python
if os.getenv("FLOWMANNER_SUBSTRATE_V2", "").lower() == "run":
    await start_trigger_bridge()  # 2s polling
else:
    await trigger_scheduler.start()  # 30s polling
```

## Problem
- **HIGH**: Two trigger dispatch systems create maintenance burden.
- Legacy scheduler has 15x slower polling (30s vs 2s).
- Feature flag adds unnecessary complexity.

## Exact Files
- **Delete:** `/opt/flowmanner/backend/app/services/trigger_scheduler.py`
- **Modify:** `/opt/flowmanner/backend/app/lifespan.py` (lines 513-545: `_start_trigger_scheduler` and `_stop_trigger_scheduler`)
- **Check:** `/opt/flowmanner/backend/app/api/v1/triggers.py` (remove legacy scheduler refs)
- **Check:** Any other imports of `trigger_scheduler`

## Exact Implementation Steps
1. Find all imports of the legacy scheduler:
   ```bash
   grep -r "trigger_scheduler" app/ --include="*.py" | grep -v __pycache__
   ```
2. Update `lifespan.py` to always start TriggerBridge:
   ```python
   async def _start_trigger_scheduler():
       from app.services.substrate.trigger_bridge import start_trigger_bridge
       await start_trigger_bridge()
       logger.info("TriggerBridge started (2s polling)")
   
   async def _stop_trigger_scheduler():
       from app.services.substrate.trigger_bridge import stop_trigger_bridge
       await stop_trigger_bridge()
   ```
3. Remove the `FLOWMANNER_SUBSTRATE_V2` check for trigger dispatch.
4. Delete `trigger_scheduler.py`.
5. Update any tests that mock the legacy scheduler.

## Constraints
- Triggers must still fire within 2 seconds of scheduled time.
- Must not break any cron trigger that was working.
- The `notify_trigger_due()` hook in TriggerBridge can remain as a future stub.

## Verification
```bash
cd /opt/flowmanner/backend
# Verify no legacy imports remain
! grep -r "trigger_scheduler" app/ --include="*.py" | grep -v __pycache__ | grep -v "# " && echo "PASS: no legacy refs"
# Verify TriggerBridge is the only path
grep -r "TriggerBridge\|start_trigger_bridge" app/ --include="*.py" | grep -v __pycache__
```
