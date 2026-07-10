# The A+E Plan — Sell the Deliverable, Prove It with Replay

**Date:** 2026-07-05
**Status:** ACTIVE — supersedes all prior strategic plans
**Grounded in:** `docs/THE-HONEST-BRAINSTORM-2026-07-05.md`, `docs/DEEP-DIVE-REPORT-2026-07-05-HERMES-ANALYSIS.md`, `docs/DEEP-DIVE-REPORT-2026-07-03.md`, `docs/ROADMAP-Q3-Q4-2026.md`, `docs/EXECUTION-PLAN-Q3-Q4-2026.md`

---

## The Key Insight

> You don't sell the replay. You sell the deliverable, and the replay is the proof.

Direction A (Audit Replay) alone is suicide — you can't out-market LangSmith/Langfuse as a solo dev. Direction E (Consulting) alone is fragile — you're selling time with no product story. But together: **consulting generates revenue and validates templates, and the replay proves the AI actually did the work.**

A client pays €500 for a competitive intelligence report. They get:
1. The report (the deliverable)
2. A shareable replay link showing exactly how the AI produced it (the proof)
3. A cost breakdown: "This report cost €0.12 in compute and took 4 minutes" (the margin story)

No other consultant can offer that. No SaaS can offer that. The replay is the trust layer.

---

## Phase 1: Weeks 1-4 — Three Things

### 1. Write 3 Mission Templates

Three templates that run on DeepSeek V4 Flash (or any capable model) and produce real deliverables:

| Template | What It Produces | Target Client | Price Point |
|----------|-----------------|---------------|-------------|
| **Code Review Agent** | Structured PR review with severity ratings, suggested fixes, and risk assessment | Dev teams, open-source maintainers | €200-500/review |
| **Competitive Intelligence Report** | Market analysis with competitor comparison, SWOT, and strategic recommendations | Startups, product teams | €500-2K/report |
| **Document Q&A System** | RAG-based Q&A over a client's document corpus, deployed on their infra | Legal, finance, compliance teams | €2K-5K/deployment |

**Implementation:**
- Backend: Seed templates in `MissionTemplate` table via migration or seed script
- Each template defines: name, description, category, system prompt, tool schemas, expected behaviors, strategy type
- Templates must work end-to-end: create mission → execute → produce deliverable → record events

### 2. Build Replay Export Endpoint

A new endpoint that takes a completed mission's event log and produces a shareable document:

**`POST /api/v1/missions/{mission_id}/export-replay`** → returns a self-contained HTML report

The report contains:
- Mission title and goal
- Step-by-step timeline of what the AI did (from substrate events)
- LLM calls: prompt → response (summarized)
- Tool calls: tool name → input → output (summarized)
- Token usage and cost breakdown
- Final deliverable (the output text/file)
- Timestamps and duration

**Why HTML?** Self-contained, shareable via URL, printable to PDF, works in any browser. No login required to view.

**Implementation:**
- New file: `backend/app/api/v1/replay_export.py`
- Reads events from `EventLog.get_events()`
- Renders to HTML using a Jinja2 template (or inline HTML builder)
- Returns `Response(media_type="text/html")` for direct browser viewing
- Also returns JSON format option for programmatic access

### 3. Rewrite the Landing Page

The current landing page pitches "Run AI Workflows For Your Clients — Build once, run forever." This communicates nothing.

**New landing page = service catalog:**

**Hero:** "I run AI workflows on my own GPUs. Here's what I can build for you."

**Three service cards:**
1. 📋 Code Review — "Automated PR review with severity ratings and suggested fixes. €200/review."
2. 🔍 Competitive Intelligence — "Market analysis and competitor comparison. Delivered in 15 minutes. €500/report."
3. 📚 Document Q&A — "Ask questions about your documents. Deployed on your infrastructure. From €2K."

**Proof section:** Each card links to a live replay demo showing the AI producing the deliverable.

**Cost transparency:** "Every run costs €0.00 in LLM compute because I own the hardware. You pay for the expertise, not the tokens."

**CTA:** "Get in touch" → email/form

**Implementation:**
- Rewrite `frontend/src/app/[locale]/(dashboard)/page.tsx` (or the public landing page)
- Minimal, focused, single-page
- No 115 pages. No marketplace. No community. Just: here's what I do, here's proof, here's how to hire me.

---

## Phase 2: Weeks 5-12 — Listen and Productize

After 3-5 completed client engagements, you'll know:

| If Clients Want... | Then Build... | Direction |
|---|---|---|
| "Can I run this myself on my own hardware?" | One-command Docker appliance with validated templates | **Direction B** (Local-LLM Appliance) |
| "I need to see exactly what the AI did for compliance" | Full observability dashboard with replay, assertions, cost tracking | **Direction A** (Audit Replay Product) |
| "Just keep doing it for me, here's money" | Recurring consulting retainer, refine templates | **Direction E** (Consulting at scale) |

**Premature Phase 3 planning is what got us to 812 routes and zero users.** Phase 2 is deliberately undefined because Phase 1 tells you what it should be.

---

## Phase 3: Months 4-6 — Deliberately Undefined

Whatever Phase 2's client feedback says. Could be:
- SaaS (if clients want self-serve)
- Appliance (if self-hosters are the market)
- Consulting firm (if the money is in services)
- All of the above (if you're lucky)

---

## The Kill List

Things to delete or permanently gate to support this plan:

| What | LOC | Action | Why |
|------|-----|--------|-----|
| Improvement loop Phases 3-6 | ~7,000 | Delete | Dead code, fake p-values, no DB tables |
| Dual-write (Mission ↔ Blueprint+Run) | ~500 | Remove | Mission canonical per `docs/DUAL-WRITE-DECISION.md` |
| STRATEGY_EXPERIMENTAL strategies | 0 (gated) | Keep gated | Swarm/pipeline/meta/langgraph fail on 27B model |
| Marketplace, community, changelog, roadmap | Already deleted | — | Done in Q3/Q4 cleanup |
| Domain agents (biotech, finance, legal) | Already deleted | — | Done in Q3/Q4 cleanup |
| 40 of 36 frontend pages (stubs/unwired) | TBD | Delete | Keep only: landing, dashboard, missions, observatory/replay, costs, settings, templates |
| i18n (reduce to English) | ~2,000 | Simplify | Zero international users; maintenance tax |
| PayPal + subscription billing | Already deleted | — | Done in Q3/Q4 cleanup |

**Total code to cut: ~9,500-10,000 LOC**

---

## What Stays (the Product Surface)

**15 pages maximum:**

| Page | Purpose |
|------|---------|
| Landing (public) | Service catalog with proof demos |
| Dashboard | Mission overview, quick stats |
| Missions list | Browse all missions |
| Mission detail | Single mission view |
| Mission replay | Event-sourced timeline (the crown jewel) |
| Mission replay export | Shareable HTML report |
| Templates gallery | Browse/use mission templates |
| Observatory | Multi-mission replay comparison |
| Costs | Token/cost tracking per mission |
| Settings | User settings, BYOK keys |
| Chat | AI conversation interface |
| Integrations | Webhook/OAuth connections |
| Inbox (HITL) | Human approval queue |
| Reliability | Error rates, circuit breaker status |
| Login/Register | Auth |

---

## Three Things To Do This Week

| # | Task | Deliverable | Time |
|---|------|-------------|------|
| 1 | **Write 3 mission templates** | Seed migration + template definitions | 1-2 days |
| 2 | **Build replay export endpoint** | `POST /missions/{id}/export-replay` → HTML | 1-2 days |
| 3 | **Rewrite landing page** | Service catalog with proof links | 1 day |

---

## LLM Provider

**Current:** DeepSeek (cloud) via `LLM_PROVIDER=deepseek`, `LLM_BASE_URL=https://api.deepseek.com/v1`
**Target:** DeepSeek V4 Flash (`deepseek-v4-flash` model identifier)
**Rationale:** Glenn wants cloud quality over local 27B model. Once customers arrive, build 384GB system for local LLM.

---

## Revenue Model

| Tier | Price | What They Get |
|------|-------|---------------|
| **Consulting** (Phase 1) | €200-5K per engagement | Custom AI workflow deliverable + replay proof |
| **Pro Templates** (Phase 2) | €49/mo | Premium template library + priority support |
| **Enterprise** (Phase 2+) | €499/mo | On-prem deployment, SSO, custom templates, SLA |

**First dollar target:** Week 2-3. One consulting engagement. €500 minimum.

---

## Provenance

This plan synthesizes Hermes's brainstorm (`THE-HONEST-BRAINSTORM-2026-07-05.md`), the independent deep-dive analysis (`DEEP-DIVE-REPORT-2026-07-05-HERMES-ANALYSIS.md`), the July 3 deep-dive (`DEEP-DIVE-REPORT-2026-07-03.md`), the Q3/Q4 roadmap (all 6 phases complete), and Glenn's directive: "I want DeepSeek V4 Flash more than my local ugly model at the moment."

Valid until: first client engagement, or next strategic pivot.
