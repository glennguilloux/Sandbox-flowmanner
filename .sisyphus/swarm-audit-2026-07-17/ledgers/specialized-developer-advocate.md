# Developer Advocate Ledger — [DA] best untold story

**Lens / verb:** PITCH — "what is the single most compelling, UNDER-TOLD story Flowmanner can tell, and what demo would prove it?"
**Persona:** specialized-developer-advocate (injected)
**Repo facts re-checked:** worktree `t_c59ff061`, branch `agent/2026-07-17-da/swarm`
**Mode:** READ-ONLY. No edits, no commits, no deploy.

---

## TL;DR headline

> **"215 production-grade agents + a built-in multi-agent debate engine you can call with one POST — Flowmanner is the fastest way to turn 'I need a legal reviewer and a security engineer to argue it out' into a scored decision."**

The untold story is NOT "we have a workflow builder." It is: **Flowmanner ships a 215-persona agent library AND a real, callable multi-agent protocol layer (debate / handoff / escalation) that most visitors never discover because it lives behind a SwarmDashboard, not a landing-page demo.**

---

## Top 5 findings

### 1. 215 expert personas ship in-repo, parsed from markdown frontmatter — a real, citable asset
- **Observation:** `backend/app/agent_definitions/**/*.md` holds 215 persona files across divisions (marketing, engineering, finance, sales, design, game-development, spatial-computing, academic, specialized, agent_personalities, support, testing, product, project-management, paid-media, browser).
- **Evidence:**
  - `backend/app/services/agent_parser.py:17` `AGENT_DEFINITIONS_DIR = .../"agent_definitions"` + `load_all_agents()` walks `**/*.md` (line 88).
  - `backend/app/api/v1/agent_personalities.py:21` resolves `agent_definitions/agent_personalities` and serves it via `GET /api/agent-personalities` (line 119) and `GET /api/agent-personalities/{path}` (line 125).
  - File count verified by directory listing: **215 `.md` files** under `backend/app/agent_definitions/`.
- **Severity:** HIGH (it is the single strongest differentiator vs Zapier/n8n/LangChain, and it is currently undocumented on the public surface).
- **Fact vs recommendation:** FACT.

### 2. A real multi-agent protocol layer exists — debate, handoff, escalation — wired to HTTP and an LLM judge
- **Observation:** Flowmanner is not just "run an agent." It has `DebateProtocol` (multi-agent debate with LLM judge scoring), `HandoffProtocol` (delegate/accept/reject/complete a task between agents), and `EscalationChain` (escalate on error with policy). These are exposed as REST endpoints.
- **Evidence:**
  - `backend/app/api/v1/swarm_protocol.py:23` router prefix `/protocol` → mounted at `/swarm`.
  - `POST /api/swarm/protocol/debate` — "Start a multi-agent debate with LLM judge scoring" (`swarm_protocol.py:104`, OpenAPI `openapi.json:23175`).
  - `POST /api/swarm/protocol/handoff/delegate`, `/handoff/{id}/accept|complete|reject` (`openapi.json:23256`+).
  - `POST /api/swarm/protocol/escalate` with `policy` enum `default|aggressive|conservative|never_escalate` (`swarm_protocol.py:62`, OpenAPI `openapi.json:23572`).
  - `GET /api/swarm/protocol/debates|handoffs|escalations|dead-letters` for full observability (`openapi.json:23439`, `23723`).
- **Severity:** HIGH (this is the "compose AI agents into a workflow" story made concrete — and it is callable today, not a roadmap item).
- **Fact vs recommendation:** FACT.

### 3. The swarm `execute` API supports a `debate` strategy — but the enum is `parallel|sequential|debate`, NOT "swarm"
- **Observation:** A developer following the "swarm" branding would guess `strategy: "swarm"`. The actual `ExecuteRequest` schema only accepts `parallel | sequential | debate`. The "swarm" naming lives on the protocol/debate layer and the `/api/swarm` execution endpoint, not as a strategy value.
- **Evidence:**
  - `openapi.json:41474` `ExecuteRequest.strategy` pattern `"^(parallel|sequential|debate)$"`, default `parallel`.
  - `ExecuteRequest` also exposes `max_agents` (1–10, default 5), `byok_key_id`, `model_override` (`openapi.json:41480`+).
  - `POST /api/swarm/execute` summary "Execute a goal using multi-agent orchestration" (`openapi.json:23050`).
- **Severity:** MEDIUM (a DX trap: the marketing word "swarm" is not a valid API value; a tutorial using `strategy:"swarm"` fails with 422).
- **Fact vs recommendation:** FACT (and a recommendation: align naming or document it).

### 4. 59 built-in mission templates span 6 categories — but AGENTS.md undercounts them (35) and the task brief repeats the stale number
- **Observation:** `templates/README.md` documents **59** built-in mission templates (Research & Analysis 5, Software Engineering 6, approval 6, automation 13, data_pipeline 13, integration 8 — note: README's own category count text says 17/12 but the catalog lists 13/8; see finding #5). Seeding is idempotent via `seed_templates.py` (`is_builtin=True`).
- **Evidence:**
  - `templates/README.md:2` "59 built-in mission templates shipped via `backend/seed_templates.py`."
  - `templates/README.md:7-14` idempotent seeding + adapter converts `default_plan` nodes/edges → substrate `Workflow`.
  - `backend/app/api/v1/__init__.py` (OPTIONAL tier) lists `templates.py` → `GET /api/agents/templates` (`openapi.json:1985`) and `POST /api/missions/advanced/templates/{id}/use` (`openapi.json:9133`).
- **Severity:** LOW–MEDIUM (great story fuel, but the catalog has an internal count mismatch and the brief's "35 templates" is stale).
- **Fact vs recommendation:** FACT (count mismatch is a recommendation to fix docs).

### 5. The "docs / changelog / roadmap / community story engine" angle in the task brief is STALE — those modules were deleted
- **Observation:** The task brief suggests: "Docs/community surface: `docs/`, `changelog`, `roadmap`, `community` modules — is there a story engine?" Evidence shows `community.py`, `changelog.py`, `roadmap.py`, `votes.py` were **deleted** in a prior Q3/Q4 pruning phase. They are not in the live API.
- **Evidence:**
  - `search_files` for `roadmap|changelog` across `backend/app/api/v1/*.py` → **0 matches**.
  - `ARCHIVE/docs/EXIT-AUDIT-2026-07-04-phase4-pruning.md:29,193-195` lists deletion of `community.py`, `changelog.py`, `roadmap.py`, `votes.py` (1,195 LOC) as Phase 4 of the pruning roadmap.
  - `openapi.json` has no `/api/roadmap`, `/api/changelog`, `/api/community` paths (only `/api/community/templates` is gone; confirmed absent in path grep).
- **Severity:** HIGH (for the orchestrator: do NOT let the synthesizer build a "story engine" narrative on top of deleted modules; it would be a factual error).
- **Fact vs recommendation:** FACT (and a recommendation: strike this angle from the squad's shared brief).

### (Bonus) A typed Python SDK exists and is publishable — `flowmanner-api-client`
- **Observation:** `sdk-python/flowmanner-api-client/` ships a generated-but-curated SDK with `FlowmannerClient`, `create_mission`, `execute_mission_async`, `wait_for_mission`, cost analytics, and a CLI (`flowmanner missions list`). This means the advocate's "every code sample must run without modification" rule is satisfiable for tutorials.
- **Evidence:** `sdk-python/flowmanner-api-client/README.md:14` (`FlowmannerClient`), `:19` (`create_mission`), `:104-120` (CLI `flowmanner missions ...`), `openapi.json` (1.3 MB full contract).
- **Severity:** MEDIUM (enables the demo hook below to be a real, runnable snippet).
- **Fact vs recommendation:** FACT.

---

## Biggest single miss / blind spot (this lens)

**The strongest asset (215 personas + a callable multi-agent debate/handoff/escalation protocol) is invisible from the developer's first 10 minutes.** There is no public landing-page demo, no Quick Start that says "POST one JSON to `/api/swarm/protocol/debate` and watch two of 215 agents argue, scored by an LLM judge." A visitor sees "Run AI Workflows" but cannot *try* the agent-swarm story without first constructing a full mission in the canvas. The DX gap is not capability — it is **discoverability of the protocol layer**. (Contrast: the SDK README shows mission CRUD but never mentions the swarm/debate endpoint — the most differentiated call in the whole API is absent from the SDK's headline example.)

---

## The single best demo hook

**"Two experts, one verdict — in 30 seconds."**
A copy-pasteable `curl` (or `flowmanner`-SDK) call that spins up a debate between two of the 215 shipped personas on a real engineering question, returns scored rounds, and proves the "compose agents" story with zero canvas, zero mission, zero setup.

```bash
# Prove the untold story in one call.
# agent_a / agent_b ids come from GET /api/agent-personalities
curl -X POST https://flowmanner.com/api/swarm/protocol/debate \
  -H "Authorization: Bearer $FLOWMANNER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Should we migrate our ETL pipeline from cron to event-driven workflows?",
    "agent_a_id": "engineering/devops-automator",
    "agent_a_name": "DevOps Automator",
    "agent_b_id": "engineering/security-engineer",
    "agent_b_name": "Security Engineer",
    "max_rounds": 3
  }'
# → returns debate_id; GET /api/swarm/protocol/debate/{id} shows each round + LLM judge score.
```

Why it wins: it is the *shortest path to the differentiated value*, it runs against real endpoints (`swarm_protocol.py:104`, `openapi.json:23175`), and it showcases two of the 215 personas + the judge in one shot. Pair it with the `POST /api/swarm/execute` + `strategy:"debate"` variant (`openapi.json:23050`, `41474`) for the "autonomous goal" framing.

> **Accuracy note for the demo author:** use `strategy: "debate"`, never `"swarm"` (finding #3). And do NOT reference `/api/roadmap|changelog|community` — deleted (finding #5).

---

## 3 ranked brainstorm recommendations

### Rec 1 — Ship a "Swarm in 30 seconds" landing-page demo + one-page Quick Start
- **Idea:** A public, no-auth-or-free-tier demo page that fires the debate call above live (or a recorded replay) and a Quick Start whose step 1 is the `curl` to `/api/swarm/protocol/debate`. Make the protocol layer the hero, not the canvas.
- **Why now:** The capability is GA and callable today; the only blocker is presentation. Every other angle (SDK, templates) is secondary to *showing the swarm*. First-10-minute DX is the advocate's #1 metric and it is currently failing.
- **Effort:** M (frontend page + one doc page; endpoints already exist, no API work).
- **File:line anchor:** `backend/app/api/v1/swarm_protocol.py:104` (`start_debate`), `openapi.json:23175`; frontend wiring target per `AGENTS.md` frontend-wiring-roadmap.

### Rec 2 — Publish the 215-persona catalog as a browsable, linkable gallery (and fix the count drift)
- **Idea:** A public `/personas` gallery generated from `agent_parser.load_all_agents()` (`agent_parser.py:74`), one card per persona with its frontmatter (name, emoji, color, division, description). Fix `templates/README.md` category counts (finding #4) and the brief's stale "35 templates."
- **Why now:** 215 personas is the headline differentiator vs any competitor; today it is a directory of `.md` files no developer ever browses. A gallery turns a repo asset into a marketing + SEO asset.
- **Effort:** M (read-only endpoint already exists at `agent_personalities.py:119`; needs a frontend view + doc sync).
- **File:line anchor:** `backend/app/services/agent_parser.py:74` (`load_all_agents`), `backend/app/api/v1/agent_personalities.py:119` (`list_agent_personalities`); doc fix at `templates/README.md:36`.

### Rec 3 — Add the swarm/debate call to the SDK headline example + align `strategy` naming
- **Idea:** (a) Make `FlowmannerClient` expose `debate(agent_a, agent_b, topic)` and show it as the SDK's first example (today the SDK README leads with `create_mission`, `sdk-python/flowmanner-api-client/README.md:14`). (b) Either accept `strategy:"swarm"` as an alias for `debate`, or document the enum prominently so tutorials don't 422 (finding #3).
- **Why now:** The SDK is the advocate's "code samples must run" guarantee. Leading with the most differentiated call (debate) makes every tutorial instantly more compelling, and fixing the `swarm` vs `debate` mismatch removes a guaranteed first-timer failure.
- **Effort:** S (SDK method wrapper + doc string; naming alias is a 1-line schema tweak in `swarm_service`/`ExecuteRequest`).
- **File:line anchor:** `sdk-python/flowmanner-api-client/README.md:14`; `openapi.json:41474` (`ExecuteRequest.strategy` pattern).

---

## Confidence & cross-check request

- **Confidence:** HIGH on findings 1, 2, 3, 5 (verified by file + OpenAPI path). MEDIUM on finding 4 (catalog count mismatch noted; 59 is the README's own headline number, but its per-category text disagrees — flag for a doc owner).
- **Single most important claim for the synthesizer to cross-check:** **Finding #5 — that `roadmap`/`changelog`/`community` are DELETED, not a "story engine."** The task brief explicitly points the squad at those modules; if another expert lens builds a narrative on them, it will be factually wrong. Confirm against `ARCHIVE/docs/EXIT-AUDIT-2026-07-04-phase4-pruning.md` before the final report cites them.
- **Second cross-check:** the `strategy:"debate"` vs `"swarm"` mismatch (finding #3) — verify no live endpoint accepts `swarm` as a strategy value before any tutorial uses it.

---

*Advocate's note (persona voice):* I'd lead the launch post with the debate demo, not the template gallery. Developers share "two AIs argued and an AI judge scored it" — that's the narrative hook that separates Flowmanner from "yet another Zapier." The 215 personas are the proof you can pick *any* two experts. Ship the 30-second demo first; everything else is a follow-on.
