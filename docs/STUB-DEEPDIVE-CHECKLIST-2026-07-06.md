# FlowManner — Deep-Dive Stub & Completion Audit (2026-07-06)

> **Purpose:** A tickable checklist of every unfinished, stubbed, broken, or
> missing piece across the entire FlowManner platform. Designed for sequential
> execution — you and DeepSeek work through it top to bottom, ticking each item.
>
> **Method:** 10-surface sweep of both source trees:
> 1. Every page LOC + data-fetch audit
> 2. Dashboard widget realness check
> 3. Component hardcoded/mock data scan
> 4. Backend empty/stub method scan
> 5. Unreachable/orphan route analysis
> 6. Backend router completeness
> 7. Disabled/hidden UI elements
> 8. i18n key coverage gaps
> 9. Git archaeology (uncommitted work + unmerged branches)
> 10. Source-grounded verification of every claim
>
> **Companion doc:** `STUB-STOCK-AUDIT-2026-07-06.md` (the first-pass audit).
> This deep-dive supersedes it with 3× more findings.
>
> **Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## 0. State of the world (verified 2026-07-06)

| Metric | Count |
|--------|-------|
| Total frontend routes | 113 |
| Total frontend pages | 154 |
| Backend endpoint modules (v1+v2+v3) | ~100 |
| Genuine stub surfaces found | **27** |
| Orphan/ghost routes | **6** |
| Backend methods returning empty (`[]`/`{}`) | **6** (3 genuine) |
| Backend 501 endpoints | **4** |
| Uncommitted frontend files (in-flight session) | **54** |
| Unmerged feature branches | **5 local + 8 remote** |
| i18n missing keys (DE/ES/JA) | **65 each** |
| i18n missing keys (FR) | **2** |

**Headline:** The site is ~90% built. The remaining 10% is spread across many
small surfaces — no single massive missing feature, but **27 items** that
collectively prevent the platform from feeling "finished." The biggest risks
are **uncommitted work loss** (54 dirty files), **unmerged branches** (some
300+ commits ahead), and **i18n gaps** that make 3 locales render raw English
keys on the homepage.

---

## 1. UNCOMMITTED WORK — save before anything else ⚠️ CRITICAL

The frontend has **54 dirty files** from an in-flight DeepSeek session. If
the session restarts or someone runs `git checkout .`, this work is gone.

### 1.1 Commit the dirty frontend work

- [ ] **Investigate the 54 dirty files** — what was DeepSeek doing?
  ```bash
  cd /home/glenn/FlowmannerV2-frontend
  git diff --stat | tail -40
  ```
  Key changes observed:
  - `SandboxPreviewButton.tsx` (+199 LOC) — major sandbox preview rework
  - `ThreadSidebar.tsx` (-112 LOC net) — sidebar cleanup
  - `ToolActivityFeed.tsx` (98 LOC changed) — tool feed refactor
  - `hooks/use-programs.ts` (302 LOC changed) — programs hook rewrite
  - `hooks/use-personal-memory.ts` (299 LOC changed) — memory hook rewrite
  - `hooks/use-critiques.ts` (95 LOC changed)
  - 6 onboarding API routes changed (auth pattern update?)
  - `lib/api-client.ts` (19 LOC) — core API client touched
  - `lib/oauth-api.ts` (77 LOC) — OAuth client rewritten

- [ ] **Decide: commit or stash?** Run `pnpm typecheck && pnpm test && pnpm build`. If green → commit. If broken → stash and triage.

- [ ] **Commit with a clear message** describing what the session accomplished.

### 1.2 Triage unmerged feature branches

Five feature branches exist locally + eight on remote. Some are 300+ commits
ahead — they may contain months of work OR be stale forks.

- [ ] **`feat/brand-strings-mission-renaming`** (1 commit ahead, 140 files, -22K LOC)
  - Renames G1-G7 workflow strings to "Mission"
  - **Large deletion count** — may delete useful code. Review diff carefully.

- [ ] **`feat/nav-automations`** (1 commit ahead, 140 files, -22K LOC)
  - Wires Programs into authed nav as "Automations" (#15)
  - Similar stat profile to above — may share base.

- [ ] **`remotes/origin/agent/20260622-5c0022/fix-deletion-guard-justify-check`** (312 commits ahead)
  - ⚠️ Huge. Almost certainly a stale branch from an old fork point.
  - Check: `git log origin/master..origin/agent/20260622-... --oneline | head` — if commits are old, delete.

- [ ] **`remotes/origin/drop-audio-features`** (285 commits ahead)
  - Audio feature removal. Likely already partially merged or obsolete.

- [ ] **`remotes/origin/feat/cli-v0.1-audit-fixes`** (311 commits ahead)
  - CLI audit fixes. Likely stale.

- [ ] **`remotes/origin/perf/health-endpoint-lightweight`** (313 commits ahead)
  - Health endpoint perf. Likely stale.

- [ ] **`remotes/origin/wt/w1-t4-cleanup`** (261 commits ahead)
  - Old worktree cleanup branch. Review per `flowmanner-source-grounded-plans` skill Example F.

- [ ] **Action:** For each remote branch, check if it's been merged or is stale:
  ```bash
  git log origin/master..origin/<branch> --oneline | tail -5  # see oldest commits
  git log origin/<branch> --since='30 days ago' --oneline | wc -l  # recent activity?
  ```
  Delete stale ones: `git push origin --delete <branch>`

---

## 2. ORPHAN GHOST ROUTES — delete (zero risk) ⚠️ HIGH

Six pages under `/[locale]/dashboard/*` render only `<h1> + "Coming soon."`.
The **real** pages live in the `(dashboard)` route group (parentheses = no
URL segment). The nav config points exclusively at the real routes.

### 2.1 Delete orphan ghost pages

- [ ] `git rm -r src/app/[locale]/dashboard/build/`
- [ ] `git rm -r src/app/[locale]/dashboard/run/`
- [ ] `git rm -r src/app/[locale]/dashboard/market/` (5 children: page, create-listing, my-installed, my-listings)
- [ ] `git rm -r src/app/[locale]/dashboard/tools/` (3 children: page, hub, memory-inspector)
- [ ] Verify: `pnpm build` — no broken links
- [ ] Verify: `npx tsx scripts/validate-nav-routes.ts`

**Why delete, not build:** The real equivalents (`/marketplace`, `/tools`,
`/memory-inspector`, `/runs`) are fully built and linked from the nav.
Building duplicate content at `/dashboard/build` creates two sources of truth.

---

## 3. FRONTEND — stubs & unfinished UI

### 3.1 Chat Canvas — 3 stub tiles ⚠️ MEDIUM

**File:** `src/components/chat/Canvas.tsx:54-67, 180-195`

The Canvas tile router has 3 tile kinds that render only a "coming soon"
placeholder instead of content. The tile *container* (drag, minimize, remove)
is fully wired; only the body is a stub.

| Tile kind | Stub message | Data source exists? |
|-----------|-------------|---------------------|
| `file-diff` | "File diff viewer — coming soon." | ✅ Sandbox produces diffs |
| `image-gen` | "Image generation — coming soon." | ✅ `image_generation` tool exists |
| `mission_status` | "Mission status — coming soon." | ✅ `/api/v2/missions/{id}/status` |

- [ ] **`file-diff` tile** — create `components/chat/tiles/FileDiffTile.tsx`.
  Fetch diff from sandbox API, render `<DiffEditor>` (Monaco or
  `react-diff-viewer`). Wire into `Canvas.tsx:182` switch case. ~150 LOC.
- [ ] **`image-gen` tile** — create `ImageGenTile.tsx`. Subscribe to chat
  message stream for `tool_image_generation` events, render image. ~100 LOC.
- [ ] **`mission_status` tile** — create `MissionStatusTile.tsx`. Call
  `GET /api/v2/missions/{id}/status`, render compact status card reusing
  `MissionStatusBadge`. ~120 LOC.

### 3.2 Contact form — silently drops messages ⚠️ HIGH

**File:** `src/app/[locale]/contact/page-client.tsx:24`

```ts
function handleSubmit(e: React.FormEvent) {
  e.preventDefault();
  // TODO: wire to backend
  setSubmitted(true);  // ← shows "thank you" without sending anything
}
```

- [ ] **Backend:** add `POST /api/v2/contact` to new `v2/contact.py` router
  (no auth — public). Create `contact_submissions` table + migration. Fire
  Slack/ntfy alert via `services/alerting.py`.
- [ ] **Frontend:** replace `setSubmitted(true)` with:
  ```ts
  await apiClient.post("/api/v2/contact", form);
  setSubmitted(true);
  ```
  Add loading state + error toast.

### 3.3 Chat Canvas — branching not wired ⚠️ LOW

**File:** `src/components/chat/Canvas.tsx:156`

```tsx
onBranchFromMessage={() => { /* TODO: Phase 3b — wire branching through Canvas props */ }}
```

- [ ] Wire `onBranchFromMessage` from `SSEChat` through `Canvas` props to
  the chat store's branching action. ~5 LOC once the store method exists.

### 3.4 Team management — presence uses WebSocket not REST ⚠️ LOW

**File:** `src/app/[locale]/(dashboard)/team/team-management-page-content.tsx:1367`

```ts
// TODO: Replace with workspace_presence API when backend ready
// Tracked in: github.com/glennguilloux/FlowmannerV2/issues/XXX
```

The WebSocket presence **works**. This is a "someday migrate" note.

- [ ] Optional: migrate to REST polling (`/api/v1/workspaces/.../presence`)
  when WebSocket scaling becomes an issue. Low priority.

### 3.5 Mission builder — 2 v2 API gaps ⚠️ LOW

**File:** `src/components/mission-builder/FlowEditor.tsx:1346, 1387`

- [ ] **v2 `RunResponse.node_states`** — add the field to the v2 schema, or
  document that the events SSE is the source of truth and remove the TODO.
- [ ] **v2 `/runs/{id}/resume`** — add the endpoint to `v2/runs.py`. The
  FlowEditor currently calls v1 (`/api/graphs/{id}/resume/{exec_id}`) as
  fallback.

### 3.6 Dashboard — 3 analytics charts are empty ⚠️ MEDIUM

**Root cause:** `services/mission_analytics.py:54-62` — three methods return
`[]` unconditionally:

```python
async def get_mission_analytics_over_time(...) -> list:
    return []  # ← stub

async def get_failure_analysis(...) -> list:
    return []  # ← stub

async def get_token_usage_breakdown(...) -> list:
    return []  # ← stub
```

These feed `GET /api/v2/missions/{id}/analytics` via
`_mission_cqrs/queries.py:563-565`. The dashboard's "over time", "token
usage", and "failure analysis" charts will always be empty.

- [ ] **`get_mission_analytics_over_time`** — implement timeseries query
  grouping missions by day over the last N days. Return
  `[{"date": "2026-07-01", "missions": 5, "success_rate": 0.8}, ...]`.
- [ ] **`get_failure_analysis`** — query failed missions, group by error
  type or task type. Return `[{"category": "LLM timeout", "count": 3}, ...]`.
- [ ] **`get_token_usage_breakdown`** — query `LLMCallRecord` grouped by
  model/provider. Return `[{"model": "deepseek-chat", "tokens": 50000, ...}]`.
- [ ] Verify: `GET /api/v2/missions/{id}/analytics` returns populated arrays.

---

## 4. BACKEND — stubs & unfinished endpoints

### 4.1 Program CQRS — `fire_program` + `consolidate` → 501 ⚠️ HIGH

**File:** `app/api/_program_cqrs/commands.py:107-175`

Two command handlers catch `NotImplementedError` and return 501:

| Command | Status | Blocks |
|---------|--------|--------|
| `fire_program` | 501 | Automations "Run" button |
| `consolidate` | 501 | Learning brief generation |

- [ ] **Implement `fire_program()`** in `mission_program_service.py` —
  delegate to `UnifiedExecutor.execute()` with a `Workflow` built from the
  program definition (use `substrate.adapters`).
- [ ] **Implement `consolidate_learning()`** — query recent `ProgramRun`
  rows, summarize via LLM, store as `LearningBrief`.
- [ ] Remove `try/except NotImplementedError` wrappers in
  `_program_cqrs/commands.py`.
- [ ] **This unblocks the entire Automations feature.** Frontend at
  `/dashboard/programs` exists, nav entry exists, only the run trigger 501s.

### 4.2 Marketplace uninstall → 501 ⚠️ LOW

**File:** `app/api/v2/marketplace.py:222-231`

```python
raise HTTPException(status_code=501, detail="Uninstall not yet implemented")
```

- [ ] Add `async def uninstall()` to `services/marketplace_service.py` —
  delete `MarketplaceInstall` row, revoke capabilities.
- [ ] Replace 501 with `return ok(await service.uninstall(...))`.

### 4.3 Slack file upload → 501 ⚠️ LOW

**File:** `app/services/connectors/slack_connector.py:437`

- [ ] Implement multipart upload via `aiohttp.FormData` or `httpx`
  multipart. ~30 LOC.

### 4.4 Twilio HMAC verification incomplete ⚠️ LOW (security)

**File:** `app/api/v1/integration_webhooks.py:154`

`_verify_twilio()` checks header **presence**, not **validity**.

- [ ] Pass request URL to `_verify_twilio()`, implement full HMAC-SHA1
  per Twilio spec. ~15 LOC. **Anyone can POST fake Twilio webhooks today.**

### 4.5 Dashboard `total_tokens` always 0 ⚠️ LOW

**File:** `app/main_fastapi.py:482`

```python
"total_tokens": 0,  # TODO: aggregate from LLMCallRecord table
```

- [ ] Replace `0` with `SELECT SUM(total_tokens) FROM llm_call_records`.
  ~5 LOC.

### 4.6 Alerting — email + pagerduty channels are placeholders ⚠️ LOW

**File:** `app/services/alerting.py:6-7` (docstring)

Webhook + ntfy are ✅ implemented. Email + pagerduty are ❌ placeholders.

- [ ] **Email:** implement `_send_email()` using `smtplib` (already
  imported). Wire to SMTP settings.
- [ ] **PagerDuty:** implement `_send_pagerduty()` using Events API v2.

### 4.7 Integration webhooks — inbound events not forwarded ⚠️ LOW

**File:** `app/api/v1/integration_webhooks.py:460`

```python
# TODO: Route to external_events durable bus when integration is wired
```

Inbound webhooks log + ack but don't forward to the external events bus.

- [ ] Wire the inbound webhook handler to dispatch events to the
  `external_events` durable bus.

### 4.8 Other backend TODOs (informational — defer)

| File:line | TODO | Impact |
|-----------|------|--------|
| `tool_router.py:480` | Integrate workspace/user permission deny-list | Tool scoring always 1.0 |
| `unified_tool_bridge.py:185` | Discovery service integration placeholder | Returns all tools, not filtered |
| `episodic_memory_service.py:65` | PII deny-list placeholder | Empty deny-list |
| `langgraph/auth_fastapi.py:286` | Deprecated auth decorator stub | No routes use it (all migrated) |
| `langfuse_service.py:79` | `_LangfuseUnavailable` stub class | ✅ Intentional graceful degradation |

---

## 5. CELERY TASK STUBS — intentionally disabled ✅ NOT STUBS

**Files:** `app/tasks/{base_task,deepagents_tasks,langgraph_tasks,task_definitions,webhook_dispatcher,webhook_tasks}.py`

Disabled 2026-06-12 with detailed revival checklists. Not regressions.

- [ ] **DEFERRED** — revive only when the corresponding feature is needed.
  Each file has a thorough checklist of what models/migrations/imports to
  create. The substrate executor handles workflow execution without Celery.
  See `STUB-STOCK-AUDIT-2026-07-06.md §3.6` for per-file revival steps.

---

## 6. i18n GAPS — raw keys rendering ⚠️ MEDIUM

### 6.1 DE / ES / JA missing entire `services.*` section

The homepage (`src/app/[locale]/page-client.tsx:74`) uses
`useTranslations("services")` for the consulting services section.

**EN/FR:** 63 keys ✅
**DE/ES/JA:** 0 keys ❌ — the entire services section renders as raw
`services.heroTitle1` etc.

- [ ] **DE:** Translate 63 `services.*` keys from EN → DE.
- [ ] **ES:** Translate 63 `services.*` keys from EN → ES.
- [ ] **JA:** Translate 63 `services.*` keys from EN → JA.

### 6.2 All locales missing `settings.toolPermissions` (2 keys)

Added by Phase 5 (ToolAllowlist) but not translated.

- [ ] **FR:** Add `settings.toolPermissions` + `settings.toolPermissionsDesc`.
- [ ] **DE:** Add both keys.
- [ ] **ES:** Add both keys.
- [ ] **JA:** Add both keys.

### 6.3 Translation workflow fix

- [ ] Add a pre-commit or CI check that compares key sets across all 5
  locales and fails if any locale is missing keys present in EN.

---

## 7. NAVIGATION — routes reachable but not in nav ⚠️ LOW

These routes exist, work, and have real content — but have **no nav entry**.
Users can only reach them by direct URL. Consider whether each should be
linked or is intentionally hidden (reached programmatically).

| Route | Has real content? | Should it be in nav? |
|-------|-------------------|---------------------|
| `/analytics` | ✅ (real component) | ✓ Add to nav? |
| `/browser` | ✅ (redirects to tools/browser?) | Consider deleting (duplicate) |
| `/circuit-breaker` | ✅ (294 LOC client) | ✓ Add to nav or merge with reliability |
| `/critiques` | ✅ (real component) | ✓ Add to nav? |
| `/developer` | ✅ (369 LOC) | Confusing vs `/developers` — pick one |
| `/feedback` | ✅ (200 LOC client) | ✓ Add to nav? |
| `/files` | ✅ (1125 LOC content) | ✓ Add to nav? |
| `/mission-dashboard` | ✅ (547 LOC client) | Old route? Superseded by `/missions`? |
| `/missions/node-groups` | ✅ (291 LOC client) | Sub-page — link from missions page? |
| `/nps` | ✅ (195 LOC client) | Admin-only? |
| `/onboarding` | ✅ (191 LOC client) | Shown programmatically after signup — OK |
| `/status` | ✅ (status page) | Link from footer? |
| `/topology` | ✅ (158 LOC client) | Duplicate of `/tools/topology`? |
| `/triggers` | ✅ (34 LOC client) | ✓ Add to nav? |

- [ ] **Review each route:** decide if it should be linked, deleted, or left
  as programmatic-only. Document the decision in nav-config.ts comments.

---

## 8. PRODUCTION READINESS CHECKS

### 8.1 Verify sandbox preview (recent fix area)

The last 5 commits were sandbox preview port fixes. Verify the fix is live:

- [ ] `curl -s https://flowmanner.com/api/sandbox/preview/{id}` returns 200
- [ ] Open a chat, launch sandbox, preview iframe loads
- [ ] Check `SANDBOXD_PREVIEW_PORT` is set correctly in both backend + sandbox

### 8.2 Verify dirty frontend files don't break production

- [ ] `pnpm typecheck` — 0 errors
- [ ] `pnpm test` — all pass
- [ ] `pnpm build` — succeeds

### 8.3 Backend health

- [ ] `curl http://127.0.0.1:8000/api/health` → 200
- [ ] `docker compose exec backend alembic current` → head
- [ ] `docker compose exec backend pytest app/tests/ -q` → 0 failures

---

## 9. PRIORITY ORDER — work top to bottom

### Phase 0: Save state (CRITICAL — do first)

1. `[1.1]` Commit the 54 dirty frontend files
2. `[1.2]` Triage unmerged branches (delete stale, review active)

### Phase 1: Zero-risk cleanup

3. `[2.1]` Delete 6 orphan ghost routes
4. `[6.2]` Add 2 missing settings keys to all 5 locales

### Phase 2: User-facing fixes

5. `[3.2]` Wire contact form to backend (revenue impact)
6. `[4.1]` Implement `fire_program` (unblocks Automations)
7. `[3.6]` Implement 3 mission analytics methods (empty dashboard charts)
8. `[4.5]` Fix dashboard `total_tokens` = 0

### Phase 3: Feature completion

9. `[3.1]` Canvas `file-diff` tile
10. `[4.2]` Marketplace uninstall
11. `[3.1]` Canvas `mission_status` tile
12. `[4.1]` Implement `consolidate_learning`

### Phase 4: i18n + polish

13. `[6.1]` Translate `services.*` for DE/ES/JA (63 keys × 3)
14. `[7]` Review unreachable routes — add nav entries or delete
15. `[4.4]` Twilio HMAC verification (security)
16. `[3.1]` Canvas `image-gen` tile

### Phase 5: Deferred

17. `[4.3]` Slack file upload
18. `[4.6]` Email + PagerDuty alert channels
19. `[3.4]` Team presence REST migration
20. `[3.5]` v2 `node_states` + `/runs/{id}/resume`
21. `[4.7]` Integration webhooks → external_events bus
22. `[4.8]` Other backend TODOs (deny-list, discovery service, etc.)
23. `[5]` Celery task revival (per-feature when needed)

---

## 10. DeepSeek prompt template

For each item above, use this prompt structure with DeepSeek:

```
You are working on FlowManner, a FastAPI + Next.js platform.

Repository: /opt/flowmanner (backend) + /home/glenn/FlowmannerV2-frontend (frontend)
Read AGENTS.md, AGENTS.homelab.md, and backend/AGENTS.md first.

TASK: [item from checklist, e.g. "Implement fire_program in mission_program_service.py"]

CONTEXT:
- File: [path:lines]
- Current behavior: [what it does now]
- Expected behavior: [what it should do]
- Related files: [list]

RULES:
1. Implement, don't describe. Write the actual code.
2. Amend plans, don't rewrite. If a plan exists at .sisyphus/plans/, update it.
3. Verify on host: run curl/pytest/pnpm test and paste output.
4. French-first for public content (fr.json primary).
5. Never claim "done" without command output proving it.
6. Commit with a clear message and push.

VERIFICATION GATES:
- [specific commands to run]
- [expected output]
```

---

## Verification commands (re-run this audit)

```bash
# Frontend stub sweep
grep -rPni --include='*.tsx' --include='*.ts' \
  -e 'TODO' -e 'coming soon' -e 'not implemented' \
  /home/glenn/FlowmannerV2-frontend/src \
  | grep -v '.stories.' | grep -v 'placeholder='

# Backend stub sweep
grep -rPni --include='*.py' \
  -e 'TODO' -e 'not implemented' -e '501' \
  /opt/flowmanner/backend/app \
  | grep -vE 'Hardcoded|MessagesPlaceholder|sys.path|is_placeholder'

# i18n key diff
python3 -c "
import json
en = json.load(open('src/i18n/locales/en.json'))
for lang in ['fr','de','es','ja']:
    d = json.load(open(f'src/i18n/locales/{lang}.json'))
    def keys(x,p=''):
        r=set()
        for k,v in x.items():
            f=f'{p}.{k}' if p else k
            r.update(keys(v,f) if isinstance(v,dict) else {f})
        return r
    miss = keys(en) - keys(d)
    if miss: print(f'{lang}: {len(miss)} missing')
"

# Orphan route check
ls /home/glenn/FlowmannerV2-frontend/src/app/\[locale\]/dashboard/{build,run,market,tools}/ 2>/dev/null

# Uncommitted work check
git -C /home/glenn/FlowmannerV2-frontend status --short | wc -l
```
