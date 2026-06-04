# TASK-BE-STUB-10 — Consolidate Browser Implementations (Remove Feature Flag)

## Current State
Two browser implementations controlled by `FLOWMANNER_HARNESS_MODE` env var:
1. **BrowserService** (Playwright-based): `/opt/flowmanner/backend/app/services/browser_service.py`
2. **HarnessBrowserService** (CDP-based): `/opt/flowmanner/backend/app/services/harness_browser_service.py`

Feature flag: `/opt/flowmanner/backend/app/services/browser_mode.py`:
```python
def use_harness() -> bool:
    val = os.environ.get("FLOWMANNER_HARNESS_MODE", "").lower()
    return val in ("1", "true", "yes", "on")
```

`browser_service.py:536`:
```python
# TODO: remove feature flag once HarnessSession replaces BrowserSession.
```

`browser_mode.py:4`:
```python
# TODO: remove this module once HarnessSession fully replaces BrowserSession.
```

## Problem
- **HIGH**: Two browser implementations to maintain, test, and debug.
- Feature flag adds unnecessary branching in the production code path.
- These TODO comments will never be cleaned up without explicit action.

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/services/browser_service.py` (get_browser_service function)
- **Delete:** `/opt/flowmanner/backend/app/services/browser_mode.py`
- **Keep:** One of `BrowserService` or `HarnessBrowserService` (pick one)
- **Delete the other:** Either remove Playwright path or CDP harness path
- **Reference:** `/opt/flowmanner/backend/app/services/browser_manager.py`

## Exact Implementation Steps
1. Determine which browser implementation is stable and performant:
   - Check production logs for `FLOWMANNER_HARNESS_MODE` usage.
   - Compare reliability of Playwright vs CDP harness.
2. Pick one implementation and remove the feature flag:
   ```python
   def get_browser_service():
       global _browser_service_instance
       if _browser_service_instance is None:
           _browser_service_instance = BrowserService()  # or HarnessBrowserService
       return _browser_service_instance
   ```
3. Delete `browser_mode.py`.
4. Remove the unused browser implementation file (or archive with .bak extension).
5. Remove `FLOWMANNER_HARNESS_MODE` from any docker-compose files or env configs.

## Constraints
- Must not break existing browser sessions during deployment.
- Must test the chosen implementation thoroughly before removing the other.

## Verification
```bash
cd /opt/flowmanner/backend
# Verify feature flag module is gone
test ! -f app/services/browser_mode.py && echo "PASS: browser_mode.py removed"
# Verify only one browser service import path
grep -r "HarnessBrowserService\|BrowserService" app/services/ --include="*.py" | grep -v __pycache__ | grep -v "test"
```
