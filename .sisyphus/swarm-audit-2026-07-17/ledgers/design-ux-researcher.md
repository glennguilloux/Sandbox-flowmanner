# UX Researcher Ledger — Lens: PERCEIVE ("what is built but unseen or unreachable")

**Expert:** design-ux-researcher (fmw1) · **Task:** t_49360107
**Date:** 2026-07-17 · **Method:** read-only source analysis (backend + homelab frontend)
**Workspace:** worktree `agent/2026-07-17-ux/swarm` @ `/opt/flowmanner/.worktrees/t_49360107`

---

## Lens & question I own

**Verb: PERCEIVE.** From a user's seat, where is the gap between what Flowmanner
*offers* (the 636-endpoint API surface, the 215-persona library, the onboarding
flow) and what a user can actually *perceive and reach*? I reason from API/UI
parity, discovery endpoints, and docs/tour surfaces — with `path:line` evidence.

Persona framing: I am the user-behavior + perception analyst. My job is not to
implement; it is to surface the places where capability exists but the user's
eye/mind cannot get to it, and to rank those by severity and reachability cost.

---

## Top 5 findings

### F1 — 185 of 215 "expert personas" are invisible to the UI (CRITICAL, fact)

**Observation.** The flagship value prop is "215 expert personas," but the only
discovery endpoint — `/api/agent-personalities` — scans a single subdirectory
(`agent_personalities/`, 30 files) and never touches the other 15 directories.
The frontend agent browser renders *everything the API returns* (no client-side
filter), so the gap is entirely a backend scan-scope bug, not a UI choice.

**Evidence.**
- `backend/app/api/v1/agent_personalities.py:21` — `_DEFINITIONS_DIR = ... / "agent_definitions" / "agent_personalities"` — the scan root is hard-coded to one folder.
- `backend/app/api/v1/agent_personalities.py:100-111` — `_load_all_personalities()` iterates only `sorted(_DEFINITIONS_DIR.iterdir())` (i.e. the 30 files inside `agent_personalities/`).
- Counts: `find backend/app/agent_definitions/agent_personalities -name '*.md'` = **30**; `find backend/app/agent_definitions -name '*.md'` = **215**. The other 15 dirs hold 185 personas.
- Frontend renders all returned: `src/app/[locale]/agents/agents-page-content.tsx:54` fetches `/api/agent-personalities` and `:135` shows `if (domains.length === 0)` empty state — it does NOT restrict to a known list.
- Frontend's `DOMAIN_LABELS` (`src/data/agents.ts:4-15`) names only **10** customer-facing domains (customer-service, finance, healthcare, hr, legal, marketing, media-creative, operations, sales, software-it). The invisible 185 include: `specialized/` (41), `engineering/` (29), `marketing/` (30 — note: 30 *also* under `agent_personalities` subset, but `game-development/` 20, `design/` 8, `testing/` 8, `support/` 6, `sales/` 8, `product/` 5, `project-management/` 6, `spatial-computing/` 6, `paid-media/` 7, `finance/` 5, `academic/` 5, `browser/` 1) — none of these directories are scanned.

**Severity:** CRITICAL. The single most-marketed differentiator (a 215-persona
library) is ~86% unreachable through the product's own browser. A user can never
discover, pick, or use the specialized/engineering/game-dev/testing personas that
are the most defensible, novel inventory.

**Fact vs rec:** FACT (counted from filesystem + code paths). Recommendation in §Recs R1.

---

### F2 — Onboarding wizard is generic and never references personas, capabilities, or the real surface (HIGH, fact)

**Observation.** The 3-step onboarding collects a workspace name and 6 hardcoded
"what do you automate?" categories, then generates sample missions. It never
introduces the persona library, the mission builder, RAG, swarm, or any of the
actual capabilities. A new user's mental model after onboarding is "a form
builder," not "an AI-agent orchestration platform with 215 experts."

**Evidence.**
- `src/app/[locale]/(dashboard)/onboarding/page-client.tsx:11-26` — `CATEGORY_KEYS` is a fixed 6-item map (email, data, approval, leads, support, reporting). No link to personas or capabilities.
- `:54-75` — `handleGenerateSampleData()` calls `onboardingApi.generateSampleData()` then routes to `/dashboard`; the step copy (`wizard.readySubtitle` etc.) is generic.
- Backend onboarding routes exist (`backend/app/api/v1/onboarding.py` prefix `/onboarding`, 6 paths per `app/api/v1/AGENTS.md`) but the frontend flow consumes only `step`/`sample-data`/`complete`/`skip`/`status` — none of which surface capability discovery.
- Contrast: the agent browser page (`agents-page-content.tsx`) is a *separate* route the wizard never points to.

**Severity:** HIGH. First-run comprehension is the cheapest place to close the
perception gap; today it teaches nothing about what makes Flowmanner different.

**Fact vs rec:** FACT.

---

### F3 — No in-product tour / contextual help for the dense mission builder and agent surface (HIGH, fact)

**Observation.** The most powerful surface (the mission builder at
`missions/builder`) and the agent/orchestration pages have no guided tour, tool
tips, or empty-state coaching. The empty state at `agents-page-content.tsx:135`
is a bare "no agents" message with no path to *create or discover* one.

**Evidence.**
- Grep for `tour|onboarding|walkthrough` across `src` returns only the generic
  onboarding wizard + a `guides/[slug]` route with **2** content files
  (`find .../guides -name '*.md' -o -name '*.ts'` = 2) — i.e. the "guides" docs
  surface is near-empty.
- `agents-page-content.tsx:135` empty state: `if (domains.length === 0)` renders a
  message but no CTA to browse personas or build a mission.
- The mission builder (`missions/builder/page.tsx`) is feature-rich (node canvas,
  node-groups, templates) with no first-use coach — confirmed by absence of any
  tour/walkthrough references in that subtree.

**Severity:** HIGH. Powerful surfaces are *reachable* but not *comprehensible*;
users who land there bounce before discovering value.

**Fact vs rec:** FACT.

---

### F4 — API→UI parity gap: 636 endpoints, but entire capability categories have weak or no UI entry points (MEDIUM, fact)

**Observation.** `openapi.json` exposes **636 paths** across `v1/v2/v3`. The
frontend has ~50 dashboard routes. Some high-value API categories are barely or
not surfaced:
- `/api/swarm` (15 paths) — swarm orchestration is a headline feature; UI has no
  dedicated swarm page (only `orchestration` references, 18 files, but no
  first-class "Swarm" route in the dashboard route list).
- `/api/agent-registry` (`backend/app/api/v1/agent_registry.py:36`, prefix
  `/agent-registry`) is described in-code as "the missing prefix alias" and at
  `:39` `_not_found()` returns 404 — i.e. a stub endpoint that advertises
  capability the UI cannot reach.
- `/api/memory` (6 paths) and `/api/orchestration` (7 paths) have
  `memory-inspector` and `orchestration` references in the UI, but `agent-capabilities`
  (5 paths) has no obvious dedicated page.

**Evidence.**
- `openapi.json` path tally: 636 total; `v2`=130, `v3`=22, `v1`=9, other=475.
- Frontend dashboard route inventory (from `find src/app/[locale]/(dashboard) -name page.tsx`) lists ~50 routes; no `swarm` route.
- `backend/app/api/v1/agent_registry.py:36,39` — stub alias endpoint returning 404.
- `app/api/v1/AGENTS.md` router inventory confirms `/swarm` inlines `SwarmOrchestrator` (a real, shipped capability) with no dedicated frontend page.

**Severity:** MEDIUM. Not "broken," but the perception/reachability ratio is low
for the most differentiated features (swarm, agent registry, memory).

**Fact vs rec:** FACT.

---

### F5 — Persona discovery has no search, filter, or recommendation; it's a flat domain grid (MEDIUM, fact+rec)

**Observation.** Even for the 30 *visible* personas, discovery is a static
group-by-domain grid (`groupByDomain` at `agents-page-content.tsx:27-41`) with no
text search, no tag/capability filter, no "recommended for your use case," and no
linkage from the onboarding categories to relevant personas. Choosing among
personas is unguided.

**Evidence.**
- `agents-page-content.tsx:27-41` — `groupByDomain` buckets by `p.domain` and
  labels via `DOMAIN_LABELS[domain] || domain`; no search input, no filter chips,
  no sort.
- The onboarding "what do you automate?" categories (`page-client.tsx:11-26`) are
  never mapped to personas — a user who picks "sales" sees no sales-persona
  shortcut.
- `AgentPersonalitiesService.ts:15` returns `CancelablePromise<any>` (untyped) —
  the SDK gives the UI no structured fields to filter on beyond `domain`/`name`/`description`.

**Severity:** MEDIUM. Discovery scales poorly as the visible set grows; today it's
already a wall of undifferentiated cards.

**Fact vs rec:** FACT with a REC component (see R3).

---

## Biggest single "built but invisible" gap

**The 215-persona library is Flowmanner's sharpest differentiator, and ~86% of it
(185 personas across 15 directories) is completely unreachable through the product.**
The discovery endpoint hard-codes its scan root to one subdirectory
(`backend/app/api/v1/agent_personalities.py:21`), the frontend `DOMAIN_LABELS`
only names 10 domains (`src/data/agents.ts:4-15`), and the agent browser renders
only what the API returns (`agents-page-content.tsx:54,135`). A user literally
cannot see, select, or run the `specialized/` (41), `engineering/` (29),
`game-development/` (20), `testing/` (8), `design/` (8) and other persona sets —
the exact inventory that makes Flowmanner more than "another workflow tool."
This is the canonical PERCEIVE miss: capability exists, marketing claims it, the
UI implies it, but the user's eye cannot reach it.

---

## 3 ranked brainstorm recommendations

**R1 — Extend the persona discovery scan to all 16 directories (idea)**
- **What:** Change `_DEFINITIONS_DIR` (or the scan in `_load_all_personalities`,
  `agent_personalities.py:21,100-111`) to walk the whole `agent_definitions/`
  tree, and extend `DOMAIN_LABELS` / add a fallback label map in
  `src/data/agents.ts:4-15` so every domain renders. Keep the `domain/slug` id
  scheme already used by `get_agent_personality` (`:125-150`).
- **Why now:** It's the single highest-leverage perception fix — unlocks 185
  personas (6× the current visible set) for near-zero UX risk, and makes the
  "215 personas" claim true in-product.
- **Effort:** S (backend: repoint one scan root + add a recursive walker;
  frontend: extend the label map + a generic fallback label).
- **Anchor:** `backend/app/api/v1/agent_personalities.py:21` and
  `src/data/agents.ts:4-15`.

**R2 — Make onboarding persona- and capability-aware (idea)**
- **What:** After the "what do you automate?" step, recommend 2–3 personas from
  the matched domain (wire `onboarding` step → `agent-personalities` lookup) and
  show one "here's what you can build" capability card (mission builder / RAG /
  swarm). Replace the generic `generateSampleData` finish with a guided first
  mission using the chosen persona.
- **Why now:** First-run comprehension is the cheapest perception lever; today the
  wizard teaches nothing about the differentiators (F2). Closes the gap before the
  user forms a "form builder" mental model.
- **Effort:** M (frontend wizard reflow + a small recommendation query; backend
  onboarding already has the step/sample-data hooks).
- **Anchor:** `src/app/[locale]/(dashboard)/onboarding/page-client.tsx:11-75`.

**R3 — Add search + tag filter + "recommended" to the agent browser (idea)**
- **What:** On `agents-page-content.tsx`, add a text search over
  `name`/`description`, capability/tag filter chips, and a "recommended for you"
  row seeded from the user's onboarding categories. Type the SDK service
  (`AgentPersonalitiesService.ts:15`) so the UI can filter on structured fields.
- **Why now:** As R1 unlocks 185 personas, a flat domain grid (F5) becomes
  unusable; discovery must scale or the unlock is wasted.
- **Effort:** M (frontend: search/filter UI + recommendation row; backend: optional
  tag field in the persona schema at `agent_personalities.py:69-76`).
- **Anchor:** `src/app/[locale]/agents/agents-page-content.tsx:27-41`.

---

## Confidence

**HIGH** on F1/F2/F3/F4/F5 — all are grounded in counted files, read endpoints,
and read frontend components (specific `path:line`). The 30-vs-215 count and the
single-directory scan root are unambiguous.

**Single most important claim for the synthesizer to cross-check:** F1 — that
`/api/agent-personalities` scans only `agent_personalities/` (30 files) and not
the full 215-persona tree. If the synthesizer's other lenses assume "215 personas
are browsable," that assumption is false in-product today. Verify by re-running
`find backend/app/agent_definitions -name '*.md' | wc -l` (expect 215) vs the
scan root at `backend/app/api/v1/agent_personalities.py:21` (expect
`.../agent_definitions/agent_personalities`).

---

*UX Researcher ledger — read-only analysis, no code changes. All claims cited to
`path:line` in `/opt/flowmanner` (backend) and `/home/glenn/FlowmannerV2-frontend`
(homelab frontend).*
