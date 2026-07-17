# Reality Checker — Integration Reality Report

**Lens:** VERIFY-CLAIMS ("is it real or fool's gold")
**Date:** 2026-07-17
**Verdict (headline):** NEEDS WORK — the swarm/self-improvement "autonomous" story is largely aspirational; docs reference phantom modules and a 0%-success deprecated strategy is the only real swarm executor.

---

## Lens & Question I Own

I am the honesty gate. The other experts will be optimistic about the "swarm,"
"autonomous harness evolution," and "215 personas / 267KB template catalog."
My job: separate what-is-real (wired to a router, with real logic) from what-is-stub /
phantom / aspirational. Every claim below cites `path:line`.

---

## Top 5 Findings

### F1 — `seed_templates.py` (claimed "267 KB" in the BRIEF) DOES NOT EXIST  [CRITICAL / fact]
- **Observation:** BRIEF §"Verified repo facts" states: "A `seed_templates.py` (267 KB)
  holds the built-in mission template catalog." No such file exists anywhere in the repo.
- **Evidence:**
  - `search_files` for `seed_templates` → 0 hits in backend.
  - `ls scripts/seed_templates.py` → `No such file or directory`.
  - The real seeding scripts are `scripts/seed_consulting_templates.py` (280 lines, seeds
    a small `TEMPLATES` list of *consulting* templates into `MissionTemplate`) and
    `scripts/reload_builtin_templates.py` (121 lines).
- **Severity:** CRITICAL. The BRIEF's own "verified fact" is fiction. This is exactly the
  fantasy-approval pattern the squad must guard against: a precise, confident, false claim.
- **Type:** fact.

### F2 — The "autonomous harness evolution / meta-optimizer" is GUTTED  [CRITICAL / fact]
- **Observation:** The BRIEF and the swarm narrative imply an autonomous self-improving
  harness. The actual code is two layers of stub:
  1. `app/services/self_improvement.py` — `SelfImprovementEngine`. Its `_analyze_failure()`
     (lines 51-63) returns **hardcoded template strings** per `failure_type`. No LLM call,
     no learning, no feedback loop. It is a string-formatter, not an optimizer.
  2. `app/services/improvement/improvement_loop_v2.py` — its own docstring (lines 7-15)
     admits: *"The original 900-line autonomous self-improvement orchestrator has been
     gutted. Phases 3–6 ... were never wired into production — 107 missions ran with zero
     improvement data recorded."* The only live component is a `review_mission` Celery
     task that writes LLM-based memory notes.
- **Evidence:** `self_improvement.py:51-63` (template-string branches);
  `improvement_loop_v2.py:7-15` (self-incriminating gutting note).
- **Severity:** CRITICAL. "Autonomous harness evolution" is the single most dangerous
  overclaim in the repo — it is marketed as a capability that does not exist as described.
- **Type:** fact.

### F3 — `swarm.py` router and `app.services.swarm.orchestrator` (SwarmOrchestrator) are PHANTOM  [HIGH / fact]
- **Observation:** `backend/app/api/v1/AGENTS.md` references `swarm.py` router **three times**
  (lines 94, 183, and the import-tiering table) claiming it "Inlines `SwarmOrchestrator`
  from `app.services.swarm.orchestrator`." Neither file exists:
  - `app/api/v1/swarm.py` → `No such file or directory`.
  - `app.services.swarm.orchestrator` → `importlib.util.find_spec` returns `False`;
    `app/services/swarm/` contains only `debate_protocol.py`, `escalation_chain.py`,
    `handoff_protocol.py`, `lease_integration.py`, `__init__.py` (no `orchestrator.py`).
  - The substrate migration table (`substrate/AGENTS.md`) also claims "swarm/orchestrator.py
    (331 lines)" was replaced by `strategies/swarm.py` — but the 331-line original is gone,
    so there is nothing to "replace."
- **Evidence:** `app/api/v1/AGENTS.md:94`, `:183`; `find`/`ls` of `app/services/swarm/`;
  `python3 -c "importlib.util.find_spec('app.services.swarm.orchestrator')"` → False.
- **Severity:** HIGH. Docs describe a module graph that does not exist; any agent trusting
  the AGENTS.md will try to import a missing module. The only real swarm HTTP surface is
  `swarm_protocol.py` (debate/handoff/escalation), registered as `/swarm` prefix in
  `app/api/v1/__init__.py:112,225,252-253`.
- **Type:** fact.

### F4 — The only REAL swarm executor is DEPRECATED with 0% measured success  [HIGH / fact]
- **Observation:** `app/services/substrate/strategies/swarm.py` (244 lines) is a genuine,
  well-built strategy (decompose → parallel dispatch → synthesize, with prompt-injection
  sanitization and subagent-failure circuit breaking). But it is marked
  `DEPRECATED = True` with the comment: *"0% success with 27B model per strategy profiling
  2026-07-04"* (`swarm.py:69-70`). It is registered in `strategies/__init__.py:34`
  (`("swarm", ".swarm", "SwarmStrategy")`), so it is reachable — but known-broken in prod.
- **Evidence:** `substrate/strategies/swarm.py:69-70`; `strategies/__init__.py:34`.
- **Severity:** HIGH. "Swarm" is sold as a headline capability; the implementation exists
  but is self-declared 0%-success and deprecated. Marketing this as production-ready is
  fool's gold.
- **Type:** fact.

### F5 — `nexus/meta_loop_orchestrator.py` is also phantom; MetaStrategy is the real (untested) replacement  [MEDIUM / fact]
- **Observation:** `app/services/substrate/strategies/meta.py` docstring claims it "Replaces:
  nexus/meta_loop_orchestrator.py (225 lines)." But `meta_loop_orchestrator.py` does not
  exist (`find` → empty), and `capability_lattice.py:4` references it. `MetaStrategy`
  (`meta.py`) is real and registered (`strategies/__init__.py:36`), but its predecessor is
  fictional — same phantom-module pattern as F3.
- **Evidence:** `find . -name meta_loop_orchestrator.py` → none; `substrate/strategies/meta.py:1-5`;
  `substrate/strategies/__init__.py:36`.
- **Severity:** MEDIUM. Documentation integrity issue; the meta-loop capability's lineage is
  misrepresented.
- **Type:** fact.

---

## What IS Real (so the squad is balanced)

- **215 personas** in `app/agent_definitions/**/*.md` — count verified (215 `.md` files).
  REAL. This powers the "persona" feature honestly.
- **`swarm_protocol.py`** (347 lines) — real debate/handoff/escalation HTTP endpoints, wired
  to real services (`debate_protocol.py` 16KB, `escalation_chain.py` 13KB,
  `handoff_protocol.py` 23KB). These are genuine, substantial protocol implementations.
- **`v2/marketplace.py`** + `nexus/marketplace_db.py` — real, DB-backed marketplace
  (PostgreSQL). REAL.
- **`SelfImprovementEngine`** is wired into real CQRS endpoints
  (`app/api/_mission_cqrs/commands.py:1121,1135`, `queries.py:521`) — so the *endpoint*
  works; it just returns canned strings, not learned insights.
- **LLM routing** (`app/services/llm_providers.py`) — real, honest leaf module. The BRIEF's
  memory note is accurate: bare model ids fall through to `_LLM_API_BASE`/`_LLM_API_KEY`
  (platform key) at `llm_providers.py:109-110,117-119`, and `llamacpp*`/`llamacpp_light`
  carry `None` key (`PROVIDER_MAP` lines 34-35) → run keyless. The catalog's "enabled"
  flags ARE honest about what resolves; the gap is that most cloud providers need env keys
  that may be unset in a given deploy (then they 401 at call time, not at routing time).

---

## Biggest Single Blind Spot

The repo's **documentation layer (AGENTS.md files, BRIEF) describes a more complete and more
"autonomous" system than the code delivers.** Three phantom modules
(`swarm.py` router, `swarm/orchestrator.py`, `nexus/meta_loop_orchestrator.py`) and one
fabricated file (`seed_templates.py` 267KB) are cited as fact. The autonomous self-improvement
story is a gutted stub with a self-confessed 0-record production history. A reader who trusts
the docs (including the other optimistic swarm experts) will certify capabilities that do not
execute. The blind spot is **trust-in-docs without code verification** — and the fix is this
report.

---

## 3 Ranked Recommendations (Flowmanner-specific)

1. **Finish the swarm strategy before marketing it (effort: L).**
   - `SwarmStrategy` (`substrate/strategies/swarm.py`) is 0%-success on the 27B model. Either
     re-profile on a stronger model, or downgrade the "swarm" claim to experimental in all
     user-facing copy. Anchor: `substrate/strategies/swarm.py:69-70`.
   - *Why now:* the capability is wired and reachable; shipping a deprecated/0%-success
     executor under a "swarm" headline is the core fool's-gold risk.

2. **Re-label or rebuild `SelfImprovementEngine` + `ImprovementLoopV2` (effort: M/L).**
   - Today it is a string-template CRUD (no LLM, no learning). Either (a) call it what it is
     ("failure-suggestion notes") everywhere, or (b) actually wire an LLM step into
     `generate_strategy` (`self_improvement.py:21-40`) so the "self-improvement" name is true.
   - Anchor: `self_improvement.py:51-63`, `improvement_loop_v2.py:7-15`.

3. **Purge phantom-module references from AGENTS.md + BRIEF (effort: S).**
   - Remove/repair the 3 phantom modules and the `seed_templates.py` 267KB claim.
     Point at the real files: `swarm_protocol.py`, `substrate/strategies/swarm.py`,
     `seed_consulting_templates.py`.
   - Anchor: `app/api/v1/AGENTS.md:94,183`; `backend/AGENTS.md` template-catalog line;
     BRIEF §"Verified repo facts".

---

## Confidence

**High.** Every finding is backed by direct file inspection or a failed `find`/`importlib`
check (not doc claims). The single most important claim for the synthesizer to cross-check:
**"the autonomous self-improvement / harness-evolution loop does not exist as an operating
system — it is a gutted stub + a template-string formatter."** If any other expert certifies
"autonomous improvement" as a strength, that is the overclaim to arbitrate.

---

## Final Certification

- **Overall Quality Rating:** C (real, substantial protocols + substrate; but phantom docs and
  a deprecated/0%-success headline capability).
- **Production Readiness:** NEEDS WORK (default; not overridden — no evidence of the
  autonomous claims actually running).
- **Required fixes before any "swarm/autonomous" marketing claim:**
  1. Reconcile docs with code (remove 3 phantom modules + fabricated seed_templates.py).
  2. Either fix `SwarmStrategy` success rate or label it experimental.
  3. Either implement real LLM-backed self-improvement or stop calling it "autonomous."
- **Re-assessment required:** after the above are addressed.
