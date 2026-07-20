# Flowmanner — Product Positioning & Platform Economy Analysis

**Type:** Read-only KG-analysis (evidence-based)
**Author:** fmw_synth (kanban t_c8390710, persona: product-manager)
**Date:** 2026-07-20
**Repo:** `/opt/flowmanner/.worktrees/t_c8390710` (branch `agent/20260720-kg/product`)
**Method:** Every claim below is anchored to a real file:line read during this analysis. No marketing copy used.

> Note on scope: the frontend source is NOT in this worktree (per `backend/AGENTS.md` and the root `AGENTS.md`, the Next.js frontend lives at `/home/glenn/FlowmannerV2-frontend` on the homelab, not in the backend repo). ICP inference is therefore grounded in the backend persona domain taxonomy (`app/agent_definitions/*`) and the feature surface, not on frontend UI copy.

---

## WHAT FLOWMANNER DOES

Flowmanner is a **multi-agent workflow automation platform** where users compose executable "missions" (and "blueprints"/"workflows") that orchestrate LLM-driven agents. The execution engine is a single unified substrate; the surface is a full API (v1 legacy, v2 default, v3 workspace-scoped) plus a marketplace, community templates, blog/roadmap/changelog, and SaaS-style workspace billing.

**Core capabilities (evidence-anchored):**

- **Mission lifecycle (plan → execute → settle).** `app/api/v2/missions.py` exposes the full CRUD + execution surface: `POST /missions/`, `plan`, `execute`, `execute-async`, `abort`, `pause`, `resume`, `retry`, `batch-abort`, `from-template`, `improvements` (apply). The router is a thin DI shell over `_mission_cqrs` command/query handlers (`backend/app/api/v2/AGENTS.md` missions inventory).
- **Unified execution substrate (the engine).** `app/services/substrate/AGENTS.md` documents `UnifiedExecutor` — one durable executor replacing 7 prior executors (mission, DAG, graph, swarm, pipeline, meta, langgraph), dispatching to 7 strategies (`strategies/{solo,dag,graph,swarm,pipeline,meta,langgraph}.py`). Four guarantees: Durable (append-only event log), Type-checked (Pydantic), Capability-bounded (CapabilityToken), Bounded (BudgetEnforcer on every LLM call).
- **Orchestration / swarm.** `backend/app/api/v1/AGENTS.md` lists `swarm_protocol.py` (`/swarm`) inlining DebateProtocol/EscalationChain/HandoffProtocol; these are migration candidates to the substrate `SwarmStrategy`. Multi-agent debate/handoff is a first-class workflow type.
- **RAG + Memory.** `backend/app/api/v1/memory.py` is the CANONICAL RAG/memory endpoint (`/memory`); `/api/v1/rag` is deprecated. `app/services/rag_service.py` delegates to a `rag/` subpackage (chunking, embedding, retrieval, vector_store). Personal memory (claim-based, conflict/correction-aware) lives at `app/api/v2/personal_memory.py` + `app/services/personal_memory_service.py`.
- **Tools / integrations.** `backend/app/api/v1/tools.py` (tool catalog), `integrations.py`, plus OAuth connectors including Stripe (`app/api/v1/stripe_oauth.py`), Linear, browser automation (`browser.py`, CRITICAL), and a generic connector framework (`app/services/connectors/`).
- **Human-in-the-loop (HITL).** `app/services/substrate/hitl_pause.py` implements real PAUSE semantics: `HITLPaused` exception → executor releases the worker lease, emits `RUN_PAUSED`, waits for human resolution via inbox → Celery resumes the run. APPROVAL and HUMAN_REVIEW node types are supported.
- **Sandboxes.** `app/api/v1/sandbox.py` (`/chat` sandbox mode), `sandbox_preview.py` (`/sandbox`), `admin_sandboxes.py` — code-execution isolation for agent tasks (`mission_code_sandbox.py`).
- **Evals.** `app/services/evaluation/llm_judge.py` — rubric-based LLM-as-judge (1–5 scoring). `eval_runner.py` runs golden test cases against models and scores with the judge. Surface at `app/api/v1/evaluation.py`. Substrate `assertion_engine.py` + `baseline_extractor.py` provide replay-time regression assertions against known-good runs (1.5× cost / 2.0× latency headroom).

**One-line value proposition (synthesized from evidence):** Flowmanner lets a non-researcher compose, run, and govern multi-agent LLM workflows — with HITL approval gates, replayable durable execution, RAG/memory, a tool/integration catalog, and an eval harness — through a versioned API and a marketplace of reusable agents/tools/templates.

---

## THE PERSONA SYSTEM AS PRODUCT

**What it is:** A curated library of **expert agent personalities** defined as markdown files with frontmatter (name, description, color, domain) + a markdown body (system prompt / guidance). Served read-only via `app/api/v1/agent_personalities.py`.

**Scale & structure (evidence, not the "216" claim):**
- The library is **185 markdown files across 16 domain directories** under `backend/agent_definitions/` (verified by `find … -name "*.md" | wc -l` = 185, and per-domain counts).
- Domain directories: `academic, browser, design, engineering, finance, game-development, marketing, paid-media, product, project-management, sales, spatial-computing, specialized, support, testing` (plus `browser`) — 16 total.
- Per-domain counts: specialized 41, marketing 30, engineering 29, game-development 20, design 8, sales 8, testing 8, finance 5, academic 5, product 5, project-management 6, spatial-computing 6, support 6, paid-media 7, browser 1.
- The task brief cites "216 expert personas"; the **actual shipped count is 185 markdown definitions across 16 domains**. The "216" figure is not reflected in the codebase and should be treated as a target/aspirational number, not a current fact. (Anchored: `agent_personalities.py:22` scans `_DEFINITIONS_DIR`; `agent_personalities.py:93` "all 16 domain subdirs".)

**How a user picks/applies one (evidence):**
- `GET /agent-personalities` lists all; supports `?domain=` and `?q=` filters (`agent_personalities.py:127`).
- `GET /agent-personalities/{domain}/{slug}` returns a single persona (`agent_personalities.py:151`). IDs are `<domain>/<slug>` paths; the domain key is hyphenated to match the frontend `DOMAIN_LABELS` (`agent_personalities.py:62-64, 156-159`).
- Personalities are **content/template definitions**, distinct from **runtime agents**: `app/api/v1/agent_registry.py` (`/agent-registry/agents`) is an alias to `/api/agents/*` CRUD — users instantiate their own agents (`AgentCreate` schema, `agent_service`). The persona library is the catalog of reusable expert "shapes"; the agent registry is the user's instantiated, owned agents.

**Why 185 personas matter (PM read):**
- They convert "build an agent from scratch" into "pick an expert and customize" — a discoverability + time-to-value lever.
- The 16 domains double as an **implicit segmentation map** of who Flowmanner is for (see ICP section). This is the product's most visible differentiator and its primary onboarding hook.
- Caveat: the persona system is **read-only catalog + markdown**; there is no evidenic "persona marketplace" transaction (personas are not bought/sold — only tools/capabilities/agents are listings in the marketplace). Personas are a *feature of the product surface*, not yet a *creator-economy asset*.

---

## PLATFORM ECONOMY

Four platform surfaces exist; their maturity and mechanics differ sharply.

### 1. Marketplace (`app/api/v2/marketplace.py` + `app/services/nexus/marketplace_db.py`)
The only surface with a real transactional economy.
- **What is traded:** "listings" of type `TOOL`, `CAPABILITY`, `COMPOSED`, `AGENT` (`marketplace_db.py:22-28`). Pricing models: `FREE`, `ONE_TIME`, `SUBSCRIPTION`, `USAGE_BASED` (`marketplace_db.py:40-46`).
- **Creator flow:** any authenticated user can `POST /marketplace/listings` (with `price`, `category`, `tags`, doc/repo/icon URLs) — `marketplace.py:126`. Author is set to `user.id`. `GET /my-listings` shows owned listings (`marketplace.py:362`). This is a genuine **creator economy**: users publish, others install/purchase.
- **Buyer flow:** `POST /marketplace/listings/{id}/install` (free, registers the capability in the user's registry) or `POST /.../purchase` (paid, settled against an internal wallet) — `marketplace.py:204, 264`. Install actually registers the tool/capability into the user's `CapabilityRegistry` (`marketplace_db.py:607-649`).
- **Internal wallet / credits:** `GET /wallet`, `POST /wallet/topup` (operator/self top-up, "no external PSP" per `marketplace.py:254`), `purchase` debits the wallet, `refund` credits it back (`marketplace.py:239-322`; `marketplace_db.py:717-904`). Settlement is **USD-only, internal credits** — there is no Stripe/PSP settlement for marketplace purchases (explicitly noted: `marketplace_db.py:781-784` "Internal wallet is USD-only … A real PSP integration would carry the listing's currency"). 402 on insufficient balance.
- **Reviews / reputation:** `POST /listings/{id}/reviews` with rating + pros/cons; listings carry `average_rating`, `review_count`, `install_count`, `verified`, `featured` (`marketplace.py:325-359`; `marketplace_db.py:75-80`). Featured listings surfaced via `GET /listings/featured`.
- **Maturity:** Real, DB-backed (Alembic migration `20260605_marketplace.py`), seeded (`scripts/seed_marketplace.py`), tested (`tests/test_api_v2_marketplace.py`, `test_seed_marketplace.py`).

### 2. Community templates (`community_templates` / `community_comments`)
- A **community template-sharing** surface exists in the data model: `app/models/community_models.py` (`CommunityTemplate`, `CommunityComment` with threaded replies), plus a raw-SQL-backed router referenced as `app/api/v1/community.py` (`/community`) in `backend/app/api/v1/AGENTS.md` (tier: OPTIONAL).
- **Evidence gap / finding:** the file `backend/app/api/v1/community.py` does **NOT exist on disk** (verified by `find backend -name community.py` → no result), even though `v1/AGENTS.md` lists it and the `community_models.py` ORM + an Alembic migration `20260610_add_community_comments.py` exist. SDK client models for `community_templates` (create/fork/rate/comment) also exist (`sdk-python/.../api/community_templates/*`). So the **community economy is partially built (models + SDK + migration) but the router is missing/absent** — a real gap to flag.
- Separately, **mission templates** (`MissionTemplate`, `is_public`/`is_builtin`) are served read-only at `GET /templates` with rating + downloads + author (`app/api/v1/templates.py:18-54`). These are a *built-in/public template gallery*, not a user-to-user paid exchange.

### 3. Roadmap (`app/api/v2/roadmap.py`)
- Read-only public roadmap. `GET /roadmap` lists `is_public` items, filterable by `status`/`category`, ordered by `sort_order` (`roadmap.py:34`). `GET /roadmap/categories` is auth-required and derived live via `GROUP BY` (no dedicated table) (`roadmap.py:52-73`). Pure transparency feature; no transactional mechanics.

### 4. Changelog (`app/api/v2/changelog.py`)
- Read-only public release notes. `GET /changelog` (paginated, newest-first) and `GET /changelog/{version}` (`changelog.py:44-77`). Motivation in-doc: "lightweight read-only changelog is cheap credibility" (R9 swarm audit). No write path, no monetization.

**Platform-economy summary:** Only the **marketplace** has a working buy/sell/install economy (internal-credit wallet, creator-published listings, reviews). Community templates have models+SDK+migration but a **missing router**. Roadmap/changelog are transparency/read-only surfaces. There is **no external-PSP marketplace settlement** today.

---

## MONETIZATION MODEL

**Subscription tiers (seats-of-capability, not seats-of-people):**
- `app/models/subscription_models.py` defines `SubscriptionTier` with: `name`, `display_name`, `price_monthly`, `missions_per_day` (default 5), `missions_per_month` (default 150), `max_concurrent_missions`, `has_priority_support`, `has_api_access`, `has_custom_models`, `paypal_plan_id` (`subscription_models.py:11-28`).
- `UserSubscription` tracks `user_id`, `tier_id`, `status`, `current_period_*`, `paypal_subscription_id` (`subscription_models.py:31-43`). So billing is **per-user subscription**, priced monthly, with PayPal as the PSP (`paypal_plan_id`, `paypal_subscription_id`).

**Workspace-scoped billing (v3, H4.1):**
- `app/api/v3/workspace_billing.py` exposes `GET /workspaces/{id}/billing`, gated by feature flag `WORKSPACES_V3_BILLING` (404 when off) (`workspace_billing.py:28-42`).
- Reads `subscription_tier_id` + `billing_customer_id` off the `Workspace` model (migrated from legacy `Tenant` in H4.1). Response exposes `plan`, `member_limit` (default 5), `storage_limit_bytes` (1 GiB hardcoded), and a `subscription` block with per-tier limits: `missions_per_day`, `missions_per_month`, `has_api_access`, `has_custom_models` (`workspace_billing.py:58-88`).

**Payments / cost attribution:**
- Stripe is wired as an **OAuth connector** (`app/api/v1/stripe_oauth.py`) — it extracts `stripe_user_id` for *agent reference* (i.e., a user connecting their Stripe account so an agent can act on it), NOT for Flowmanner's own SaaS billing. PayPal is the billing PSP (`subscription_models.py:28,43`).
- Cost tracking per LLM call exists (`mission_executor`/`cost_tracker.py` writes `LLMCallRecord`; substrate enforces `BudgetEnforcer` on every LLM call). This is infra cost-control, surfaced via usage APIs (`app/api/v1/usage.py`), not a user-facing metering line item in this code.

**Rate-limit / tier gating (monetization enforcement):**
- `app/api/v2/tier_rate_limit.py` enforces per-endpoint limits scaled by tier: multipliers `free 1.0, starter 2.0, pro 5.0, business 10.0, enterprise 20.0` (`tier_rate_limit.py:41-47`). Base limits e.g. `mission:create 30/min`, `mission:execute 20/min`, `chat:stream 10/min` (`tier_rate_limit.py:50-64`). Tier resolved from active `UserSubscription` → `SubscriptionTier.name`, else workspace `plan`, else `free` (`tier_rate_limit.py:100-139`). This is the **soft paywall**: higher tiers get materially more throughput.

**Monetization model (synthesized):**
- **Primary:** per-user monthly SaaS subscription (Free/Starter/Pro/Business/Enterprise) priced by `price_monthly`, differentiated by mission quotas, concurrency, API access, custom models, priority support. PSP = PayPal.
- **Secondary (nascent):** marketplace internal-credit purchases of tools/capabilities/agents (creator economy) — settled in an internal USD wallet, **not** an external PSP. No revenue share / payout-to-creator logic is present (wallet is operator-topped, refunds credit the buyer's wallet only).
- **Workspace tiering** (v3) adds member limits + storage caps as an org-level dimension.
- **Not present:** metered usage billing, seat-based per-human pricing, marketplace creator payouts, Stripe-for-platform billing.

---

## TARGET USERS (ICP)

Inferred from the persona domain taxonomy, the feature surface, and the workspace/tier model. The 16 persona domains are the strongest signal of *who Flowmanner expects to use it*:

| ICP segment | Evidence anchor | Why they care |
|---|---|---|
| **Engineering / QA / DevOps** | `engineering` (29), `testing` (8) persona dirs; `mission_code_sandbox.py`, `graph.py`, `swarm_protocol.py` | Automate code review, test generation, pipeline orchestration, infra tasks |
| **Marketing / Paid Media / Sales** | `marketing` (30), `paid-media` (7), `sales` (8) dirs | Campaign copy, ad ops, outreach sequences, Lead workflows |
| **Product / Project Management** | `product` (5), `project-management` (6) dirs; `templates.py`, `roadmap.py` | Spec drafting, roadmap comms, sprint/PM automation |
| **Design** | `design` (8) dirs | Asset/UX generation workflows |
| **Finance / Legal / Support (specialized)** | `specialized` (41, largest), `finance` (5), `support` (6); `legal-billing-time-tracking.md` | Domain-specific expert agents (legal billing, finance ops, support triage) |
| **Game Development / Spatial Computing** | `game-development` (20), `spatial-computing` (6) dirs | Niche creative/3D workflows |
| **Academic / Research** | `academic` (5) dirs | Literature/research agents |
| **Platform / builders** | `agent_registry.py`, `marketplace.py`, `integrations.py`, Stripe/Linar/Browser connectors | Teams building their own agent tooling on the substrate |

**Buyer vs user:**
- **Primary user:** an individual operator / builder inside a function (marketer, engineer, PM, founder) who composes missions using domain personas.
- **Economic buyer:** the workspace owner/admin on a paid tier (`workspace_billing.py` `member_limit`, `billing_customer_id`) — typically a team lead or startup founder consolidating multiple function-automations onto one platform.
- **Marketplace creator:** advanced users who publish tools/capabilities/agents for others to install/purchase (`marketplace.py:126` create listing).

**Stage signal:** Free tier defaults (5 missions/day, 150/month, 1 concurrent — `subscription_models.py:21-23`) + PayPal monthly + community/roadmap/changelog transparency surfaces indicate a **self-serve PLG (product-led growth)** motion aimed at individuals/small teams, with Enterprise tier (20× rate multiplier, `has_custom_models`) as the land-and-expand ceiling.

---

## DIFFERENTIATION

vs. generic "AI agent builder" (e.g., raw LangChain/AutoGPT/n8n-with-LLM):

1. **The substrate (unified durable executor).** One `UnifiedExecutor` with 7 strategies replacing 7 bespoke executors; append-only event log is the source of truth; crash recovery via replay (`substrate/AGENTS.md` §"4 guarantees", `replay_engine.py`). Generic builders lack durable, replayable, observable execution.
2. **HITL governance as a first-class node.** `hitl_pause.py` implements true *pause-and-resume*: lease released, `RUN_PAUSED` emitted, human resolves via inbox, Celery resumes. APPROVAL/HUMAN_REVIEW node types. Most agent builders treat human-in-the-loop as an afterthought prompt; Flowmanner bakes it into the execution lifecycle.
3. **The 185-persona expert library across 16 domains.** Turns "write a system prompt" into "pick an expert." This is a curation/content moat generic builders don't have.
4. **Eval + regression harness.** LLM-as-judge rubric scoring (`llm_judge.py`) + substrate replay assertions with cost/latency ceilings (`assertion_engine.py`, `baseline_extractor.py`). Lets users prove a workflow still behaves after a model change — a reliability differentiator.
5. **Capability-bounded execution.** Tool calls require a `CapabilityToken` issued/verified by `CapabilityEngine`; every LLM call goes through `BudgetEnforcer`. Governance/guardrail posture vs. unbounded agent loops.
6. **Versioned, envelope-standardized API (v1/v2/v3) + workspace scoping.** `app/api/v2/AGENTS.md` (universal `ok/paginated/err` envelope, feature flags, 404-not-403 existence hiding). Enterprise-grade API hygiene.
7. **Marketplace creator economy + community templates.** Reusable agents/tools/templates with install/purchase/reviews — network-effects potential, though currently internal-credit only (see gaps).

---

## KEY FINDINGS

1. **Persona count is 185, not 216.** The brief's "216 expert personas" is not borne out: the shipped library is **185 markdown definitions across 16 domains** (`backend/agent_definitions/*`; `agent_personalities.py:93`). Treat "216" as aspirational.
2. **Marketplace is the only real economy.** Buy/sell/install of `TOOL`/`CAPABILITY`/`COMPOSED`/`AGENT` listings with an internal-credit wallet, reviews, and featured surfacing — fully DB-backed and tested (`marketplace.py`, `marketplace_db.py`, migration `20260605_marketplace.py`).
3. **Marketplace settlement is internal-credit only — no external PSP.** Purchases debit an operator-topped USD wallet; refunds credit the buyer. No creator payout / revenue-share logic exists (`marketplace_db.py:757-784`, `marketplace.py:249-261`). This caps the creator economy at "credits," not real money.
4. **Community router is missing despite models + SDK + migration existing.** `backend/app/api/v1/community.py` is referenced in `v1/AGENTS.md` and has ORM (`community_models.py`) + Alembic (`20260610_add_community_comments.py`) + SDK client models, but **the file is absent on disk** (verified). The community template economy is unfinished.
5. **Monetization = per-user PayPal subscription tiers (Free→Enterprise).** `subscription_models.py` defines `price_monthly`, mission quotas, API/custom-model flags, `paypal_plan_id`. Tier enforcement is via `tier_rate_limit.py` multipliers (free 1× → enterprise 20×). Stripe is an *OAuth connector for user accounts*, not Flowmanner's billing PSP (`stripe_oauth.py`).
6. **Workspace billing is v3-gated and partially live.** `workspace_billing.py` reads `subscription_tier_id`/`billing_customer_id` from `Workspace` (H4.1 migration) but requires `WORKSPACES_V3_BILLING` flag (404 when off). Adds member_limit (default 5) + 1 GiB storage cap.
7. **HITL is a genuine execution primitive, not a prompt trick.** `hitl_pause.py` pauses the run, releases the worker lease, and resumes via Celery after human inbox resolution — a real governance differentiator.
8. **The substrate is the core technical moat.** `UnifiedExecutor` + 7 strategies + append-only event log + replay recovery + CapabilityToken + BudgetEnforcer (`substrate/AGENTS.md`) make execution durable, bounded, and observable — distinct from generic agent loops.
9. **Evals are built-in.** LLM-as-judge (`llm_judge.py`) + substrate replay assertions with 1.5× cost / 2.0× latency headroom (`baseline_extractor.py`) let users regression-test workflows — a reliability differentiator unusual for this category.
10. **ICP is function-segmented by persona domains.** The 16 domains (engineering, marketing, sales, product, design, finance, legal/support, game-dev, spatial, academic…) are the de-facto segmentation map; PLG motion indicated by Free-tier defaults + PayPal + transparency surfaces (roadmap/changelog).

---

*End of analysis. Read-only — no code changed, no commit/push/deploy performed. Awaiting review.*
