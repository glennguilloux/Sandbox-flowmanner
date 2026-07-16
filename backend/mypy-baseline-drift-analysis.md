# mypy-baseline-drift — Analysis & Burn-down Plan

**Task:** t_2666ebfd (SELF-AUDIT-MED-07)
**Date:** 2026-07-16
**Analyst:** fmw3 (Hermes)
**Baseline file:** `backend/mypy-baseline.txt` (314 lines)

---

## 0. Headline finding (more important than the original "314" number)

The baseline is **severely out of date** and the CI "baseline-enforced" gate is
currently **RED**. I regenerated the baseline from current source using the exact
command documented in `.github/workflows/ci.yml` (lines 112-119):

```
mypy app/ --ignore-missing-imports --no-error-summary --hide-error-context 2>&1 \
  | sed -E 's/:[0-9]+(:[0-9]+)?:/:line:/g' | sort -u
```

Results (distinct normalized lines):

| Metric | Count |
|--------|-------|
| Baseline entries (claimed debt) | 314 |
| Current real distinct errors | **447** (347 `error:` + 100 `note:`) |
| Baseline entries already fixed in source (**stale noise**) | **153** |
| Current errors NOT in baseline (**CI would fail on these**) | **286** |

So the original self-audit number (314) *understates* the debt, and ~half the
baseline (153/314) is stale. Because CI does `diff mypy-baseline.txt -`, any run
today surfaces **286 new errors** → the gate is effectively broken (it blocks on
errors that were never baselined, OR the baseline simply hasn't been refreshed
since the substrate / `_mission_cqrs` code influx).

---

## 1. Categorization of the 447 current errors

### A. Missing 3rd-party stubs — `import-untyped` (~43 primary + notes)
Pure environment/config debt, **not code bugs**.
Missing stubs: `redis`, `redis.asyncio`, `yaml`, `requests`, `requests.adapters`,
`cachetools`, `croniter`.
**Fix:** add to `requirements.txt` (dev): `types-redis`, `types-PyYAML`,
`types-requests`, `types-cachetools`, `types-croniter`. Or add precise
`[[tool.mypy.overrides]]` with `ignore_missing_imports = true` per 3rd-party
module (the repo already does this for `app.migrations.versions.*`). This single
change removes ~43 errors with zero code risk.

### B. Notes / LSP noise (`annotation-unchecked`, continuation notes) (~110 lines)
"By default the bodies of untyped functions are not checked" — informational, not
errors. Already excluded under `--check-untyped-defs`. No action.

### C. Real logic type errors in active code (~290)
Dominant new-error codes (NOT in baseline → CI-red):
- `attr-defined` (66) — e.g. `User.has no attribute is_superuser`,
  `AuthSession.has no attribute scopes`, `type[SubstrateEvent].has no attribute event_type`.
  Many are real model/schema mismatches in the CQRS + substrate work.
- `arg-type` (64) — incompatible argument types across service/router boundaries.
- `assignment` (43) — incompatible assignments.
- `call-arg` (36) — wrong arg counts (e.g. `update_agent_template`, `ToolRegistry.get`).
- `return-value`, `union-attr`, `misc`, `override`, `index`, etc.

These are **genuine type-safety debt** introduced by in-flight refactors
(substrate strategies, `_mission_cqrs`, model migrations). They are the real
burn-down target — but each needs per-file investigation (out of scope for this
small-fix card; see Plan §3).

### D. Stale baseline entries already fixed in source (153)
Including:
- `sentry_integration.py` ×6 `no-redef` — source already has `# type: ignore[no-redef]`
  on every `from sentry_sdk...` import.
- `cosine_similarity_calc.py` `np` — `numpy` imported locally inside the function.
- `auth.py` `JSONResponse` — imported locally inside `_auth_response`.
- `tabular_data_cleaner.py` str→float — referenced line no longer exists (file shrank).
- `linear.py` dict-item ×4, `stable_diffusion_pipeline.py` `asyncio` (now fixed, see §2).

These 153 lines are pure noise inflating the "debt" metric and should be dropped
by regenerating the baseline.

---

## 2. Clear-win fix applied this card

**File:** `backend/app/tools/stable_diffusion_pipeline.py`
**Bug:** `await asyncio.sleep(3)` at the Replicate poll loop (line ~411) with no
`import asyncio` at module level → **runtime `NameError`** on the Replicate/Local
provider path. Masked only because `no_strict_optional` + the stale baseline hid it.
**Fix:** added `import asyncio` to the module imports.
**Verification:**
- `ruff check` + `ruff format --check`: PASS
- mypy: the `name-defined` for `asyncio` is resolved (this baseline entry is now burn-down).
- No behavior change; no dedicated test file for this module.

This is the only code change made (1 line). All other 446 errors are left for the
burn-down plan — bulk-fixing them in one card is explicitly out of scope and
risk-prone.

---

## 3. Prioritized burn-down plan

**P0 — Restore a truthful gate (do this first, low risk, high value):**
1. Add stub packages to dev requirements: `types-redis`, `types-PyYAML`,
   `types-requests`, `types-cachetools`, `types-croniter`. Removes ~43 env errors.
2. Regenerate `mypy-baseline.txt` from current source (documented command) so it
   drops the 153 stale lines and becomes a HONEST contract. New count ≈ 447−43−153
   ≈ 250 real errors.
3. Re-run CI: the `diff` gate now reflects reality; new-error detection works again.

**P1 — Fix the silent-logic bugs (highest correctness value):**
- `unused-coroutine` ×2 (`provider_fallback.py`, `config_manager.py`) — forgotten
  `await`; the intended side effect (cost tracking / config query) silently no-ops.
- `name-defined` ×2 (`auth_v3_models.py` `User`, `reviewer_guard/orchestrator.py`
  `_vr`) — likely missing import or typo.
- `method-assign` ×2 (`main_fastapi.py`, `test_side_effect_safety.py`) — assigning
  to a method (monkeypatch done wrong / real bug).

**P2 — Model/schema contract drift (largest bucket, needs care):**
- `attr-defined` (66) in `_mission_cqrs/*`, `app/api/v1/agent.py`, `deps.py`, etc.
  Audit whether the model/schema actually gained/lost the attribute or the call
  site is wrong. Fix the side that is incorrect; do NOT paper over with `# type: ignore`.
- `arg-type` (64) + `call-arg` (36): signature mismatches at service↔router seams.

**P3 — Subsystem-level (biggest effort, defer):**
- `override` clusters in `substrate/strategies/*` (7 files) and `plugin_runtime.py`
  — LSP violations in the execution-strategy hierarchy. Worth a dedicated card.
- `abstract` (cannot instantiate) in `a2a`, `domain_agents`, `web_search/providers`.

---

## 4. What would reduce the baseline (summary)

1. Install the 5 `types-*` stub packages (env debt, no code change).
2. Regenerate the baseline so it stops counting 153 already-fixed lines and starts
   counting the 286 real new errors → honest gate.
3. Per-PR type hygiene: the pre-commit mypy hook already runs `--follow-imports=silent`
   on changed files, so new code can't add unbaselined errors locally — but the
   **full-suite** baseline gate must be kept current or it loses meaning.
4. Tackle P1 (silent-logic bugs) before P2/P3 — they are real defects, not just
   type noise.

---

## 5. Verification commands used (canonical venv)

```bash
cd /opt/flowmanner/backend
export PYTHONPATH=/opt/flowmanner/backend
PY=/opt/flowmanner/backend/.venv/bin/python

# Current real error count
$PY -m mypy app/ --ignore-missing-imports --no-error-summary --hide-error-context 2>&1 \
  | sed -E 's/:[0-9]+(:[0-9]+)?:/:line:/g' | sort -u | wc -l

# Diff vs committed baseline (what CI does)
$PY -m mypy app/ --ignore-missing-imports --no-error-summary --hide-error-context 2>&1 \
  | sed -E 's/:[0-9]+(:[0-9]+)?:/:line:/g' | sort -u | diff mypy-baseline.txt -

# Lint the changed file
$PY -m ruff check app/tools/stable_diffusion_pipeline.py
$PY -m ruff format --check app/tools/stable_diffusion_pipeline.py
```

**Changed files:** `backend/app/tools/stable_diffusion_pipeline.py` (1 line: `import asyncio`),
plus this analysis doc. No other files touched. No commit/push/deploy performed.
