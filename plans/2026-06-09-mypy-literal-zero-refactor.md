# Mypy Literal-Zero Refactor Plan

> **Last updated:** 2026-06-09 (revised: 2026-06-09, after Phase 2 verification)
> **Current phase:** Phase 1 ✅ + Phase 2 ✅ landed; Phase 3 ready to start
> **Target:** Reduce backend mypy errors from 636 → 0

## ⚠️ Revision note (2026-06-09)

The original baseline estimate of "638 errors" included a stale 153 `[annotation-unchecked]` figure that was sampled from a state where the `failure_types.py` dataclass was unimportable, so mypy silently under-counted. After fixing the dataclass (commit `a020e0f`) and Phase 2's `disable_error_code = ["annotation-unchecked"]` (commit `90ce54a`), the **real baseline is 636 errors** (638 - 2 actual annotation-unchecked notes). Phase 2 cleared 2 errors, not 153. The literal-zero gap is 636 errors, not 485. Phases 3–5 need to address all 636.

## Background

Backend mypy currently sits at **636 errors** (under the `namespace_packages = false` working config). The collision on `backend/scripts/import_bindings.py` has two root causes:

1. **Namespace package collision** — `backend/scripts/` has no `__init__.py`, so PEP 420 namespace packaging causes `import_bindings.py` to be visible as both `import_bindings` and `scripts.import_bindings`.
2. **Actual duplicate files** — three operational scripts exist in **both** `backend/scripts/` and `backend/app/scripts/`: `create_chat_tables.py`, `seed_dashboard_data.py`, `seed_orchestration.py` (Phase 1 removed these duplicates in commit `d9dfd26`).

### Why we can't just toggle config

The two obvious one-line fixes (each tried in earlier sessions) both regress badly:

| Fix | New error count | Why it broke |
|---|---|---|
| `namespace_packages = false` alone (no Phase 1 dedup) | 435 | Stopped treating `backend/scripts/` as a namespace, surfacing latent type errors in scripts the app depends on |
| `exclude = ["backend/scripts/"]` alone | 622 | `exclude` pattern didn't match as expected; different resolution path |
| Both + delete the 3 duplicates | 638 | "True" latent errors surface across the whole backend |
| `files = ["backend/app", "backend/tests"]` (CLI arg = `backend/`) | 1 (miscount — actually 636) | mypy v1.8's `files` config defines a baseline but CLI args are added to the set |

A literal-zero goal therefore requires fixing the **636 latent type errors** that the current setup is silently hiding.

## Error profile (sampled with `namespace_packages = false` + Phase 2 enabled)

Total: **636 errors** across **~182 files** (974 source files checked).

### By code (top 10 — 92% of all errors)

| Code | Count | % of total | Nature |
|---|---|---|---|
| `[assignment]` | 100 | 16% | Real type mismatches — `dict` vs `list`, `Sequence[str]` vs `list[dict]` |
| `[arg-type]` | 95 | 15% | Wrong arg types to functions — `dict` passed where `str` expected, etc. |
| `[attr-defined]` | 83 | 13% | Missing attributes — opentelemetry stubs, `None` types missing members |
| `[str]` | 64 | 10% | Incompatible types in list comps, non-indexable collections |
| `[call-arg]` | 61 | 10% | Wrong/unknown kwargs to calls, missing required args |
| `[index]` | 53 | 8% | Indexing non-indexable types |
| `[return-value]` | 41 | 6% | Functions returning wrong types |
| `[union-attr]` | 34 | 5% | Accessing attribute on a union-typed value |
| `[unused-coroutine]` | 28 | 4% | `await` or `create_task` on a coroutine that was discarded |
| `[operator]` | 26 | 4% | Unsupported operand types |
| Other (misc, name-defined, arg-type, etc.) | 51 | 8% | Scattered |

### By file (top 10)

| Count | File |
|---|---|
| 29 | `backend/app/services/improvement/failure_repository.py` |
| 27 | `backend/app/governance/workflow_config/config_manager.py` |
| 24 | `backend/scripts/seed_demo_data.py` |
| 20 | `backend/app/services/mission_executor.py` |
| 17 | `backend/app/tools/llm_output_evaluator.py` |
| 15 | `backend/app/services/feedback_synthesizer.py` |
| 12 | `backend/app/services/improvement/knowledge_transfer.py` |
| 12 | `backend/app/integrations/openwhisk/api_gateway.py` |
| 12 | `backend/app/integrations/monitoring/health_check.py` |
| 11 | `backend/app/api/v1/data_export.py` |

## Strategy

Work in **6 phases**, each a separate commit. Each phase should leave the repo in a green state (mypy error count non-increasing, all existing tests passing). The literal-zero goal is the **last** commit, not the first.

### Phase 1 — Prerequisite: delete the 3 duplicate scripts

**Commit:** `chore(backend): remove 3 duplicate scripts in backend/app/scripts/`
**Risk:** Low — these files are dead code (not in the Docker image, per the audit in the previous session).
**Actions:**
- `git rm` `backend/app/scripts/create_chat_tables.py`, `seed_dashboard_data.py`, `seed_orchestration.py`
- Verify `backend/scripts/` versions are the operational source of truth (Dockerfile line 81 `COPY scripts/ /app/scripts/`)
- Verify no code in `backend/app/` imports these modules
- Mypy after: 1 error (unchanged — but the duplicate-file path is closed)

### Phase 2 — Suppress `[annotation-unchecked]` notes (bulk) ✅ LANDED

**Commit:** `chore(backend): suppress [annotation-unchecked] notes project-wide` (commit `90ce54a`)
**Count cleared:** 2 (not 153 as the original plan estimated)
**Risk:** Low — these are notes about unchecked bodies in third-party / untyped code, not real errors. The codebase already follows a pattern of per-bucket suppression commits.
**Actions:**
- ✅ Add `disable_error_code = ["annotation-unchecked"]` to root `[tool.mypy]`
- Mypy after: 636 errors (down from 638)

### Phase 3 — Top-5-file fix-up batch

**Commit:** `fix(backend): resolve type errors in top 5 highest-error files`
**Count cleared:** ~117 (29+27+24+20+17) — actual count to be confirmed after sampling
**Risk:** Medium — these are real type errors. Some fixes may need to widen dataclass fields, add `# type: ignore[arg-type]` for genuinely-Any contracts, or refactor type signatures.
**Working mode:** Apply `namespace_packages = false` to root `[tool.mypy]` (temporarily, then permanently in Phase 6) so the working tree shows the real 636-error profile.
**Actions (per file, sub-commits if needed):**
1. `failure_repository.py` (29) — sample audit then fix
2. `config_manager.py` (27) — sample audit then fix
3. `seed_demo_data.py` (24) — likely mostly `[arg-type]` and `[assignment]` from dict-shaped seeds
4. `mission_executor.py` (20) — core service, may need careful signature work
5. `llm_output_evaluator.py` (17) — tool code, may be more forgiving

### Phase 4 — Mid-tier fix-up batch

**Commit:** `fix(backend): resolve type errors in mid-tier service files`
**Count cleared:** ~74 (15+12+12+12+11+10+10+10+9+9)
**Risk:** Medium — same as Phase 3 but distributed across more files.
**Files:** `feedback_synthesizer`, `knowledge_transfer`, `openwhisk/api_gateway`, `monitoring/health_check`, `data_export`, `metrics_collector`, `decomposition_service`, `chat.py (v2)`, `chain_executor`, `context_builder`

### Phase 5 — Scatter sweep

**Commit:** `fix(backend): resolve remaining scattered type errors`
**Count cleared:** ~500 (residual — 636 - 117 - 74 = 445 minimum, but pattern diversity likely adds 50+ more for genuine noise)
**Risk:** Medium-low — these are small clusters per file; patterns likely repeat from Phases 3–4.
**Actions:**
- Re-run mypy, group remaining errors by code
- Apply per-code fix patterns (e.g., all `[str]` errors together, all `[attr-defined]` together)
- For genuinely unfixable third-party cases (opentelemetry stubs), use `type: ignore[attr-defined]` per-line

### Phase 6 — Re-enable `namespace_packages = false`

**Commit:** `chore(backend): set namespace_packages = false in [tool.mypy] to clear final collision`
**Count cleared:** 1
**Risk:** Low — at this point all 638 latent errors are fixed, so the namespace change should be a clean delta.
**Actions:**
- Add `namespace_packages = false` to root `[tool.mypy]`
- Run mypy — should report **0 errors** for the first time
- If any residual, suppress with targeted `type: ignore` (expect ≤ 5)

## Verification strategy

Per phase:
- `mypy backend/` — error count must monotonically decrease (or stay flat) and never increase
- `git diff --check` — no whitespace errors
- `git log --oneline` — clean linear history

End-to-end (after Phase 6):
- `mypy backend/` — 0 errors, exit code 0
- Run a representative subset of backend tests (focused on the files touched in Phases 3–5): `pytest backend/tests/ -k "failure_repository or config_manager or mission_executor"`
- Full backend test suite as a final gate (longer, but worth the confidence)
- Commit message should call out "closes the last 1-error mypy baseline" for traceability

## Effort estimates (revised)

| Phase | Count | Commit? | Approx. effort | Risk |
|---|---|---|---|---|
| 1. Delete 3 duplicates | 0 | ✅ landed (`d9dfd26`) | 15 min | Low |
| 2. annotation-unchecked sweep | 2 (revised) | ✅ landed (`90ce54a`) | 30 min | Low |
| 3. Top-5-file fix-up | ~117 | yes (or 5 sub-commits) | 3–5 hours | Medium |
| 4. Mid-tier fix-up | ~74 | yes | 2–3 hours | Medium |
| 5. Scatter sweep | ~500 (revised) | yes | 6–10 hours | Medium-low |
| 6. Enable namespace_packages = false | 1 | yes | 30 min + verification | Low |
| **Total** | **636 + 1** | **6+ commits** | **~15–22 hours** | — |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Real type errors mask real runtime bugs | Run a test subset after each phase; if a fix breaks a test, prefer a `# type: ignore[arg-type]` + comment explaining the contract over a structural change |
| `seed_demo_data.py` is 24 errors — could be heavy refactor | Phase 3 sub-commit per file keeps blast radius small; if a file is too costly, isolate to a follow-up |
| `failure_repository.py` (29) is the biggest — possibly architectural | Same — sub-commit; if too costly, suppress the specific noisy lines with comments |
| Re-enabling `namespace_packages = false` surfaces a new error we didn't see in the sample | Phase 5 should leave the surface clean; the latency-tolerant answer is a per-line `type: ignore` for ≤ 5 stragglers |
| Some `[attr-defined]` errors are from missing third-party stubs (opentelemetry) | Use per-line `type: ignore[attr-defined]`, which is already the established pattern in the codebase |

## Out of scope (for this refactor)

- Frontend type checking (Next.js, TS) — separate
- Adding strict mypy flags (`--strict`, `--disallow-untyped-defs`) — would explode the count further
- Restructuring the 21-file `backend/scripts/` catalog — orthogonal
- Refactoring the `TestResult` enrichment from `454b026` — already landed, working

## Rollback strategy

Each phase is a single commit and independently revertible. If a later phase regresses something, `git revert <sha>` restores the prior state. Phases 1 and 2 are essentially zero-risk rollbacks; Phases 3–5 may need a test-suite pass before declaring green.

## Key fixes / decisions

- **Decision:** The literal-zero goal is achievable but expensive (~15–22 hours of careful work after revision). Phased approach lets us ship incremental value (Phase 1 alone is a clean structural improvement).
- **Decision (revised):** The 153 `[annotation-unchecked]` figure in the original plan was a stale estimate from a state where `failure_types.py` was unimportable. The real count was 2. Phases 3–5 must address 636 errors, not 542.
- **Decision:** Use `disable_error_code = ["annotation-unchecked"]` (Phase 2) — consistent with the prior session's pattern of per-bucket suppression commits.
- **Decision:** Phase 6 is the literal-zero "punchline" commit; everything before it is setup.
- **Decision:** No structural changes to the `app/scripts/` directory or `__init__.py` files in this refactor — out of scope.
- **Lesson:** Always verify basher agent output with explicit `grep -c` AND `wc -l` cross-check on mypy output. The basher's `tail -N` truncation pattern gave false "1 error" reads throughout the session.
