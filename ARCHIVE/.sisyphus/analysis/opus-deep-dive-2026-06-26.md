# FlowManner Deep Dive — Product Readiness & Next 60 Days

**Date:** 2026-06-26
**Auditor:** Opus (Kimi k2.7-code)
**Scope:** Backend (`/opt/flowmanner/backend/`) + Frontend (`/home/glenn/FlowmannerV2-frontend/`)
**Source of truth:** live OpenAPI spec, source files, running backend container, and project docs.

---

## Executive Summary

FlowManner is not a product yet. It is a **large, capable backend with a thin, partially-wired frontend** sitting on top of an unfinished schema cutover. The good news: the core execution substrate (`UnifiedExecutor`) is real, the Blueprint/Run data model is real, auth/chat/health are live, and the backend can actually run workflows against DeepSeek. The bad news: a brand-new user cannot reliably create, save, execute, and iterate on a workflow through a single coherent UI path because the builder still writes to the old `graphs`/`missions` tables while the new `blueprints`/`runs` tables live in parallel. The “agents get smarter over time” promise is mostly backend code; the user-facing memory surface is a read-only inspector that is not connected to chat or execution.

The biggest risk is not a missing feature — it is **architectural drag from maintaining two data planes**. Every day the dual-write layer stays on, the codebase gets harder to reason about, harder to deploy, and harder to explain to a user. The second-biggest risk is the DeepSeek dependency, which is operationally fine today but directly contradicts the sovereign/self-hosted positioning.

The next 60 days should be about **finishing one vertical user loop**, not adding more capabilities.

---

## 1. Feature Surface Map

### Method

I inventoried the live OpenAPI spec, the backend router files, and the frontend pages/components. Classifications:

- 🟢 **Live & functional** — routes registered, frontend wired, exercised end-to-end.
- 🟡 **Backend exists, frontend missing/incomplete** — API is real but the UI does not call it, or calls an older API.
- 🔴 **Stub/scaffold** — file exists but returns limited/mock data or is half-implemented.
- ⚫ **Dead** — orphaned code, no route registration, or references removed features.

### Backend surface

The backend exposes **596 registered OpenAPI paths**:

| Prefix | Paths | Notes |
|---|---|---|
| `/api/v2` | 127 | Modern API surface (missions, blueprints, runs, chat, personal memory, agents, workspaces, programs). |
| `/api` (top-level, legacy) | 434 | Most of the product surface: missions, chat, auth, admin, marketplace, plugins, etc. |
| `/api/v1` | 9 | Deprecated RAG + usage analytics only. |
| `/api/v3` | 22 | Auth/oidc/admin extensions. |

The backend has 77 files under `app/api/v1/` declaring ~497 routes in source, but the live router wiring is dominated by top-level `/api/*` routers plus `/api/v2`. Many “v1” files are actually mounted at `/api/*` without a version prefix.

### Feature-area classification

| Area | Backend | Frontend | Verdict |
|---|---|---|---|
| **Auth / users / sessions** | 🟢 23+ paths, NextAuth-compatible cookie flow, 2FA, OIDC scaffolding | 🟢 Signin/signup, session provider | 🟢 Live |
| **Chat** | 🟢 Threads, messages, streaming, BYOK, stored keys | 🟢 Chat page, branches, streaming | 🟢 Live |
| **Mission/Blueprint builder** | 🟡 `/api/v2/blueprints`, `/api/v2/runs`, `/api/graphs`, `/api/missions` all exist; execution works through UnifiedExecutor | 🟡 Builder still saves to `/api/graphs` and creates legacy missions; Blueprints page exists but is browse-only | 🟡 Backend ready, frontend split across old/new |
| **Workflow execution** | 🟢 `UnifiedExecutor` with strategies (solo, DAG, graph, swarm, pipeline, meta, LangGraph); event log, lease manager, replay, circuit breaker | 🟡 Execution polling hook exists; UI shows status but not all pause/resume/cancel paths are wired | 🟡 Functional backend, uneven UI |
| **Connectors / integrations** | 🟢 GitHub, Slack, Discord, Notion, Linear, Google, email, webhook; OAuth token encryption (Fernet) | 🔴 No connector settings UI; only Slack webhook for notifications | 🟡 Backend exists, frontend missing |
| **Episodic / personal memory** | 🟢 `/api/v2/personal_memory` (recall, inspector, claims, provenance, forget) | 🟢 Memory inspector page | 🟡 Backend + inspector exist, but not consumed by chat or execution |
| **Tool routing** | 🟢 `tool_router.py`, depth policy, routing events API | 🔴 Not exposed in builder node palette or chat tool-calling | 🟡 Backend code, no user surface |
| **Multi-agent / swarm** | 🟢 `SwarmOrchestrator`, debate/escalation/handoff, v2 agents | 🟡 2 components, 75 frontend refs, but no clear end-to-end user flow | 🟡 Partial |
| **HITL pause/approve** | 🟢 Backend HITL pause in substrate, approve/reject task endpoints | 🟡 Some UI exists; not consistently wired | 🟡 Partial |
| **Evaluation / LLM-as-judge** | 🟢 Dataset builder, eval runner, judge endpoints | 🟡 Evaluation viewer components exist | 🟡 Niche, likely not used by first users |
| **Marketplace / plugins** | 🟢 12 marketplace paths, plugin registry | 🟢 Frontend pages exist | 🟡 Speculative for pre-launch |
| **Browser automation** | 🟢 17 browser paths | 🟢 `/browser` page | 🟡 Works, but not core loop |
| **Admin / observability** | 🟢 Admin, audit, feature flags, analytics, health | 🟢 Admin pages | 🟢 Live but owner-only |
| **Billing / subscriptions** | 🟢 PayPal, subscription gating | 🟢 Billing settings page | 🔴 Pre-revenue dead weight |
| **RAG / file ingestion** | 🟡 Legacy v1 RAG paths; vector store present | 🟡 Files/RAG pages | 🟡 Not clearly integrated into missions |
| **Code sandbox / playground** | 🟢 Backend sandbox preview auth chain recently fixed | 🟡 Playground UI | 🟡 Works but secondary |

### Key finding: two products in one repo

There are effectively two execution/data planes:

1. **Old plane:** `Mission`, `Graph`, `WorkflowRun`, legacy `mission_executor.py`, `/api/missions/`, `/api/graphs/`. The frontend builder writes here.
2. **New plane:** `Blueprint`, `Run`, `SubstrateEvent`, `UnifiedExecutor`, `/api/v2/blueprints`, `/api/v2/runs`. This is where the product wants to go.

The dual-write CQRS layer (`app/api/_mission_cqrs/`) is actively keeping them in sync, but reads default to the old tables (`USE_NEW_READS=false`). The frontend has not made the jump.

---

## 2. Core User Loop Audit

### Step 1 — Sign up / sign in

🟢 **Works.** NextAuth JWT flow, backend `/api/auth/*`, cookie path fixed to `/`. Recent auth chain fixes for sandbox preview suggest the cookie/auth plumbing is currently solid.

### Step 2 — Create a mission/workflow

🟡 **Half-wired.**

- User clicks “New Mission” → `/missions/builder`.
- Builder is a real React Flow canvas with undo/redo, ELK layout, groups, version history, export/import, validation, and templates.
- **But it persists to `/api/graphs/`, not `/api/v2/blueprints`.** The Blueprints page (`/blueprints`) calls `/api/v2/blueprints` and can start a run from a published blueprint, but there is no UI to author a blueprint.
- The “Mission” listing page still reads from `/api/missions/` (legacy).

A new user will create a “mission” in the builder, save it as a graph, and then wonder why it does not appear under Blueprints or Runs.

### Step 3 — Configure tools / connectors

🔴 **Not usable.**

- Backend supports OAuth for GitHub, Slack, Google Drive, Notion, Linear; tokens are encrypted at rest with Fernet.
- Frontend settings has no connector-management page. The only connector-like UI is a Slack webhook URL under Notifications.
- The builder node palette may show tool nodes, but tool execution in `NodeExecutor._handle_tool` uses a **hardcoded handler map** (`web_search`, `code_executor`, `file_reader`, etc.), not the connector manager. So even if a user supplied a GitHub token, there is no obvious path for a “Create GitHub Issue” node to consume it.

### Step 4 — Run and see results

🟡 **Works at the backend, inconsistent at the UI.**

- `/api/v2/blueprints/{id}/run` creates a `Run`, `RunService.execute()` converts the blueprint snapshot to a `Workflow`, and `UnifiedExecutor` executes it.
- Strategies exist for solo, DAG, graph, swarm, pipeline, meta, LangGraph.
- `NodeExecutor` handles `LLM_CALL`, `TOOL_CALL`, `CODE_EXECUTION`, `RAG_QUERY`, `WEB_SEARCH`.
- Execution polling hook (`useExecutionPoll`) exists and drives the builder UI.
- **But** because the builder does not produce Blueprints, the cleanest run path (`blueprint → run`) is only accessible if blueprints are seeded by hand. The legacy `/api/missions/{id}/execute` path also exists and delegates to UnifiedExecutor through CQRS, so execution *does* work, just through the older model.

### Step 5 — Review, approve, iterate

🟡 **Partial.**

- HITL pause is implemented in the substrate (`HITLPaused` propagates out of strategies).
- Approve/reject endpoints exist at `/api/v2/missions/{id}/tasks/{task_id}/approve`.
- Replay engine and run-diff endpoints exist at `/api/v2/runs/{id}/replay`.
- The UI has some pause/resume scaffolding, but cancel/resume are commented with TODOs in the builder, and the HITL surface is not a first-class part of the core loop.

### Step 6 — “Agents get smarter over time”

🔴 **Not delivered to the user.**

- `episodic_memory_service.py`, personal memory claims, recall, provenance, forget, and the v2 inspector API all exist.
- The Memory Inspector page (`/memory-inspector`) is polished and shows claims grouped by type (`preference`, `fact`, `observation`, `sensitive`).
- **Chat does not recall claims.** `chat_service.py` has no references to `memory_service`, `MemoryBridge`, `episodic`, or `RAGService`. It is a stateless LLM wrapper with optional web search.
- **Execution does not inject memory into prompts.** `NodeExecutor._handle_llm` injects recent substrate events as context, but not the user’s long-term claims or mission episodes.
- The user can open the Memory Inspector and see nothing (empty state) because nothing is writing relevant memories from real usage.

**Verdict:** The wedge feature is built but not productized. A user cannot experience it.

---

## 3. Technical Debt & Risk Flags

### 3.1 The Blueprint/Run cutover is the #1 risk

- `USE_NEW_READS=false` means every mission query still reads the old tables.
- The dual-write layer (`_mission_cqrs/compat.py`, `commands.py`) is complex fire-and-forget code. It is a source of bugs, race windows, and cognitive load.
- Recent commits show this is active and painful: “phase B parity verifier,” “dual-write retry,” migration drift (`reconcile_schema_001 migration is broken`), DB stuck at `20260617_pending_writes`.
- **Risk of staying here:** every new feature must be written twice or wrapped in compat; migrations become impossible; the team burns cycles on cutover instead of user value. The longer this state persists, the more likely the cutover becomes a “rewrite” decision.

**Recommendation:** Do not add any new user-facing features until the cutover is complete and `USE_NEW_READS=true` is the default.

### 3.2 API surface is speculative for the current stage

- 596 OpenAPI paths, 77 backend router files, 107 frontend pages.
- Many are owner-only or pre-revenue: subscriptions/billing, marketplace, plugin registry, admin audit, feature flags, OIDC, 2FA, NPS, newsletters.
- For a bootstrapped product with no paying customers, this is over-engineering. It creates the illusion of a mature platform while the core loop is split across two data models.

### 3.3 Connector security is structurally okay, operationally fragile

- OAuth tokens are encrypted with Fernet; `AES_ENCRYPTION_KEY` is required in production.
- Client IDs/secrets for the platform OAuth apps live in environment variables. There is per-user OAuth credential storage too (`UserOAuthCredentials`).
- No obvious plaintext credential storage in the routes inspected.
- **Concerns:**
  - Key rotation story is unclear.
  - The connector manager and node executor are not integrated, so the actual blast radius of a leaked credential is hard to reason about.
  - No clear scope-of-access UI; a user cannot see which tools have which permissions.

### 3.4 Test coverage is broad but shallow in critical areas

- 230 test files exist.
- There are tests for depth routing, tool routing, episodic memory, handoff packets, blueprint/run lifecycle, and dual-write failure logging.
- However, there are **zero tests under `app/tests/` for the substrate executor**; integration tests are in `tests/integration/`.
- With the cutover mid-flight, the most important property — “a user can create a blueprint, run it, and view the result end-to-end” — is not obviously locked by an automated test.

---

## 4. The LLM Question

### Current state

```
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=***
```

Live health check reports `deepseek/deepseek-v4-flash`.

### Is this a positioning problem?

**Yes.** “Your agents get smarter over time” and “sovereign infrastructure” are the product story. Routing every inference call to a Chinese-hosted API undermines both claims. A security-conscious buyer evaluating FlowManner against self-hosted or EU/US alternatives will flag this immediately.

### Is this a cost problem?

**Partially.** DeepSeek is cheap compared to OpenAI, but it is still metered. For a bootstrapped founder, the real cost is not the API bill — it is the inability to control latency, uptime, data residency, and model behavior. Every dollar that leaves Glenn’s infrastructure is a dollar not spent on the moat.

### What would a hybrid approach look like?

The backend already supports `llamacpp` and `llamacpp_light` providers and has `LLAMACPP_URL` / `LLAMACPP_LIGHT_URL` settings. The right production posture is:

1. **Default to self-hosted llama.cpp** for all standard inference.
2. **Use external APIs only as a capability fallback**, not as the primary engine — e.g., a stronger model for plan generation or eval judging when the local model is insufficient.
3. **Expose provider/model selection per workflow node**, not just globally, so power users can make the trade-off explicitly.
4. **Remove DeepSeek from the default `.env`** and product messaging; document it as a development option only.

This is technically feasible today. The blocker is product/policy, not code.

---

## 5. Prioritized 60-Day Plan

### Tier 1 — “Make it real”

*Goal: turn FlowManner from “code that exists” into “a product a person can use and derive value from.”*

#### 1. Finish the Blueprint/Run cutover (Week 1–3)
**What:** Flip `USE_NEW_READS=true`, migrate the DB past the pending-writes state, retire the dual-write CQRS for missions, and make `/api/v2/blueprints` the primary write path.
**Why:** Unblocks every other feature; removes the #1 source of bugs and confusion.
**Effort:** 2–3 weeks.
**Blocked by:** The broken `reconcile_schema_001` migration must be regenerated (autogenerate) and applied against a copy of the live DB before flipping the flag.

#### 2. Move the builder to Blueprints (Week 2–4)
**What:** Change the mission builder save endpoint from `/api/graphs/` to `/api/v2/blueprints/`. Update the “Missions” page to list Blueprints. Wire “Run” to `/api/v2/blueprints/{id}/run`. Redirect `/missions/builder` → `/blueprints/builder` or keep it as a redirect.
**Why:** Creates one coherent authoring → execution → run-review loop.
**Effort:** 1–2 weeks.
**Blocked by:** #1.

#### 3. Make chat remember (Week 3–5)
**What:** Inject relevant personal-memory claims into `chat_service.py` prompts; write meaningful claims from chat interactions (user preferences, corrections, recurring topics). Surface a “Memory” hint in the chat UI.
**Why:** This is the wedge. Without it, FlowManner is just another chat UI.
**Effort:** 1–2 weeks.
**Blocked by:** #1 (memory claims should attach to the new user/run model).

#### 4. Ship one connector end-to-end (Week 4–6)
**What:** Pick **GitHub** (highest-value for code/test/fix loops). Build a connector settings UI, store the OAuth token, expose a “Create GitHub Issue” or “Search Code” node in the builder, and route it through the connector manager instead of the hardcoded handler map.
**Why:** Proves the “workflow with integrations” story and gives users a concrete reason to build a workflow.
**Effort:** 2 weeks.
**Blocked by:** #2 (builder must produce blueprints that the executor understands).

#### 5. Default to self-hosted LLM (Week 5–7)
**What:** Set `LLM_PROVIDER=llamacpp` and a local model as default. Validate that chat and blueprint execution work acceptably. Document DeepSeek as a dev-only fallback. Add a settings toggle for model/provider per workspace.
**Why:** Aligns product with positioning; removes external dependency for the production story.
**Effort:** 1–2 weeks.
**Blocked by:** Local hardware capacity; must benchmark token throughput first.

#### 6. One end-to-end smoke test + deploy guardrail (Week 6–8)
**What:** A single Playwright/pytest test that signs up, creates a blueprint, runs it, and checks the run result. Run it before every deploy.
**Why:** Prevents regressions in the only path that matters.
**Effort:** 3–5 days.
**Blocked by:** #2.

### Tier 2 — “Make it defensible”

*Goal: make FlowManner genuinely better than alternatives, not just different.*

#### 7. Memory-driven execution adaptation (Week 8–10)
**What:** Inject episodic memory / mission episodes into `NodeExecutor._handle_llm`; use the tool router and depth policy to adapt plan depth based on past successes/failures. Surface “Why this step?” links from memory provenance.
**Why:** This is the moat.
**Effort:** 2–3 weeks.
**Blocked by:** #3 and #4.

#### 8. Cost-aware execution as a first-class feature (Week 9–11)
**What:** Surface budget limits, token usage, and cost per run in the run UI. Add a “run under $X” mode. Use the circuit breaker and provider fallback to enforce it.
**Why:** Reinforces the cost-survival narrative and differentiates from metered competitors.
**Effort:** 2 weeks.
**Blocked by:** #2.

#### 9. Evaluation-driven self-improvement loop (Week 10–12)
**What:** Use the existing eval framework to run regression tests on blueprints after code/model changes. Auto-suggest blueprint improvements based on failed runs.
**Why:** Turns “agents get smarter” from a slogan into a measurable loop.
**Effort:** 2–3 weeks.
**Blocked by:** #6 and #7.

#### 10. HITL governance that users actually use (Week 11–12)
**What:** A simple “Approvals” inbox where users see paused runs, approve/reject steps, and add corrections that become memory claims.
**Why:** The interruptible/resumable story is core positioning.
**Effort:** 2 weeks.
**Blocked by:** #2 and #7.

### What to *not* build in the next 60 days

- **Marketplace, plugins, billing, subscriptions** — pre-revenue dead weight.
- **v3 auth / OIDC / 2FA** — only needed for enterprise, which is not the immediate ICP.
- **Browser automation page** — cool, but not core to the workflow loop.
- **New strategies (meta, LangGraph)** — the existing solo/DAG/graph strategies are enough to prove value.
- **More connectors beyond GitHub** — ship one perfectly before adding N.

---

## 6. Final Verdict

FlowManner is **~60% built and ~20% productized**. The execution engine is real, the new data model is correct, and the auth/chat foundation is solid. The gap is not capability — it is **coherence**. A new user today walks into a split world where the builder writes to old tables, the execution engine reads from new ones, memory is visible but unused, and the flagship “sovereign” story depends on DeepSeek.

**The only thing that matters for the next 60 days is finishing the Blueprint/Run cutover and wiring one clean user loop through it.** Everything else — memory, connectors, self-hosted LLMs, defensibility — becomes straightforward once that loop is singular. Until then, every new feature is debt.

---

## Appendix: Audit Evidence

- OpenAPI path count from `http://localhost:8000/openapi.json`: **596 paths**.
- Backend API files: 77 in `app/api/v1/`, 27 route-decorated files, 12 connector modules.
- Frontend dashboard pages: 41 `page.tsx` files.
- Frontend API path references: `/api/v1/` 37, `/api/v2/` 145, `/api/v3/` 1.
- Frontend route refs: `missions` 317, `runs` 179, `swarm` 75, `graphs` 43, `blueprints` 13.
- Backend live health: healthy, LLM provider `deepseek/deepseek-v4-flash`.
- Test files: 230 total, including `tests/integration/test_blueprint_run_lifecycle.py`, `tests/test_tool_router.py`, `tests/test_episodic_memory_integration_pg.py`, `tests/test_dual_write_failure_logged_at_warning_b4.py`.
- `USE_NEW_READS` defaults to off in `app/api/_mission_cqrs/compat.py`.
- `chat_service.py` has 0 references to memory/RAG services; `NodeExecutor._handle_llm` injects substrate events but not long-term claims.
