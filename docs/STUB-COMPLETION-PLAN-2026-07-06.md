# FlowManner — Stub Completion Plan (2026-07-06)

> **Source document:** `docs/STUB-DEEPDIVE-CHECKLIST-2026-07-06.md`
> **Machine:** Homelab (172.16.1.1 / 10.99.0.3)
> **Backend:** `/opt/flowmanner/backend/`
> **Frontend:** `/home/glenn/FlowmannerV2-frontend/`
>
> **Plan shape:** This is NOT a from-scratch build plan. The site is ~90%
> built. This plan fixes the 27 remaining stub/broken/incomplete surfaces
> identified in the deep-dive audit, sequenced by dependency and risk.
>
> **The companion prompt for DeepSeek is at the bottom of this file
> (Section 7).** Copy-paste it verbatim into DeepSeek.

---

## 0. Pre-flight: state of the world (verified 2026-07-06 16:40)

### Frontend gates (ALL GREEN ✅)

```
npx tsc --noEmit          → 0 errors
npx vitest run            → 929 passed (75 files)
npx next build            → succeeded
git status --short | wc -l → 61 dirty files
```

The 61 dirty files are a **coherent refactor**: a new `src/lib/server-fetch.ts`
helper that deduplicates the `auth() + fetch(BACKEND_URL)` pattern across all
Next.js API routes. Also includes `SandboxPreviewButton` rework (+199 LOC),
hook refactors (`use-programs`, `use-personal-memory`, `use-critiques`), and
7 new untracked files (3 e2e specs, 2 test files, `server-fetch.ts`, phase3
handoff doc). **All gates pass on the dirty tree** — this work is committable.

### Backend gates

```
curl http://127.0.0.1:8000/api/health → (verify, should be 200)
alembic current                        → head
pytest app/tests/ -q                   → 329 passed (last known)
```

---

## Phase 0: Save state (CRITICAL — do before anything else)

### 0.1 Commit the 54 modified + 7 untracked frontend files

The dirty work is a `serverFetch` refactor + hook cleanup + sandbox preview
rework. Gates are green. Commit it before this session's context is lost.

**Steps:**
1. `cd /home/glenn/FlowmannerV2-frontend`
2. Review: `git diff --stat | tail -5` → should show ~54 files, +1238/-1584
3. Stage tracked changes: `git add -u`
4. Stage new files: `git add src/lib/server-fetch.ts src/components/chat/ToolCallCard.test.tsx src/hooks/__tests__/use-personal-memory.test.tsx e2e/ plans/phase3-exit-audit-handoff.md`
5. Commit:
   ```
   refactor: extract serverFetch helper + modernize data hooks

   - Add src/lib/server-fetch.ts: deduplicates auth() + fetch(BACKEND_URL)
     across all Next.js API routes. Replaces ~20 lines per route with 2.
   - Migrate 6 onboarding API routes to serverFetch.
   - Rewrite use-programs, use-personal-memory, use-critiques hooks
     (simpler, fewer re-renders, better error handling).
   - Rework SandboxPreviewButton (+199 LOC): robust preview lifecycle.
   - Clean up ThreadSidebar (-112 LOC) and ToolActivityFeed.
   - Add FormData support to apiClient (no Content-Type override).
   - Add 3 e2e specs: chat-tool-calling, dashboard-data, mission-execute.
   - Add unit tests: ToolCallCard, use-personal-memory.

   Gates: tsc --noEmit clean, 929 vitest tests pass, next build succeeds.
   ```
6. `git push origin master`

**Verification:**
```bash
git status --short | wc -l          # → 0
git log --oneline -1                 # → the commit above
```

### 0.2 Triage unmerged branches

13 branches exist (5 local + 8 remote). Most remote branches are 300+ commits
ahead and likely stale.

**Decision tree per branch:**
- If `< 5 commits ahead` and recent → review for merge
- If `> 100 commits ahead` → check `git log --since='14 days ago'`; if empty, delete as stale
- If the branch name matches a shipped feature → delete

**Action:**
```bash
# Check which remote branches have recent activity
for b in agent/20260622-5c0022/fix-deletion-guard-justify-check \
         drop-audio-features drop-audio-features-v2 drop-audio-frontend-cleanup \
         feat/cli-v0.1-audit-fixes fix/pr-check-pytest-blockers \
         perf/health-endpoint-lightweight wt/w1-t4-cleanup; do
  echo "=== $b ==="
  git log origin/$b --since='30 days ago' --oneline | wc -l
done
```

- [ ] Delete stale remote branches (the ones with 0 recent commits)
- [ ] Review `feat/brand-strings-mission-renaming` and `feat/nav-automations` — these are local, 1 commit each, may be worth merging or rebasing

---

## Phase 1: Zero-risk cleanup (no logic changes)

### 1.1 Delete 6 orphan ghost routes

**Why:** These render only "Coming soon." The real pages exist in the
`(dashboard)` route group and the nav points there. Ghosts confuse the route
map and pollute the build.

**Files to delete:**
```
src/app/[locale]/dashboard/build/page.tsx
src/app/[locale]/dashboard/run/page.tsx
src/app/[locale]/dashboard/market/page.tsx
src/app/[locale]/dashboard/market/create-listing/page.tsx
src/app/[locale]/dashboard/market/my-installed/page.tsx
src/app/[locale]/dashboard/market/my-listings/page.tsx
src/app/[locale]/dashboard/tools/page.tsx
src/app/[locale]/dashboard/tools/hub/page.tsx
src/app/[locale]/dashboard/tools/memory-inspector/page.tsx
```

**Steps:**
1. `git rm -r src/app/[locale]/dashboard/build src/app/[locale]/dashboard/run src/app/[locale]/dashboard/market src/app/[locale]/dashboard/tools`
2. `pnpm build` → confirm no broken links
3. `npx tsx scripts/validate-nav-routes.ts` → confirm nav still valid
4. Commit: `refactor: delete 6 orphan dashboard ghost routes (build, run, market, tools)`

**Keep:** `/dashboard/{page,swarm,programs,evaluation,settings}` — those are real and wired.

### 1.2 Add 2 missing i18n keys to all locales

**Keys:** `settings.toolPermissions`, `settings.toolPermissionsDesc`

**Steps:**
1. For each locale file (`fr.json`, `de.json`, `es.json`, `ja.json`), add to the `settings` section:
   ```json
   "toolPermissions": "<translated 'Tool Permissions'>",
   "toolPermissionsDesc": "<translated 'Control which tools the AI assistant can use in this workspace'>"
   ```
2. EN values for reference:
   - `toolPermissions`: `"Tool Permissions"`
   - `toolPermissionsDesc`: `"Control which tools the AI assistant can use in this workspace"`
3. Commit: `i18n: add settings.toolPermissions keys to all 5 locales`

---

## Phase 2: User-facing fixes (revenue + core feature)

### 2.1 Wire contact form to backend (SILENTLY DROPS MESSAGES)

**Current:** `src/app/[locale]/contact/page-client.tsx:24` — `handleSubmit`
calls `setSubmitted(true)` without sending data. Every contact form submission
is lost.

**Backend task:**
1. Create `backend/app/api/v2/contact.py`:
   ```python
   from fastapi import APIRouter, Depends
   from pydantic import BaseModel, EmailStr
   from app.api.deps import get_current_user_optional  # public endpoint
   from app.api.v2.base import ok

   router = APIRouter(prefix="/contact", tags=["v2-contact"])

   class ContactSubmission(BaseModel):
       name: str
       email: EmailStr
       company: str | None = None
       message: str

   @router.post("")
   async def submit_contact(payload: ContactSubmission):
       # Store in DB
       # Fire Slack/ntfy alert via services/alerting.py
       return ok({"status": "received"})
   ```
2. Create `backend/app/models/contact.py` — `ContactSubmission` ORM model
3. Create Alembic migration for `contact_submissions` table
4. Mount router in `backend/app/api/v2/__init__.py`
5. Wire alert: call `alerting.send_alert()` on submission

**Frontend task:**
1. In `contact/page-client.tsx`, replace `handleSubmit`:
   ```ts
   async function handleSubmit(e: React.FormEvent) {
     e.preventDefault();
     setSubmitting(true);
     try {
       await apiClient.post("/api/v2/contact", form);
       setSubmitted(true);
     } catch (err) {
       toast.error("Failed to send message. Please try again.");
     } finally {
       setSubmitting(false);
     }
   }
   ```
2. Add `submitting` state + disable button while loading

**Verification:**
```bash
# Backend
curl -X POST http://127.0.0.1:8000/api/v2/contact \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@test.com","message":"Hello"}'
# → 201, {"data":{"status":"received"},...}

# Frontend
pnpm typecheck && pnpm test
```

### 2.2 Implement `fire_program` (unblocks Automations feature)

**Current:** `backend/app/api/_program_cqrs/commands.py:107` — `fire_program`
catches `NotImplementedError` → returns 501. The `/dashboard/programs` page
exists, nav entry exists, but the "Run" button 501s.

**Backend task:**
1. Read `backend/app/services/mission_program_service.py` — find the
   `fire_program` method that raises `NotImplementedError`
2. Implement it:
   - Build a `Workflow` from the program definition using
     `substrate.adapters` (see how `mission_to_workflow` works)
   - Call `UnifiedExecutor.execute(session, workflow)`
   - Create a `ProgramRun` row tracking the execution
   - Return `ProgramRunResponse`
3. Also implement `consolidate_learning` (T9):
   - Query recent `ProgramRun` rows for the program
   - Summarize outputs via LLM
   - Store as `LearningBrief`
4. Remove the `try/except NotImplementedError` wrappers in
   `_program_cqrs/commands.py:119-124` and `:161-165`

**Verification:**
```bash
# Should return 200, not 501
curl -X POST http://127.0.0.1:8000/api/v2/programs/{id}/fire \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: test-$(date +%s)"
# → 200, {"data":{"run_id":"...","status":"running",...}}

docker compose exec backend pytest app/tests/test_program_cqrs.py -v
```

### 2.3 Implement 3 mission analytics methods (empty dashboard charts)

**Current:** `backend/app/services/mission_analytics.py:54-62` — three
methods return `[]` unconditionally. They feed `GET /api/v2/missions/{id}/analytics`.

**Backend task:**
1. `get_mission_analytics_over_time(db, user_id, days=30)`:
   ```python
   # Group missions by day, return timeseries
   # SELECT DATE(created_at), COUNT(*), AVG(status='completed')
   # FROM missions WHERE created_at > now() - interval 'N days'
   # GROUP BY 1 ORDER BY 1
   ```
2. `get_failure_analysis(db, user_id)`:
   ```python
   # Query failed missions, group by failure reason / task type
   # Return [{"category": "LLM timeout", "count": 3, "examples": [...]}]
   ```
3. `get_token_usage_breakdown(db, user_id)`:
   ```python
   # SELECT model, SUM(total_tokens), SUM(cost)
   # FROM llm_call_records WHERE user_id = ?
   # GROUP BY model ORDER BY SUM(total_tokens) DESC
   ```

**Verification:**
```bash
curl http://127.0.0.1:8000/api/v2/missions/{id}/analytics \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# → "over_time", "token_usage", "failure_analysis" arrays should be populated
# (or empty if no data, but NOT hardcoded [])
```

### 2.4 Fix dashboard `total_tokens` = 0

**Current:** `backend/app/main_fastapi.py:482`:
```python
"total_tokens": 0,  # TODO: aggregate from LLMCallRecord table
```

**Fix:** Replace `0` with:
```python
"total_tokens": (
    await db.execute(
        select(func.coalesce(func.sum(LLMCallRecord.total_tokens), 0))
    )
).scalar() or 0,
```

**Verification:**
```bash
curl http://127.0.0.1:8000/api/dashboard  # or wherever this endpoint is
# → total_tokens should be a real number, not 0
```

---

## Phase 3: Feature completion

### 3.1 Canvas `file-diff` tile

**Current:** `src/components/chat/Canvas.tsx:54-67` — renders "coming soon" stub.

**Task:**
1. Create `src/components/chat/tiles/FileDiffTile.tsx`
2. Fetch diff data from the sandbox API (check what endpoint produces diffs)
3. Render using `react-diff-viewer-continued` (check if installed, else `pnpm add`)
4. Wire into the `file-diff` case in `Canvas.tsx:182`

### 3.2 Marketplace uninstall

**Current:** `backend/app/api/v2/marketplace.py:231` — returns 501.

**Task:**
1. Add `async def uninstall(cls, user_id, listing_id)` to `MarketplaceService`
2. Delete the `MarketplaceInstall` row
3. Revoke capabilities via `CapabilityEngine`
4. Replace the 501 with `return ok(await service.uninstall(...))`

### 3.3 Canvas `mission_status` tile

**Task:**
1. Create `src/components/chat/tiles/MissionStatusTile.tsx`
2. Call `GET /api/v2/missions/{id}/status`
3. Render compact status card (reuse `MissionStatusBadge`)
4. Wire into the `mission_status` case in `Canvas.tsx:182`

### 3.4 Implement `consolidate_learning` (companion to 2.2)

Covered in task 2.2 — implement alongside `fire_program`.

---

## Phase 4: i18n + polish

### 4.1 Translate `services.*` section for DE / ES / JA (63 keys each)

The homepage consulting section (`src/app/[locale]/page-client.tsx:74`) uses
`useTranslations("services")`. EN and FR have 63 keys. DE/ES/JA have 0.

**Task:**
1. Copy the `services` object from `en.json`
2. For each locale (`de`, `es`, `ja`), translate all 63 values
3. Add the translated object to the locale file

### 4.2 Review unreachable routes

14 routes exist with real content but no nav entry. Decide for each: add to
nav, link from a parent page, or leave as programmatic-only.

Routes to review: `/analytics`, `/circuit-breaker`, `/critiques`, `/feedback`,
`/files`, `/triggers`, `/developer` (vs `/developers`), `/mission-dashboard`
(vs `/missions`), `/topology` (vs `/tools/topology`).

### 4.3 Twilio HMAC verification (security)

**Current:** `backend/app/api/v1/integration_webhooks.py:154` — checks header
presence only.

**Task:**
1. Pass the request URL through to `_verify_twilio()`
2. Implement full HMAC-SHA1: `base64.b64encode(hmac.new(secret, url + sorted_form_params, sha1))`
3. Compare with `hmac.compare_digest()`

### 4.4 Canvas `image-gen` tile

Same pattern as 3.1/3.3 — create tile component, wire into switch case.

---

## Phase 5: Deferred (on-demand)

- [ ] Slack file upload multipart (`slack_connector.py:437`)
- [ ] Email + PagerDuty alert channels (`alerting.py`)
- [ ] Team presence REST migration
- [ ] v2 `node_states` + `/runs/{id}/resume`
- [ ] Integration webhooks → external_events bus
- [ ] Celery task revival (6 files, per-feature when needed)
- [ ] Tool deny-list integration (`tool_router.py:480`)
- [ ] Tool discovery service (`unified_tool_bridge.py:185`)
- [ ] PII deny-list runtime config (`episodic_memory_service.py:65`)

---

## 6. Verification gates (run after each phase)

### Frontend
```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit                    # 0 errors
npx vitest run                      # all pass
npx next build                      # succeeds
```

### Backend
```bash
cd /opt/flowmanner
docker compose exec backend pytest app/tests/ -q --tb=no 2>&1 | tail -5
curl http://127.0.0.1:8000/api/health
```

### i18n
```bash
cd /home/glenn/FlowmannerV2-frontend
python3 -c "
import json
en = json.load(open('src/i18n/locales/en.json'))
def keys(x,p=''):
    r=set()
    for k,v in x.items():
        f=f'{p}.{k}' if p else k
        r.update(keys(v,f) if isinstance(v,dict) else {f})
    return r
en_keys = keys(en)
for lang in ['fr','de','es','ja']:
    d = json.load(open(f'src/i18n/locales/{lang}.json'))
    miss = en_keys - keys(d)
    print(f'{lang}: {len(miss)} missing')
"
```

---

## 7. DEEPSEEK PROMPT (copy-paste verbatim)

> The prompt below is self-contained. DeepSeek should paste it as its first
> message. It covers Phases 0–4. Phase 5 is deferred.

````
You are working on FlowManner, a FastAPI + Next.js AI workflow platform.

## Environment
- Machine: Homelab (172.16.1.1 / 10.99.0.3)
- Backend: /opt/flowmanner/backend/ (FastAPI, Python 3.11, Docker)
- Frontend: /home/glenn/FlowmannerV2-frontend/ (Next.js 15, TypeScript, pnpm)
- Git: backend on `main`, frontend on `master`
- Full audit: /opt/flowmanner/docs/STUB-DEEPDIVE-CHECKLIST-2026-07-06.md

## CRITICAL RULES (READ FIRST)

1. **Read AGENTS.md + backend/AGENTS.md before touching any file.**
2. **IMPLEMENT code changes. Do NOT write meta-docs, handoff docs, or analysis.**
3. **After every change, run the verification commands. Paste the output.**
4. **If tsc --noEmit or pytest fails, FIX IT before the next task.**
5. **One commit per logical change. Clear commit messages.**
6. **Amend plans, don't rewrite. If a plan doc exists, update it in place.**
7. **Verify on host: curl endpoints, run tests. Never claim done without output.**
8. **Never deploy. Edit source only. Rebuilds are done by the human.**
9. **French-first for public content (fr.json is primary).**
10. **Follow the migration convention: never DELETE rows. Use UPDATE + sentinel.**

## GATES (run after each task — all must pass)

Frontend:
  cd /home/glenn/FlowmannerV2-frontend
  npx tsc --noEmit         # 0 errors
  npx vitest run           # all pass
  npx next build           # succeeds

Backend:
  cd /opt/flowmanner
  docker compose exec -T backend pytest app/tests/ -q --tb=no

i18n:
  python3 -c "
  import json
  en = json.load(open('/home/glenn/FlowmannerV2-frontend/src/i18n/locales/en.json'))
  def keys(x,p=''):
      r=set()
      for k,v in x.items():
          f=f'{p}.{k}' if p else k
          r.update(keys(v,f) if isinstance(v,dict) else {f})
      return r
  en_keys = keys(en)
  for lang in ['fr','de','es','ja']:
      d = json.load(open(f'/home/glenn/FlowmannerV2-frontend/src/i18n/locales/{lang}.json'))
      miss = en_keys - keys(d)
      if miss: print(f'{lang}: {len(miss)} missing')
      else: print(f'{lang}: OK')
  "

---

## PHASE 0: SAVE STATE (do this FIRST, before anything else)

### Task 0.1: Commit the 61 dirty frontend files

The frontend has 61 uncommitted files (54 modified + 7 untracked). This is a
coherent refactor: a new serverFetch helper, hook rewrites, sandbox preview
rework. Gates are GREEN (929 tests pass, tsc clean, build succeeds).

Steps:
1. cd /home/glenn/FlowmannerV2-frontend
2. git diff --stat | tail -5    # confirm ~54 files, +1238/-1584
3. git add -u                   # stage tracked changes
4. git add src/lib/server-fetch.ts src/components/chat/ToolCallCard.test.tsx \
         src/hooks/__tests__/use-personal-memory.test.tsx \
         e2e/chat-tool-calling.spec.ts e2e/dashboard-data.spec.ts \
         e2e/mission-execute.spec.ts plans/phase3-exit-audit-handoff.md
5. Commit with message:
   refactor: extract serverFetch helper + modernize data hooks

   - Add src/lib/server-fetch.ts: deduplicates auth() + fetch(BACKEND_URL)
   - Migrate 6 onboarding API routes to serverFetch
   - Rewrite use-programs, use-personal-memory, use-critiques hooks
   - Rework SandboxPreviewButton (+199 LOC)
   - Clean up ThreadSidebar and ToolActivityFeed
   - Add FormData support to apiClient
   - Add 3 e2e specs + 2 unit test files

   Gates: tsc clean, 929 vitest tests pass, next build succeeds.
6. git push origin master

Verify:
  git status --short | wc -l    # → 0
  git log --oneline -1          # → the commit

### Task 0.2: Triage stale remote branches

Run:
  for b in agent/20260622-5c0022/fix-deletion-guard-justify-check \
           drop-audio-features drop-audio-features-v2 drop-audio-frontend-cleanup \
           feat/cli-v0.1-audit-fixes fix/pr-check-pytest-blockers \
           perf/health-endpoint-lightweight wt/w1-t4-cleanup; do
    count=$(git log origin/$b --since='30 days ago' --oneline 2>/dev/null | wc -l)
    echo "$b: $count recent commits"
  done

For any branch with 0 recent commits AND > 50 commits ahead of master:
  git push origin --delete <branch>
(Do NOT delete feat/brand-strings-mission-renaming or feat/nav-automations —
those are local and may be active.)

---

## PHASE 1: ZERO-RISK CLEANUP

### Task 1.1: Delete 6 orphan ghost routes

These render only "Coming soon." The real pages exist in the (dashboard)
route group and the nav points there.

  git rm -r src/app/[locale]/dashboard/build
  git rm -r src/app/[locale]/dashboard/run
  git rm -r src/app/[locale]/dashboard/market
  git rm -r src/app/[locale]/dashboard/tools

KEEP: src/app/[locale]/dashboard/{page,swarm,programs,evaluation,settings}*

Verify:
  npx next build                              # no broken links
  npx tsx scripts/validate-nav-routes.ts      # nav still valid

Commit: refactor: delete 6 orphan dashboard ghost routes (build, run, market, tools)

### Task 1.2: Add 2 missing i18n keys to all locales

In each of fr.json, de.json, es.json, ja.json, add to the "settings" section:
  "toolPermissions": "<translate 'Tool Permissions'>"
  "toolPermissionsDesc": "<translate 'Control which tools the AI assistant can use in this workspace'>"

Run the i18n gate (above). It should show 0 missing for all locales.

Commit: i18n: add settings.toolPermissions keys to all 5 locales

---

## PHASE 2: USER-FACING FIXES

### Task 2.1: Wire contact form to backend

CURRENT: src/app/[locale]/contact/page-client.tsx:24
  handleSubmit calls setSubmitted(true) WITHOUT sending data.
  Every contact form submission is silently lost.

BACKEND:
1. Create backend/app/models/contact.py — ContactSubmission ORM model:
   id (UUID), name (str), email (str), company (str|None), message (str),
   created_at (datetime), status (str default "new")
2. Create Alembic migration: alembic revision --autogenerate -m "add contact_submissions"
   - Review the generated migration
   - docker compose exec backend alembic upgrade head
3. Create backend/app/api/v2/contact.py:
   - POST /api/v2/contact (no auth — public)
   - Pydantic schema: ContactSubmissionCreate (name, email, company?, message)
   - Store in DB, fire alert via app.services.alerting.send_alert()
   - Return ok({"status": "received"})
4. Mount in backend/app/api/v2/__init__.py

FRONTEND:
1. In src/app/[locale]/contact/page-client.tsx, replace handleSubmit:
   - Add `submitting` state
   - await apiClient.post("/api/v2/contact", form)
   - setSubmitted(true) on success
   - toast.error on failure
   - Disable button while submitting

Verify:
  curl -X POST http://127.0.0.1:8000/api/v2/contact \
    -H "Content-Type: application/json" \
    -d '{"name":"Test","email":"test@test.com","message":"Hello"}'
  # → 200 or 201

Commit: feat: wire contact form to backend POST /api/v2/contact

### Task 2.2: Implement fire_program + consolidate_learning

CURRENT: backend/app/api/_program_cqrs/commands.py:107-175
  Both methods catch NotImplementedError and return 501.
  This blocks the entire Automations feature (/dashboard/programs "Run" button).

STEPS:
1. Read backend/app/services/mission_program_service.py — find the
   fire_program and consolidate_learning methods that raise NotImplementedError
2. Read backend/app/services/substrate/adapters.py — understand mission_to_workflow
3. Read backend/app/services/substrate/executor.py — understand UnifiedExecutor.execute()

Implement fire_program:
  - Convert the program definition to a Workflow via substrate adapters
  - Call UnifiedExecutor.execute(session, workflow)
  - Create a ProgramRun row tracking the result
  - Return ProgramRunResponse

Implement consolidate_learning:
  - Query recent ProgramRun rows for the program (limit configurable)
  - Summarize the outputs via an LLM call (use BudgetEnforcer.call())
  - Store the summary as a LearningBrief row
  - Return ConsolidateResponse

Remove the try/except NotImplementedError wrappers in
_program_cqrs/commands.py lines 119-124 and 161-165.

Verify:
  # Should be 200, NOT 501
  curl -X POST http://127.0.0.1:8000/api/v2/programs/{id}/fire \
    -H "Authorization: Bearer $TOKEN" \
    -H "Idempotency-Key: test-$(date +%s)"

  docker compose exec backend pytest app/tests/ -k "program" -v

Commit: feat: implement fire_program + consolidate_learning (closes Automations 501)

### Task 2.3: Implement 3 mission analytics methods

CURRENT: backend/app/services/mission_analytics.py:54-62
  get_mission_analytics_over_time → return []
  get_failure_analysis → return []
  get_token_usage_breakdown → return []
  These feed GET /api/v2/missions/{id}/analytics. Dashboard charts are empty.

Implement each with real SQL queries (see plan Section 2.3 for SQL sketches):
  1. get_mission_analytics_over_time: GROUP BY DATE(created_at) over last N days
  2. get_failure_analysis: query failed missions, GROUP BY error category
  3. get_token_usage_breakdown: query llm_call_records, GROUP BY model

Verify:
  curl http://127.0.0.1:8000/api/v2/missions/{id}/analytics \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
  # over_time, token_usage, failure_analysis should be arrays (possibly empty
  # if no data, but not hardcoded [])

Commit: feat: implement mission analytics timeseries, failure analysis, token breakdown

### Task 2.4: Fix dashboard total_tokens = 0

CURRENT: backend/app/main_fastapi.py:482
  "total_tokens": 0,  # TODO: aggregate from LLMCallRecord table

Fix: replace 0 with a real SUM query against llm_call_records.
Read the file around line 482 to understand the context and what ORM models
are available (likely LLMCallRecord in app/models/).

Verify:
  curl http://127.0.0.1:8000/api/dashboard  # or the correct endpoint path
  # total_tokens should be a real number

Commit: fix: aggregate total_tokens from LLMCallRecord in dashboard stats

---

## PHASE 3: FEATURE COMPLETION

### Task 3.1: Canvas file-diff tile

CURRENT: src/components/chat/Canvas.tsx lines 54-67, 180-195
  The "file-diff" tile kind renders only "File diff viewer — coming soon."

STEPS:
1. Check if react-diff-viewer-continued is installed:
   grep "react-diff-viewer" package.json
   If not: pnpm add react-diff-viewer-continued
2. Create src/components/chat/tiles/FileDiffTile.tsx:
   - Accept a tile prop with payload containing the diff data or file path
   - Fetch the diff from the sandbox API (check what endpoint exists —
     grep for "diff" in backend/app/api/v1/sandbox*.py)
   - Render using DiffViewer
3. Wire into Canvas.tsx: replace the "file-diff" stub case (around line 182)
   with <FileDiffTile tile={tile} />

Verify:
  npx tsc --noEmit && npx vitest run

Commit: feat: implement Canvas file-diff tile

### Task 3.2: Marketplace uninstall

CURRENT: backend/app/api/v2/marketplace.py:231
  raise HTTPException(status_code=501, detail="Uninstall not yet implemented")

STEPS:
1. Read backend/app/services/marketplace_service.py
2. Add async def uninstall(cls, db, user_id, listing_id):
   - Delete the MarketplaceInstall row (or mark uninstalled)
   - Revoke capabilities if any were granted
3. Replace the 501 in v2/marketplace.py with:
   result = await service.uninstall(db, user.id, listing_id)
   return ok(result)

Verify:
  curl -X DELETE http://127.0.0.1:8000/api/v2/marketplace/listings/{id}/install \
    -H "Authorization: Bearer $TOKEN"
  # → 200, not 501

Commit: feat: implement marketplace listing uninstall

### Task 3.3: Canvas mission_status tile

Same pattern as 3.1:
1. Create src/components/chat/tiles/MissionStatusTile.tsx
2. Call GET /api/v2/missions/{id}/status (the mission_id comes from tile.payload)
3. Render a compact status card
4. Wire into Canvas.tsx mission_status case

Commit: feat: implement Canvas mission_status tile

---

## PHASE 4: i18n + POLISH

### Task 4.1: Translate services.* for DE / ES / JA

The homepage (src/app/[locale]/page-client.tsx line 74) uses
useTranslations("services"). EN has 63 keys. DE/ES/JA have 0.

Steps:
1. Read the "services" section from src/i18n/locales/en.json
2. For each of de.json, es.json, ja.json:
   - Add a "services" top-level key
   - Translate all 63 values into the target language
   - Preserve the key names exactly
3. Run the i18n gate — all locales should show 0 missing

Commit: i18n: translate services.* section for DE, ES, JA (63 keys each)

### Task 4.2: Twilio HMAC verification (SECURITY)

CURRENT: backend/app/api/v1/integration_webhooks.py:154
  _verify_twilio checks header PRESENCE only, not validity.

STEPS:
1. Read the _verify_twilio function (around line 148)
2. Pass the request URL through to the function
3. Implement full HMAC-SHA1 per Twilio's spec:
   - signature = base64(hmac_sha1(secret, url + sorted_form_params))
   - Compare with hmac.compare_digest()

Verify:
  docker compose exec backend pytest app/tests/ -k "webhook" -v

Commit: fix: implement full Twilio HMAC-SHA1 webhook verification (security)

---

## WHEN YOU ARE DONE

After completing all tasks (or when stopping):

1. Run ALL gates one final time. Paste output.
2. Run: git status --short (should be clean in both repos)
3. Run: git log --oneline -10 (show the commits you made)
4. Push both repos: git push origin main (backend), git push origin master (frontend)
5. Write a brief summary: what you did, what you skipped, what needs human review.

## STOP CONDITIONS

- If a task takes > 2 hours, stop and document where you are.
- If you break the test suite and can't fix it in 3 attempts, stop and ask.
- If you're unsure about a design decision, document the question and move on.
- Do NOT attempt Phase 5 (deferred items) without explicit instruction.
````

---

## Appendix: File reference table

| Item | File | Lines |
|------|------|-------|
| Orphan ghosts | `src/app/[locale]/dashboard/{build,run,market,tools}/` | — |
| Contact form | `src/app/[locale]/contact/page-client.tsx` | 24 |
| fire_program 501 | `backend/app/api/_program_cqrs/commands.py` | 107-175 |
| Marketplace 501 | `backend/app/api/v2/marketplace.py` | 231 |
| Analytics stubs | `backend/app/services/mission_analytics.py` | 54-62 |
| Dashboard tokens | `backend/app/main_fastapi.py` | 482 |
| Canvas stubs | `src/components/chat/Canvas.tsx` | 54-67, 180-195 |
| Twilio HMAC | `backend/app/api/v1/integration_webhooks.py` | 154 |
| i18n services | `src/app/[locale]/page-client.tsx` | 74 |
