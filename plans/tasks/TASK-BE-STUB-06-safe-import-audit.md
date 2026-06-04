# TASK-BE-STUB-06 — Audit and Fix Silent Router Drops (v1 _safe_import)

## Current State
`/opt/flowmanner/backend/app/api/v1/__init__.py:7-14`:
```python
def _safe_import(module_name, attr="router"):
    try:
        mod = __import__(f"app.api.v1.{module_name}", fromlist=[attr])
        return getattr(mod, attr)
    except Exception as e:
        logger.warning(f"Skipping {attr} from app.api.v1.{module_name}: {e}")
        return None
```
60+ routers use this pattern. At least 20 modules don't exist as files:
community, domain_agents, file, flow_compat, llm, llm_advanced, memory, mission_advanced_routes, mission_decomposition_routes, delegations, feedback_routes, blog, admin, integrations, marketplace, linear, data_export, feature_flags, changelog, agent_capabilities, agent_personalities

## Problem
- **CRITICAL**: If any router has a runtime import error, the entire API path silently vanishes with only a log warning. No alert, no 500 — just a 404 later.
- 20+ imports fail every startup. This creates log noise and masks real import failures.
- No way to distinguish "intentionally missing" from "unexpectedly broken."

## Exact Files
- **Modify:** `/opt/flowmanner/backend/app/api/v1/__init__.py` (entire file)
- **Reference:** `/opt/flowmanner/backend/app/api/v1/` (check which files actually exist)

## Exact Implementation Steps
1. Replace the uniform `_safe_import` with a categorized import system:
   ```python
   from enum import Enum
   
   class RouterTier(Enum):
       CRITICAL = "critical"  # auth, mission, chat — fail startup if missing
       STANDARD = "standard"  # most routers — warn if missing
       OPTIONAL = "optional"  # integrations, community — info only
   
   def _import_router(module_name, attr="router", tier=RouterTier.STANDARD):
       try:
           mod = __import__(f"app.api.v1.{module_name}", fromlist=[attr])
           return getattr(mod, attr)
       except ImportError:
           if tier == RouterTier.CRITICAL:
               logger.critical(f"CRITICAL router missing: {module_name}")
               raise
           elif tier == RouterTier.OPTIONAL:
               logger.info(f"Optional router not available: {module_name}")
           else:
               logger.warning(f"Router not available: {module_name}")
           return None
       except Exception as e:
           logger.error(f"Router import failed: {module_name}: {e}")
           if tier == RouterTier.CRITICAL:
               raise
           return None
   ```
2. Categorize each import:
   - **CRITICAL**: auth, users, mission, chat, graph
   - **STANDARD**: browser, agent, byok, subscription, webhooks, tools, etc.
   - **OPTIONAL**: community, integrations, marketplace, blog, newsletter, etc.
3. Remove imports for modules confirmed non-existent and not planned.
4. Add a health-check endpoint that reports router import status.
5. Add a startup validation that counts expected vs actual routers.

## Constraints
- Must not break any existing working routes.
- Must not slow down startup (imports are fast even with validation).
- Must maintain backward compatibility with existing API consumers.

## Verification
```bash
cd /opt/flowmanner/backend
# List which routers actually exist
ls app/api/v1/*.py | sed 's|app/api/v1/||;s|\.py||' | sort
# Compare against __init__.py imports
grep "_safe_import\|_import_router" app/api/v1/__init__.py | wc -l
# Startup should not have missing CRITICAL router errors
python -c "from app.api.v1 import api_v1_router; print('OK')"
```
