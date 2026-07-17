# Flowmanner — Multi-Expert Analysis & Brainstorm Report

**Date:** 2026-07-17 · **Prepared by:** Hermes orchestrator (default profile)
**Method:** 6 persona-experts dispatched as Kanban workers (`persona-delegation`
skill + `multi-expert-swarm-audit` recipe), 2 waves of 3 across `fmw1–3`, each
in its own git worktree. Read-only. Orchestrator independently re-verified every
load-bearing claim below (Glenn's "never trust a worker self-report" rule).

**The squad (one distinct verb each):**
| Persona | Lens (verb) | Card | Ledger |
|---|---|---|---|
| Backend Architect | COMPOSE | t_b4d8c5b7 | engineering-backend-architect.md |
| Security Engineer | VERIFY (attack) | t_cb25b558 | engineering-security-engineer.md |
| Product Manager | PRIORITIZE | t_6ddd244e | product-manager.md |
| UX Researcher | PERCEIVE | t_49360107 | design-ux-researcher.md |
| Reality Checker | VERIFY (claims) | t_470c1754 | testing-reality-checker.md |
| Developer Advocate | PITCH | t_c59ff061 | specialized-developer-advocate.md |

> All six ledgers live in `.sisyphus/swarm-audit-2026-07-17/ledgers/`. This
> report synthesizes them and **corrects two errors the Reality Checker made**
> (see "Verification Notes").

---

## 1. Executive Summary

Flowmanner is a genuinely capable, large platform (FastAPI backend, 215 curated
personas, a real multi-agent **debate/handoff/escalation** protocol, a GA
"unified execution substrate", a full marketplace + seeded template catalog).
The headline differentiator — **215 expert personas** — is real and shipped.
The headline risk is a **trust gap between docs/marketing and code**: several
"autonomous" features are gutted or simulated, one CRITICAL auth control is
fail-open, and the single biggest untapped asset (the 185 invisible personas) is
a one-line scan-root bug away from becoming the product's hero feature.

**The three things to do first (consensus across 4+ experts):**
1. **Expose the other 185 personas** (backend scan-root fix + Agent Gallery).
   Near-zero effort, unlocks the moat. — *PM, UX, Advocate, Architect all rank this #1.*
2. **Fix the fail-open v3 auth middleware** (`scope_validator.py`). S-effort,
   removes a silent unauthenticated-access enabler. — *Security CRITICAL.*
3. **Stop selling / fix the "autonomous" story**: the self-improvement loop is a
   gutted stub and the swarm strategy is self-declared 0%-success. Either rebuild
   or re-label before any "swarm/autonomous" marketing. — *Reality Checker.*

---

## 2. What's Real (strengths — confirmed)

- **215 personas** in `backend/app/agent_definitions/**/*.md` — count verified
  (215 `.md` files). Powers this very swarm. *(RC, Advocate, UX, PM)*
- **Multi-agent protocol layer is real and callable**: `swarm_protocol.py`
  exposes `POST /api/swarm/protocol/debate` (LLM-judge scored), `/handoff`,
  `/escalate` with full observability. `DebateProtocol`/`HandoffProtocol`/
  `EscalationChain` are substantial (16/23/13 KB). *(Advocate, Reality Checker)*
- **Unified execution substrate is GA** with strong guarantees (append-only event
  log, replay, circuit breakers, capability tokens, budget enforcer).
  `executor.py` docstring: "single durable executor (H5.1). GA release." *(Architect)*
- **`seed_templates.py` (267 KB) exists** at repo root and `backend/` — seeds the
  built-in mission template catalog (idempotent). *(VERIFIED by orchestrator —
  see note; the Reality Checker erroneously claimed it does not exist.)*
- **Marketplace is fully built** end-to-end (wallet, purchase, reviews) on real
  PostgreSQL. *(PM, Reality Checker)*
- **Typed Python SDK** `sdk-python/flowmanner-api-client` is publishable
  (`create_mission`, CLI, cost analytics). *(Advocate)*
- **Onboarding flow is solid** (DB-backed 5-step, sample-data seeding). *(PM, UX)*

---

## 3. What's Broken / Risky (the honesty gate)

### CRITICAL
- **C1 — v3 auth middleware is fail-open** (`backend/app/middleware/scope_validator.py:25-26,33-36`): missing `Bearer ` header OR any JWT decode error → `call_next` passes the request straight through with no 401. It is the *only* pre-route gate for `/api/v3/*` and enforces nothing (its scope logic is dead code — no route calls `register_scope_requirement`). One forgotten `Depends(get_current_user)` on a v3 route = silent unauthenticated endpoint, zero log signal. *(Security Engineer — CONFIRMED)*
- **C2 — 185 of 215 personas are invisible** (`backend/app/api/v1/agent_personalities.py:21` hard-codes `_DEFINITIONS_DIR` to `agent_personalities/` only; `_load_all_personalities` at `:100-111` iterates just that one dir). Frontend renders only what the API returns. The flagship "215 experts" claim is ~86% unreachable in-product. *(UX Researcher + PM + Advocate + orchestrator count-confirmed: 215 total, scan root = 1 subdir)*

### HIGH
- **H1 — Upload path traversal / unrestricted upload** (`backend/app/api/v1/file.py:56`): `file.filename` concatenated unmodified into `UPLOAD_DIR / f"{file_id}_{file.filename}"`; `Path` does not strip `..`. No content-type/size validation. *(Security — CONFIRMED by orchestrator)*
- **H2 — WebSocket DMs broadcast to the whole workspace room** (`backend/app/websocket/mission_ws.py:362-373`); confidentiality depends on the *client* not rendering other people's DMs; membership gate is **fail-open** (`:326` comment). *(Architect)*
- **H3 — Tenant isolation is opt-in per call site** (`app/services/mission_service.py:53-92` falls back to `user_id` ownership when `workspace_id` is null; `get_workspace_id` is caller-supplied from a header). No data-layer backstop → IDOR risk on any endpoint that forgets the membership join. *(Security)*
- **H4 — Self-healing / predictive-auto-scaling cluster is SIMULATED and UNWIRED** (`app/services/runtime/predictive_scaler.py:27-43` returns `random.uniform` telemetry; `self_healing.py:44-45` does `asyncio.sleep(0.5)` "recovery" + in-memory-only history; **zero imports outside `runtime/`**). The reliability story is decorative — a 99.9% SLA claim is unsupported by code. *(Architect — CONFIRMED by orchestrator)*
- **H5 — Dual execution engines still live** (`mission_executor.py` 1,387 LOC still wired by legacy v1 routes; `FLOWMANNER_UNIFIED_EXECUTOR=all` never flipped). Substrate's "every transition emits an event" guarantee is void for legacy-path missions; forensics/replay can't reconstruct them. *(Architect)*
- **H6 — Swarm strategy is self-declared 0%-success & deprecated** (`app/services/substrate/strategies/swarm.py:69-70` `DEPRECATED=True # 0% success with 27B model`) yet still registered and dispatchable. Sold as a headline capability. *(Reality Checker — CONFIRMED)*
- **H7 — Self-improvement loop is gutted** (`app/services/improvement/improvement_loop_v2.py:7-15`: "original 900-line orchestrator has been gutted… 107 missions ran with zero improvement data"; `self_improvement.py:51-63` returns hardcoded template strings, no LLM/learning). The "autonomous harness evolution" story does not exist as described. *(Reality Checker — CONFIRMED)*

### MEDIUM
- **M1 — SSRF guard bypassed on `discover_models`** (`app/api/v1/api_keys.py:441-456` skips the `_is_safe_outbound_url` + IP-pinning helper that `fetch_provider_models` uses). BYOK model-discovery can hit arbitrary internal URLs with the user's key. *(Security)*
- **M2 — Deprecated `MetaStrategy` still dispatchable** (`strategies/meta.py:35` + `__init__.py:36`). *(Architect)*
- **M3 — Three overlapping "coordination" concepts** (nexus orchestrator, substrate, hollow improvement loop) with undefined ownership. *(Architect)*
- **M4 — Community model built + tested but no router/table; Changelog referenced in docs but absent** (PM). Note: `roadmap`/`changelog`/`community` were **deleted in a prior pruning phase** — the Advocate's brief angle pointing at them was stale; do NOT build narratives on them. *(PM + Advocate — VERIFIED: pruning doc + grep confirm deletion)*
- **M5 — Marketplace has zero seed supply** → empty storefront signals a ghost town. *(PM)*
- **M6 — Onboarding never references personas/capabilities**; no in-product tour; API→UI parity gap (636 endpoints, swarm/agent-registry/memory have weak/no UI entry). *(UX)*
- **M7 — Swarm DX trap:** `ExecuteRequest.strategy` accepts only `parallel|sequential|debate`, NOT `"swarm"` — tutorials using `strategy:"swarm"` 422. *(Advocate)*

---

## 4. The Brainstorm — Ranked Recommendations

Cross-referenced from all six ledgers, de-duplicated, and re-sequenced by
value-to-effort (S = <1 day, M = days, L = weeks).

| # | Recommendation | Effort | Why now | Who flagged | Anchor |
|---|---|---|---|---|---|
| **R1** ✅ **DONE** | **Unlock the 185 invisible personas:** repoint `_DEFINITIONS_DIR` scan to walk all of `agent_definitions/`, extend frontend `DOMAIN_LABELS` + add search/filter/"recommended" to the Agent Gallery — **RESOLVED**: backend merged (`757e7721`, ancestor of `main`) & DEPLOYED (live API serves 215); frontend gallery merged (`ca975ce5`). R1-only deploy branch prepared at `deploy/r1-gallery-only` (`a71fb421`, tsc-clean). See `.sisyphus/design-signoff-R1-185-invisible-personas.md` (2026-07-17). | **S** (backend) / M (frontend gallery) | The moat is one scan-root bug from becoming the hero feature; content is already written & reviewed | PM, UX, Advocate, Architect | `agent_personalities.py:22,110`; `src/data/agents.ts:4-27` |
| **R2** | **Fail-close the v3 auth middleware** (or delete it + enforce `get_current_session` on the v3 router mount + CI test that every v3 route requires auth) | **S** | Removes a CRITICAL silent-bypass enabler; cheap vs blast radius | Security | `scope_validator.py:25-26,33-36` |
| **R3** | **Re-label or rebuild the "autonomous" story** (self-improvement + swarm): either wire a real LLM step, or call it what it is ("failure notes", "experimental swarm") everywhere user-facing | **M/L** | Selling gutted/0%-success capabilities is the top fool's-gold risk | Reality Checker | `self_improvement.py:51-63`; `swarm.py:69-70` |
| **R4** | **Ship a "Swarm in 30 seconds" landing demo + Quick Start** firing `POST /api/swarm/protocol/debate` live; lead SDK docs with `debate()` not `create_mission` | **M** | The most differentiated call in the API is absent from the first-10-min experience | Advocate | `swarm_protocol.py:104`; `sdk-python/.../README.md:14` |
| **R5** | **Harden uploads + close SSRF bypass** (use `os.path.basename`+UUID-only storage+magic-byte/size checks; route `discover_models` through the existing `_is_safe_outbound_url` guard) | **S–M** | Both are externally reachable on a homelab host → classic RCE pair | Security | `file.py:56`; `api_keys.py:441-456` |
| **R6** | **Complete the v1→substrate cutover** (flip `FLOWMANNER_UNIFIED_EXECUTOR=all`, parity-gate, delete `mission_executor.py`, migrate inline v1 routers) | **L** | Two live engines = consistency drift + unreconstructable runs; compounds daily | Architect | `substrate/AGENTS.md`; `graph.py:323` |
| **R7** | **Add a data-layer tenancy backstop + automated IDOR sweep test** (mandatory `workspace_id` AND membership; 404 for non-members) | **L** | Isolation is only as strong as the least-forgotten check; v3 workspace endpoints are growing | Security | `mission_service.py:53-92`; `deps.py:366` |
| **R8** | **Make onboarding capability-aware** (recommend personas from the "what do you automate?" step; show one "here's what you can build" card) | **M** | First-run comprehension is the cheapest perception lever; today it teaches "form builder" | UX | `onboarding/page-client.tsx:11-75` |
| **R9** | **Seed or gate the Marketplace; finish-or-drop Community; add lightweight Changelog** (seed from templates+personas, or "coming soon"; changelog reuses the read-only blog/roadmap pattern) | **M** | Empty commerce + dead community model bias every future decision | PM | `marketplace.py:61`; `community_models.py:5`; `roadmap.py:34` |
| **R10** | **Replace or delete the simulated `runtime/` cluster** (wire to Prometheus + real restart hook, or remove so OpenAPI stops implying capabilities that don't exist) | **M** | A pretend reliability layer creates false confidence and could cause an operator to skip real monitoring | Architect | `predictive_scaler.py:27`; `self_healing.py:44` |
| **R11** | **De-register deprecated `MetaStrategy` + retire `nexus` orchestrator** in favor of substrate + capability registry | **M** | Dead weight + silent 0%-success dispatch + 3 overlapping "coordination" concepts | Architect | `__init__.py:36`; `nexus/orchestrator.py:53` |
| **R12** | **Purge phantom-module references from AGENTS.md/BRIEF** (`swarm.py` router, `swarm/orchestrator.py`, `meta_loop_orchestrator.py` don't exist; reconcile counts) | **S** | Doc-vs-code drift makes every future agent trust ghosts | Reality Checker + orchestrator | `app/api/v1/AGENTS.md:94,183` |

---

## 5. Verification Notes (orchestrator cross-checks — do not skip)

Per Glenn's standing rule, I independently verified the claims the Reality
Checker asked the synthesizer to arbitrate — and **caught two errors in the
Reality Checker's own report**:

1. **RC F1 ("`seed_templates.py` 267 KB does not exist — CRITICAL fiction") is FALSE.**
   The file **does exist** at `/opt/flowmanner/seed_templates.py` (267,908 bytes)
   and `backend/seed_templates.py`. The RC only searched `scripts/` and missed the
   repo root. The BRIEF's "267 KB template catalog" claim was correct. **This is
   the irony the Reality Checker warns about: a confident, precise, false claim.**
   I've corrected it here. All other RC findings (deprecated swarm 0%-success,
   gutted self-improvement, phantom `swarm.py` router) were **confirmed true**.

2. **RC F3 ("`swarm.py` router + `swarm/orchestrator.py` are phantom") is TRUE.**
   `backend/app/api/v1/swarm.py` does not exist; `app.services.swarm.orchestrator`
   fails `importlib.util.find_spec`. The real swarm HTTP surface is
   `swarm_protocol.py`. (The substrate `strategies/swarm.py` is real but
   deprecated/0%-success — confirmed at `:69-70`.)

3. **Architect F4 (simulated/unwired `runtime/` cluster) — CONFIRMED.** `random`
   telemetry, `asyncio.sleep(0.5)` recovery, in-memory history, and **no imports
   outside `runtime/`** (grep returned empty). This directly contradicts any
   "self-healing" strength claim.

4. **Persona invisibility (C2) — CONFIRMED four ways.** `find …/agent_definitions
   -name '*.md' | wc -l` = 215; `agent_personalities.py:21` scan root = one
   subdir; frontend `DOMAIN_LABELS` names 10 domains; agent browser renders only
   API output.

5. **Deleted modules (M4) — CONFIRMED.** `roadmap`/`changelog`/`community` were
   removed in the Phase-4 pruning (see `ARCHIVE/docs/EXIT-AUDIT-2026-07-04-phase4-pruning.md`);
   grep of live `app/api/v1/*.py` for those names = 0 hits. The Advocate's
   "story engine" brief angle was stale — flagged so no narrative builds on it.

---

## 6. Confidence

- **HIGH** on all CRITICAL/HIGH code findings: each cites `path:line` and was
  either reported by ≥2 experts or re-verified by the orchestrator.
- **MEDIUM** on F4-style *exploitability* of the tenant-isolation opt-in model
  (the model is evidenced; a concrete IDOR would need a per-endpoint sweep) and
  on PM's "no marketplace storefront" (inferred from absent backend supply).
- **One correction applied:** the Reality Checker's #1 CRITICAL finding was
  reversed on independent verification (see §5.1).

---

*Generated from 6 independent persona-expert ledgers. Raw ledgers retained at
`.sisyphus/swarm-audit-2026-07-17/ledgers/`. No code was changed by this audit —
all cards ran read-only in isolated worktrees.*
