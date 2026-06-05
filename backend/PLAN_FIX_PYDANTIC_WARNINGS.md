# Plan: Fix Pydantic V2 Deprecation Warnings & datetime.utcnow() Deprecations

## Summary of Issues Found

After running both **inner tests** (`app/tests/`) and **outer tests** (`tests/`), all tests pass but there are **104 warnings** across two categories:

### 1. Pydantic V2 Deprecation Warnings (class-based `config` → `ConfigDict`)

**Files to fix (12 files, ~25 classes):**

| File | Classes | Lines |
|------|---------|-------|
| `app/schemas/auth.py` | `UserResponse` | 29-30 |
| `app/schemas/chat.py` | `ChatFolderResponse`, `ChatThreadResponse`, `ChatMessageResponse`, `ChatFileResponse`, `ChatBranchResponse`, `ChatTemplateResponse` | 22-23, 46-47, 65-66, 85-86, 104-105, 128-129 |
| `app/schemas/agent.py` | `AgentCatalogItem`, `AgentCatalogDetail` | 79-80, 97+ |
| `app/schemas/delegation.py` | `DelegationResponse`, `WorkspaceMemberResponse` | 30-31, 58-59 |
| `app/schemas/roles.py` | `RolePermissionResponse`, `RoleResponse`, `UserRoleAssignmentResponse` | 27-28, 42-43, 64-65 |
| `app/models/io_models.py` | `IOBlob` | 50-51 |
| `app/api/v1/workspace_shares.py` | `ShareResponse` | 49-50 |
| `app/api/v2/workspaces.py` | `WorkspaceResponse` | 38-39 |
| `app/integrations/openwhisk/client.py` | `@validator` → `@field_validator` | 35-39 |
| `app/schemas/auth_v3.py` | `UserSummary`, `UserResponse` | 112-113, 140-141 |
| `app/schemas/workspace_v3.py` | `WorkspaceResponse` | 34-35 |
| `app/schemas/extension.py` | `ExtensionResponse` | 42-43 |

**Fix Pattern:**
```python
# OLD (deprecated)
class MyModel(BaseModel):
    ...
    class Config:
        from_attributes = True

# NEW (Pydantic V2)
class MyModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ...
```

### 2. datetime.utcnow() Deprecation Warnings (2 files, 6 occurrences)

**Files to fix:**

| File | Lines | Count |
|------|-------|-------|
| `app/services/nexus/failure_analyzer.py` | 518 | 1 |
| `app/services/nexus/meta_loop_orchestrator.py` | 128, 139, 156, 173, 257 | 5 |

**Fix Pattern:**
```python
# OLD (deprecated)
from datetime import datetime
datetime.utcnow()

# NEW (Python 3.11+)
from datetime import datetime, UTC
datetime.now(UTC)
```

---

## Execution Plan

### Phase 1: Fix Pydantic ConfigDict Warnings (12 files)

**Priority: High** — These are the bulk of warnings and block clean CI output.

**Order (independent, can run in parallel):**
1. `app/schemas/auth.py` — 1 class
2. `app/schemas/chat.py` — 6 classes
3. `app/schemas/agent.py` — 2 classes (note: `AgentTemplateResponse` already uses `ConfigDict`)
4. `app/schemas/delegation.py` — 2 classes
5. `app/schemas/roles.py` — 3 classes
6. `app/models/io_models.py` — 1 class (also has `arbitrary_types_allowed=True`)
7. `app/api/v1/workspace_shares.py` — 1 class
8. `app/api/v2/workspaces.py` — 1 class
9. `app/integrations/openwhisk/client.py` — `@validator` → `@field_validator`
10. `app/schemas/auth_v3.py` — 2 classes
11. `app/schemas/workspace_v3.py` — 1 class
12. `app/schemas/extension.py` — 1 class

**Special case: `io_models.py`**
```python
# OLD
class IOBlob(BaseModel):
    ...
    class Config:
        arbitrary_types_allowed = True

# NEW
class IOBlob(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ...
```

**Special case: `openwhisk/client.py`**
```python
# OLD
from pydantic import BaseModel, Field, validator

@validator('api_host')
def validate_api_host(cls, v):
    ...

# NEW
from pydantic import BaseModel, Field, field_validator

@field_validator('api_host')
@classmethod
def validate_api_host(cls, v):
    ...
```

### Phase 2: Fix datetime.utcnow() Warnings (2 files)

**Priority: High** — These are stdlib deprecations, not just Pydantic.

**Changes:**
1. `app/services/nexus/failure_analyzer.py:518`
2. `app/services/nexus/meta_loop_orchestrator.py:128, 139, 156, 173, 257`

All files already import `datetime` — just add `UTC` to imports and replace.

### Phase 3: Verify Fixes

**Run both test suites:**
```bash
# Inner tests (app/tests/)
cd /opt/flowmanner/backend
PYTHONPATH=/opt/flowmanner/backend python -m pytest -q app/tests/test_auth_v3_unit.py app/tests/test_health.py

# Outer tests (tests/ — substrate + chaos)
PYTHONPATH=/opt/flowmanner/backend python -m pytest -q tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/chaos/test_kill_worker_mid_mission.py tests/chaos/test_kill_worker_mid_mission_process.py
```

**Expected result:** All tests pass, **0 warnings** (or only external library warnings we can't control).

---

## Implementation Notes

### For DeepSeek (or any agent executing this):

1. **Work file-by-file**, not line-by-line — each file is independent
2. **Use `patch` tool** with exact old_string/new_string for precision
3. **Run tests after each file** (or each batch of 3-4) to catch regressions early
4. **chmod 644** any new `.py` files created (write_file creates 600)
5. **Don't modify test files** — only source code

### Common Pitfalls to Avoid:

- ❌ Don't change `from_attributes = True` to `populate_by_name=True` — they're different
- ❌ Don't remove `arbitrary_types_allowed` from `IOBlob` — it needs it for `bytes`
- ❌ Don't forget `@classmethod` on `@field_validator` methods
- ❌ Don't use `datetime.UTC` without importing it: `from datetime import datetime, UTC`

### Verification Commands:

```bash
# Quick pydantic warning check
cd /opt/flowmanner/backend
PYTHONPATH=/opt/flowmanner/backend python -c "
import warnings
warnings.filterwarnings('error', category=DeprecationWarning, module='pydantic')
from app.schemas.auth import UserResponse
from app.schemas.chat import ChatThreadResponse
from app.models.io_models import IOBlob
from app.api.v1.workspace_shares import ShareResponse
print('All schemas import without pydantic deprecation warnings')
"
```

```bash
# Quick datetime.utcnow() check
grep -rn "datetime\.utcnow()" /opt/flowmanner/backend/app/services/
# Should return nothing
```

---

## Time Estimate

| Phase | Files | Est. Time |
|-------|-------|-----------|
| 1: Pydantic ConfigDict | 12 | ~30 min |
| 2: datetime.utcnow() | 2 | ~5 min |
| 3: Verify | Both suites | ~2 min |

**Total: ~40 minutes**

---

## Success Criteria

- [ ] All 12 files use `model_config = ConfigDict(...)`
- [ ] `openwhisk/client.py` uses `@field_validator`
- [ ] All 6 `datetime.utcnow()` replaced with `datetime.now(UTC)`
- [ ] Inner tests pass with 0 pydantic warnings
- [ ] Outer tests pass with 0 pydantic/datetime warnings
- [ ] No new test failures introduced

---

## Post-Fix: Docker Rebuild

After all fixes verified locally:
```bash
# From homelab
bash /opt/flowmanner/deploy-backend.sh
# Wait ~2 min, then verify
curl http://127.0.0.1:8000/api/health
```

---

*Generated after verifying both inner (app/tests/) and outer (tests/) test suites pass with 104 warnings.*