# Handoff — 2026-07-03 (HITL Wiring + Mypy Fixes)

**Session:** 2026-07-03 wiring session
**Agent:** Buffy (Codebuff)
**Status:** 3 commits ahead of `origin/main`, frontend changes uncommitted

---

## ⚠️ Do first in next session

1. **Push commits:** `cd /opt/flowmanner && git push origin main` (3 commits: HITL SSE endpoint, db dep fix, mypy fixes)
2. **Deploy frontend:** `cd /home/glenn/FlowmannerV2-frontend && ship` (or `bash /opt/flowmanner/deploy-frontend.sh`) — inbox nav entry + SSE hook changes need deploying

---

## What was done this session

### 1. HITL Inbox SSE Wiring (B3)

**Problem:** The inbox frontend was fully built but the SSE real-time updates were broken:
- Frontend connected to `/api/users/me/notifications/stream` — this endpoint didn't exist (notification router import fails silently in `v1/__init__.py`)
- Frontend listened for `event: notification` but the HITL stream sends `event: hitl_inbox`

**Fix:**
- Added `GET /api/inbox/stream` endpoint in `hitl.py` using existing `hitl_inbox_sse_stream` — bypasses the broken notification router entirely
- Updated `use-inbox-sse.ts` to connect to `/api/inbox/stream` and listen for `hitl_inbox` events
- Added inbox nav entry in `nav-config.ts` + `nav.inbox` i18n key in all 5 locales
- Fixed `floating-nav.test.tsx` (count 11→12, added "inbox" to expected IDs)

### 2. Backend Startup Fix

**Problem:** `SENTRY_WEBHOOK_SECRET` validation (added in previous session's commit) was crashing the backend (exit code 3) because the env var wasn't set.

**Fix:** Added `SENTRY_WEBHOOK_SECRET` (48-char hex) to `.env`. Note: `docker compose restart` doesn't re-read env_file — must use `docker compose up -d --no-deps backend`.

### 3. Mypy Fixes (deferred from deep-dive session)

**4 errors fixed:**
- `budget_enforcer.py:102-103` — `entry["input"]`/`entry["output"]` wrapped in `float()` (was `float * (float|str)`)
- `budget_enforcer.py:113` — `entry["provider"]` wrapped in `str()` (return type `float|str` vs `str`)
- `causal_decomposer.py:696` — Replaced invalid `context_data` kwarg with proper `FailureContext` fields

---

## What was discovered as already built

| Item | Status |
|------|--------|
| B2a: Reliability Center UI | ✅ Built 2026-07-01, field-name bugs already fixed |
| B2b: Tool Routing Inspector UI | ✅ Fully built and wired |
| C1: LLM judge → BudgetEnforcer | ✅ Done in deep-dive session |
| C2: Cloud model refs → local | ✅ Done in deep-dive session |

---

## Current state

| Check | Status |
|-------|--------|
| Git | 3 commits ahead of `origin/main`, clean tree |
| Backend health | ✅ 200 |
| Backend tests | 443 passed, 1 pre-existing failure (audioop deprecation) |
| Frontend tests | 878/878 passed |
| TypeScript | Clean |
| mypy (fixed files) | 0 errors |
| Alembic | At head (`20260630_plan_candidates`) |

---

## Next session priorities (from deep-dive roadmap)

| Priority | Item | Effort |
|----------|------|--------|
| P2 | B2c: Plugin Manager UI — extensions vs plugins deep-dive first | M |
| P2 | B1: Standardize on React Query + apiClient (58 raw fetch calls) | M |
| P2 | A3: Delete `langchain/` legacy subpackage | S |
| P2 | A2: Migrate 6 v1 routers off old executors | L |
| P3 | A1: Delete 7 old executors (after A2) | L |
| P3 | E3: Randomize BYOK encryption salt | S |
| P3 | E4: Verify Sentry initialization | S |
| P3 | E5: Audit webhook verifiers for constant-time comparison | S |

---

## Key files changed (backend)

```
backend/app/api/v1/hitl.py              — +47 lines (SSE stream endpoint)
backend/app/services/budget_enforcer.py  — +3/-3 (float/str casts)
backend/app/services/improvement/causal_decomposer.py — +4/-4 (FailureContext fix)
.env                                     — +1 line (SENTRY_WEBHOOK_SECRET)
```

## Key files changed (frontend, uncommitted)

```
src/hooks/use-inbox-sse.ts                           — endpoint + event type change
src/components/layout/nav-config.ts                  — inbox nav entry
src/components/layout/__tests__/floating-nav.test.tsx — updated assertions
src/i18n/locales/{en,de,es,fr,ja}.json               — nav.inbox key
```

---

## Known issues for next session

1. **Notification router import failure** in `v1/__init__.py` (line 171) — `notification_router = None` because `notification_service.py` fails to import. Root cause unknown. The inbox SSE endpoint bypasses this, but the general notification stream (`/api/notifications/stream`) is broken.

2. **Pre-existing test failure:** `test_audio_format_converter.py::test_all_supported_formats` — `audioop` module deprecated in Python 3.13.

3. **Improvement loop needs investigation** — Glenn said "be careful, needs big investigation first" before cutting Phases 3-6.

4. **Extensions vs plugins** — Glenn said "deep-dive first before merging" — two separate backend systems (`plugins.py` 853 lines vs `extensions.py`).

5. **Jaeger and Langfuse dropped** — Glenn confirmed not using either. Jaeger service removed from docker-compose in previous session. Langfuse disabled via `LANGFUSE_ENABLED=False`.
