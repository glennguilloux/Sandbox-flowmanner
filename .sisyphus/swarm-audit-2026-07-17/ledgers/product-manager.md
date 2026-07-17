# Product Manager Ledger — Prioritize Flowmanner Value

**Persona:** Alex (PM) · **Lens:** PRIORITIZE (value-to-effort, built-but-unshipped)
**Task:** t_6ddd244e · **Date:** 2026-07-17 · **Mode:** READ-ONLY analysis
**Workspace:** `/opt/flowmanner/.worktrees/t_6ddd244e`

> Every claim below cites `path:line` evidence from this worktree. Items labeled
> **[FACT]** are observed in code; **[REC]** are recommendations from the PM lens.

---

## 1. Lens & question I own

**Verb: PRIORITIZE.** Of everything Flowmanner *can* do, what should Glenn ship
next for the best value-to-effort, and what is built-but-unshipped? I prioritize.

The platform has a wide API surface (v1 ~80 routers, v2 24 routers, v3 12 routers —
`backend/app/api/AGENTS.md` inventory) but a PM's job is to separate *deployed
value* from *code that exists*. I traced the highest-leverage product surfaces:
the multi-agent persona library (215 definitions), the built-in mission template
catalog (60 seed templates), and the "platform" modules (marketplace / community /
changelog / roadmap / blog).

---

## 2. Top 5 prioritization findings

### Finding 1 — 185 of 215 built-in personas are NOT surfaced as a product
**Severity: HIGH · [FACT]**

- `app/agent_definitions/` holds 215 markdown persona definitions
  (`find app/agent_definitions -name '*.md' | wc -l` → 215).
- Only `app/agent_definitions/agent_personalities/` (30 files) is served to users,
  via `app/api/v1/agent_personalities.py:119` (`list_agent_personalities`, no auth).
- The other 185 definitions (across `specialized/`, `support/`, `testing/`,
  `engineering/`, `marketing/`, `finance/`, `sales/`, `academic/`, … — 15 domain
  dirs) are **not exposed by any product API**. The v2 `/agents` router
  (`app/api/v2/agents.py:52`) is *owner-scoped* (`list_agents(db, str(user.id), …)`)
  — it returns only user-created agents, never the 185 built-in library.
- **PM read:** Flowmanner's headline differentiator ("215 expert agents") is
  real as *content* but invisible as *product*. A brand-new user cannot browse or
  deploy the 185 specialized personas. This is the single biggest
  built-but-unshipped value asset.

### Finding 2 — Community platform module is a dead data layer (no router, no table)
**Severity: HIGH · [FACT]**

- `app/models/community_models.py` defines `CommunityTemplate` + `CommunityComment`
  (full ORM, 15 columns + threaded comments).
- `app/tests/test_community_models.py` exists — the data layer was built and tested.
- But there is **no `community.py` router**. The model docstring itself says
  *"The table itself is created by raw SQL in community.py's `_ensure_table()`"*
  (`app/models/community_models.py:5`) — that file does not exist in the repo
  (`search app/api/v1/community.py` → not found). AGENTS.md lists `community.py`
  as `OPTIONAL` (`app/api/v1/AGENTS.md:27`) but the file is absent.
- **PM read:** Community is 50% built (model + test, no API, no UI, no table
  bootstrap). It cannot ship without a router + migration. Effort to finish is
  moderate, but it currently produces zero user value and silently rots.

### Finding 3 — Changelog is referenced in docs but does not exist anywhere
**Severity: MEDIUM · [FACT]**

- `app/api/v1/AGENTS.md:141` lists `changelog.py` ("Product changelog") in the
  router inventory.
- No `changelog.py` router exists; no `changelog` model exists
  (`ls app/models/ | grep -i changelog` → none).
- What *does* exist: `app/api/v2/blog.py` (read-only blog + case-study,
  `blog_models.py`) and `app/api/v2/roadmap.py` (read-only, `roadmap_models.py`).
- **PM read:** The "transparency" surface (changelog) is missing while blog + roadmap
  are live. For a solo-founder product, a lightweight auto-generated changelog from
  deploy/PR history is near-free credibility and is currently a doc-vs-code gap.

### Finding 4 — Marketplace is fully built end-to-end (wallet, purchase, reviews) but has no seed supply and likely no storefront
**Severity: MEDIUM · [FACT + REC]**

- `app/api/v2/marketplace.py` (379 lines) is a complete commerce surface: listings,
  featured, categories, install/uninstall, wallet top-up, purchase (402 on
  insufficient balance, `:264-280`), transactions, refund, reviews
  (`marketplace.py:61-379`). Mounted at `app/api/v2/__init__.py:93-95`.
- Backing service `app/services/nexus/marketplace_db.py:245`
  (`class MarketplaceService`) + `app/models/marketplace_txn_models.py` exist.
- **No seed/supply:** there is no seed script populating listings (contrast with
  `seed_templates.py` which *is* loaded at startup via
  `docker-entrypoint.py:42` → `scripts/reload_builtin_templates.py`).
- **PM read:** An empty marketplace is worse than no marketplace — it signals a
  ghost town. Either (a) seed it with the 60 built-in templates + 215 personas as
  first-class listings, or (b) gate it behind a "coming soon" until supply exists.
  Shipping the UI on an empty catalog burns trust.

### Finding 5 — Onboarding exists and is solid, but its "Explore Features" step is unearned
**Severity: LOW · [FACT]**

- `app/api/v1/onboarding.py` defines a real 5-step flow
  (`ONBOARDING_STEPS`, `:14-20`): welcome → create_mission → add_byok(opt) →
  run_mission → explore. State is DB-backed (`onboarding_state` table).
- A `/sample-data` endpoint pre-creates 2 completed sample missions
  (`:134-201`) so the dashboard isn't empty on first run — good activation hygiene.
- But "explore" (the step that would surface personas/templates/marketplace) has no
  backing content surfacing; the rich library from Findings 1–4 is not wired into
  the first-run experience.
- **PM read:** Onboarding mechanics are sound. The gap is *content discovery* inside
  onboarding — the 185 personas and 60 templates should be one click from "explore,"
  not buried.

---

## 3. Biggest single miss / blind spot (PM lens)

**The 185 built-in specialized personas are Flowmanner's moat and they are invisible.**

Flowmanner's stated identity is "orchestrate AI agents, missions, swarms." The asset
that makes that real — 215 curated expert persona definitions — is only 14% surfaced
(30 `agent_personalities` via `app/api/v1/agent_personalities.py`). The other 185
(`specialized/`, `support/`, `testing/`, `engineering/`, `finance/`, `sales/`,
`marketing/`, `academic/`, `game-development/`, `spatial-computing/`, `paid-media/`,
`design/`, `project-management/`, `browser/`) are unreachable product content.

This is the highest value-to-effort gap in the entire codebase: the content is
*already written and reviewed* (it's what powers this very swarm audit), the
infrastructure to serve it exists (the `agent_personalities` pattern is the template),
and the marginal engineering cost to expose the remaining 185 is small (extend the
existing file-scan loader, add a category filter). Yet today a user cannot discover,
preview, or deploy them. That is mispriced, unshipped inventory.

---

## 4. Three ranked brainstorm recommendations

### REC A (Rank 1) — Expose the full 215-persona library as a browsable "Agent Gallery"
- **Idea:** Extend `app/api/v1/agent_personalities.py` (the file-scan loader at
  `:84-111`) to scan *all* 15 domain dirs under `app/agent_definitions/`, not just
  `agent_personalities/`. Add `?domain=` + `?q=` filters. Surface in a frontend
  "Agent Gallery" with one-click "deploy as my agent."
- **Why now:** The content is done; the loader pattern already works for 30; the
  marginal cost is ~1 file change + 1 frontend page. It converts the #1 moat from
  invisible to the headline feature.
- **Effort:** **S** (backend loader change is tiny; frontend gallery page is M, but
  reuses existing `agent_personalities` UI components).
- **Anchor:** `app/api/v1/agent_personalities.py:21` (`_DEFINITIONS_DIR` is hard-coded
  to `agent_personalities/` only) and `:84-111` (`_load_all_personalities`).

### REC B (Rank 2) — Seed the Marketplace from existing inventory OR gate it
- **Idea:** Either (a) write a seed script that lists the 60 built-in mission
  templates (`seed_templates.py` → `MissionTemplate`, surfaced via
  `app/api/v1/templates.py`) and the 215 personas as marketplace listings with
  `price=0` "install," so the catalog is never empty; or (b) if monetization isn't
  ready, hide the marketplace storefront behind a "coming soon" state until supply
  exists.
- **Why now:** An empty commerce surface (`app/api/v2/marketplace.py` is fully built
  but has no seed, Finding 4) actively *harms* perceived maturity. Cheap to fix;
  high trust payoff.
- **Effort:** **M** (seed script + wire templates→listings is S; gating UI is S;
  doing both well is M).
- **Anchor:** `app/api/v2/marketplace.py:61` (listings endpoint, currently returns
  empty with no seed) and `docker-entrypoint.py:42` (startup seed hook — natural
  place to add marketplace seeding).

### REC C (Rank 3) — Finish or formally descope Community; add a lightweight Changelog
- **Idea:** Community has a tested model (`app/models/community_models.py`) but no
  router/table bootstrap (Finding 2). Decision: either build the `community.py`
  router + Alembic migration to ship it, or delete the orphan model+test to stop
  carrying dead weight. In parallel, add a read-only changelog derived from deploy/PR
  history (blog + roadmap already prove the read-only-router pattern at
  `app/api/v2/blog.py` / `app/api/v2/roadmap.py`).
- **Why now:** Dead code (Community) biases future PM/scaffolding decisions ("we have
  community, right?") and the missing changelog is a free credibility win for a
  founder-led product.
- **Effort:** **M** (Community router + migration is M; changelog is S reusing the
  blog/roadmap read-only pattern).
- **Anchor:** `app/models/community_models.py:5` (docstring admits the router is
  missing) and `app/api/v2/roadmap.py:34` (the read-only pattern to copy for
  changelog).

---

## 5. Confidence & cross-check request

**Confidence: MEDIUM-HIGH** on the factual claims (all cite code) and MEDIUM on the
prioritization ranking (I could not see the frontend repo — `/home/glenn/
FlowmannerV2-frontend/` is a separate local-only repo not in this worktree, so
"no storefront page" for marketplace/community is inferred from the absence of any
backend supply + the AGENTS.md router inventory, not from frontend proof).

**Single most important claim for the synthesizer to cross-check:**
> "185 of 215 built-in personas are not surfaced to users" — verify against the
> actual frontend: does any page call `/agent-personalities` beyond the 30 in
> `agent_personalities/`, or is there a separate `personas` browse surface I missed
> in the backend? If the frontend *does* surface the other 185, my Finding 1
> downgrades from HIGH to LOW. The backend evidence (only
> `app/api/v1/agent_personalities.py` serves definitions, owner-scoped v2 `/agents`
> does not) strongly supports the claim, but frontend confirmation is the tie-breaker.
