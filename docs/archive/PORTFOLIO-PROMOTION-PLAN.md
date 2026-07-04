# Flowmanner × Portfolio Promotion Plan

**Date:** June 5, 2026
**Last Updated:** June 5, 2026
**Goal:** Drive traffic from Glenn's portfolio site (glennguilloux.com) to Flowmanner, establish credibility, and convert visitors into waitlist signups or demo users.

---

## ✅ COMPLETED (Session 1 — June 5, 2026)

### Flowmanner Platform (flowmanner.com)
- **Phase 0** ✅ — Close the Gate: fixed failing tests, killed ~120 dead files, deployed clean state
- **Phase 1** ✅ — Runaway Agent Simulator: seed script created demo blueprints, blueprints list page (`/blueprints`), runs list page (`/runs`), "Replay to here" button on timeline events, nav links added
- **Phase 2** ✅ — Substrate Visibility: replay-at-sequence, auto-assertions endpoint, CQRS wiring, run diffing (commit 083d808)
- **Phase 3 (partial)** ✅ — New demo-first landing page at flowmanner.com ("Your AI agents. Your budget. Your control."), blog post drafted at `docs/blog-how-to-run-ai-agents-without-going-bankrupt.md`

### Portfolio Site (glennguilloux.com)
- **flowmanner.html** ✅ — New dedicated showcase page (480 lines): hero, runaway agent story with mock timeline, three layers of protection, features grid, stats & tech stack, CTA/waitlist section
- **ai-system-building.html** ✅ — Added Flowmanner case study section after Real-World Case Studies: mock timeline, three-layer cards, stats badges, tech stack badges, CTA to live demo. Emoji replaced with FontAwesome icons.
- **autonomous-operations.html** ✅ — Added circuit breaker deep-dive section: $487 problem narrative, LLM pricing table, state machine diagram (ARMED→TRIGGERED→CIRCUIT_BROKEN), demo timeline with FontAwesome icons, code snippet, CTA
- **ai-web-dev.html** ✅ — Added Flowmanner orchestration backend section: 4 feature bullets, tech stack grid with icons, CTA to flowmanner.com
- **main.js** ✅ — Updated all Flowmanner references: diagnostics detail mentions circuit breakers/replay/assertions, panel copy updated with 557 endpoints/sovereign deployment, specs updated (EN + FR)
- **root-translations.js** ✅ — Added 100+ French translation entries for all new sections (fm_*, cb_*, fm_webdev_*)

### Remaining Work
- 🔴 Capture screenshots of the Flowmanner demo for portfolio + blog post
- 🔴 Publish blog post as HTML page on the portfolio
- 🔴 Record 60-second demo video
- 🟡 Add nav link to flowmanner.html in existing portfolio pages
- 🟡 SEO optimization across all pages (keywords, meta descriptions)
- 🟡 Wire waitlist form to a real backend endpoint on flowmanner.com
- 🟡 Cross-linking: Portfolio ↔ Flowmanner (about page, GitHub README)
- 🟡 Social media content: Twitter/X thread + HN submission
- 🟡 Enhance cognitive-amplification.html and sense-making.html with Flowmanner mentions
- 🔵 Add French translations for remaining non-Flowmanner sections (71 existing keys on autonomous-operations.html)
- 🔵 Normalize encoding style in root-translations.js (mixed raw UTF-8 vs \uXXXX escapes)

---

## Current State of the Portfolio

### What Exists Now (after Session 1)
- **Dedicated Flowmanner showcase page** — `flowmanner.html` with full demo story ✅
- **Flowmanner sections on 3 service pages** — ai-system-building, autonomous-operations, ai-web-dev ✅
- **Updated main.js** — Flowmanner references mention circuit breakers, replay, assertions ✅
- **Flowmanner link in nav** — `ai-system-building.html` has an "AI Workflows" nav item pointing to `flowmanner.com` ✅
- **100+ French translations** — All Flowmanner section keys translated ✅
- **Blog post drafted** — `docs/blog-how-to-run-ai-agents-without-going-bankrupt.md` (not yet on portfolio)
- **AI Maturity Framework** — 6-layer model that perfectly frames Flowmanner's value
- **Bilingual** — EN/FR support via `root-translations.js` and `lang-toggle`

### Still Missing
- No screenshots/demo video on the portfolio pages
- Blog post not yet published as HTML on the portfolio
- Waitlist form on flowmanner.com is a no-op (no backend)
- No SEO optimization done yet
- cognitive-amplification.html and sense-making.html untouched
- No social media content created yet

---

## The Strategy: "Show, Don't Tell"

The portfolio already positions Glenn as an AI systems expert. Flowmanner is the **proof** — it's not just consulting advice, it's a production platform. The promotion should feel like a natural extension of the existing content, not an ad.

### Positioning Matrix

| Portfolio Page | Flowmanner Angle | CTA |
|----------------|-------------------|-----|
| `ai-system-building.html` | "Layer 5-6 in production" — Flowmanner IS the autonomous operator with safety | "See it live" → /blueprints |
| `autonomous-operations.html` | Circuit breakers = the safety & governance layer | "Try the demo" → /blueprints |
| `ai-web-dev.html` | Flowmanner as the orchestration backend for AI web apps | "Explore the platform" → flowmanner.com |
| `cognitive-amplification.html` | Replay = understanding what the AI "thought" | "Watch a replay" → /runs |
| `sense-making.html` | Auto-assertions = automated sense-making of agent behavior | "See assertions" → /runs |
| **NEW: `flowmanner.html`** | Dedicated showcase page | "Join waitlist" → /#waitlist |

---

## Execution Plan

### Phase A: Dedicated Flowmanner Showcase Page (HIGH IMPACT)

**Create `flowmanner.html`** — a full showcase page following the portfolio's existing design patterns (Tailwind, FontAwesome, bilingual, cinematic styling).

#### Content Structure:

1. **Hero Section**
   - Headline: "AI Agent Orchestration — With Guardrails"
   - Subheadline: "Version, replay, and debug every AI agent run. Circuit breakers that guarantee your agents never go rogue."
   - CTAs: "Try the Live Demo" → flowmanner.com/blueprints, "Join Waitlist" → flowmanner.com/#waitlist
   - Visual: Embedded screenshot of the Run Timeline with cost trajectory

2. **The Problem** (mirrors the blog post)
   - "Your AI agent just spent $487 in an afternoon"
   - LLM pricing table (GPT-4o, Claude, DeepSeek)
   - Real-world horror stories (airline chatbot, unauthorized spending)

3. **The Demo** (interactive or video)
   - Option A: Embed the 60-second demo video (once recorded)
   - Option B: Link to the live demo with a screenshot preview
   - Option C: Animated GIF of the circuit breaker catching the runaway agent

4. **Three Layers of Protection**
   - Circuit Breakers — cost/time/iteration caps per agent run
   - Time-Travel Debugging — replay any run to any point in the event stream
   - Auto-Assertions — 5 behavioral baselines generated from successful runs

5. **Architecture Diagram**
   - Show the two-machine setup (VPS + Homelab)
   - Highlight: FastAPI, PostgreSQL, Redis, Qdrant, WireGuard, Nginx
   - Position as "sovereign deployment" — your data, your hardware

6. **Tech Stack Badge**
   - React/Next.js, Python/FastAPI, PostgreSQL, Redis, Qdrant, Docker, WireGuard
   - This matches the portfolio's own tech stack — reinforces credibility

7. **Social Proof / Metrics**
   - 557 API endpoints documented
   - 7 strategy types (Solo, DAG, Pipeline, Graph, Swarm, Meta, LangGraph)
   - 67 backend tests passing
   - Open-source substrate (Apache 2.0)

8. **CTA Section**
   - "Join the waitlist" email capture
   - "Try the live demo" button
   - Links to the blog post

#### Design Requirements:
- Follow existing portfolio patterns: Tailwind, FontAwesome icons, same color palette (#F2F0E9 bg, #2E4036 theme, #1A1A1A text)
- Bilingual EN/FR (use `root-translations.js` pattern)
- Mobile responsive
- Include nav link back to portfolio

---

### Phase B: Enhance Existing Pages (MEDIUM IMPACT)

#### B1. `ai-system-building.html` — Add Flowmanner Case Study Section

**Where:** After the "Real-World Case Studies" section (Nubank, Ramp)

**What to add:**
```html
<!-- Flowmanner: AI Maturity in Production -->
<section class="py-20 bg-gradient-to-br from-[#2E4036] to-[#1A1A1A]">
  <div class="max-w-6xl mx-auto px-4">
    <h2>Flowmanner: Layer 5-6 in Production</h2>
    <p>Built and deployed a full agent orchestration platform that operates
    at Layers 5 (Autonomous Operator) and 6 (Challenger) of the AI Maturity
    Framework — with circuit breakers that prevent runaway agents.</p>
    <ul>
      <li>✅ Circuit Breakers — per-run cost/time/iteration limits</li>
      <li>✅ Time-Travel Debugging — replay any agent run to any point</li>
      <li>✅ Auto-Assertions — behavioral baselines from successful runs</li>
      <li>✅ 7 Execution Strategies — Solo, DAG, Pipeline, Graph, Swarm, Meta, LangGraph</li>
      <li>✅ Sovereign Deployment — runs on your own hardware</li>
    </ul>
    <a href="https://flowmanner.com/blueprints">Try the Live Demo →</a>
  </div>
</section>
```

#### B2. `autonomous-operations.html` — Add Circuit Breaker Deep-Dive

**Where:** After the "Safety & Governance" section

**What to add:**
- A subsection titled "Circuit Breakers: The Safety Net for Autonomous Agents"
- Explain the ARMED → TRIGGERED → CIRCUIT_BROKEN state machine
- Show the cost trajectory chart screenshot
- Link to the Runaway Agent Simulator demo
- Position Flowmanner as the implementation of the safety concepts described on the page

#### B3. `ai-web-dev.html` — Add Flowmanner as Orchestration Backend

**Where:** In the tech stack section or after the service offerings

**What to add:**
- "For complex multi-agent workflows, we use Flowmanner as the orchestration backend"
- Highlight: FastAPI backend, 557 API endpoints, event sourcing, replay engine
- Link to the API docs at flowmanner.com/docs

#### B4. `main.js` — Enhance Flowmanner References

**Where:** Lines 86, 91, 186, 189 (existing Flowmanner mentions)

**What to change:**
- Update the PORTFOLIO_COPY to include circuit breaker, replay, and assertions in the Flowmanner description
- Add a "Live Demo" link alongside the existing flowmanner.com link
- Add Flowmanner to the archive/projects section if not already there

---

### Phase C: Content Marketing (ONGOING)

#### C1. Blog Post Integration

The blog post "How to Run AI Agents Without Going Bankrupt" (already written at `docs/blog-how-to-run-ai-agents-without-going-bankrupt.md`) should be:

1. **Published on the portfolio** — Add a `/blog` section or integrate into an existing content area
2. **Linked from ai-system-building.html** — "Read our guide on agent cost management"
3. **Shared on social media** — Twitter/X thread + HN submission
4. **Cross-linked from Flowmanner** — Add a "Blog" link on flowmanner.com that points to the portfolio blog post

#### C2. SEO Optimization

Target keywords to embed across the portfolio pages:
- "AI agent orchestration"
- "AI agent safety"
- "circuit breaker AI"
- "AI workflow automation"
- "agent cost control"
- "AI agent debugging"
- "time-travel debugging AI"
- "runaway AI agent"

**Where to place:**
- Page titles and meta descriptions
- H2/H3 headings
- Alt text on screenshots
- Internal link anchor text

#### C3. Social Proof Content

Create shareable content assets:
- **60-second demo video** — Screen recording of the Runaway Agent Simulator
- **Animated GIF** — Circuit breaker catching the runaway agent (for Twitter/blog)
- **Architecture diagram** — Two-machine setup visual (for the showcase page)
- **Screenshot collection** — Blueprints page, Run Timeline, Assertions Panel, Run Diff

---

### Phase D: Cross-Linking Strategy

```
Portfolio → Flowmanner:
  - Nav: "AI Workflows" link (already exists) ✅
  - ai-system-building.html → flowmanner.com/blueprints (demo)
  - autonomous-operations.html → flowmanner.com/blueprints (demo)
  - ai-web-dev.html → flowmanner.com (platform)
  - flowmanner.html → flowmanner.com/#waitlist (waitlist)
  - Blog post → flowmanner.com/blueprints (demo CTA)

Flowmanner → Portfolio:
  - flowmanner.com/about → glennguilloux.com (creator attribution)
  - Blog post on flowmanner.com → portfolio showcase page
  - GitHub README → portfolio + flowmanner.com
```

---

## Priority Order (Updated)

| Priority | Task | Impact | Effort | Status |
|----------|------|--------|--------|--------|
| 🔴 P0 | Create `flowmanner.html` showcase page | Very High | 4-6h | ✅ Done |
| 🔴 P0 | Capture screenshots + demo video | Very High | 2-3h | ❌ TODO |
| 🟡 P1 | Enhance `ai-system-building.html` with case study | High | 1-2h | ✅ Done |
| 🟡 P1 | Enhance `autonomous-operations.html` with circuit breaker section | High | 1-2h | ✅ Done |
| 🟡 P1 | Publish blog post on portfolio | High | 1h | ❌ TODO |
| 🟢 P2 | Enhance `ai-web-dev.html` with orchestration mention | Medium | 30min | ✅ Done |
| 🟢 P2 | Update `main.js` Flowmanner references | Medium | 30min | ✅ Done |
| 🟢 P2 | SEO optimization across all pages | Medium | 2h | ❌ TODO |
| 🟢 P2 | Wire waitlist form to backend | Medium | 2h | ❌ TODO |
| 🔵 P3 | Cross-linking (Portfolio ↔ Flowmanner) | Low-Med | 30min | ❌ TODO |
| 🔵 P3 | Social media content (Twitter thread, HN) | Medium | 2-3h | ❌ TODO |
| 🔵 P3 | Enhance cognitive-amplification.html + sense-making.html | Low | 1h | ❌ TODO |
| 🔵 P3 | Normalize root-translations.js encoding | Low | 30min | ❌ TODO |

---

## Success Metrics

- **Traffic:** Flowmanner.com referral traffic from glennguilloux.com (Google Analytics)
- **Conversions:** Waitlist signups originating from portfolio
- **Demo runs:** Blueprint executions traced to portfolio referral
- **SEO:** Ranking for "AI agent orchestration" + Glenn's name
- **Social:** Twitter/X engagement on the demo thread

---

## Notes for the Implementing Agent

1. **Design consistency** — The portfolio uses Tailwind CSS, FontAwesome, dark theme (`bg-gray-900`, `text-white`, `bg-gray-800/50` cards). Don't use the SPA's custom classes like `text-clay` — use Tailwind utilities (`text-orange-400`).
2. **Bilingual** — All new content needs EN/FR. Add entries to `root-translations.js` with `data-translate` attributes on HTML elements. Use `\uXXXX` escapes for French accented characters.
3. **No build step** — The portfolio is vanilla HTML + Tailwind CDN + main.js (React 19 with htm). Don't add a build system.
4. **Mobile-first** — All pages are responsive. Test on mobile.
5. **FontAwesome icons only** — Don't use raw emoji in HTML. Use FontAwesome (`<i class="fas fa-..."></i>`) for visual consistency.
6. **Nav and footer** — Copy from existing pages using Python regex extraction. Watch for duplicate `</body></html>` closing tags.
7. **The blog post** is already written at `docs/blog-how-to-run-ai-agents-without-going-bankrupt.md`. Needs to be converted to HTML with the portfolio's nav/footer/template.
8. **Portfolio path** — `/mnt/apps/BACKUP-RAG/clickandbuilds/glennguilloux/`
9. **Translations file** — `/mnt/apps/BACKUP-RAG/clickandbuilds/glennguilloux/root-translations.js` (format: `"key": { "en": "...", "fr": "..." }`)
