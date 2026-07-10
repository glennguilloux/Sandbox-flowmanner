# Task: Phase 2 — User-Facing Fixes (Revenue + Core Feature)

**Status:** DRAFT
**Priority:** P0 — these are broken features users hit daily
**Estimated effort:** 2–3 sessions
**Created:** 2026-07-06
**Audited:** 2026-07-06 (ground-truth verification against live codebase)
**Source:** `docs/STUB-COMPLETION-PLAN-2026-07-06.md` §Phase 2
**Depends on:** Phase 0 (save state) ✅ complete

---

## Problem

Four user-facing issues:

1. **Contact form silently drops messages** — `handleSubmit` calls `setSubmitted(true)` without sending data. Every submission is lost.
2. **`fire_program` + `consolidate_learning` CQRS wrappers are dead code** — the backing service methods are ALREADY implemented, but `commands.py` still wraps calls in `try/except NotImplementedError` with outdated "T8 stub" comments. The endpoints actually work, but the wrappers add unnecessary exception handling and misleading documentation.
3. **Mission analytics return hardcoded `[]`** — three methods at `mission_analytics.py:54-63` return `[]` unconditionally.
4. **Dashboard `total_tokens` = 0** — hardcoded TODO in stats endpoint.

---

## ⚠️ Critical Pre-Task Correction (2.2)

**DeepSeek's original task claimed `fire_program` raises `NotImplementedError` → 501. This is WRONG.**

Ground truth (verified 2026-07-06):
- **`fire_program`** at `backend/app/services/mission_program_service.py:307-400` is **FULLY IMPLEMENTED** (~95 lines). It creates a Mission, creates a ProgramRun, dispatches to UnifiedExecutor, tracks cost/tokens/duration, and handles errors.
- **`consolidate_learning`** at `backend/app/services/mission_program_service.py:440-520+` is **FULLY IMPLEMENTED** (~80+ lines). It queries terminal runs, fetches episodic memory summaries, calls BudgetEnforcer for LLM synthesis, merges learning brief, and persists.
- **The HTTP routes work:** `programs.py:271-281` calls `commands.fire_program()` → `service.fire_program()` and returns `ProgramRunResponse`. `programs.py:342-351` does the same for consolidate.
- **Only the CQRS layer is stale:** `commands.py:107-124` and `:149-165` still wrap the calls in `try/except NotImplementedError` with comments saying "T8 will replace this stub" — but T8/T9 already shipped.
- **ProgramError maps to 500** (not 501) per `programs.py:21`.

**The actual task:** Remove the dead `try/except NotImplementedError` wrappers, update the doc comments, and verify the endpoints return 200 on the live backend.

---

## Acceptance Criteria

- [ ] `POST /api/v2/contact` endpoint exists and stores submissions
- [ ] Frontend contact form sends data to backend and shows success/error
- [ ] Dead `try/except NotImplementedError` wrappers removed from `commands.py:119-124` and `:161-164`
- [ ] Doc comments on `fire_program` and `consolidate` in `commands.py` updated to reflect real implementation
- [ ] `GET /api/v2/missions/{id}/analytics` returns real data (not hardcoded `[]`)
- [ ] Dashboard stats endpoint returns real `total_tokens` (not 0)
- [ ] All backend tests pass
- [ ] Frontend typechecks clean

---

## Sub-tasks

### 2.1 — Wire contact form to backend

**Current:** `src/app/[locale]/contact/page-client.tsx:22-26` — `handleSubmit` calls `setSubmitted(true)` without sending data.

**Important context the plan missed:**
- The form has a **`subject`** field (line 12: `subject: "Sales"`). The backend schema must include it.
- The form also has `company` (line 10).
- `apiClient` is at `@/lib/api-client` and exports `{ apiClient }` (instance, line 238). Import pattern: `import { apiClient } from "@/lib/api-client"`. It has `.post()`, `.get()`, etc.
- Alerting service at `backend/app/services/alerting.py` has: `send_circuit_alert()`, `send_slo_alert()`, `send_5xx_alert()`. There is NO generic `send_alert()`. For contact form, call `send_circuit_alert()` with a contact-specific title, or create a simple `send_contact_alert()` wrapper.

#### Backend

1. **Create `backend/app/models/contact.py`** — `ContactSubmission` ORM model:
   - `id` (UUID, PK)
   - `name` (String, not null)
   - `email` (String, not null)
   - `company` (String, nullable)
   - `subject` (String, not null, default "Sales") ← **MISSING from original plan**
   - `message` (Text, not null)
   - `status` (String, default "new")
   - `created_at` (DateTime)

2. **Create Alembic migration:**
   ```bash
   cd /opt/flowmanner
   docker compose exec backend alembic revision --autogenerate -m "add contact_submissions"
   # Review the generated migration
   docker compose exec backend alembic upgrade head
   ```

3. **Create `backend/app/api/v2/contact.py`**:
   - `POST /api/v2/contact` (public — no auth required)
   - Pydantic schema: `ContactSubmissionCreate` (name, email, company?, subject, message)
   - Store in DB
   - Fire alert via `alerting.send_circuit_alert(title="New Contact Submission", ...)` (the service has circuit breaker alerts, adapt for contact)
   - Return `ok({"status": "received"})`

4. **Mount router** in `backend/app/api/v2/__init__.py`:
   ```python
   from app.api.v2.contact import router as contact_router
   api_v2_router.include_router(contact_router)
   ```

#### Frontend

1. In `contact/page-client.tsx`, add import:
   ```ts
   import { apiClient } from "@/lib/api-client";
   ```

2. Replace `handleSubmit`:
   - Add `const [submitting, setSubmitting] = useState(false);`
   - `await apiClient.post("/api/v2/contact", form)`
   - `setSubmitted(true)` on success
   - Show error toast on failure (check what toast library is used — likely `sonner` or `react-hot-toast`)
   - Disable button while `submitting`

**Verify:**
```bash
curl -X POST http://127.0.0.1:8000/api/v2/contact \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@test.com","subject":"Sales","message":"Hello"}'
# → 200 or 201

cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit
```

**Commit:** `feat: wire contact form to backend POST /api/v2/contact`

---

### 2.2 — Remove dead CQRS wrappers for fire_program + consolidate_learning

**⚠️ CORRECTED: These are NOT unimplemented. The service methods work. Only the CQRS wrappers are stale.**

**Current state (verified):**
- `commands.py:97-139` — `fire_program` wraps call in `try/except NotImplementedError` (lines 119-124). The service method at `mps.py:307` is fully implemented and never raises `NotImplementedError`. This is **dead code**.
- `commands.py:143-177` — `consolidate` wraps call in `try/except NotImplementedError` (lines 161-164). The service method at `mps.py:440` is fully implemented and never raises `NotImplementedError`. Also **dead code**.
- Both have comments claiming "T8/T5 stub" / "replace this stub" — these shipped already.

**Steps:**

1. **Read the code to confirm:**
   - `backend/app/services/mission_program_service.py:307-400` (fire_program — verify it's real)
   - `backend/app/services/mission_program_service.py:440-520` (consolidate_learning — verify it's real)
   - `backend/app/api/_program_cqrs/commands.py:97-139` and `:143-177`

2. **In `commands.py`**, for `fire_program` (lines 107-124):
   Remove the `try/except NotImplementedError` wrapper. Keep only the direct call + audit logging:
   ```python
   async def fire_program(self, ...) -> ProgramRunResponse:
       """Trigger a program run (T8 — implemented). Creates Mission + ProgramRun,
       dispatches to UnifiedExecutor, returns ProgramRunResponse."""
       service = self._build_service()
       run = await service.fire_program(
           user.id, program_id,
           trigger_type=trigger_type,
           trigger_payload=trigger_payload,
       )
       # Audit (non-blocking)
       if self.audit is not None and hasattr(self.audit, "program_fired"):
           try:
               self.audit.program_fired(...)
           except Exception:
               logger.debug("program_fired audit failed", exc_info=True)
       return ProgramRunResponse.model_validate(run)
   ```

3. **For `consolidate`** (lines 152-164):
   Remove the `try/except NotImplementedError` wrapper. Same pattern — direct call + audit.

4. **Update the doc comments** to remove "T5 stub raises NotImplementedError" / "surface as ProgramError so HTTP layer returns 501" — replace with accurate "T8/T9 — implemented" descriptions.

5. **Note:** The HTTP routes in `programs.py` already catch `ProgramError` → map to 500. This is correct and doesn't need changes. The `ProgramError` comes from other sources like `ProgramNotFound`, `ProgramBudgetExceeded`, etc. — not from the removed `NotImplementedError` wrappers.

**Verify:**
```bash
# Should return 200 (not 501)
curl -X POST http://127.0.0.1:8000/api/v2/programs/{id}/fire \
  -H "Authorization: Bearer ***" \
  -H "Idempotency-Key: test-$(date +%s)"

curl -X POST http://127.0.0.1:8000/api/v2/programs/{id}/consolidate \
  -H "Authorization: Bearer ***" \
  -H "Idempotency-Key: test-$(date +%s)"

docker compose exec backend pytest app/tests/ -k "program" -v
```

**Commit:** `refactor: remove dead NotImplementedError wrappers from fire_program/consolidate CQRS handlers`

---

### 2.3 — Implement 3 mission analytics methods

**Current:** `backend/app/services/mission_analytics.py:54-63` — three methods return `[]` unconditionally.
These feed `GET /api/v2/missions/{id}/analytics` (verified at `missions.py:445-451`).

The top-level `get_mission_analytics()` (lines 13-51) is already implemented — it queries Mission table correctly. Only the three sub-methods are stubbed.

**Context:**
- Mission model: `app/models/mission_models.py:143` — `class Mission(Base)` with `__tablename__ = "missions"`, has `created_at`, `status`, `tokens_used`, `user_id`, `failure_reason`
- LLMCallRecord: `app/models/llm_call_record.py:20` — has `prompt_tokens`, `completion_tokens`, `model_id`, `cost_usd`, `timestamp`

**Implement:**

1. **`get_mission_analytics_over_time(db, user_id, days=30)`:**
   ```python
   # SELECT DATE(created_at) as day, COUNT(*) as total,
   #        COUNT(*) FILTER (WHERE status = 'completed') as completed
   # FROM missions WHERE user_id = ? AND created_at > now() - interval 'N days'
   # GROUP BY day ORDER BY day
   ```

2. **`get_failure_analysis(db, user_id)`:**
   ```python
   # Query missions with status = 'failed' (or error states)
   # Group by failure_reason or mission_type
   # Return [{"category": "LLM timeout", "count": 3}, ...]
   ```

3. **`get_token_usage_breakdown(db, user_id)`:**
   ```python
   # SELECT model_id, SUM(prompt_tokens + completion_tokens) as total_tokens, SUM(cost_usd)
   # FROM llm_call_records
   # GROUP BY model_id ORDER BY total_tokens DESC
   ```
   ⚠️ **Note:** LLMCallRecord has `prompt_tokens` + `completion_tokens` — there is NO `total_tokens` column. Use `prompt_tokens + completion_tokens`.

**Verify:**
```bash
curl http://127.0.0.1:8000/api/v2/missions/{id}/analytics \
  -H "Authorization: Bearer ***" | python3 -m json.tool
# over_time, token_usage, failure_analysis should be arrays
# (possibly empty if no data, but NOT hardcoded [])
```

**Commit:** `feat: implement mission analytics timeseries, failure analysis, token breakdown`

---

### 2.4 — Fix dashboard `total_tokens` = 0

**Current:** `backend/app/main_fastapi.py:482`:
```python
"total_tokens": 0,  # TODO: aggregate from LLMCallRecord table
```

**⚠️ Correction:** LLMCallRecord has `prompt_tokens` + `completion_tokens` — there is NO `total_tokens` column. The query must SUM both.

The dashboard route is `backend/app/api/v2/dashboard.py`. The `main_fastapi.py:482` is inside a function that builds stats for graph executions. It already imports `LLMCallRecord` (verified at `dashboard.py:15`).

**Fix at `main_fastapi.py:482`:**
```python
"total_tokens": (
    await db.execute(
        select(func.coalesce(
            func.sum(LLMCallRecord.prompt_tokens + LLMCallRecord.completion_tokens), 0
        ))
    )
).scalar() or 0,
```

**Also check:** There are 3 instances of `"total_tokens": 0` — lines 455, 482, 490. All need fixing.

**Verify:**
```bash
curl http://127.0.0.1:8000/api/dashboard/stats
# total_tokens should be a real number, not 0
```

**Commit:** `fix: aggregate total_tokens from LLMCallRecord in dashboard stats`

---

## Verification Gate (after all sub-tasks)

```bash
# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/ -q --tb=no 2>&1 | tail -5
curl http://127.0.0.1:8000/api/health

# Frontend
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit
```

---

## File Map

| File | Action |
|------|--------|
| `backend/app/models/contact.py` | **NEW** — ContactSubmission ORM model |
| `backend/app/api/v2/contact.py` | **NEW** — POST /api/v2/contact endpoint |
| `backend/app/api/v2/__init__.py` | Register contact router |
| `backend/alembic/versions/` | **NEW** — migration for contact_submissions table |
| `src/app/[locale]/contact/page-client.tsx` | Wire handleSubmit to backend via `apiClient.post()` |
| `backend/app/api/_program_cqrs/commands.py` | Remove dead `try/except NotImplementedError` wrappers, update doc comments |
| `backend/app/services/mission_analytics.py` | Implement 3 `return []` stubs (lines 54-63) |
| `backend/app/main_fastapi.py` | Fix total_tokens = 0 (lines 455, 482, 490) |

---

## Risks

| Risk | Mitigation |
|------|------------|
| ~~fire_program needs deep substrate knowledge~~ | **Correction:** Already implemented. Task is just removing dead wrappers. |
| Analytics queries may be slow on large datasets | Add appropriate indexes; already using `func.sum()` pattern from existing `get_mission_analytics()` |
| Contact form spam (public endpoint) | Add rate limiting; consider CAPTCHA in a follow-up |
| `prompt_tokens + completion_tokens` may overflow for very large values | SQLAlchemy handles this; both are `Integer` columns (max ~2.1B) |
| The `subject` field is currently hardcoded to "Sales" in the form | Include it in the schema; the form has a dropdown select |
