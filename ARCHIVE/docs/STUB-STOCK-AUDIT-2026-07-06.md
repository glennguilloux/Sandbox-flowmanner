# FlowManner — Stub / Mock / Placeholder Audit (2026-07-06)

> **Method:** source-grounded sweep of both trees — frontend
> (`/home/glenn/FlowmannerV2-frontend/src`) and backend
> (`/opt/flowmanner/backend/app`). Every finding below was verified by reading
> the actual source, not by trusting prior audits. False positives (HTML
> `placeholder=` attributes, intentional `Hardcoded tuples` comments,
> `MessagesPlaceholder` imports, `_NoOpAudit` duck-typed fallbacks that are
> load-bearing by design) were filtered out.
>
> **Headline:** The site is ~95% built. There are **7 genuine stub surfaces**
> (3 frontend, 4 backend) and **6 dead orphan routes**. No mock data is
> shipping to production users. The biggest risk is **orphan route confusion**
> (`/dashboard/*` ghosts vs the real `/(dashboard)/*` pages), not missing
> features.

---

## 0. Already verified DONE — do NOT re-plan

These were flagged by initial grep but are **fully built** on source inspection.
Skip them in any future plan.

| Surface | Evidence |
|---------|----------|
| Reliability Center | `/(dashboard)/reliability/page-client.tsx` calls `GET /api/reliability` |
| Tool Routing Inspector | `/(dashboard)/tool-routing/page-client.tsx` (416 LOC) |
| Plugin Manager | `/(dashboard)/plugins/page-client.tsx` (1168 LOC) + `@/lib/plugins-api.ts` |
| Memory Inspector | `/(dashboard)/memory-inspector/page.tsx` → `MemoryInspector` component |
| Marketplace (real) | `/(dashboard)/marketplace/marketplace-page-content.tsx` full CRUD |
| All public marketing pages | `/about` (276 LOC), `/workflows` (426), `/pricing` (313), `/agents` (197), `/security` (89), `/careers` (285), `/blog` (252), `/changelog` (329), `/documentation` (270), `/api-reference` (409) — all complete, zero stubs |
| Differentiator tools (10) | `tools/differentiators.py` (1106 LOC) — all 10 implemented with real DB/Qdrant calls. **The file's docstring is stale** (says "returns a coming soon stub"); the code does not. |
| DevOps tools (github_actions, aws_s3, vercel, git_repo) | Each implements 6-7 real actions. The `"Action not implemented"` return is a default fallback for unknown action names, not a stub. |
| Alerting channels | `services/alerting.py` — webhook + ntfy fully implemented; only email/pagerduty are placeholder channels (see §3.4). |
| Substrate (H5.1) | GA. 7 strategies on 1 executor. Old executors still in tree but new code targets substrate. |
| Celery task stubs (6 files) | Intentionally disabled 2026-06-12 with revival checklists. Not regressions — see §3.6. |

---

## 1. Frontend stubs (by page / component)

### 1.1 `/(dashboard)` orphan "Coming soon" pages — **6 dead routes** ⚠️ HIGH

**What:** Six pages under `/[locale]/dashboard/*` render only `<h1> + "Coming
soon."`:

| Route | File |
|-------|------|
| `/dashboard/build` | `dashboard/build/page.tsx` (20 LOC) |
| `/dashboard/run` | `dashboard/run/page.tsx` (20 LOC) |
| `/dashboard/market` + 3 children | `dashboard/market/{page,create-listing,my-installed,my-listings}/page.tsx` (5 × ~20 LOC) |
| `/dashboard/tools` + 2 children | `dashboard/tools/{page,hub,memory-inspector}/page.tsx` (3 × ~20 LOC) |

**Current purpose:** Placeholder routes from an earlier nav structure.

**Intended final behavior:** None — these are **orphans**. The real pages
live in the `(dashboard)` route group (note the parentheses = route group,
no URL segment). The nav config (`nav-config.ts`) points exclusively at
the real routes:

| Nav says | Real route |
|----------|------------|
| `/marketplace` | `/(dashboard)/marketplace/page.tsx` ✓ |
| `/tools` | `/(dashboard)/...` via `/tools` top-level page ✓ |
| `/memory-inspector` | `/(dashboard)/memory-inspector/page.tsx` ✓ |
| `/runs` | `/(dashboard)/runs/page.tsx` ✓ |

**What's missing:** Nothing feature-wise. The orphan pages are reachable
only by direct URL (`/dashboard/build`) and confuse the route map. They
also pollute the build (8 extra static pages).

**Next steps (recommended: DELETE):**
1. `git rm -r src/app/[locale]/dashboard/build`
2. `git rm -r src/app/[locale]/dashboard/run`
3. `git rm -r src/app/[locale]/dashboard/market` (all 5 children)
4. `git rm -r src/app/[locale]/dashboard/tools` (all 3 children)
5. Keep `/dashboard/{page,swarm,programs,evaluation,settings}` — those are
   real and wired.
6. Verify: `pnpm build` — confirm no broken links; `npx tsx scripts/validate-nav-routes.ts`.

**Why not "finish" them:** The equivalent real pages already exist and are
linked from the nav. Building duplicate content at `/dashboard/build` would
create two sources of truth. The 6 orphan pages are cargo from a nav
restructure that left ghosts behind.

---

### 1.2 Chat Canvas — 3 stub tiles ⚠️ MEDIUM

**File:** `src/components/chat/Canvas.tsx:54-67, 180-195`

**What:** The Canvas tile router has 3 tile kinds that render a "coming soon"
placeholder instead of real content:

| Tile kind | Stub message |
|-----------|--------------|
| `file-diff` | `"File diff viewer — coming soon."` |
| `image-gen` | `"Image generation — coming soon."` |
| `mission_status` | `"Mission status — coming soon."` |

**Current purpose:** The Canvas (multi-pane chat workspace) supports 7 tile
kinds. 4 are implemented (`chat`, `code-sandbox`, `browser-sandbox`,
`agent-trace`); 3 are declared in `TILE_KIND_META` but render only an icon +
stub string.

**Intended final behavior:**
- `file-diff` — show a Monaco-style diff viewer when an agent edits files
  in the sandbox (the sandbox already produces diffs; this is a viewer).
- `image-gen` — show generated images inline (the backend has an
  `image_generation` tool path; this is the rendering surface).
- `mission_status` — show a live mission status panel (the
  `/missions/[id]/observatory` page already has this data; this is a
  compact tile version).

**What's missing:** The tile content components. The tile *container*
(header, drag, minimize, remove) is fully wired; only the body is a stub.

**Next steps (per tile):**
1. `file-diff` — create `components/chat/tiles/FileDiffTile.tsx` that
   fetches the diff from the sandbox API and renders a `<DiffEditor>` (Monaco
   or `react-diff-viewer`). Wire in `Canvas.tsx:182` switch case.
2. `image-gen` — create `ImageGenTile.tsx` that subscribes to the chat
   message stream for `tool_image_generation` events and renders the image.
3. `mission_status` — create `MissionStatusTile.tsx` that calls
   `GET /api/v2/missions/{id}/status` and renders a compact status card.
   Reuse the `MissionStatusBadge` component from the observatory page.

**Priority:** MEDIUM. The Canvas works without them (users just can't add
these 3 tile types productively). `file-diff` is the highest-value of the
three because the sandbox already produces the data.

---

### 1.3 Contact page — form not wired ⚠️ MEDIUM

**File:** `src/app/[locale]/contact/page-client.tsx:24`

**What:** `handleSubmit` calls `setSubmitted(true)` but never sends data
to the backend. The "thank you" success state shows regardless.

**Current purpose:** Public contact form (name, email, company, message).

**Intended final behavior:** POST to a backend endpoint that stores the
submission and optionally notifies via email/Slack.

**What's missing:**
- No backend endpoint exists for contact form ingestion (grep confirmed:
  no `/api/v1/contact` or `/api/v2/contact` router).
- No `apiClient.post()` call in the handler.

**Next steps:**
1. Backend: add `POST /api/v2/contact` to a new `v2/contact.py` router
   (no auth — public). Store in a `contact_submissions` table (new model +
   migration). Fire a Slack/ntfy alert via `services/alerting.py`.
2. Frontend: replace `setSubmitted(true)` with:
   ```ts
   await apiClient.post("/api/v2/contact", form);
   setSubmitted(true);
   ```
   Add loading + error states.

**Priority:** MEDIUM. The form currently silently drops every message.
This is a **customer-acquisition bug**, not just a stub.

---

### 1.4 Team management — presence uses WebSocket, not REST API ⚠️ LOW

**File:** `src/app/[locale]/(dashboard)/team/team-management-page-content.tsx:1367`

**What:** `// TODO: Replace with workspace_presence API when backend ready`

**Current purpose:** The team page shows online/offline presence via
WebSocket (`socket.emit("workspace:subscribe")`). The comment notes the
intended migration to a REST presence API.

**Reality:** The WebSocket presence **works** — this is a "someday migrate"
note, not a broken feature. The presence API (`/api/v1/workspaces/.../presence`)
exists but the frontend hasn't switched to polling it.

**Next steps:** None required. Optional: when the WebSocket presence causes
scaling issues, migrate to REST polling. Low priority.

---

### 1.5 Mission builder — 2 TODO comments ⚠️ LOW

**File:** `src/components/mission-builder/FlowEditor.tsx:1346, 1387`

**What:**
1. `// TODO: v2 RunResponse has no node_states field — visual node overlays
   // won't update during runs. Poll /runs/{id}/events to reconstruct if needed.`
2. `// TODO: migrate to v2 when resume endpoint is available (v2 has abort/retry but no resume)`

**Current purpose:** The FlowEditor runs workflows and polls for status.

**Reality:** Both are **v2 API gaps**, not frontend bugs:
- The v2 `/runs` response lacks `node_states`, so the editor can't show
  per-node progress overlays during a run. It polls and shows run-level
  status instead.
- v2 has no `POST /runs/{id}/resume` endpoint, so the editor calls the
  v1 endpoint (`/api/graphs/{id}/resume/{exec_id}`) for resume.

**Next steps:**
1. Add `node_states` to the v2 `RunResponse` schema (or document that it's
   intentionally omitted and the events SSE is the source of truth).
2. Add `POST /api/v2/runs/{id}/resume` to `v2/runs.py`.

**Priority:** LOW. The editor works via v1 fallback + polling. These are
polish items for the v2 migration, not user-facing breakage.

---

## 2. Frontend non-findings (clarified)

- **`/dashboard/evaluation`** — 42 LOC, imports `EvaluationDashboard`
  component. **Fully built.**
- **`/dashboard/programs`** — 111 LOC list + new + [id]. **Fully built.**
- **`/dashboard/settings`** — 11 LOC shell that renders `SettingsPageClient`.
  **Fully built** (the content is in the client component).
- **`/dashboard/swarm`** — 38 LOC, renders `<SwarmDashboard />` (966 LOC,
  fetches real data from `/api/v1/swarm/protocol`). **Fully built.**
- **Onboarding "sample data"** — `generateSampleData()` is a real feature
  (creates demo missions for new users), not mock data shipping to prod.

---

## 3. Backend stubs (by service / endpoint)

### 3.1 Program CQRS — `fire_program` + `consolidate` return 501 ⚠️ MEDIUM

**File:** `app/api/_program_cqrs/commands.py:107-175`

**What:** Two command handlers catch `NotImplementedError` from the
underlying `mission_program_service` and re-raise as `ProgramError` →
HTTP 501:

| Command | Status | Message |
|---------|--------|---------|
| `fire_program` | 501 | `"fire_program is not yet implemented"` |
| `consolidate` | 501 | `"consolidate is not yet implemented"` |

**Current purpose:** The program (Automation) entity supports CRUD + audit,
but the "trigger a run" (`fire`) and "consolidate learning" (`consolidate`)
operations are stubbed at the service layer. The CQRS handler is a thin
shell that converts `NotImplementedError` into a stable 501 response.

**Intended final behavior:**
- `fire_program` — trigger a program run (like mission `execute` but for
  the Automation entity). Maps to T8 in the program rollout plan.
- `consolidate` — aggregate recent run outputs into a learning brief.
  Maps to T9.

**What's missing:** The `mission_program_service.py` methods
`fire_program()` and `consolidate_learning()` raise `NotImplementedError`.

**Next steps:**
1. Implement `fire_program()` in `mission_program_service.py` — delegate
   to `UnifiedExecutor.execute()` with a `Workflow` built from the program
   definition (use `substrate.adapters`).
2. Implement `consolidate_learning()` — query recent `ProgramRun` rows,
   summarize via LLM, store as a `LearningBrief`.
3. Remove the `try/except NotImplementedError` wrappers in
   `_program_cqrs/commands.py` once the service methods are real.

**Priority:** MEDIUM. The frontend `/dashboard/programs` page can list,
create, and edit programs, but the "Run" button will 501. This is the
highest-value backend stub because it blocks the entire Automations feature.

---

### 3.2 Marketplace uninstall — 501 ⚠️ LOW

**File:** `app/api/v2/marketplace.py:222-231`

**What:**
```python
@router.delete("/listings/{listing_id}/install")
async def uninstall_listing(...):
    """Uninstall a marketplace listing (placeholder — full uninstall logic TBD)."""
    raise HTTPException(status_code=501, detail="Uninstall not yet implemented")
```

**Current purpose:** The marketplace supports browse + install + review, but
not uninstall.

**Intended final behavior:** Remove the listing from the user's installed
list, revoke any granted capabilities, and optionally clean up persisted state.

**What's missing:** `MarketplaceService.uninstall()` method.

**Next steps:**
1. Add `async def uninstall(self, user_id, listing_id)` to
   `services/marketplace_service.py` — delete the `MarketplaceInstall`
   row, revoke capabilities via `CapabilityEngine`.
2. Replace the 501 with `return ok(await service.uninstall(...))`.

**Priority:** LOW. Users can install but not uninstall via UI. Workaround:
re-install overwrites. Not blocking.

---

### 3.3 Slack connector — file upload returns 501 ⚠️ LOW

**File:** `app/services/connectors/slack_connector.py:437`

**What:** `_upload_file()` returns 501: `"File upload requires multipart
handling - use direct API call"`.

**Current purpose:** The Slack connector handles text messages, but file
uploads need multipart form handling that isn't implemented.

**Next steps:** Implement multipart upload via `aiohttp.FormData` or
`httpx` multipart. ~30 LOC.

**Priority:** LOW. Text messaging works. File upload is an edge case.

---

### 3.4 Alerting — email + pagerduty channels are placeholders ⚠️ LOW

**File:** `app/services/alerting.py:6-7` (docstring only)

**What:** The docstring lists 4 channels:
- `webhook` — ✅ fully implemented
- `ntfy` — ✅ fully implemented
- `email` — ❌ placeholder (no SMTP send code beyond module import)
- `pagerduty` — ❌ placeholder (no Events API v2 call)

**Reality:** Only webhook + ntfy are wired. The `NOTIFY_CHANNELS` env var
can list `email,pagerduty` but they'll silently no-op.

**Next steps:**
1. Email: implement `_send_email()` using `smtplib` (the module is already
   imported). Wire to the SMTP settings in `config.py`.
2. PagerDuty: implement `_send_pagerduty()` using the Events API v2
   (`POST https://events.pagerduty.com/v2/enqueue`).

**Priority:** LOW. Webhook + ntfy cover current ops needs. Email/pagerduty
are enterprise-tier channels.

---

### 3.5 Integration webhooks — Twilio HMAC verification incomplete ⚠️ LOW

**File:** `app/api/v1/integration_webhooks.py:154`

**What:** `_verify_twilio()` checks only that the `x-twilio-signature`
header is **present**, not that it's **valid**. The full HMAC-SHA1
verification (which requires the request URL + sorted form params) is a
TODO.

**Current purpose:** Inbound webhook ingestion for Stripe, Slack, GitHub,
Twilio, Monday.com. Twilio verification is intentionally weak.

**Next steps:** Pass the request URL through to `_verify_twilio()` and
implement the full HMAC-SHA1 per Twilio's spec. ~15 LOC.

**Priority:** LOW (but a **security** item — anyone can POST a fake Twilio
webhook today). Fix when Twilio integration goes live.

---

### 3.6 Celery task stubs (6 files) — **intentionally disabled** ✅ NOT A STUB

**Files:** `app/tasks/{base_task,deepagents_tasks,langgraph_tasks,task_definitions,webhook_dispatcher,webhook_tasks}.py`

**What:** Each file is a stub docstring explaining it was disabled
2026-06-12 due to import errors, with a **detailed revival checklist**.

**Reality:** These are **not regressions**. They were intentionally
disabled during Q1-B cleanup because they imported non-existent modules.
The revival checklists are thorough (which models to create, which
migrations to add, which imports to fix).

**Next steps:** Revive only if the corresponding feature is needed:
- `base_task` → needs `CeleryTask` ORM model + migration
- `deepagents_tasks` → needs `deepagents_integration.py` service
- `langgraph_tasks` → needs `get_llm()` in `llm_config.py`
- `task_definitions` → needs `WorkflowRuns` model + `MonitoringService`
- `webhook_dispatcher/tasks` → needs `WebhookSubscription` model + sync session

**Priority:** DEFERRED. The substrate executor + trigger bridge handle
workflow execution without Celery. These tasks are for future background-job
features (stuck-workflow cleanup, webhook retry, monitoring rollups).

---

### 3.7 Minor backend TODOs (informational)

| File:line | TODO | Impact |
|-----------|------|--------|
| `main_fastapi.py:482` | `"total_tokens": 0 # TODO: aggregate from LLMCallRecord` | Dashboard stats show 0 total tokens. LOW — cosmetic. |
| `tool_router.py:480` | `# TODO: integrate with workspace/user permission deny-list` | Tool permission scoring always returns 1.0. LOW — no deny-list exists yet. |
| `integration_webhooks.py:460` | `# TODO: Route to external_events durable bus` | Inbound webhooks log + ack but don't forward. LOW — the external_events page reads from a different source. |
| `unified_tool_bridge.py:185` | `# Placeholder for discovery service integration` | Tool discovery returns all tools instead of semantically filtered. LOW. |
| `episodic_memory_service.py:65` | `# Placeholder for runtime-configured deny-list entries` | PII deny-list is empty. LOW — no runtime config wired. |
| `langgraph/auth_fastapi.py:286` | `# This is a stub - the actual auth should be done via FastAPI dependencies` | Deprecated decorator that passes through. LOW — no routes use it (all migrated to `Depends(get_current_user)`). |
| `langfuse_service.py:79` | `_LangfuseUnavailable` stub class | Intentional graceful degradation when Langfuse SDK isn't installed. ✅ Not a stub. |

---

## 4. Priority order for completion

Grouped by impact × effort. Tackle top-down.

### Tier 1 — User-facing value, ship now

| # | Item | Effort | Why first |
|---|------|--------|-----------|
| 1 | **Delete 6 orphan `/dashboard/*` pages** (§1.1) | 1h | Removes confusion, cleans build, zero risk. Pure deletion. |
| 2 | **Wire contact form to backend** (§1.3) | 3h | Currently **silently drops every customer message**. Revenue impact. |
| 3 | **Implement `fire_program`** (§3.1) | 1-2d | Unblocks the entire Automations feature. Frontend exists, nav exists, only the run trigger is missing. |

### Tier 2 — Feature completion

| # | Item | Effort | Why next |
|---|------|--------|----------|
| 4 | **Canvas `file-diff` tile** (§1.2) | 1d | Sandbox already produces diffs; this is the viewer. High perceived value. |
| 5 | **Marketplace uninstall** (§3.2) | 3h | Closes the marketplace CRUD loop. |
| 6 | **Canvas `mission_status` tile** (§1.2) | 1d | Reuses observatory data; compact card. |
| 7 | **`consolidate_learning`** (§3.1) | 1d | Completes the program CQRS surface. Pairs with #3. |

### Tier 3 — Polish / hardening

| # | Item | Effort | Why defer |
|---|------|--------|-----------|
| 8 | **Twilio HMAC verification** (§3.5) | 2h | Security fix, but only matters when Twilio is live. |
| 9 | **Dashboard `total_tokens` aggregation** (§3.7) | 2h | Cosmetic dashboard stat. |
| 10 | **Canvas `image-gen` tile** (§1.2) | 1d | Image gen tool exists but isn't a headline feature. |
| 11 | **Slack file upload** (§3.3) | 3h | Edge case; text messaging works. |
| 12 | **v2 `node_states` + `/runs/{id}/resume`** (§1.5) | 1d | v1 fallback works. v2 migration polish. |

### Tier 4 — Deferred / on-demand

| # | Item | Why defer |
|---|------|-----------|
| 13 | **Email + PagerDuty alert channels** (§3.4) | Webhook + ntfy cover current needs. |
| 14 | **Celery task revival** (§3.6) | Substrate handles execution. Revive per-feature when needed. |
| 15 | **Team presence REST migration** (§1.4) | WebSocket presence works. |
| 16 | **Tool deny-list integration** (§3.7) | No deny-list data exists yet. |
| 17 | **Tool discovery service** (§3.7) | Returns all tools; semantic filtering is optimization. |

---

## 5. What is NOT a stub (common misconceptions)

- **The `(dashboard)` route group** is the real dashboard. The bare
  `/dashboard` directory has some real pages (swarm, programs, evaluation,
  settings) and 6 orphan ghosts (§1.1). Don't confuse the two.
- **`_NoOpAudit` classes** in `mission_program_service.py`,
  `personal_memory_service.py`, `memory_correction_service.py` are
  **intentional duck-typed fallbacks** — the audit log is fire-and-forget,
  and these no-op implementations ensure the service works before the audit
  table is wired. They are load-bearing design, not stubs.
- **`Hardcoded tuples`** comments in model files are explicit design choices
  ("do NOT derive from enum iteration because..."). Not stubs.
- **`is_placeholder()`** in `tools/base.py` is a utility that *detects*
  placeholder API keys (e.g. `sk-xxx`) to prevent sending them to live APIs.
  It's a safety feature, not a stub.
- **Differentiator tools** (`tools/differentiators.py`) — the docstring
  says "returns a coming soon stub" but the code is 1106 LOC of real
  implementations hitting PostgreSQL + Qdrant. The docstring is stale;
  the tools work.

---

## 6. Verification commands

```bash
# Re-run this audit's frontend sweep
grep -rPni --include='*.tsx' --include='*.ts' \
  -e 'TODO' -e 'coming soon' -e 'not implemented' \
  /home/glenn/FlowmannerV2-frontend/src \
  | grep -v '.stories.' | grep -v 'placeholder='

# Re-run this audit's backend sweep
grep -rPni --include='*.py' \
  -e 'TODO' -e 'not implemented' -e '501' -e 'placeholder' \
  /opt/flowmanner/backend/app \
  | grep -vE 'Hardcoded|MessagesPlaceholder|sys.path|is_placeholder'

# Confirm orphan pages still exist
ls /home/glenn/FlowmannerV2-frontend/src/app/\[locale\]/dashboard/{build,run,market,tools}/

# Confirm program 501s
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://127.0.0.1:8000/api/v2/programs/{id}/fire \
  -H "Authorization: Bearer $TOKEN"
# Expected: 501
```
