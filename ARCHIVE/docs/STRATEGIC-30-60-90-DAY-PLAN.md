# Flowmanner Strategic 30/60/90 Day Plan

**Date:** 2026-07-02
**Author:** Strategic analysis (Gemini) synthesizing all prior plans, audits, and competitive assessments
**Timeframe:** 30/60/90 days (July – September 2026)
**Constraint:** Solo founder, 10-15 hours/week

---

## 1. Executive Summary

**Stop building. Start showing.**

You have 812 API routes, 100+ frontend pages, 1012 passing tests, a fully event-sourced substrate with 6 completed agentic workflow chunks, cost-aware plan selection, 18 integration webhooks, and zero users. The next dollar of value comes not from another backend feature, but from proving the system works in a way that makes someone want to use it.

**The plan in five sentences:**
- **Week 1-2:** Build the "killer demo" — a 90-second screen recording of a mission executing with live cost tracking, HITL approval, and time-travel replay.
- **Week 3-4:** Polish the one end-to-end loop (create blueprint → run → observe → replay) until it's flawless for a stranger.
- **Week 5-6:** Launch on Hacker News with the demo, a blog post, and a self-hosted Docker install path.
- **Week 7-8:** Respond to the first 10 users' feedback. Fix only what they hit.
- **Week 9-12:** Build the first monetizable feature based on real usage data, not speculation.

Everything else — marketplace, plugins, more integrations, multi-modal I/O, federation, YAML DSL — is premature until you have 10 active users who can tell you what they actually need.

---

## 2. Strategic Assessment

| Dimension | Score | Assessment |
|-----------|-------|------------|
| Technical depth | A | 812 routes, event-sourced substrate, cost-aware planning, HITL, circuit breakers |
| Product coherence | D | 100+ routes, many stubs; the "happy path" is unclear; no one has ever signed up cold |
| Distribution | F | Zero users, no waitlist, no content, no community |
| Revenue readiness | F | No billing, no trial, no pricing page that connects to anything real |
| Competitive positioning | B | "Accountable workflows on sovereign infrastructure" is a genuine niche |
| Sustainability | C- | Solo founder, bootstrapped, 10-15h/week. Bus factor of 1 |

**The Core Problem:** You've been building depth when you need surface area. The substrate is excellent. But no one outside your homelab has ever seen any of it work. A polished 90-second demo is worth more than 50 new API endpoints.

---

## 3. The 30/60/90 Day Plan

### 🎯 DAY 30 (August 1): "The Demo"

**Theme:** Prove the system works by recording the killer demo and polishing the happy path.

| # | Deliverable | Hours | Success Metric |
|---|------------|-------|----------------|
| 1 | **Killer Demo (90s recording)** — Plan → Execute → Approve → Replay, showing $0.00 cost on sovereign infra | 8-10 | A stranger watches it and says "I want to try this" |
| 2 | **3-5 Hero Templates** — Code Review Agent, Research Report, Data Pipeline (seed_templates.py) | 6-8 | Each template runs 20 times with excellent output |
| 3 | **Happy Path Audit** — Sign up → Create → Run → Observe works without console errors | 8-10 | A friend can complete the flow without asking for help |
| 4 | **Hide Stub Pages** — Remove navigation links to unfinished pages (10 polished > 100 broken) | 2-3 | Only functional pages appear in sidebar |
| 5 | **E2E Playwright Test** — One test covering the full happy path | 3-4 | Test passes in CI |

**Explicitly NOT building:** More backend features, CI/CD, billing, marketplace, test fixes.

**Exit gate:** Show the demo to 3 people who've never seen FlowManner. All 3 understand what it does.

---

### 🚀 DAY 60 (September 1): "The Launch"

**Theme:** Get the product in front of real users and gather feedback.

| # | Deliverable | Hours | Success Metric |
|---|------------|-------|----------------|
| 1 | **Hacker News "Show HN" Post** — Lead with the problem ("AI agents are black boxes"), not the solution | 4-6 | 100+ upvotes, 10+ sign-ups |
| 2 | **Blog Post** — Technical depth on architecture, why event-sourcing matters for AI governance | 6-8 | Published on flowmanner.com |
| 3 | **Docker Quickstart** — One-command self-hosted install (docker-compose.quickstart.yml) | 4-6 | Someone runs it on a clean machine in <15 min |
| 4 | **Cross-posts** — r/selfhosted (sovereignty angle), r/LocalLLaMA (local GPU angle) | 2-3 | 50+ visitors from each |
| 5 | **Landing Page Update** — Embed demo video, "Get Started" button, pricing (even if free for self-hosted) | 3-4 | Conversion from visit to sign-up measurable |

**Explicitly NOT building:** Billing integration, more integrations, marketplace, CI/CD pipeline.

**Exit gate:** At least 3 users have run a mission on their own infrastructure.

---

### 💰 DAY 90 (October 1): "First Revenue Signal"

**Theme:** Listen to users, fix what they hit, earn the first dollar.

| # | Deliverable | Hours | Success Metric |
|---|------------|-------|----------------|
| 1 | **User Feedback Sprint** — DM every sign-up, fix top 3 issues within 48 hours | 8-10 | 3 users complete the full loop without intervention |
| 2 | **First Revenue Experiment** — Based on feedback, build what someone will pay for | 10-15 | First dollar earned (consulting counts) |
| 3 | **Open-Source Decision** — AGPL-3.0 license (what n8n uses) | 2-3 | LICENSE file committed, README updated |
| 4 | **Monthly Active Users Tracking** — Basic analytics on mission completions | 2-3 | MAU metric visible on dashboard |

**Explicitly NOT building:** Billing/Stripe (manual first), marketplace, plugins, more features.

**Exit gate:** You have data — either you're growing (continue) or you're not (pivot/pause).

---

## 4. What NOT to Build

| Item | Why Not | When to Reconsider |
|------|---------|-------------------|
| Agent Marketplace | Zero publishers, zero users. Ghost town. | When 20+ users ask "can I share my agent?" |
| Plugin System | Same as marketplace. Who's writing plugins? | When 5+ users ask for extensibility |
| More backend features (episodic memory, advanced routing, reflexion) | Substrate is sufficient. Adding more before proving anyone uses the current one is engineering for engineering's sake. | When users report specific capability gaps |
| CI/CD pipeline | Manual deploys ~2x/week. At this scale, manual is fine. | When you have a second contributor or deploy >1x/day |
| Billing/Stripe integration | First revenue will be manual (PayPal, consulting invoice). Building Stripe before having a customer is building a cash register before opening the store. | When you have 5+ paying customers |
| More integrations beyond existing 18 | 18 webhooks is already more than most competitors at launch. | When users ask for specific integrations |
| v1 API RBAC cleanup (634 routes) | Technical debt affecting zero users. v2 API has proper RBAC. | When you deprecate v1 |
| WireGuard SPOF fix | Zero users = zero downtime cost. 25-minute fix can wait. | When you have paying customers who care about uptime |
| Test failure fixes (4 remaining) | Edge cases in plan selection mode. Don't affect user-facing product. | When you work on that code area again |
| Frontend route consolidation | Hiding stubs (Day 30 task) is the 80/20 fix. | Never — just hide stubs and move on |
| Blueprint/Run cutover (Phases B-L) | Dual-write layer works. Multi-week infrastructure project that changes nothing for users. | After launch, based on user needs |

---

## 5. Go-to-Market Strategy

### Ideal First User
The **DevOps/SRE engineer** at a 20-200 person company who is already using AI tools but frustrated by:
- Black-box AI agents they can't audit
- Cloud-only AI platforms that don't meet data residency requirements
- No cost visibility on AI agent spending

**Why this persona:** They understand Docker and self-hosting (zero onboarding friction), have budget ($50-200/month is noise), and hang out on Hacker News and r/selfhosted.

### Distribution Channels

| Channel | Priority | Action | Expected Outcome |
|---------|----------|--------|------------------|
| Hacker News "Show HN" | P0 | Post with demo + self-hosted install + blog | 100-500 visitors, 10-50 sign-ups |
| Reddit r/selfhosted | P0 | Cross-post focusing on sovereignty | 50-200 visitors |
| Reddit r/LocalLLaMA | P1 | Post focusing on running agents on own GPUs | 30-100 visitors |
| Dev.to / Hashnode | P1 | "Why I Event-Sourced My AI Agent Platform" | SEO + long-tail traffic |
| Product Hunt | P2 | Save for v2 launch with more polish | Broader but less targeted |
| Twitter/X | P2 | Share demo GIF + design decision threads | Slow burn, personal brand |

### Open-Source Strategy
**Open-source the core platform under AGPL-3.0.** This is not optional — it's your distribution moat.

- Your ICP expects self-hosted tools to be open-source
- It's your defense against LangGraph Platform ($135M funding, 200 employees)
- AGPL ensures cloud providers can't freeload while keeping self-hosters happy

---

## 6. Revenue Model

### Open-Core + Managed Hosting

| Tier | Price | What's Included | License |
|------|-------|-----------------|---------|
| Community (self-hosted) | Free | Full platform, unlimited missions, community support | AGPL-3.0 |
| Pro (self-hosted) | $29/month | Priority support, advanced analytics, team RBAC | Commercial add-on |
| Team (managed hosting) | $149/month | Hosted, managed updates, SLA, 5 seats | Commercial hosted |
| Enterprise | Custom ($500+/month) | Dedicated instance, custom integrations, consulting | Commercial |

### Realistic Timeline to First Dollar

| Milestone | Timeline | Revenue |
|-----------|----------|--------|
| HN launch + first sign-ups | Week 5-6 (mid-August) | $0 |
| First consulting engagement | Week 8-10 | $500-2000 one-time |
| First paid support subscription | Month 3-4 | $99/month |
| First managed hosting customer | Month 4-6 | $149-499/month |
| MRR reaches $1000 | Month 6-9 | $1000/month |

**Most realistic first dollar:** Consulting. After HN launch, 1-2 users will ask "can you help me set up FlowManner for [use case]?" Charge $100-200/hour.

---

## 7. Risk Matrix

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R1 | Nobody cares — HN post gets 0 traction | Medium | Critical | Try 3 channels. If all fail, the problem is the product, not distribution. |
| R2 | Demo falls apart during recording or when strangers try it | High | High | Test obsessively. Have fallback pre-recorded demo. E2E test catches regressions. |
| R3 | LangGraph ships "good enough" accountability | Low (18mo) | Critical | Their phone-home license is structural. Double down on sovereignty + forensic audit. |
| R4 | Burnout — 10-15h/week with zero validation for 4+ months | High | Critical | The 30-day milestone creates external validation quickly. |
| R5 | Homelab failure — hardware dies | Low | Critical | Backups on cron. Document rebuild procedure. |
| R6 | Auth breaks for new users | Medium | High | E2E test for sign-up → use flow. Highest-risk area. |
| R7 | Scope creep — "just one more feature" before launching | High | High | This plan is the scope boundary. If it's not in Days 30-90, it doesn't exist. |

### What Would Make You Shut It Down?
- Three distribution channels fail (HN, Reddit, dev.to all get <10 visitors)
- Zero retention after 30 days (10+ sign-ups, none return)
- A well-funded competitor ships your exact positioning

### Pivot Options
| Pivot | When | What Changes |
|-------|------|-------------|
| Consulting-first | Interest but not self-serve adoption | Stop building product. Offer "AI workflow audit" as service. |
| Observability-only | Users care about audit/replay but not orchestration | Strip orchestration. Become "LangSmith for self-hosted". |
| Open-source library | Platform too much, substrate valued | Extract substrate as pip install flowmanner-substrate |
| Sell the tech | No traction after 6 months | Codebase is impressive. AI observability startup might acquire. |

---

## 8. The One-Page Summary

```
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
```

---

## Appendix: Quick Technical Decisions

| Question | Answer | Rationale |
|----------|--------|----------|
| Fix 4 test failures first? | No | Edge cases in plan selection mode. Zero user impact. |
| Fix WireGuard SPOF? | No | Zero users = zero downtime cost. 25-minute fix that can wait. |
| Invest in CI/CD? | No | Manual deploys are fine at 2x/week. No scale yet. |
| Consolidate 100+ frontend routes? | No | Hide stubs in navigation instead. 80/20 fix. |
| Open-source? | Yes, AGPL-3.0 | Your ICP expects it. It's your distribution advantage. |
| Default LLM to local? | Yes. LLM_PROVIDER=llamacpp | Sovereignty story only works if default is sovereign. |
| Blueprint/Run cutover? | Defer | Dual-write layer works. Multi-week infra project, no user value. |

---

*This plan synthesizes: BRAINSTORM-PROMPT-NEXT-PLAN.md, STRATEGIC-90DAY-PLAN.md (June 5), FLOWMANNER-ROADMAP.md, HANDOFF-2026-07-01, EXIT-AUDIT-2026-07-01, tools-catalog-roadmap.json, WIREGUARD-WATCHDOG.md, and FLOWMANNER-CANONICAL-KNOWLEDGE.md.*
