# ADR-002: v1 → Unified-Substrate Execution Cutover

**Status:** Accepted (safe slice) — destructive cleanup PENDING human approval
**Date:** 2026-07-17
**Decision-maker:** Architecture review (R6, Swarm audit REPORT.md §3 H5)
**Supersedes / relates to:** `substrate/H5-1-DESIGN.md §5` (three-phase rollout),
`app/services/substrate/AGENTS.md` ("Migration state and feature flag"),
`app/services/AGENTS.md` §1 (mission execution cluster)

---

## Context

Flowmanner's H5.1 program collapsed **7 separate execution engines** (mission,
DAG, graph, swarm, swarm-pipeline, langgraph, meta) into a single durable
`UnifiedExecutor` that dispatches to typed `ExecutionStrategy` objects. The
original rollout (`H5-1-DESIGN.md §5`) was gated behind an
`FLOWMANNER_UNIFIED_EXECUTOR` env var with three phases:

- **Phase A** — `off` (default) / `run` / `all`, coexistence behind the flag.
- **Phase B** — 2–4 weeks parallel run + parity tests.
- **Phase C** — flip to `all`, delete old executors, remove flag code.

The R6 card was written against the audit's snapshot of that plan: it assumed
`mission_executor.py` (~1,387 LOC) was **still in the tree and still wired by v1
routes**, and that `FLOWMANNER_UNIFIED_EXECUTOR=all` had **never been flipped**.

### Ground-truth investigation (2026-07-17, this worktree)

Before designing the cutover, the actual state was verified against
`agent/2026-07-17-impl/r6` (`git rev-parse HEAD` = `b8bd713e`). The audit's
premise is **stale** — most of the cutover already shipped:

| Audit premise | Actual state (verified) | Evidence |
|---|---|---|
| `mission_executor.py` (1,387 LOC) still in tree | **DELETED** | `git log --diff-filter=D -- "*mission_executor.py"` → `e6d6d19b refactor(Phase 2 Steps 5+6): … delete mission_executor (~2,000 LOC)`; `git cat-file -e HEAD:backend/app/services/mission_executor.py` → *does not exist in HEAD* |
| Old executors coexist behind the flag | **ALL DELETED** | `graph_executor.py`, `dag_executor.py`, `swarm/orchestrator.py`, `swarm_pipeline/orchestrator.py`, `langgraph/agent.py`, `nexus/meta_loop_orchestrator.py` — all `MISSING` on disk |
| `FLOWMANNER_UNIFIED_EXECUTOR=all` never flipped | **Flag is not read by any source module** | `grep -rn UNIFIED_EXECUTOR app/ --include=*.py` (excl. tests) → matches **only** in 3 Markdown docs; no `app/config.py` field, no compose/`.env`, no `os.getenv` |
| v1 routers `flow_compat.py`, `swarm.py`, `mission_decomposition_routes.py` inline old executors | **Those router files are GONE**; surviving routers do not import old executors | `flow_compat.py`, `swarm.py`, `mission_decomposition_routes.py` `MISSING`; only residue is a **comment** at `app/api/v1/plugins.py:477` referencing "the old `ExecutionContext` from graph_executor" |
| `graph.py:323` / `substrate.py:235` are "no substrate run" execution branches | Neither line is an execution branch | `graph.py:323` is inside `compare_executions` (a read/diff endpoint on `GraphExecution`); `substrate.py:235` is a *replay-events* message string ("Mission has no substrate run") in the H5.2 read API — not an execution path |

**The single durable execution path today** is
`get_unified_executor().execute(session, workflow)`, reached from:
`app/api/_mission_cqrs/commands.py`, `app/services/mission_program_service.py`,
`app/services/run_service.py`, `app/services/trigger_service.py`,
`app/tasks/hitl_resume.py`, `app/tasks/mission_execution.py`. This matches
`app/api/AGENTS.md §8` ("All LLM calls in CQRS routes go through
`substrate.UnifiedExecutor` … `MissionExecutor` is no longer the execution
path", post-Phase-8.1).

### What remains (the real, small residue)

The code-level cutover is effectively **complete**. What is left is *not* a
risky engine swap; it is **cleanup of a now-vestigial abstraction and stale
documentation**:

1. **Vestigial env var** `FLOWMANNER_UNIFIED_EXECUTOR` — read nowhere in code, so
   setting it has **no effect**. This is a *silent-misconfiguration hazard*: an
   operator who sets `=off` (or omits it) reasonably expects the old engines to
   serve traffic. They cannot — the old engines are deleted — so the var lies.
2. **Stale documentation** in three files still describing the flag as live:
   `app/services/AGENTS.md:116`, `app/services/substrate/AGENTS.md:74,81`,
   `app/services/substrate/H5-1-DESIGN.md:532,543,553`.
3. **A dangling comment** at `app/api/v1/plugins.py:477` referencing the deleted
   `graph_executor.ExecutionContext`.

Because the card is explicitly **design + safe slice only** (no destructive
change, no flag flip, no route edits), this ADR *documents* the true state and
the remaining sequence, and the accompanying commit ships **only a guard + tests**
(see "Decision → Safe slice"). Items 1–3 above are deferred to a follow-up card
under explicit human approval.

---

## Decision

### The cutover is ratified as effectively-done; the remaining work is *decommissioning*, not *cutover*.

Rather than execute the original three-phase flip (which presumed live
coexistence that no longer exists), we recognize the substrate as the sole GA
execution engine and treat the leftover flag/docs/comment as **decommissioning
debt**. Two options were considered for how to handle the vestigial flag:

#### Option 1 — Silently delete the flag references and stale docs (do nothing at runtime)

Just remove the Markdown mentions and the plugins.py comment; leave no runtime
signal.

#### Option 2 — Add a startup guard that *warns* if the vestigial flag is set to anything other than `all` in production, THEN clean up docs (chosen for the guard; docs cleanup deferred)

Keep a loud, observable signal during the decommission window so that any
environment still exporting `FLOWMANNER_UNIFIED_EXECUTOR=off|run` (which would
now be a dangerous lie) is surfaced in logs at boot, before the var is finally
removed.

### Trade-off matrix

| Criterion | Opt 1 — silent delete | Opt 2 — guard-then-delete (chosen) |
|---|---|---|
| **Reversibility** | High (docs only) | High (guard is additive, no behavior change) |
| **Operational safety** | Low — a stale `=off` in an env file goes unnoticed; operators keep a false mental model | High — boot-time warning names the exact misconfig and points at this ADR |
| **Coupling added** | None | Minimal — one method on `Settings`, one call in `lifespan` |
| **Cost / complexity** | Lowest | Low (≈40 LOC + tests) |
| **Detects config drift** | No | Yes — catches leftover env exports across all deploy targets |
| **Blast radius if wrong** | n/a | None — the guard only logs; it never raises, never changes execution |

Option 2 wins on the axis that matters here: this is a system where a
`FLOWMANNER_UNIFIED_EXECUTOR=off` left in a `.env` on any host would give an
operator a **false belief that the legacy engines are serving traffic**. A
warning that costs ~40 LOC and can never change behavior is cheap insurance
during the window before the var is fully removed.

### Safe slice shipped in *this* commit (non-destructive)

1. **`Settings.warn_vestigial_executor_flag()`** in `app/config.py` — reads
   `FLOWMANNER_UNIFIED_EXECUTOR` from the environment (NOT a typed Settings
   field, to avoid resurrecting it as config) and returns a warning string when,
   in a non-development `APP_ENV`, it is set to anything other than `all`
   (case-insensitive) or unset. Returns `None` otherwise. **Never raises.**
2. **A call site in `app/lifespan.py`** that logs the warning at startup
   (non-fatal, `logger.warning`).
3. **Regression / fitness tests** in `backend/tests/`:
   - `test_substrate_cutover_guard.py` — unit tests for the guard across
     `unset / off / run / all / ALL / garbage` × `development / production`.
   - `test_substrate_cutover_fitness.py` — **architectural fitness functions**
     that would catch a *regression* of the cutover: (a) the deleted executor
     modules stay unimportable; (b) no source module (excluding docs/tests)
     reads `FLOWMANNER_UNIFIED_EXECUTOR`; (c) `get_unified_executor` remains the
     only exported execution entry point. These are the "parity/regression tests
     that catch behavior change" the card asked for, reframed to the true state:
     the behavior to protect is *"there is exactly one engine and the flag is
     dead."*

### Explicitly NOT in this commit (deferred to a human-approved follow-up)

- Flipping / removing the `FLOWMANNER_UNIFIED_EXECUTOR` env var from any deploy
  target (it is already inert; removal is a hygiene task).
- Deleting `mission_executor.py` — **already deleted** (`e6d6d19b`).
- Editing any legacy router execution path — **none remain**.
- Rewriting the stale AGENTS.md / H5-1-DESIGN.md flag documentation — recommended
  as the first follow-up, but a doc edit is out of scope for the "tests + guard
  only" boundary of this card.

### Follow-up decommission sequence (for the approving human)

1. **Confirm no deploy target exports the var** — `grep -rn UNIFIED_EXECUTOR`
   across `/opt/flowmanner/.env*`, `docker-compose*.yml`, and the homelab/VPS
   env. The startup guard from this slice will surface any that are set to a
   non-`all` value in logs.
2. **Remove the var** from any env file that still sets it (no restart-time
   behavior change; it is inert).
3. **Delete the guard** added in this slice once step 2 is verified across all
   hosts (the guard is transitional scaffolding).
4. **Update the three stale docs** (`app/services/AGENTS.md`,
   `substrate/AGENTS.md`, `H5-1-DESIGN.md`) to state the cutover is complete and
   the flag is retired.
5. **Fix the dangling comment** at `app/api/v1/plugins.py:477`.

---

## Consequences

### Easier

- **One execution engine, documented as such.** New contributors stop reading
  the three-phase flag plan as if it were live and mis-modeling the system.
- **Config drift is observable.** Any host still exporting a non-`all` value is
  named in boot logs during the decommission window.
- **Regression protection.** The fitness tests fail loudly if someone
  reintroduces an old executor module or re-wires the dead flag into a code path.

### Harder / trade-offs given up

- **We keep a small amount of transitional scaffolding** (the guard) that must
  itself be removed later — a deliberate two-step to avoid a silent config lie.
- **The card's original "parity between two live engines" test is not
  buildable** — there is only one engine. We give up literal A/B parity testing
  and substitute architectural fitness functions that protect the *invariant*
  the parity test was meant to defend (single engine, dead flag).

### Neutral / notes

- No runtime behavior changes in this commit. `assert_production_ready()` and
  the existing secret validation are untouched; the new guard only adds a
  `logger.warning` path.
- The `substrate/AGENTS.md` "Before deleting an old executor" checklist is now
  historical — the executors are already gone; the checklist is preserved for
  provenance but should be marked complete in the follow-up doc pass.
