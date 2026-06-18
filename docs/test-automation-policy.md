# Test Automation Policy — Operational Targets

> **What this is:** The current numeric targets, SLAs, and rules for the Flowmanner test suite. Numbers live here so the [strategy document](./test-automation-strategy.md) can stay focused on principles, definitions, and structure.
>
> **What this is not:** The strategy, the philosophy, the contracts, the templates, or the environment layout. Those are in the strategy doc.

**Status:** v1.2 — flake threshold reconciled with strategy §10.4; marker descriptions synced with strategy §10.2.1; addopts paths corrected
**Last updated:** 2026-06-18
**Owner:** rotating, see [strategy doc §13.2](./test-automation-strategy.md#132-ownership)
**Review cadence:** monthly, or sooner if a number proves badly off

> **All targets in this document are "initial targets."** They will be revised as we collect real data from CI runs, flake dashboards, and time-to-debug measurements. If a number here contradicts a number in the strategy doc, the **strategy doc wins** (this file is the implementation; the strategy doc is the contract).

---

## 1. Pyramid targets

| Layer | Count target (initial) | Wall-clock budget | Hard limit | Flake budget |
|-------|------------------------|-------------------|------------|--------------|
| Unit (pytest, RTL) | 1,000+ tests | < 30 s | 60 s | < 0.1 % |
| Integration | 200+ tests | < 3 min | 5 min | < 0.5 % |
| E2E (Playwright) | 30+ critical journeys | < 8 min | 15 min | < 1 % |
| Chaos | 10+ scenarios | run on demand | n/a | n/a |

> **Count targets are aspirational ceilings for the year, not the floor for next sprint.** We are currently at ~168 backend test files; the gap to 1,000 is a multi-quarter initiative, not a single-PR goal.

## 2. Suite wall-clock budgets

| Suite | Budget | Hard limit | Owner |
|-------|--------|-----------|-------|
| Pre-commit unit | 30 s | 60 s | developer local |
| PR unit + sanity (auto-tagged) | 90 s | 3 min | GitHub Actions |
| Full PR suite (unit + sanity + integration) | 5 min | 10 min | GitHub Actions |
| Nightly full (unit + integration + E2E) | 30 min | 60 min | GitHub Actions scheduled |
| Playwright E2E (smoke) | 8 min | 15 min | GitHub Actions |
| Deploy probe (per-service, post-restart) | 30 s | 90 s | `deploy-*.sh` |

> **The hard limit is a guardrail**, not a target. A suite that runs at 9:30 when the limit is 10 min is fine. A suite that runs at 11 min is **broken and must be split or moved to nightly**.

## 3. Coverage floors (changed lines)

| Area | Floor | Hard minimum |
|------|-------|--------------|
| Backend (general) | 80 % | 70 % |
| Backend critical (auth, billing, missions, sandbox-preview) | 90 % | 85 % |
| Frontend (general) | 70 % | 60 % |
| Frontend critical (auth flow, billing, mission UI) | 85 % | 75 % |

> Floors are measured on **changed lines only**, not the whole file. A 3-line bug fix in a 2,000-line module does not need 100 % coverage of the file.

## 4. Flake rules

| Rule | Value |
|------|-------|
| Failures in a rolling 14-day window to trigger quarantine | 3 |
| Quarantine SLA (time to fix or delete) | 7 days |
| Re-flake after leaving quarantine → permanent deletion | 1 (one strike) |
| Quarantined tests run on | every PR, but **do not block merge** |

> Quarantine is a **delay**, not a **pardon**. A test that flakes even once after leaving quarantine is, by definition, not load-bearing — it is deleted immediately and its contract is moved to `docs/LEGACY.md`. Three flakes → quarantine is generous; one re-flake → deletion is the standard.

## 5. SLAs

| Item | SLA |
|------|-----|
| Add a regression test for a new bug fix | same PR |
| Quarantine a flaky test after its 3rd failure | within 7 days |
| Fix or delete a quarantined test | within 7 days of quarantine |
| Debug a failing test using the CI reproducer | ≤ 5 min |
| File a "smell" from an exploratory session | within 24 h |
| Update smoke/sanity after a charter surfaces a gap | within 48 h |
| Review the policy doc | monthly |
| Review the strategy doc | quarterly |

## 6. "Suite is healthy" criteria

The suite is considered healthy when **all** of these hold for two consecutive measurement weeks:

- [ ] Median time-to-green for a PR is < 90 s.
- [ ] Quarantine list is empty or shrinking.
- [ ] New regressions are caught by an existing test ≥ 60 % of the time.
- [ ] A developer answers "why did this fail?" in < 5 min for ≥ 90 % of failures.
- [ ] No suite exceeds its hard limit (column 4 of §2).

If any criterion regresses for two consecutive weeks, the **strategy doc is the first place we look**, not the test code.

## 7. Operational rules

### 7.1 Pytest discovery (mandatory `addopts`)

`backend/pyproject.toml` must contain the following in `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
addopts = [
    "--ignore=tests/smoke",
    "--ignore=tests/chaos",
]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "smoke: smoke tests (excluded from default runs; run with `pytest backend/tests/smoke/`)",
    "chaos: chaos tests (excluded from default runs; run with `pytest backend/tests/chaos/`)",
    "sanity: sanity tests (per-area markers: sanity_auth, sanity_chat, …)",
    "sanity_auth: sanity tests for the auth area",
    "sanity_chat: sanity tests for the chat area",
    "sanity_missions: sanity tests for the missions area",
    "sanity_byok: sanity tests for the BYOK area",
    "sanity_websocket: sanity tests for the WebSocket area",
    "sanity_frontend: sanity tests for the frontend area",
    "regression: regression tests; defend against a specific past bug (§5)",
    "flaky: quarantined flaky test; does not block merge (§10.4)",
]
```

Paths are relative to `backend/pyproject.toml` (where the `[tool.pytest.ini_options]` table lives).

**Why directory-based ignore, not marker-based:** `pytest -m "not integration"` evaluates True for *any* test without the `integration` marker — which would sweep unmarked smoke tests and `@pytest.mark.chaos` tests into the per-PR pipeline, where they will fail (no real DB/Redis/LLM) and block merges. The `--ignore` rules make this impossible regardless of marker discipline. See the [strategy doc §10.2.1](./test-automation-strategy.md#1021-the-marker-sweep-trap-and-how-we-avoid-it) for the full reasoning.

### 7.2 Forbidden without override

- `git push --force` to `main` or any deployed branch.
- `gh pr merge --admin` or any other bypass of branch protection.
- `pytest --no-header --tb=no` in CI (we want the traceback).
- Disabling a test via `xfail` without a linked ticket and an expiration date.
- Deleting a test file without a justification comment in the commit body.
- Removing the `addopts` from `pyproject.toml` (§7.1) without an updated `addopts` that keeps the same exclusion guarantees.

### 7.3 Override path (when something must ship urgently)

1. Open a PR marked `URGENT` in the title.
2. Two reviewers, one of whom is a CODEOWNER.
3. A `git notes add` entry on the merge commit recording the override reason.
4. The override is reviewed in the next weekly retro.

### 7.4 Bypass of CI checks (force-merge, admin override, etc.)

Same as §7.2 — all are forbidden in policy and tooling. If you genuinely need to ship, follow §7.3.

## 8. How to propose a change to this document

1. Open a PR that updates this file with the proposed new value.
2. Include in the PR body:
   - The current value.
   - The proposed value.
   - The data that justifies the change (link to a dashboard, a query, or a CI artifact).
   - The expected impact (will any test be quarantined? will a PR be slower? will a coverage floor catch more bugs?).
3. One reviewer from the platform team is enough; no ADR required.
4. Update §9 (changelog) as part of the same PR.

## 9. Change log

| Date | Version | Change | Reason |
|------|---------|--------|--------|
| 2026-06-18 | v1.2 | Three fixes: (1) §4 flake deletion threshold changed from 3 → 1 ("one strike you're out") to match strategy §10.4 (the contract); (2) §7.1 marker descriptions synced with strategy §10.2.1; (3) §7.1 addopts paths corrected to be relative to backend/pyproject.toml | Strategy §10.4 defines "one strike you're out" — a test that re-flakes once after leaving quarantine is deleted. Policy doc had the stale value of 3 from v1. Marker descriptions and addopts paths were out of sync with the actual pyproject.toml location. |
| 2026-06-18 | v1 | Initial targets set | Document created. No data yet; values are informed estimates pending first measurement cycle. |
| 2026-06-18 | v1.1 | Added §7.1 "Pytest discovery" mandating the `addopts` rule that excludes `backend/tests/smoke` and `backend/tests/chaos` from default test collection | Qwen review (v1.2 of strategy doc) caught a marker-sweep bug: `pytest -m "not integration"` would sweep unmarked smoke and chaos tests into the per-PR pipeline. Directory-based ignore via `addopts` is robust against marker typos and is the chosen fix. Cross-references strategy doc §10.2.1. |
