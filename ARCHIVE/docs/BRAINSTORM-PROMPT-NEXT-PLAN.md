# Flowmanner — Next Plan Brainstorm Prompt

> **Instructions:** Copy everything below the `---` line into your frontier LLM. This prompt contains full context about the project's architecture, current state, completed work, known issues, and strategic options. The LLM should produce a detailed, prioritized execution plan for the next 2-4 weeks of work.

---

## ROLE

You are a senior platform architect and technical strategist. I need you to produce a detailed, prioritized execution plan for the next phase of my product, **Flowmanner** — an agentic AI workflow automation platform. I've spent 4 months building it and I'm at a critical inflection point: V1 is production-stable, and I need to decide what to build next to reach product-market fit.

I'm a solo founder/bootstrapper. I have limited time (10-15 hours/week) and need to maximize impact. Every hour spent on the wrong feature is a week of runway lost.

**Produce a plan that is:**
1. Prioritized by user value (not technical elegance)
2. Realistic for a solo developer (no "hire a team" suggestions)
3. Honest about what's worth building vs. what's premature
4. Specific enough to execute immediately (file paths, API designs, implementation order)
5. Critical — tell me what NOT to build and why

---

## WHAT IS FLOWMANNER?

Flowmanner is a **multi-agent AI workflow automation platform** — think "Zapier meets LangChain, but agents are first-class citizens that can be published, monetized, and composed into visual workflows."

### Core Value Proposition
Users create **Missions** (complex tasks) that are decomposed and executed by specialized **Agents**. Agents are composable, shareable via a **Marketplace**, and their execution is fully observable through a **Mission Observatory** with event sourcing and replay.

### Key Differentiators (planned)
1. **Sovereign Infrastructure** — runs on self-hosted hardware (not cloud-dependent)
2. **Cost-Aware Plan Selection** — generates K plan candidates, scores them, auto-selects best value
3. **Full Observability** — every agent action is traced, logged, and replayable
4. **Marketplace** — third-party developers publish agents/tools that users can install
5. **Human-in-the-Loop** — agents can pause and ask for human approval before destructive actions

---

## CURRENT ARCHITECTURE

### Infrastructure (2 machines)

```
Internet → VPS (IONOS, 74.208.115.142) → Nginx :443
  ├── /* → frontend:3000 (Next.js 16.2.6)
  ├── /api/* → WireGuard → Homelab:8000 (FastAPI)
  └── /api/auth/* → frontend:3000 (NextAuth)

Homelab (Arch Linux, i7-11700K, 62GB RAM, 2×RTX 5060 Ti 32GB VRAM):
  - FastAPI backend (Python 3.12)
  - PostgreSQL 16
  - Redis 7
  - Qdrant (vector search)
  - RabbitMQ + Celery workers
  - Jaeger (distributed tracing)
  - llama.cpp (Qwen3.6-27B local LLM)
```

### Tech Stack
- **Frontend:** Next.js 16.2.6, React 19, TypeScript, Tailwind CSS, TanStack Query, React Flow
- **Backend:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, Celery
- **Databases:** PostgreSQL (primary), Redis (cache), Qdrant (vectors), RabbitMQ (message broker)
- **Auth:** NextAuth JWT + v3 cookie-based auth (dual strategy)
- **Observability:** OpenTelemetry, Jaeger, Langfuse, Sentry
- **Deployment:** Docker Compose, bash scripts, no CI/CD

### API Surface
- **812 total routes** across v1 (legacy), v2 (public API), v3 (auth)
- **177 v2 routes** with cursor pagination, tier-based rate limiting, OpenAPI 3.1 spec
- **18 webhook integrations** (GitHub, Slack, Stripe, Jira, Asana, etc.)

### Frontend Pages (~100+ routes)
Dashboard, Missions, Agents, Chat, Marketplace, Costs, Analytics, Blueprints (with CRUD + executions), Mission Builder (React Flow), Mission Observatory (event timeline + plan comparison), Integrations, Developer portal, Admin panel, etc.

---

## WHAT'S BEEN BUILT (completed)

### V1 Phases 1-5 (COMPLETE)
- **P1:** Fixed auth infinite loop, broken pages, cleaned up fm_tokens
- **P2:** Substrate test suite (event log, replay, executor, chaos tests)
- **P3:** DB append-only trigger, orchestrator budget wiring, LISTEN/NOTIFY triggers
- **P4:** Observability (ntfy alerts, Langfuse dashboards, backup crons)
- **P5:** Docker hygiene (446GB reclaimed), fail2ban, ops machine cleanup, nginx health

### Recent Features (June 29 - July 1, 2026)
- **Cost-Aware Plan Selection:** K=3 plan candidates generated (heuristic + 2 LLM personas), scored, auto-selected. `BUDGET_AWARE_PLAN_SELECTION=auto` active in production.
- **Plan Comparison UI:** Frontend component showing candidates side-by-side with quality bars, cost/latency metrics, risk flags. Click-to-select with per-card loading states.
- **Event Bus:** Full pipeline with failure alerts (Slack), analytics endpoint, 18 integration webhooks wired.
- **Trigger Pipeline:** Cron-based triggers with proper cron matching, routed through UnifiedExecutor.
- **My Blueprints CRUD:** Tabbed Browse/Manage interface with create, edit, publish, delete, execute, execution history.
- **Pydantic v2 Migration:** Fixed 235 test failures (forward reference resolution).
- **Test Infrastructure:** 1016 tests passing (was 3553 failed + 79 errors at one point).

### Production Health (as of 2026-07-01)
- 10/10 Docker containers healthy
- Frontend: HTTP 200
- Backend: HTTP 200 (db ok, redis ok, langfuse healthy, LLM healthy)
- Alembic: `20260630_plan_candidates` (head)
- Tests: 1012 passed, 4 failed (plan selection mode edge cases), 3 skipped
- Disk: 47% used (965 GB free of 1.9 TB)

---

## KNOWN ISSUES & WEAKNESSES

### Open Weaknesses (from architecture audit)

| ID | Issue | Severity | Status |
|----|-------|----------|--------|
| W5 | No CI/CD pipeline | HIGH | Open — manual `deploy-backend.sh` / `deploy-frontend.sh` |
| W10 | WireGuard SPOF | MEDIUM | Open — if tunnel drops, entire API surface unreachable |
| W11 | Event sourcing untested | MEDIUM | Partial — built but no replay tests in production |
| W12 | No deterministic LLM testing | MEDIUM | Open — can't reproduce agent decisions |
| W13 | No agent evaluation framework | MEDIUM | Open — no systematic quality measurement |
| W14 | No execution sandbox isolation | HIGH | Open — agents run in-process, not sandboxed |
| W15 | No semantic caching | LOW | Open — repeated similar prompts re-call LLM |
| W16 | No prompt management | LOW | Open — prompts hardcoded in Python |
| W17 | No HITL primitives | MEDIUM | Open — no approval gates for destructive actions |

### Immediate Technical Debt
1. **4 test failures** — caused by `BUDGET_AWARE_PLAN_SELECTION=auto` changing planner code path
2. **No CI/CD** — all deploys are manual bash scripts
3. **WireGuard SPOF** — watchdog script + nginx graceful degradation recommended (25 min fix)
4. **100+ frontend routes** — many are stub pages with no real functionality
5. **v1 API surface** — 634 routes on v1 lack role-based access control

---

## WHAT'S PLANNED BUT NOT BUILT (V2 roadmap)

### Phase 6: Memory + HITL + Cost (4-6 weeks estimated)
1. **P6.1 Episodic Memory** — consolidation worker, Qdrant embeddings, forget policy
2. **P6.2 Human-in-the-Loop** — approval gates, Inbox UI, WebSocket push
3. **P6.3 Cost Attribution** — per-agent billing, workspace-level cost queries
4. **P6.4 Circuit Breakers** — per-mission limits, destructive action policy

### Phase 7: Plugin System (already partially built)
- Plugin runtime + sandbox (9.1-9.6 in NEXT-SESSION.md are marked COMPLETE)
- Custom Node SDK (Python)
- Marketplace integration
- Plugin security scanner
- Visual workflow builder integration (React Flow nodes)

### Explicitly Deferred (V3 / Never)
- ❌ Federation protocol — YAGNI
- ❌ Neo4j — Postgres + Qdrant suffice
- ❌ YAML agent DSL — Python is fine
- ❌ Multi-modal input — text-only for now
- ❌ Agent-to-human rich output — chat is fine for V1

---

## MY CONSTRAINTS

1. **Solo founder** — 10-15 hours/week of focused development time
2. **Bootstrapped** — no external funding, need to reach revenue or break-even
3. **Homelab-first** — can't afford cloud infrastructure, running on personal hardware
4. **No users yet** — the product is built but hasn't been marketed or launched
5. **Technical debt is real** — 634 v1 routes lack RBAC, no CI/CD, manual deploys
6. **Marketplace is empty** — no third-party publishers yet

---

## WHAT I NEED FROM YOU

Produce a detailed plan that answers these questions:

### 1. Strategic Direction
- Should I focus on getting users first (marketing/launch) or build more features first?
- What's the minimum feature set needed to attract early adopters?
- Is the current architecture over-engineered for a product with zero users?

### 2. Prioritized Next Steps (2-4 weeks)
- What are the 3-5 highest-impact things I should build next?
- For each item: what files to modify, estimated effort, expected impact, and success criteria
- What should I absolutely NOT build yet?

### 3. Go-to-Market Strategy
- Who is the ideal first user? (developer? ops team? AI researcher?)
- What's the distribution channel? (Hacker News? Product Hunt? GitHub?)
- Should I open-source it? Freemium? Paid-only?

### 4. Revenue Model
- What's the most realistic path to first dollar?
- Marketplace commission? SaaS subscription? Self-hosted license?
- What pricing tier structure makes sense?

### 5. Technical Priorities
- Should I fix the test failures and WireGuard SPOF first, or ignore them and ship features?
- Is CI/CD worth investing in before having users?
- Should I consolidate the 100+ frontend routes into fewer, polished pages?

### 6. Risk Assessment
- What are the biggest risks to this project succeeding?
- What would make me shut it down?
- What pivot options exist if the current approach doesn't work?

---

## ADDITIONAL CONTEXT

### Competitive Landscape
- **LangChain/LangGraph** — open-source, developer-focused, no visual builder
- **CrewAI** — multi-agent, but no marketplace or observability
- **Zapier** — no-code, but no AI agents, no self-hosting
- **n8n** — open-source workflow automation, but no agent-native design
- **Dify** — open-source LLM app builder, closest competitor but cloud-first

### My Strengths
- Deep technical execution (4 months, 812 API routes, 100+ pages, full observability stack)
- Sovereign infrastructure story (privacy-conscious enterprises)
- Cost-aware plan selection (unique feature)
- Full event sourcing + replay (debugging superpower)
- 18 pre-built integrations (GitHub, Slack, Jira, Stripe, etc.)

### My Weaknesses
- Zero users, zero revenue
- Over-engineered for current stage
- No marketing or distribution
- Technical debt in auth, testing, deployment
- Solo founder = bus factor of 1

---

## OUTPUT FORMAT

Please structure your response as:

1. **Executive Summary** (3-5 sentences: what to do, why, in what order)
2. **Strategic Assessment** (honest evaluation of where I am)
3. **Prioritized Plan** (numbered list, each item with: what, why, effort, impact, files)
4. **What NOT to Build** (explicit list with reasoning)
5. **Go-to-Market Recommendation** (specific, actionable)
6. **Revenue Path** (first dollar timeline and method)
7. **Risk Matrix** (top 5 risks with mitigations)
8. **30-60-90 Day Milestones** (concrete checkpoints)

Be brutally honest. I'd rather hear "this is over-engineered, simplify" than "great work, keep building."









DRAFT REPLY Claude Opus 4.6

Date: 2026-07-01 Author: Strategic analysis synthesizing all prior plans, audits, and competitive assessments Timeframe: 30/60/90 days (July – September 2026) Constraint: Solo founder, 10-15 hours/week

1. Executive Summary
Stop building. Start showing.

You have 812 API routes, 100+ frontend pages, 1012 passing tests, a fully event-sourced substrate with 6 completed agentic workflow chunks, cost-aware plan selection, 18 integration webhooks, and zero users. The next dollar of value comes not from another backend feature, but from proving the system works in a way that makes someone want to use it.

The plan in five sentences:

Week 1-2: Build the "killer demo" — a 90-second screen recording of a mission executing with live cost tracking, HITL approval, and time-travel replay. This is your launch asset.
Week 3-4: Polish the one end-to-end loop (create blueprint → run → observe → replay) until it's flawless for a stranger.
Week 5-6: Launch on Hacker News with the demo, a blog post, and a self-hosted Docker install path.
Week 7-8: Respond to the first 10 users' feedback. Fix only what they hit.
Week 9-12: Build the first monetizable feature based on real usage data, not speculation.
Everything else — marketplace, plugins, more integrations, multi-modal I/O, federation, YAML DSL — is premature until you have 10 active users who can tell you what they actually need.

2. Strategic Assessment
The Honest Diagnosis
Dimension	Score	Assessment
Technical depth	A	812 routes, event-sourced substrate, cost-aware planning, HITL, circuit breakers — this is deeper than most funded startups
Product coherence	D	100+ routes, many stubs; the "happy path" for a new user is unclear; no one has ever signed up cold
Distribution	F	Zero users, no waitlist, no content, no community. The site says "Run AI Workflows" but a visitor can't try it.
Revenue readiness	F	No billing, no trial, no pricing page that connects to anything real
Competitive positioning	B	"Accountable workflows on sovereign infrastructure" is a genuine niche that LangGraph/CrewAI/MAF won't fully cover
Sustainability	C-	Solo founder, bootstrapped, 10-15h/week. Bus factor of 1. No revenue timeline.
The Core Problem
You've been building depth when you need surface area. The substrate is excellent. The agentic chunks are well-designed. But no one outside your homelab has ever seen any of it work. You're at the stage where a polished 90-second demo is worth more than 50 new API endpoints.

Is It Over-Engineered?
Yes, for a product with zero users — but that's not as bad as it sounds. The engineering isn't wasted; it's premature. The event-sourced substrate, the cost attribution, the HITL gates — these are the right things to have for the "accountable workflows" positioning. The problem is you built them before proving anyone wants "accountable workflows." The fix isn't to throw them away; it's to stop building more of them and start showing what you have.

What Your Prior Analysis Already Told You
Your own Opus analyses from June 23 were prescient:

"Stop selling 'durable workflows.' Start selling 'accountable workflows.'" —
Competitive Durability Assessment

"FlowManner's value was never 'make the LLM work.' It was always 'make the LLM accountable.'" —
Frontier Model Impact

The strategic insight is correct. What's missing is the go-to-market execution that translates it into users.

3. Prioritized Next Steps (5 Items)
Priority 1: The Killer Demo (Week 1-2)
What: A 90-second screen recording showing FlowManner's unique value — a mission that plans, executes with live cost tracking, hits an approval gate, gets human approval, continues, completes, and then the user time-travel replays to inspect what happened and why.

Why: This single artifact is your launch material. It's what goes on Hacker News, in the blog post, on the landing page, and in every email you send. No demo = no launch. No launch = no users. No users = no revenue.

How:

Create a compelling mission template: "Research Report Agent" — takes a topic, searches the web, synthesizes findings, asks for human approval before publishing.
Run it live against your self-hosted Qwen3.6-27B. Show the $0.00 cost (sovereign infra!).
Show the approval gate popup, approve it, watch it finish.
Open the Mission Observatory. Click through the event timeline. Show cost per step.
Time-travel replay: scrub to an earlier state, show the "what if?" diff.
Record with OBS. Edit to 90 seconds. Export as MP4 + GIF.
Files to modify:

seed_templates.py — add 3-5 polished "hero" templates
Frontend: Mission Observatory page — ensure the event timeline renders cleanly
Frontend: Plan Comparison UI — ensure it loads without errors
Frontend: HITL approval UI — ensure it works end-to-end
Effort: 10-15 hours (1 week at your pace) Impact: ★★★★★ — This is the single highest-leverage thing you can do. Success criteria: A stranger watches the demo and says "I want to try this."

Priority 2: Stranger-Proof the Happy Path (Week 3-4)
What: Make the exact sequence "sign up → create blueprint → run it → see results → replay" work flawlessly for someone who has never seen your codebase.

Why: The demo gets them to the site. The happy path keeps them. If they sign up and hit a broken page, an auth loop, or a "coming soon" stub, they're gone forever.

How:

Audit every page on the happy path. Sign up fresh. Walk through every screen. Fix every broken thing.
Kill or hide stub pages. The 100+ routes include many that show empty states or "coming soon." Hide navigation links to unfinished pages. Better to show 10 polished pages than 100 broken ones.
Fix the LLM default. The 60-day plan noted LLM_PROVIDER=deepseek in .env — should default to local llama.cpp for the self-hosted story.
Add one E2E Playwright test for the happy path: signup → create → run → observe.
Files to modify:

Frontend sidebar/navigation — hide links to stub pages
.env / backend/app/config.py — default LLM_PROVIDER=llamacpp
e2e/happy-path.spec.ts — new Playwright test
Various frontend pages on the critical path — cosmetic fixes
Effort: 15-20 hours (2 weeks) Impact: ★★★★☆ — Converts demo-watchers into users Success criteria: A friend/colleague can sign up, run a mission, and see results without asking you for help.

Priority 3: Launch on Hacker News (Week 5-6)
What: Write a "Show HN" post with the demo, the positioning, and a self-hosted Docker install path.

Why: HN is the single best distribution channel for a self-hosted, sovereignty-focused, technically deep product. Your ideal first user lives on HN. The post writes itself: "I built an open-source alternative to LangGraph that runs on your own hardware with full audit trails and cost tracking."

How:

Write the HN post. Lead with the problem ("AI agents are black boxes"), not the solution.
Create a docker compose one-command install for self-hosted users.
Write a blog post on flowmanner.com with technical depth (architecture, design decisions, why event-sourcing matters for AI governance).
Ensure the landing page has: the demo video, a "Get Started" button that works, pricing (even if it's "free for self-hosted, contact us for managed").
Post on a Tuesday or Wednesday between 8-10am ET.
Files to modify:

Landing page content — embed demo video, update copy
docker-compose.dev.yml or new docker-compose.quickstart.yml — one-command install
Blog post (new page)
README.md — quick start instructions
Effort: 10-15 hours (1 week focused on content, 1 week on install path) Impact: ★★★★★ — This is your distribution. Without it, the product doesn't exist in the market. Success criteria: 100+ HN upvotes, 10+ sign-ups, 3+ people who actually run a mission.

Priority 4: User Feedback Sprint (Week 7-8)
What: Talk to every person who signed up. Fix what they hit. Ignore everything else.

Why: Your first 10 users will tell you more about what to build next than any roadmap document. Their pain points are your product roadmap.

How:

Email/DM every sign-up. Ask: "What did you try? Where did you get stuck? What would make you use this daily?"
Set up a simple feedback channel (GitHub Issues, Discord, or even a shared Google Doc).
Fix the top 3 issues users report. Ship fixes within 48 hours.
Do NOT build new features. Only fix broken things and polish rough edges.
Effort: 10-15 hours (responding + fixing) Impact: ★★★★☆ — Real user data > all speculation Success criteria: 3 users complete the full loop (create → run → observe) without intervention.

Priority 5: First Revenue Experiment (Week 9-12)
What: Based on user feedback, build the first thing someone would pay for. Likely candidates:

Candidate	Signal to watch for	Revenue model
Managed hosting	"I don't want to run Docker on my own server"	$49/month SaaS
Team/workspace features	"Can my team see the missions?"	$149/month team plan
Priority support	"I'm stuck and need help"	$99/month support tier
Custom integrations	"Can it connect to our [X]?"	One-time consulting ($500-2000)
Why: You need signal before building billing. The first revenue might be consulting, not SaaS. That's fine — consulting validates demand.

Effort: Variable — depends entirely on user feedback Impact: ★★★☆☆ initially, but this is the path to sustainability Success criteria: First dollar earned from FlowManner.

4. What NOT to Build
CAUTION

These items will feel productive but are value-destroying at your current stage. Do not build them until you have 50+ active users.

Item	Why Not	When to Reconsider
Agent Marketplace	Zero publishers, zero users. A marketplace with no supply AND no demand is a ghost town.	When you have 20+ users who ask "can I share my agent?"
Plugin System	Same as marketplace. Who's writing plugins?	When 5+ users ask for extensibility
More backend features (episodic memory, advanced routing, reflexion)	Your Q2-Q3 agentic chunks are already complete. The substrate is sufficient. Adding more substrate before proving anyone uses the current one is engineering for engineering's sake.	When users report specific capability gaps
CI/CD pipeline	You deploy manually ~2x/week. At this scale, manual deploys are fine. CI/CD is a scaling investment for a team, not a solo founder with no users.	When you have a second contributor or deploy >1x/day
Billing/Stripe integration	Premature. Your first revenue will be manual (PayPal, bank transfer, consulting invoice). Building Stripe integration before having a customer is building a cash register before opening the store.	When you have 5+ paying customers
More integrations beyond existing 18	18 webhooks is already more than most competitors at launch. Ship what you have.	When users ask for specific integrations
v1 API RBAC cleanup (634 routes)	Technical debt that affects zero users. The v2 API has proper RBAC.	When you deprecate v1
WireGuard SPOF fix	Yes, it's a SPOF. But with zero users, downtime costs nothing. A 25-minute fix can wait.	When you have paying customers who care about uptime
Test failure fixes (4 remaining)	Edge cases in plan selection mode. They don't affect the user-facing product.	When you work on that code area again
Frontend route consolidation	Hiding stub pages (Priority 2) is the 80/20 fix. A full route consolidation is a multi-week refactor with no user-facing value.	Never — just hide the stubs and move on
5. Go-to-Market Recommendation
Ideal First User
The DevOps/SRE engineer at a 20-200 person company who is already using AI tools (Copilot, ChatGPT) but frustrated by:

Black-box AI agents they can't audit
Cloud-only AI platforms that don't meet their data residency requirements
LangChain/CrewAI complexity without observability
No cost visibility on AI agent spending
Why this persona:

They understand Docker, self-hosting, and event logs (your onboarding friction is zero for them)
They have the authority to adopt tools for their team
They have budget for developer tools ($50-200/month is noise in their tooling spend)
They hang out on Hacker News, Reddit r/selfhosted, and DevOps-focused Discords
Distribution Strategy
Channel	Priority	Action	Expected Outcome
Hacker News "Show HN"	P0	Post with demo + self-hosted install + architecture blog post	100-500 visitors, 10-50 sign-ups
Reddit r/selfhosted	P0	Cross-post focusing on the sovereignty angle	50-200 visitors from the privacy-conscious crowd
Reddit r/LocalLLaMA	P1	Post focusing on running agents on your own GPUs	30-100 visitors from the local LLM community
Dev.to / Hashnode blog	P1	Technical blog: "Why I Event-Sourced My AI Agent Platform"	SEO + long-tail traffic
Product Hunt	P2	Save for a "v2 launch" with more polish	Broader but less targeted audience
Twitter/X	P2	Share the demo GIF + threading about design decisions	Slow burn, builds personal brand
YouTube	P3	Extended demo walkthrough (5-10 min)	Long-tail discovery, trust building
Open Source Strategy
IMPORTANT

Open-source the core platform. This is not optional — it's your distribution moat.

Why:

Your target persona (DevOps/SRE) expects self-hosted tools to be open-source. Closed-source self-hosted is a contradiction in their worldview.
Open-source is your defense against LangGraph Platform. They have $135M in funding and 200 employees. You have a Docker compose file. Your advantage is transparency and sovereignty — open-source IS that advantage.
Open-source creates distribution you can't buy: GitHub stars, contributor PRs, package registry installs, blog posts by users.
License: AGPL-3.0 (what n8n uses). Requires anyone running it as a hosted service to open-source their modifications. This protects you from cloud providers offering "managed FlowManner" while keeping self-hosters happy.

Revenue from open-source: See §6 below.

6. Revenue Path
Realistic Timeline to First Dollar
Milestone	Timeline	Revenue
HN launch + first sign-ups	Week 5-6 (mid-August)	$0
First consulting engagement ("help me set up FlowManner for my use case")	Week 8-10	$500-2000 one-time
First paid support subscription	Month 3-4	$99/month
First managed hosting customer	Month 4-6	$149-499/month
MRR reaches $1000	Month 6-9	$1000/month
Revenue Model: Open-Core + Managed Hosting
Tier	Price	What's Included	License
Community (self-hosted)	Free	Full platform, unlimited missions, community support	AGPL-3.0
Pro (self-hosted)	$29/month	Priority support, advanced analytics dashboard, team RBAC	Commercial add-on
Team (managed hosting)	$149/month	Hosted on your infra, managed updates, SLA, 5 seats	Commercial hosted
Enterprise	Custom ($500+/month)	Dedicated instance, custom integrations, consulting	Commercial
Why open-core over pure SaaS:

You can't afford cloud infrastructure for SaaS. Your homelab IS the product.
Self-hosted resonates with your ICP (DevOps/SRE teams who distrust cloud AI).
Open-core creates a funnel: free users → paying support/features → enterprise contracts.
AGPL ensures cloud providers can't freeload.
Why NOT marketplace commission: Marketplace commission requires (a) publishers, (b) buyers, (c) a payment system. You have none of these. It's a year-2 revenue stream at the earliest.

First Dollar — Most Realistic Path
Consulting. After the HN launch, 1-2 users will ask "can you help me set up FlowManner for [specific use case]?" Say yes. Charge $100-200/hour. This validates demand AND tells you what to build next.

7. Risk Matrix
#	Risk	Probability	Impact	Mitigation
R1	Nobody cares — the HN post gets 0 traction, no sign-ups	Medium	Critical	Iterate on positioning. Try r/selfhosted, r/LocalLLaMA, dev.to. If 3 channels fail, the problem is the product, not distribution. Pivot to consulting/services.
R2	Demo falls apart — the happy path breaks during recording or when strangers try it	High	High	Test obsessively. Record multiple takes. Have a fallback pre-recorded demo. The Playwright E2E test (Priority 2) catches regressions.
R3	LangGraph Platform ships "good enough" accountability — per-node cost tracking + managed replay dashboard in LangGraph 3.0	Low (18mo)	Critical	Their license-server phone-home is structural. Their event model is checkpoint-based, not event-sourced. Double down on sovereignty + forensic audit. But if they close the gap, pivot to being a LangGraph ecosystem tool (observability plugin).
R4	Burnout — 10-15h/week on a project with zero users, zero revenue, for 4+ months	High	Critical	The 30-day milestone (demo + HN post) is designed to create external validation quickly. If the HN post gets traction, it's energizing. If it doesn't, you have signal to pivot or pause.
R5	Homelab failure — hardware dies, losing the production environment	Low	Critical	Ensure backups are current (backup-flowmanner.sh runs on cron). Document the full rebuild procedure. Consider a cold standby on cheap VPS.
R6	Auth breaks for new users — the dual-auth system (NextAuth JWT + Zustand fm_tokens) has a history of 401 loops	Medium	High	Priority 2 includes an E2E test for the sign-up → use flow. The auth issues were fixed in previous phases, but this is the highest-risk area for new users.
R7	Scope creep — you start building "just one more feature" before launching	High	High	This plan is the scope boundary. Print it out. Tape it to your monitor. If it's not in Priorities 1-3, it doesn't exist until August.
What Would Make You Shut It Down?
Three distribution channels fail — HN, Reddit, and dev.to all get <10 visitors. This means the market doesn't care about the problem you're solving.
Zero retention after 30 days — 10+ people sign up, but none come back. This means the product doesn't deliver value.
A well-funded competitor ships your exact positioning — LangGraph Platform adds event-sourced audit + AGPL self-hosted. Unlikely but possible.
Pivot Options If Current Approach Fails
Pivot	When to Consider	What Changes
Consulting-first	If the product gets interest but not self-serve adoption	Stop building product features. Offer "AI workflow audit" as a service using FlowManner as your internal tool.
Observability-only	If users care about audit/replay but not orchestration	Strip the orchestration layer. Become "LangSmith for self-hosted" — an observability tool that plugs into LangGraph/CrewAI/etc.
Open-source library	If the platform is too much but the substrate is valued	Extract the event-sourced substrate as a Python library (pip install flowmanner-substrate). Let others build on it.
Sell the tech	If no market traction after 6 months	The codebase is genuinely impressive. An AI observability startup might acquire the substrate code.
8. 30-60-90 Day Milestones
Day 30 (August 1): "The Demo"
 3-5 polished mission templates seeded (Research Agent, Code Review, Data Pipeline)
 Killer demo recorded (90 seconds, shows plan → execute → approve → replay)
 Happy path works for strangers (sign up → create → run → observe)
 Stub pages hidden from navigation
 E2E Playwright test for happy path passes
 Blog post draft written
 Docker quickstart tested on a clean machine
Exit gate: Show the demo to 3 people who've never seen FlowManner. All 3 understand what it does.

Day 60 (September 1): "The Launch"
 HN "Show HN" posted
 Blog post published on flowmanner.com
 Cross-posted to r/selfhosted and r/LocalLLaMA
 README.md has quickstart instructions
 Landing page has demo video embedded
 10+ sign-ups from organic traffic
 Feedback channel established (GitHub Issues or Discord)
 First user completes the full loop without assistance
Exit gate: At least 3 users have run a mission on their own infrastructure.

Day 90 (October 1): "First Revenue Signal"
 Top 3 user-reported issues fixed
 At least 1 consulting engagement or support inquiry
 Decision made on open-source license (AGPL-3.0 recommended)
 If traction: start building the #1 user-requested feature
 If no traction: post-mortem written, pivot decision made
 Monthly active users tracked (target: 10+)
 First revenue earned (even $1 counts)
Exit gate: You have data — either you're growing (continue) or you're not (pivot/pause).

9. The One-Page Summary
┌─────────────────────────────────────────────────────────┐
│                    STOP BUILDING                        │
│                    START SHOWING                        │
│                                                         │
│  Week 1-2:  Record the killer demo                     │
│  Week 3-4:  Polish the happy path for strangers        │
│  Week 5-6:  Launch on Hacker News                      │
│  Week 7-8:  Listen to users, fix what they hit         │
│  Week 9-12: Build what they'll pay for                 │
│                                                         │
│  DO NOT:                                                │
│  - Build more backend features                         │
│  - Set up CI/CD                                        │
│  - Fix technical debt                                  │
│  - Build marketplace/plugins/billing                   │
│  - Consolidate frontend routes                         │
│  - Add more integrations                               │
│                                                         │
│  YOUR MOAT: "Accountable workflows on sovereign infra" │
│  YOUR DEMO: Plan → Execute → Approve → Replay          │
│  YOUR ICP:  DevOps/SRE at 20-200 person company       │
│  YOUR CHANNEL: Hacker News → r/selfhosted → dev.to    │
│  YOUR FIRST $: Consulting ($100-200/hr)                │
│                                                         │
│  IF IT WORKS:  Double down on what users love          │
│  IF IT DOESN'T: Pivot to observability-only or consult │
└─────────────────────────────────────────────────────────┘
Appendix A: Technical Decisions (Quick Answers)
Question	Answer	Rationale
Fix 4 test failures first?	No. They're edge cases in plan selection mode.	Zero user impact. Fix when you're in that code area.
Fix WireGuard SPOF?	No. Zero users = zero downtime cost.	25-minute fix that can wait until you have paying customers.
Invest in CI/CD?	No. Manual deploys are fine at 2x/week.	CI/CD is a scaling investment. You have no scale.
Consolidate 100+ frontend routes?	No. Hide stubs in navigation instead.	80/20 fix. Full consolidation is a week with no user value.
Open-source?	Yes, AGPL-3.0.	Your ICP expects it. It's your distribution advantage.
Default LLM to local?	Yes. LLM_PROVIDER=llamacpp	Sovereignty story only works if the default is sovereign.
Blueprint/Run cutover (Phases B-L)?	Defer. The dual-write layer works.	Finishing the cutover is a multi-week infrastructure project that changes nothing for users.
Appendix B: Prior Plans Cross-Reference
This plan is informed by and supersedes the following documents for sequencing decisions only (the technical designs in those documents remain valid):

Document	Status	Relationship
Q2-Q3 Agentic Workflow v1
✅ Complete (all 6 chunks shipped)	Foundation this plan builds on
Q2-Q3 Agentic Workflow v2
Strategic pivot applied	This plan adopts its "accountable > durable" thesis
60-Day Execution Plan
Superseded for sequencing	Cutover and memory work deferred in favor of launch
Deep Research Report
Pricing and competitive analysis reused	§6.2 pricing tiers adapted for open-core model
Competitive Durability Assessment
Core positioning thesis adopted	"Accountable workflows" framing from this doc
Frontier Model Impact
Investment priorities adopted	"Double down on control plane" thesis
Omega Roadmap
Architectural vision preserved	H1-H5 horizons remain the long-term north star
