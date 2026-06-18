# Test Automation Strategy

**Status:** v1.4 — codebase-verification pass: health endpoints, DB smoke example, logging path, test count, deploy probes, frontend source paths, implementation status, and flake deletion policy all reconciled with the live repo.
**Last updated:** 2026-06-18
**Owners:** Backend & Frontend leads
**Scope:** Flowmanner — Next.js frontend (homelab source `/home/glenn/FlowmannerV2-frontend/`; VPS rsync target `/opt/flowmanner/frontend/`) and FastAPI backend (`/opt/flowmanner/backend/`)
**Companion docs:**
- [test-automation-policy.md](./test-automation-policy.md) — operational numbers, SLAs, "healthy suite" criteria.

> **Implementation status (2026-06-18):** This document defines the target strategy. The following infrastructure pieces are newly created alongside this revision and may still be sparsely populated:
> - Test directories: `backend/tests/{smoke,sanity,regression,_quarantine,unit}/` — created as structural placeholders
> - Doc directories: `docs/{test-cases,exploratory}/`, `docs/LEGACY.md`, `docs/test-automation/sanity-matrix.md` — stubs
> - CI: `.github/workflows/pr-check.yml` — deletion-check only
> - Tooling: `scripts/select-sanity.py` — functional but minimal
> - `backend/pyproject.toml` `addopts` — implemented
> - Pytest markers (`sanity_*`, `regression`, `flaky`) — registered in pyproject.toml; adoption across existing tests is gradual

---

## TL;DR for engineers

Five rules, in order of how often you will need them:

1. **New test?** Use the decision tree in §2.1.
2. **Bug fix?** Add a regression test in `backend/tests/regression/` (template in §15.1). Same PR.
3. **PR change?** Add or update a sanity test with the right marker (`@pytest.mark.sanity_<area>` or `@sanity` in Playwright). See §4.
4. **Flaky test?** Quarantine per [policy doc §4](./test-automation-policy.md#4-flake-rules), fix within SLA, or delete with justification.
5. **Don't delete tests without justification.** Retire to `docs/LEGACY.md` instead (§5.1).

The rest of this document is the *why* behind these rules. Skim the table of contents in §1 first; only read the section you need.

---

## 1. Executive Summary

This document defines how Flowmanner approaches test automation across the stack. It is the single source of truth for **which tests run when, on which environments, with which guardrails**, and **how a human or agent extends the suite without breaking trust in it**.

Frontend paths in this document refer to the frontend source tree. On the homelab, this is `/home/glenn/FlowmannerV2-frontend/`. On the VPS, the read-only copy lives at `/opt/flowmanner/frontend/`.

The strategy rests on three principles:

1. **The test pyramid is enforced, not aspirational.** Operationally: there is a count target, a wall-clock budget, and a flake budget per layer in [the policy doc](./test-automation-policy.md) §1, and CI measures all three. A layer that is missing its target is a backlog item, not a "we'll get there someday."
2. **Speed-to-signal over coverage numbers.** A green pipeline that takes 45 minutes is a liability; a flaky suite that takes 3 minutes is a worse one. Both are tracked and bounded by [policy doc §2](./test-automation-policy.md). Coverage floors exist ([policy doc §3](./test-automation-policy.md)) but they apply to **changed lines**, not whole files.
3. **Every test is a contract.** A test case (§6) is a specification of behavior, the pytest function is one implementation of it. A test that cannot be traced to a contract is a candidate for deletion.

### 1.1 How to read this document

This document deliberately mixes three kinds of statement. To avoid treating any of them as more permanent than they are:

| Kind | Where it lives | How to change it |
|------|----------------|------------------|
| **Policy** — "we do X" or "X is forbidden" | This document | ADR + PR review |
| **Current target** — "X is 90 s" or "X is 80 %" | [Policy doc §1–§5](./test-automation-policy.md) | One PR with data justifying the change |
| **Enforced rule** — automated in CI | `pre-commit-config.yaml`, `.github/workflows/*`, linter rules | Edit the tool config, not this document |

If a number in this document and a number in the policy doc disagree, **this document is the contract; the policy doc is the implementation**. Update the policy doc to match the contract, not the other way around.

### 1.2 Terminology

We use these terms precisely throughout:

| Term | Definition |
|------|------------|
| **Test** | A runnable function (pytest test, Playwright test, RTL test). The *implementation*. |
| **Test case** | A specification of behavior, in a `docs/test-cases/*.md` table. The *contract*. A case may have zero, one, or many automated tests implementing it. |
| **Suite** | A collection of tests grouped by marker, file path, or tag. |
| **Probe** | A short, non-DB, non-external-dep health check (e.g. `/health`). Distinct from a full smoke test (§3.1). |
| **LEGACY** | A test case moved to `docs/LEGACY.md` because the contract it enforces is no longer load-bearing (§5.1). The case is not deleted; it is intentionally retired. |

The remaining sections define the building blocks:

| § | Topic | Purpose |
|---|-------|---------|
| 3 | Smoke tests (and deploy probes) | Is the system alive end-to-end? |
| 4 | Sanity tests | Did the change break the obvious thing? |
| 5 | Regression tests | Did we re-introduce a known bug? |
| 6 | Test cases | What is the catalog format? |
| 7 | Checklists | What must be true before merge? |
| 8 | Exploratory testing | How do humans/agents hunt the unknown? |
| 9 | Debug logs | How do we debug a failed run? |
| 10 | Guardrails | What stops bad tests from shipping? |
| 11 | Assertions | How do we write assertions that hold up? |
| 12 | Environment matrix | What runs where? |

---

## 2. Test Pyramid & Strategy Overview

```
       ╱  E2E / Playwright  ╲          ~5%    — full user journey
      ╱  Integration (API)    ╲         ~25%   — cross-module wiring
     ╱  Unit (pytest, RTL)      ╲       ~70%   — pure logic, fast
    ─────────────────────────────
```

**Targets (current):** see [policy doc §1](./test-automation-policy.md#1-pyramid-targets). The numbers there are **initial targets**, not yet backed by data; they will be revised after the first measurement cycle.

The backend currently has **~170 pytest files** in `backend/tests/`. The strategy below formalizes how new tests are added, marked, and selected.

### 2.1 Decision tree: where does my test go?

When adding a new test, walk this tree in order. The first question whose answer is "yes" tells you where it belongs.

```
Q1: Does this defend against a specific past bug?
  YES ──► §5 Regression test
  NO  ──► continue

Q2: Is this a user-journey through the browser (multi-page, real DOM, real nav)?
  YES ──► §3 / §4  →  frontend/e2e/ with @sanity or @e2e
  NO  ──► continue

Q3: Does this need real DB, real Redis, real Celery, or multiple modules wired together?
  YES ──► backend/tests/integration/  (@pytest.mark.integration)
  NO  ──► continue

Q3.5: Is this a single API route/handler with mocked dependencies (TestClient + a fixture, no real DB)?
  YES ──► backend/tests/  (no marker; e.g. test_auth_api.py)
  NO  ──► continue

Q4: Is this testing pure logic, a single function, or a single class?
  YES ──► backend/tests/ or backend/tests/unit/  (no marker)
  NO  ──► continue

Q5: Is this asserting that a running container responds on `/health` or `/ready`?
  YES ──► §3.1 deploy probe  (deploy-*.sh), not a pytest
  NO  ──► continue

Q6: Is this a new check we run before every merge to defend a "happy path" of the area you touched?
  YES ──► §4 sanity test  (@pytest.mark.sanity_<area> or @sanity in Playwright)
  NO  ──► continue

Q7: Is this a deliberate-failure scenario (kill Redis, expired key, network drop)?
  YES ──► backend/tests/chaos/  (@pytest.mark.chaos)
  NO  ──► ask: does this test actually exist in a contract (§6)?
              NO  ──► write a test case first, then a test
              YES ──► it is probably a regression — re-check Q1
```

**Rule of thumb:** if a test "could be" a regression, a sanity, *and* a smoke test, it is **usually a regression** — name the bug, write it as a regression, and stop. Duplicate coverage of the same contract across all three layers is a smell, not a virtue.

---

## 3. Smoke Tests and Deploy Probes

**Definitions:**

- **Deploy probe** — a 1-second check that a process is up and answering its health endpoint. No DB, no external deps, no LLM. Runs inside `deploy-*.sh` immediately after a container restart. If a probe fails, the deploy is rolled back (see `deploy-backend.sh`).
- **Smoke test** — a 30-second end-to-end check that the system is alive *and* wired correctly: DB, Redis, external services, critical config, and (where present) the LLM provider. Runs after the probe passes, on every deploy and every nightly build. **If a smoke test fails, the deploy is considered failed** even if the probe was green.

The split exists because the two failure modes are different:

| | Deploy probe | Smoke test |
|---|--------------|-----------|
| **Fails when** | Container crashed, port not bound, app panicked at startup | DB unreachable, secret missing, Redis down, LLM provider 5xx |
| **Owner** | `deploy-*.sh` | `backend/tests/smoke/`, `frontend/e2e/smoke/` |
| **Cost of failure** | Roll back the deploy (cheap) | Page on-call (expensive) |
| **Time budget** | 1 s | 30 s |

If you cannot tell which of the two a check is, the rule is: **if it touches the network beyond localhost, it is a smoke test, not a probe.**

### 3.1 Scope

**Deploy probe (in `deploy-*.sh`):**

- Process is up and responding on its health endpoint (`/health`, `/ready`).
- HTTP status is 200; body matches the expected shape.

**Smoke test (in `backend/tests/smoke/`, `frontend/e2e/smoke/`):**

- All of the above, **plus**:
- Database connection works (one read + one write to a no-op table or `SELECT 1`).
- Redis/Qdrant/RabbitMQ/Celery are reachable.
- Critical config (env vars, secrets refs) resolves without raising.
- LLM provider is reachable (or its absence is explicitly tolerated in dev).

### 3.2 Where they live

```
backend/tests/smoke/                     # backend smoke (full end-to-end)
frontend/e2e/smoke/                      # Playwright "is the page up" checks
deploy-*.sh                              # post-deploy curl-based probes (process-only)
```

**Note:** Currently only `deploy-backend.sh` implements a health probe. A probe for `deploy-frontend.sh` (checking the Next.js container on port 3000) is a planned addition.

### 3.3 Implementation rules

1. **Smoke tests stay under 30 s total; probes stay under 1 s.** If a smoke test takes longer, split it or move the slow part to a sanity suite.
2. **No mocked LLM calls in smoke.** The point of smoke is to prove the real path works. A mocked smoke is a unit test with extra steps.
3. **Idempotent.** Runnable 100× in a row; never leaves a row in the DB.
4. **Self-disqualifying — incident path.** A smoke test that passes while the system is broken is **deleted, not amended**. Within 24 h of the deletion:
   - File an incident on the test's owner.
   - Replace the smoke test with a new test that asserts the actual failure mode.
   - Add a one-line root cause to the replacement commit body (`Why: <one sentence>`).

   There is no 90-day grace period: a wrong smoke is a wrong smoke, and the next deploy must not inherit the false confidence. The retirement of the bad test is logged in the incident, **not** in `docs/LEGACY.md` (LEGACY is for retired contracts, §5.1 — not for failed smoke).

### 3.4 Example (smoke test, backend)

```python
# backend/tests/smoke/test_health_and_db.py
import httpx
from sqlalchemy import text

def test_health_returns_ok():
    r = httpx.get("http://localhost:8000/health", timeout=2)
    assert r.status_code == 200
    # adapt to actual /health response shape
    assert r.json() == {"status": "ok"}

async def test_db_is_reachable():
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db_session

    async for session in get_db_session():
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

### 3.5 Example (deploy probe, deploy script)

```bash
# inside deploy-backend.sh — this is a PROBE, not a smoke test
for i in {1..30}; do
  curl -fsS http://localhost:8000/health && exit 0
  sleep 1
done
echo "deploy probe failed" >&2; exit 1
```

The deploy script's `/health` check does **not** test DB or Redis. That is a smoke test (§3.4) and runs in `backend/tests/smoke/` after the deploy completes.

---

## 4. Sanity Tests

**Definition:** Sanity tests are a fast, narrow check that the **most recent change** did not break the obvious thing. They are what a senior engineer runs in their head — formalized.

### 4.1 The difference vs. smoke and probe

| Probe | Smoke | Sanity |
|-------|-------|--------|
| Process-level, run after every container restart | System-level, run after every deploy and every nightly | Change-level, run on every PR |
| "Is the container up?" | "Is anything alive and wired together?" | "Is **my** thing still working?" |
| Catches: crashed container, port not bound, app panic at startup | Catches: infra, network, env, dependency reachability | Catches: logic, contracts, schema, regression of the touched area |

If you are confused which one to use, run through the decision tree in §2.1.

### 4.2 What "obvious" means for Flowmanner

For each domain area, a sanity suite is defined:

| Area | Sanity checks (must all pass for the PR to merge) |
|------|----------------------------------------------------|
| Auth | Signup → login → refresh-token works; `/me` returns 200 with valid JWT. |
| Chat | One non-streaming chat turn returns 200 with content; streaming variant emits ≥1 chunk. |
| Missions | A mission with `model_preference` runs to completion (≥1 token in `output_data`). |
| BYOK | A real (rate-limited) BYOK key resolves a model and returns 200 from `/v1/chat/completions` with a non-empty completion. The CI fixture is a *dedicated, rate-limited* test key — **not** a mock. (Sanity must prove the real provider path; a mocked BYOK is a unit test with extra steps.) **The CI BYOK key must have a hard monthly spend cap and provider-level rate-limit alerting configured, so a flaky retry loop or a runaway CI matrix cannot drain credits or trigger cascading failures.** |
| WebSocket | WS handshake completes and a ping/pong round-trip succeeds. |
| Frontend | Homepage loads (200), `/login` route renders, authed `/dashboard` renders for a fixture user. |

### 4.3 Sanity selection rules

- **Auto-selected per PR.** CI inspects the diff and selects the relevant sanity suites. Touching `app/chat/**` ⇒ run `pytest -m sanity_chat`. Touching `frontend/src/app/dashboard/**` ⇒ run Playwright with `--grep @sanity_dashboard`.
  - **Implementation (tooling to build):** a path-based CI matrix in `.github/workflows/sanity-matrix.yml`, or a `scripts/select-sanity.py` that maps `git diff --name-only` to marker expressions. Until either exists, the path-to-marker mapping is maintained manually in `docs/test-automation/sanity-matrix.md` (also to be created).
- **Tagged, not free-form.** Use pytest markers (`@pytest.mark.sanity_chat`) and Playwright tags (`@sanity`).
- **Under 60 s total.** If a sanity suite exceeds 60 s, it has grown into a regression test and must be split.

### 4.4 Implementation

```python
# backend/tests/sanity/test_sanity_auth.py
import pytest

pytestmark = pytest.mark.sanity_auth

def test_signup_login_me_flow(client):
    # ...full happy path, no mocking
    ...
```

```typescript
// frontend/e2e/sanity/sanity_dashboard.spec.ts
import { test, expect } from "@playwright/test";

test("authenticated dashboard renders @sanity", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /welcome/i })).toBeVisible();
});
```

---

## 5. Regression Tests

**Definition:** A regression test exists to **prove a specific bug never reappears**. It is born from a real failure, not from a hypothetical one.

### 5.1 Lifecycle

```
Bug reported
   │
   ▼
Reproduce in a test (RED) ──► commit & link in PR
   │
   ▼
Fix the code (GREEN)
   │
   ▼
Test becomes part of the regression suite forever
   │
   ▼
If the test is later deemed "not load-bearing"
   │
   ├──► Path A: Contract is still valid but enforcement moved elsewhere
   │       (e.g. enforced at the gateway). Move the case to docs/LEGACY.md.
   │
   └──► Path B: Contract is no longer valid (feature removed)
           Mark the test with BOTH:
           - `@pytest.mark.removed_in_<version>` — the tombstone marker. Documents the
             removal; greppable for cleanup at the next major version.
           - `@pytest.mark.skip(reason="removed in <version>; see <ticket>")` — the
             actual skip. **Required**, because a removed test is by definition broken,
             and the per-PR CI sweep (`pytest -m "not integration"`, §10.2) will run it
             and fail the build if it is not skipped.
           Keep it in the file for one release as a tombstone, then delete the test and
           the `removed_in_*` marker in the next cleanup PR.
```

**LEGACY** is a tracked file (`docs/LEGACY.md`) that lists every test case we have explicitly retired from active enforcement. The case is not deleted from history — it is **intentionally retired**, and the file records:

- The case ID and original ticket.
- Why it was retired (e.g. "rate-limiting moved to nginx, app-layer check is redundant").
- Who approved the retirement (CODEOWNER sign-off).
- The date.

A LEGACY case is **never silently re-enabled**. Bringing it back requires a PR that:

1. Links a new bug or audit finding.
2. Re-implements the test (or un-quarantines it).
3. Removes the entry from `docs/LEGACY.md` as part of the same PR.

If you cannot tell which path a retiring test belongs to, **default to Path A (LEGACY)** — the cost of a tracked retirement is low, and the audit value is high.

### 5.2 Naming & location

- File: `test_regression_<ticket>_<short_slug>.py` (e.g., `test_regression_4d8e04d_sandbox_uuid_vs_jwt.py`).
- Each regression test contains a docstring with: bug ticket, root cause, fix commit, and link to the post-mortem.
- Regression tests are **never** moved to a unit folder, even if they look small. Their identity is "this was once broken."

### 5.3 Template

```python
"""Regression for #142 — UUID-vs-JWT confusion in sandbox_preview.

Root cause: get_refresh_token() was not consulted when the cookie
value was a UUID rather than a signed JWT. Auth chain returned 401
for every sandbox preview request.

Fix: 4d8e04d — _is_jwt() heuristic + DB lookup.
"""
import pytest

pytestmark = pytest.mark.regression

def test_sandbox_preview_accepts_uuid_cookie(client, db_session):
    # setup: create refresh token row
    # act: call /sandbox/preview with cookie = token.id (not the JWT)
    # assert: 200, not 401
    ...
```

### 5.4 Coverage of the "known bug" universe

A regression test is added for any of:

- Any bug fixed in the last 90 days (SLA — see §13).
- Any bug with severity ≥ SEV-2, regardless of age.
- Any bug that escaped to production in the last 12 months.

The active set of regression tests is enumerable by `pytest --collect-only -m regression` (backend) and `find frontend/e2e -name '*regression*'` (frontend). **No separate inventory file is maintained** — the test's docstring (§5.2) is the source of truth, and the active set is regenerable on demand.

---

## 6. Test Cases

**Definition:** A test case is the **specification** of behavior — what we claim the system does. The pytest test is one *implementation* of that case. Cases are tracked even when there is no automated test.

### 6.1 Case record format

Each case lives in the code as a docstring on the test, and (for high-value flows) in a `test_cases/` markdown table:

| Field | Meaning |
|-------|---------|
| `ID` | Stable identifier, e.g., `TC-CHAT-007` |
| `Title` | One-line description |
| `Preconditions` | State required before the test runs |
| `Steps` | Numbered, deterministic |
| `Expected` | What success looks like, in measurable terms |
| `Priority` | P0 (must never break) → P3 (nice to have) |
| `Owner` | The team or agent responsible |
| `Last run` | Timestamp + green/red |
| `Linked bugs` | Tickets this case defends against |

### 6.2 Where cases live

```
docs/test-cases/
├── chat.md
├── auth.md
├── missions.md
└── sandbox.md
```

Markdown over a test-management tool — the cases live next to the docs and survive tool changes.

### 6.3 Example

```markdown
### TC-CHAT-007 — Streaming chat emits at least one chunk within 5 s

- **Priority:** P0
- **Preconditions:** Authed user; BYOK key configured; LLM reachable.
- **Steps:**
  1. POST `/api/chat/stream` with a simple prompt.
  2. Open the SSE stream.
- **Expected:** First chunk arrives within 5 s; final `done` event present; total tokens > 0 in `output_data`.
- **Owner:** Backend / chat
- **Linked bugs:** #88 (silent mocker), #142 (stream stalls)
```

### 6.4 P0 invariants

A case is P0 if violating it would:

- Leak data, lose data, or corrupt a tenant boundary.
- Make the product unusable for the primary happy path.
- Cause a billing or quota misattribution.

P0 cases **must** be covered by automated tests. Manual-only P0 is a debt item tracked in §13.

---

## 7. Checklists

**Definition:** Checklists are **gates** — finite, version-controlled lists of "is this true?" items that must all be ✅ before an action is allowed.

### 7.1 Pre-merge checklist (per PR)

The PR template embeds this; the CI bot checks the items it can.

- [ ] Tests added for every new branch of logic.
- [ ] No test deleted without a justification comment (`# deleted because …`).
- [ ] All tests pass locally (`pytest -m "not integration"` for unit, plus relevant sanity).
- [ ] `lsp_diagnostics` clean on changed files.
- [ ] No new `as any`, `@ts-ignore`, `as unknown as T`, or empty `except:`.
- [ ] No new env vars without a default in `.env.example` and a `settings` entry.
- [ ] Migration added if a schema changed; `alembic upgrade head` runs clean.
- [ ] Frontend: no console.error in Playwright traces for the touched page.
- [ ] All `TODO(owner)` tags have a GitHub handle, not "someone".
- [ ] PR description links the issue, the test plan, and a rollback note.

### 7.2 Pre-deploy checklist

- [ ] All sanity suites green on the staging artifact.
- [ ] Smoke pass on the running container.
- [ ] DB migrations applied and idempotent.
- [ ] Rollback image present and tagged.
- [ ] Ntfy channel green (no SEV-1 alert in the last 15 min).
- [ ] Deploy command timeout set to 300 s; not blindly retried.

### 7.3 Post-deploy checklist (within 5 min of deploy finishing)

- [ ] `/health` and `/ready` 200.
- [ ] Synthetic mission with `model_preference` returns > 0 tokens.
- [ ] One real-user happy path (login → dashboard) observed via logs.
- [ ] Error rate (5xx) on `/api/*` < 0.5 % over the first 5 min.
- [ ] No new exceptions in the last 5 min that match a SEV-1 pattern.

### 7.4 Checklists as code

Where possible, the checklist is enforced, not just ticked:

```yaml
# .github/workflows/pr-check.yml (excerpt)
- uses: actions/checkout@v4
  with:
    fetch-depth: 0  # full history; required for the git diff below to resolve

- name: Assert no test file was deleted without justification
  run: |
    set -euo pipefail
    # Use the PR's base SHA directly, not `origin/${{ github.base_ref }}`:
    # with fetch-depth: 1 (the default) the base branch is not guaranteed to
    # be a resolvable ref, and `git diff origin/<base>...HEAD` will fail with
    # `fatal: ambiguous argument`.
    DELETED=$(git diff --diff-filter=D --name-only ${{ github.event.pull_request.base.sha }}...HEAD \
      | grep -E '^(backend|frontend)/.*\.(py|ts|tsx)$' || true)
    if [ -n "$DELETED" ]; then
      echo "::error::Test file(s) deleted without justification:"
      echo "$DELETED"
      echo "Either add a justification to the commit body or retire the case to docs/LEGACY.md (§5.1)."
      exit 1
    fi
```

> **What this catches:** file deletions under `backend/tests/**` and `frontend/**/*.{ts,tsx}`. It is the *minimum* check.
>
> **What this does not catch:** deletions of test functions inside an existing file, or deletions of test fixtures. Those rely on the PR reviewer's eye and on `pytest --collect-only` diffs in the PR summary, which CI should also surface (tooling to build).

---

## 8. Exploratory Testing

**Definition:** Exploratory testing is **unscripted investigation** by a human or an agent with time-boxed charters. It exists to find what the script did not imagine.

### 8.1 When it runs

- **After every release to staging** (1 hour, structured charter).
- **Before any feature flag is set to 100 %**.
- **After a production incident** to find the *next* incident, not just close this one.
- **Monthly** by a rotating owner, with a charter from §8.2.

### 8.2 Charter template

```
Charter: <one sentence>
Time-box: 60 min
Focus area: <module, user role, environment>
Notes / Setup: <seeded data, special config>
Risk model: <what we expect to break>
```

### 8.3 Flowmanner charters (rolling)

- **CHX-01** As a free user, do everything possible without paying; find a path to a paid feature.
- **CHX-02** Send a mission with `model_preference` to each of: missing key, revoked key, expired key, model-id-that-does-not-exist.
- **CHX-03** Interact with the chat stream and kill the tab at every possible moment; check for orphaned state in DB.
- **CHX-04** With a sandbox session, deliberately trigger 401, 403, 404, 500 in turn; verify the UI handles each.
- **CHX-05** Auth: refresh, expire, reuse-after-expiry, concurrent refresh from two devices.

### 8.4 Session output

Every session produces a single file: `docs/exploratory/<date>-<owner>-<charter>.md`, with:

- Bugs filed (links).
- Risk areas flagged (no bug yet, but smell).
- Updates to §6 test cases (if a behavior was previously implicit).
- Updates to §3 smoke / §4 sanity (if a now-obvious check was missing).

---

## 9. Debug Logs

**Definition:** The mechanism by which a failed run becomes an actionable answer in ≤ 5 minutes.

### 9.1 The five-minute rule

If a developer or an agent cannot answer "why did this fail?" within 5 minutes of looking at the CI artifact, the logging is broken — not the test.

### 9.2 What every test run captures

For **every** run (pass or fail):

- `run_id` (UUID, unique per run).
- `commit_sha` and `branch`.
- Triggering event (`push`, `pull_request`, `schedule`, `manual`).
- Exact command and resolved env (masked).
- Wall-clock per test and per phase (collection, setup, run, teardown).

For **failing** runs only (in addition to the above):

- The diff hunk under test — the lines from the PR that exercise the failing test.
- Full pytest output with `-vvv` and `--tb=long`.
- The last 200 lines of `docker logs` for the backend container, if the test is integration+.
- Captured stdout/stderr per test (pytest `caplog` + `capsys`).
- Playwright trace + video for E2E failures.
- A **reproducer script** — a single command that recreates the failure locally, stored in the run artifact.

### 9.3 Local reproduction

```bash
# from the run artifact:
make reproduce RUN_ID=2026-06-18-abc123
```

`make reproduce` fetches the artifact, restores the same env (from a pinned `.env.test.<run_id>`), and re-runs only the failed tests with the same markers.

### 9.4 Backend logging standard

```python
# logging configured in app/main_fastapi.py; extract to app/core/logging.py as the suite grows
logger.info("mission.start", extra={
    "run_id": run_id,
    "mission_id": mission.id,
    "user_id": user.id,
    "model_id": model_id,
})
```

Rules:

- One log line per state transition (`start`, `route`, `execute`, `complete`, `error`).
- Every log line has `run_id` and a domain id (`mission_id`, `chat_id`, …).
- Never log raw prompts or completions in prod — use a `truncate=True` flag.
- Never log secrets, even truncated. Use `***` for any value matching a key regex.

### 9.5 Frontend logging standard

- `console.error` only for unexpected errors (not for "user typed bad email").
- Errors bubble to a single `reportError(err, ctx)` that POSTs to `/api/telemetry/errors` with `run_id` if present.
- Playwright tests assert on the absence of `console.error` for the touched page.

### 9.6 Runbook: a test failed, now what?

1. Open the CI artifact. Read the **reproducer command**.
2. Run it locally. If it fails, read the captured logs filtered by `run_id`.
3. If it passes locally, the test is **flaky** → §10.4.
4. If the test is correct, fix the code. Do not "fix" the test to pass.
5. Add a one-line root cause to the commit body: `Why: <one sentence>`.

---

## 10. Guardrails

**Definition:** Automated, non-bypassable checks that stop bad tests, bad merges, and bad deploys before they consume a human's time.

### 10.1 Pre-commit guardrails

| Guardrail | Blocks | Tool |
|-----------|--------|------|
| Type errors | Bad types from landing | `mypy` (backend), `tsc --noEmit` (frontend) |
| Lint | Style + a class of bugs | `ruff` (backend), `eslint` (frontend) |
| Secrets in diff | Leaked credentials | `gitleaks` |
| Forbidden suppressions | `as any`, `@ts-ignore` | Custom grep rule in `pre-commit` |
| Test deleted | Silent loss of coverage | CI check (see §7.4) |
| Migration w/o downgrade | One-way schema change | `alembic` downgrade dry-run in CI |

### 10.2 PR guardrails (CI)

- All pre-commit checks pass.
- Unit + sanity tests pass. Two valid invocations:
  - **Single command:** `pytest -m "sanity or not integration"`
  - **Two commands (preferred for clarity):** `pytest -m "not integration"` followed by `pytest -m sanity`

  Area-specific markers (`sanity_auth`, `sanity_chat`, …) must be **listed explicitly** — pytest marker expressions do not support globs. Example: `pytest -m "sanity_auth or sanity_chat or not integration"`.

#### 10.2.1 The marker-sweep trap (and how we avoid it)

`pytest -m "not integration"` is **not** a synonym for "run the unit + sanity suite." In pytest, `not integration` evaluates to True for **any test that does not have the `integration` marker** — which includes:

- **Smoke tests** (no marker, by design — see §3.1 and §14). They would run on per-PR CI and immediately fail because the PR runner has no real DB, Redis, or LLM.
- **Chaos tests** (carry `@pytest.mark.chaos`, not `integration`). They would run on per-PR CI and either fail or, worse, damage the CI container.

This is a real failure mode, not a hypothetical one: a naive `pytest -m "not integration"` on the current suite would sweep every smoke and chaos test into the PR pipeline.

**The fix — directory-based ignore via `pyproject.toml` `addopts`:** smoke and chaos are never discovered by default; they are run only when explicitly requested by path. The integration marker continues to handle integration exclusion, since integration tests are a *subset* of the unit-tree we DO want to opt into nightly/staging.

```toml
# pyproject.toml [tool.pytest.ini_options]
addopts = [
    "--ignore=backend/tests/smoke",
    "--ignore=backend/tests/chaos",
]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "smoke: smoke tests (excluded from default runs; run with `pytest backend/tests/smoke/`)",
    "chaos: chaos tests (excluded from default runs; run with `pytest backend/tests/chaos/`)",
    "sanity: sanity tests (per-area markers: sanity_auth, sanity_chat, …)",
    "regression: regression tests; defend against a specific past bug (§5)",
    "flaky: quarantined flaky test; does not block merge (§10.4)",
]
```

After this is in place, the per-PR CI command is simply:

```bash
pytest -m "not integration"
```

To run smoke: `pytest backend/tests/smoke/`. To run chaos: `pytest backend/tests/chaos/`. To run the full nightly: `pytest` (no marker filter).

> **If you cannot add `addopts` to `pyproject.toml` for any reason**, the equivalent CLI form is:
>
> ```bash
> pytest -m "not integration" --ignore=backend/tests/smoke --ignore=backend/tests/chaos
> ```
>
> Do **not** rely on marker-only exclusion (`-m "not integration and not smoke and not chaos"`) — it fails the moment someone adds a smoke test without the marker.
- Coverage on changed lines meets the floor in [policy doc §3](./test-automation-policy.md#3-coverage-floors-changed-lines). Backend general: 80 %. Frontend general: 70 %. Auth, billing, missions, sandbox-preview: 90 %.
- No new test marked `@pytest.mark.skip` or `xfail` without a linked ticket and an expiration date.
- No test takes > 30 s without being marked `slow`.
- A new test file must have at least one assertion per function.

> **Wall-clock and coverage numbers are in the policy doc, not here.** When those numbers change, only the policy doc changes.

### 10.3 Merge-time guardrails

- PR is up-to-date with `main` (or rebase was performed).
- All required reviews (`CODEOWNERS`) approved.
- No unresolved `TODO` comments introduced (existing TODOs grandfathered).
- PR body contains a rollback plan (one sentence is enough).

### 10.4 Flake quarantine

The rule, in one sentence: **3 flakes in any rolling 14-day window → quarantine; if it flakes again after leaving quarantine, it is deleted permanently** (full numeric rule in [policy doc §4](./test-automation-policy.md#4-flake-rules)).

In practice:

- **First quarantine.** Test fails 3× in 14 days → marked `@pytest.mark.flaky` and moved to `tests/_quarantine/`. Still runs, but failure no longer blocks merge. A GitHub issue is auto-assigned to the original author with the SLA from policy doc §4.
- **Fix within SLA.** Author fixes the test, removes the `flaky` marker, moves the test back to its proper suite.
- **One strike you're out.** If the test leaves quarantine and flakes **any** time in the next 14 days, it is **deleted immediately** and its contract is moved to `docs/LEGACY.md` (§5.1). Quarantine is a delay, not a pardon.

> A test that re-flakes once after leaving quarantine is, by definition, not load-bearing. Three is generous; one is the actual standard.

### 10.5 Bypass policy

`--no-verify`, `gh pr merge --admin`, force-push to `main`: all are **forbidden in policy and tooling**. If something must ship urgently, the path is:

1. Open a PR marked `URGENT`.
2. Two reviewers (one must be a CODEOWNER).
3. A `git notes add` entry recording the override reason.
4. The override is reviewed in the next weekly retro.

---

## 11. Assertions

**Definition:** The smallest unit of "this is true" in a test. Bad assertions turn green pipelines into false confidence.

### 11.1 The three laws

1. **An assertion asserts behavior, not implementation.** Assert that `/me` returns 200 with a body matching the user schema, not that it called `db.query(User).first()`.
2. **An assertion is specific.** `assert r.status_code == 200` is fine; `assert r.ok` is not.
3. **An assertion fails loud.** Never swallow an assertion in a `try/except`; never coerce a failure into a warning.

### 11.2 Style

**Backend (pytest):**

```python
# Good
assert response.status_code == 200
assert response.json()["tokens"] > 0
assert "model_id" in response.json()

# Bad
assert response  # too vague
assert response.status_code in (200, 201)  # lazy OR
assert response.json().get("tokens", 0) >= 0  # always true if missing
```

**Frontend (Playwright + RTL):**

```typescript
// Good
await expect(page.getByRole("button", { name: "Submit" })).toBeEnabled();
await expect(page).toHaveURL(/\/dashboard/);

// Bad
expect(page).toBeDefined();                       // not a real Playwright assertion
const headerExists = await page.locator("h1").count() > 0;  // boolean, no failure surface
expect(headerExists).toBe(true);                  // passes even if selector matches the wrong h1
```

### 11.3 Assertion library conventions

- Backend: stock `pytest` asserts. No `assertpy`, no `hamcrest` — keep the dependency surface small.
- Frontend: `expect` from `@playwright/test` for E2E; `expect` from `@testing-library/jest-dom` for component tests.
- Snapshot tests are **discouraged**. They are assertions about pixels or strings, not behavior. If used, snapshots are reviewed on every change and pinned to a specific commit.

### 11.4 Custom matchers

When the same assertion shape repeats, extract a matcher:

```python
# backend/tests/_helpers/matchers.py
def assert_mission_complete(mission):
    assert mission.status == "completed", f"mission {mission.id} is {mission.status}"
    assert mission.output_data, f"mission {mission.id} has empty output_data"
    assert mission.tokens_used > 0, f"mission {mission.id} used 0 tokens"
```

Use it everywhere. If two tests assert the same thing in two ways, that is a bug — pick one.

### 11.5 Anti-patterns (auto-detected by linter)

- `assert True`
- `assert x is not None` (use a positive form: `assert isinstance(x, SomeType)`).
- `assert ... or ...` (split into two assertions with clear messages).
- `assert_called_with(ANY, ANY)` (you asserted nothing).
- Assertion inside a `try: ... except: pass`.

---

## 12. Environment / Configuration Matrix

**Definition:** What code runs where, with which config, against which dependencies. This matrix is the source of truth for "why did it work in CI and fail in prod?" answers.

### 12.1 Environments

| Name | Purpose | URL (LAN) | Data | LLM | Who can deploy |
|------|---------|-----------|------|-----|-----------------|
| **local** | Developer / agent workstation | `localhost:3000`, `localhost:8000` | seeded dev DB | local llama.cpp OR mock | the developer |
| **CI** | GitHub Actions runners | ephemeral | ephemeral Postgres/Redis containers | mocked (`respx`, `pytest-httpx`) | CI only |
| **staging** | Pre-prod replica of prod | `10.99.0.3:8000` (homelab) | anonymized prod snapshot, refreshed weekly | BYOK keys (real, rate-limited) | ops/dev |
| **prod** | Live users | `https://flowmanner.com` (via VPS) | real | real | ops/dev with PR + 1 reviewer |

### 12.2 Matrix: what runs where

> **Default test discovery excludes `backend/tests/smoke/` and `backend/tests/chaos/`** (see §10.2.1 for the `pyproject.toml` `addopts` rule). The cells below assume that exclusion is in place; a `path` column on the left indicates when a suite is invoked by an explicit path rather than by the default sweep.

| Suite | How invoked | local | CI (per PR) | CI (nightly) | staging | prod |
|-------|-------------|-------|-------------|--------------|---------|------|
| Unit (pytest) | default sweep | ✅ | ✅ | ✅ | ✅ | — |
| Sanity (auto-tagged) | default sweep, marker filter | ✅ | ✅ | ✅ | ✅ | — |
| Integration | default sweep, `pytest -m integration` (excluded from per-PR with `-m "not integration"`) | ✅ (optional) | ❌ (run on merge to main) | ✅ | ✅ | — |
| Regression | default sweep | ✅ | ✅ | ✅ | ✅ | — |
| **Smoke** | **explicit path: `pytest backend/tests/smoke/`** | ✅ | ❌ | ✅ | ✅ | — |
| **Chaos** | **explicit path: `pytest backend/tests/chaos/`** | ❌ | ❌ | ❌ | ✅ (weekly) | ❌ |
| E2E (Playwright) | `playwright test` | ✅ (smoke only) | ❌ (run on merge to main) | ✅ | ✅ | — |
| Load / perf | dedicated harness | ❌ | ❌ | ❌ | ✅ (monthly) | ❌ |
| Synthetic prod probes | `deploy-*.sh` curl | ❌ | ❌ | ❌ | ❌ | ✅ (continuous) |

### 12.3 Configuration matrix

| Var | local | CI | staging | prod |
|-----|-------|----|---------|------|
| `ENV` | `dev` | `ci` | `staging` | `prod` |
| `DB_URL` | `postgresql://localhost:5432/flowmanner_dev` (via `docker compose up postgres`); **SQLite is unsupported for tests** — only the CLI seeder (`make seed`) may use it. | ephemeral postgres container | homelab postgres | homelab postgres |
| `REDIS_URL` | `redis://localhost` | container | homelab redis | homelab redis |
| `LLM_PROVIDER` | `mock` or `llama.cpp` | `mock` | `byok` | `byok` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `INFO` | `INFO` |
| `SENTRY_DSN` | — | — | set | set |
| `NTFY_CHANNEL` | — | — | `flowmanner-staging` | `flowmanner-prod` |
| `FEATURE_FLAGS` | all on | all on | all on | controlled by ops |

### 12.4 Service dependencies matrix

| Service | local | CI | staging | prod |
|---------|-------|----|---------|------|
| PostgreSQL | docker (`docker compose up postgres`); **SQLite is unsupported for tests** | container | homelab | homelab |
| Redis | docker | container | homelab | homelab |
| Qdrant | docker | container | homelab | homelab |
| RabbitMQ | docker | container | homelab | homelab |
| Celery worker | local process or docker | container | homelab | homelab |
| llama.cpp | optional, on | mocked | off | off |
| Jaeger | optional | optional | on | on |

### 12.5 Secrets & config

- `.env*` files are **never** committed. `.env.example` is the contract.
- CI reads secrets from GitHub Actions secrets; staging/prod from the homelab Vault.
- A missing env var that is required must crash at startup, not at first request. The startup crash is itself a smoke test.

### 12.6 Promoting between environments

```
local ──PR──► CI ──merge──► staging ──manual approve──► prod
```

- `local → CI`: PR opened, all checks pass.
- `CI → staging`: merge to `main` triggers the staging deploy (`deploy-backend.sh`).
- `staging → prod`: explicit `git tag vX.Y.Z` plus an ops PR. No cron-driven prod deploys.

---

## 13. SLAs, Ownership, and Continuous Improvement

### 13.1 SLAs and operational targets

All numeric SLAs (time-to-add, time-to-quarantine, coverage floors, wall-clock budgets, "suite is healthy" criteria) live in the [policy doc](./test-automation-policy.md). This section is reserved for **policy-level** SLAs that govern how the policy doc is updated:

| Item | Policy-level SLA |
|------|------------------|
| Update the policy doc after a real measurement cycle | within 14 days of gathering the data |
| Review the policy doc | monthly |
| Review the strategy doc | quarterly |
| Update `docs/LEGACY.md` after a retirement | within the retirement PR |
| Add a regression test for a new bug fix | same PR (operational rule in §5) |

### 13.2 Ownership

- **Backend**: `backend/tests/**` is owned by whoever owns the module under test. Use `CODEOWNERS`.
- **Frontend**: `frontend/e2e/**` and `frontend/src/**/*.test.tsx` are owned by the frontend lead.
- **Infra / smoke / chaos / deploy probes**: ops/dev.
- **This document**: a rotating owner, reviewed quarterly.
- **Policy doc**: rotating, reviewed monthly.
- **`docs/LEGACY.md`**: a CODEOWNER for the relevant module signs off on retirements.

#### 13.2.1 When the boundary is unclear

Some tests do not fit cleanly into one module's ownership. Examples:

- A regression test in `app/chat/llm_executor.py` that depends on a `Mission` model owned by a different team.
- A Playwright E2E that exercises auth (backend) plus the dashboard UI (frontend).
- A chaos test that kills Redis but asserts on the Celery worker.

The rule for these cases is **whoever's bug it is, owns the test**. In practice:

1. If the test fails in CI, the on-call for the **first failing assertion's domain** owns the fix.
2. If ownership cannot be determined from the assertion, the **lead of the touched module in the PR** owns it (they introduced the boundary case).
3. If both teams must change code, **co-own**: the test file's `CODEOWNERS` lists both, and either can review the test.
4. If after 24 hours nobody has claimed it, the **test falls to the platform lead** for triage. The platform lead's job is to assign, not to fix.

The "co-own" arrangement is the default for cross-module contracts (auth + UI, mission + chat, sandbox + mission). It is not a fallback for unclear ownership — it is the correct answer when the **test itself** is about the boundary.

### 13.3 Review cadence

- **Weekly** (5 min): flake dashboard, top 3 failing tests, quarantine list. *Owner: platform on-call.*
- **Monthly** (30 min): policy doc review with the data from the last 4 weeks. *Owner: policy doc rotating owner.*
- **Quarterly** (2 h): full strategy doc review; this document. *Owner: strategy doc rotating owner.*
- **Per-release**: walk `docs/LEGACY.md` and confirm each entry is still retired.

### 13.4 "Suite is healthy" — pointer only

The current definition of "the suite is healthy" lives in [policy doc §6](./test-automation-policy.md#6-suite-is-healthy-criteria) and changes with measurement. This document intentionally does not duplicate the criteria; the *consequence* of regressing against them is the only policy that lives here:

> If the criteria in policy doc §6 regress for two consecutive measurement weeks, the **strategy doc is the first place we look**, not the test code. A green badge that does not meet the criteria is a process bug, not a test bug.

---

## 14. Quick-Reference: Where to Put a New Test

> **Important (see §10.2.1):** smoke and chaos are excluded from default test discovery via `pyproject.toml` `addopts`. Run them with `pytest backend/tests/smoke/` or `pytest backend/tests/chaos/`. The marker column below is for documentation; smoke tests carry no marker because they are excluded by path, not by marker.

| I want to test… | Put it in | Marker | Example file |
|------------------|-----------|--------|--------------|
| A pure function | `backend/tests/unit/` | (none) | `test_pure_helpers.py` |
| A model field validator | `backend/tests/unit/` | (none) | `test_user_validation.py` |
| A single API route, mocked DB | `backend/tests/` | (none) | `test_auth_api.py` |
| A route that hits real DB | `backend/tests/integration/` | `@pytest.mark.integration` | `test_chat_e2e_db.py` |
| A bug we already fixed | `backend/tests/regression/` | `@pytest.mark.regression` | `test_regression_4d8e04d_*.py` |
| Is the system alive end-to-end | `backend/tests/smoke/` | (none — excluded by path) | `test_health.py` |
| Did my PR break the obvious | `backend/tests/sanity/` | `@pytest.mark.sanity_<area>` | `test_sanity_auth.py` |
| A service under failure | `backend/tests/chaos/` | `@pytest.mark.chaos` (excluded by path) | `test_celery_redis_down.py` |
| A user journey in the browser | `frontend/e2e/` | `@sanity` or `@e2e` | `chat-journey.spec.ts` |
| A React component in isolation | `frontend/src/**/*.test.tsx` | (none) | `Button.test.tsx` |

---

## 15. Appendix A — Templates

### 15.1 Regression test template

```python
"""Regression for <TICKET> — <one-line summary>.

Root cause: <what was wrong>.
Fix: <commit SHA> — <one-line fix description>.
"""
import pytest

pytestmark = pytest.mark.regression

def test_<short_slug>(client, db_session):
    # arrange
    ...
    # act
    response = client.post(...)
    # assert
    assert response.status_code == 200
    ...
```

### 15.2 Sanity test template

```python
import pytest

pytestmark = pytest.mark.sanity_<area>

def test_<area>_<happy_path>_<expected_outcome>(client, seed_user):
    response = client.post("/api/<route>", json={...})
    assert response.status_code == 200
    assert response.json()["ok"] is True
```

### 15.3 Exploratory session template

```markdown
# Exploratory Session — <date> — <owner>

**Charter:** <one sentence>
**Time-box:** <X> min
**Focus area:** <module / role / env>
**Risk model:** <what we expect to break>

## Findings

### Bugs filed
- #<n> — <title>

### Smells (no bug yet)
- <observation>

## Suggested follow-ups
- [ ] <test case update>
- [ ] <sanity or smoke addition>
```

### 15.4 Pre-merge checklist (PR template)

```markdown
## What

<!-- one paragraph -->

## Why

<!-- link to issue / RFC / chat -->

## Test plan

- [ ] Unit tests added
- [ ] Sanity tests added (which marker)
- [ ] Regression test added (if bug fix)
- [ ] Manual verification (steps)

## Rollback

<!-- one sentence -->

## Risk

<!-- low / medium / high + why -->
```

---

## 16. Appendix B — Glossary

| Term | Meaning |
|------|---------|
| **Smoke test** | System-level aliveness check that touches DB, Redis, and external deps. See §3. |
| **Deploy probe** | A 1-second, no-DB, no-external-deps check that a container answers `/health` or `/ready`. Lives in `deploy-*.sh`. See §3. |
| **Sanity** | Change-level "did I break the obvious" check, auto-tagged per PR. See §4. |
| **Regression** | A test that defends against a specific historical bug. See §5. |
| **Test case** | A specification of behavior in `docs/test-cases/*.md`. The *contract*; the pytest test is its *implementation*. See §6. |
| **LEGACY** | A test case moved to `docs/LEGACY.md` because the contract is no longer load-bearing. The case is retired, not deleted. See §5.1. |
| **Quarantine** | A flaky test that runs but does not block merges, with a 7-day SLA. See policy doc §4. |
| **Charter** | A one-sentence, time-boxed scope for exploratory testing. See §8.2. |
| **Reproducer** | A single command that recreates a failure locally, attached to every CI run. See §9.3. |
| **Run ID** | A UUID attached to every test run and every log line within it. See §9.2. |
| **Environment matrix** | The table of "what code runs where, with which config." See §12. |
| **Policy doc** | [test-automation-policy.md](./test-automation-policy.md) — where operational numbers live. This document is the contract; the policy doc is the implementation. |
| **P0 case** | A behavior whose violation is a SEV-1 incident. See §6.4. |

---

*End of document. PRs that change the strategy itself should update §1 and add a note in the changelog section below.*

## Changelog

- **2026-06-18** — v1. Drafted. Strategy covers smoke / sanity / regression / cases / checklists / exploratory / logs / guardrails / assertions / matrix for the current Next.js + FastAPI stack.
- **2026-06-18** — v1.1. Addressed review feedback:
  - Extracted all numeric targets to a companion [test-automation-policy.md](./test-automation-policy.md) so the strategy doc stays stable.
  - Added **§1.1 "How to read this document"** distinguishing policy / current target / enforced rule.
  - Added **§1.2 Terminology** (test vs. test case, probe, LEGACY) to standardize vocabulary.
  - Added **§2.1 Decision tree** for "where does my new test go?"
  - Split **§3 Smoke Tests** into deploy probe (process-only, in `deploy-*.sh`) vs. smoke test (full DB+deps+LLM).
  - Formalized **§5.1 LEGACY** as a tracked retirement path with re-enable policy.
  - Added **§13.2.1 "When the boundary is unclear"** for cross-module test ownership.
  - Replaced "coverage theater" with "coverage numbers"; added operational meaning to "enforced, not aspirational."
- **2026-06-18** — v1.2. Second-pass review fixes (Kimi review):

  **RED (must-fix) — all addressed:**
  - §3.3 — removed bogus "90-day clock (§5.1)" cross-reference. Replaced with a concrete 24-hour incident path for a wrong smoke test. The retirement of a failed smoke is logged in the incident, not in `docs/LEGACY.md` (LEGACY is for retired *contracts*, not failed tests).
  - §7.4 — fixed the broken `git diff` deletion check. New version uses `git diff --diff-filter=D` and exits with a list of the offending files.
  - §10.2 — fixed invalid pytest marker syntax. The previous `pytest -m "sanity_*" or not integration"` is not valid (mixing glob + `or` + unclosed quote). Now documents the two valid forms (single command, or two commands) and warns that area-specific markers must be listed explicitly.
  - §11.5 — fixed anti-pattern. `assert x is SomeType()` asserts identity with a class object, not type. Now correctly shows `assert isinstance(x, SomeType)`.
  - §9.2 — fixed contradiction. The "diff hunk under test" was listed under "for every run" with a parenthetical "(for the failing test only)". Moved it cleanly under "failing runs only".

  **YELLOW (important, follow-up) — all addressed:**
  - §4.2 — BYOK sanity now uses a real, rate-limited test key, not a mock. Sanity must prove the real provider path.
  - §4.3 — added explicit tooling-to-build pointer for the diff-based sanity selection: `scripts/select-sanity.py` or a path-based CI matrix, with a fallback `docs/test-automation/sanity-matrix.md` for the manual mapping until either exists.
  - §5.4 — removed the reference to `docs/REGRESSION-INVENTORY.md (to be created)`. The active set is regenerable on demand via `pytest --collect-only -m regression`; no separate inventory file.
  - §12.3 and §12.4 — Postgres is now the explicit local default via `docker compose up postgres`. SQLite is **unsupported for tests**; it is allowed only for the CLI seeder (`make seed`). Prevents dialect-only bugs from showing up only in CI/staging.
  - §10.4 — simplified the flake count to one rule: 3 flakes in 14 days → quarantine; if it flakes again after leaving quarantine, delete immediately. "One strike you're out."

  **Nitpicks — all addressed:**
  - Added **TL;DR for engineers** at the top of the document, summarizing the five rules engineers hit most.
  - §2.1 — added Q3.5 for "single API route/handler with mocked dependencies" so the "single route, mocked DB" case in §14 has a clean branch.
  - §3.4 — added the missing `from sqlalchemy import text` import in the smoke-test example.
  - §11.2 — replaced `await expect(page).toBeTruthy()` (not a real Playwright assertion) with a more realistic anti-example that shows the failure mode of a boolean test.
  - §13.1 — removed the `REGRESSION-INVENTORY.md (when created)` reference, replacing it with the regression test SLA that the strategy actually enforces.
  - §13.4 — trimmed the framing so it no longer duplicates the contract/implementation distinction from §1.1.

- **2026-06-18** — v1.3. Third-pass review fixes (Qwen review):

  **🔴 Critical (would break CI on day one) — fixed:**
  - **§10.2 — the marker-sweep bug.** `pytest -m "not integration"` evaluates True for *any* test without the `integration` marker. That meant unmarked smoke tests (§3.1) and `@pytest.mark.chaos` tests would be swept into the per-PR pipeline and fail (no real DB/Redis/LLM in the PR runner). **Fixed by directory-based ignore**, not marker-based:
    - Added new **§10.2.1 "The marker-sweep trap"** explaining the failure mode and the fix.
    - Documented the mandatory `pyproject.toml` `addopts` rule that excludes `backend/tests/smoke/` and `backend/tests/chaos/` from default discovery.
    - Documented the full `markers` list (smoke, chaos, sanity, regression, flaky) so future contributors do not have to guess.
    - Cross-referenced from [policy doc §7.1](./test-automation-policy.md#71-pytest-discovery-mandatory-addopts), which makes the rule operational (and adds a §7.2 entry: removing the `addopts` without replacement is forbidden without override).
  - **§12.2 — matrix updated** to be consistent with the new exclusion: smoke and chaos now have a "How invoked" column entry pointing to `pytest backend/tests/smoke/` / `pytest backend/tests/chaos/`. Added an explicit "Regression" row (previously implicit in "default sweep").
  - **§14 — quick-reference** updated with the same note: smoke/chaos run by explicit path, not by the default sweep.

  **🟡 Yellow (real edge cases) — all addressed:**
  - **§5.1 Path B — tombstone execution risk.** A `removed_in_vX` test would be swept up by the (now-corrected) `not integration` filter and fail the build. Now requires BOTH `@pytest.mark.removed_in_<version>` (documentation marker) **and** `@pytest.mark.skip(reason="removed in <version>; see <ticket>")` (actual skip). Documented why both are required.
  - **§7.4 — git diff depth.** With `actions/checkout@v4`'s default `fetch-depth: 1`, `origin/${{ github.base_ref }}` is not a resolvable ref, and the original script would crash. Fixed to use `${{ github.event.pull_request.base.sha }}...HEAD` directly, and added a documented `fetch-depth: 0` checkout step.
  - **§4.2 — BYOK spend guardrail.** Added a one-liner: the CI BYOK key must have a hard monthly spend cap and provider-level rate-limit alerting, so a flaky retry loop or runaway matrix cannot drain credits.

  **Policy doc sync:**
  - Added **[policy doc §7.1 "Pytest discovery"](./test-automation-policy.md#71-pytest-discovery-mandatory-addopts)** with the full `pyproject.toml` snippet and the rationale. Made the rule operational (forbidden without override). Bumped the policy doc to v1.1.

- **2026-06-18** — v1.4. Codebase-verification pass:
  - Fixed all `/healthz` → `/health` and `/readyz` → `/ready` references (endpoints verified against `backend/app/api/v1/health.py`).
  - Fixed §3.4 smoke example: `from app.db import session_scope` → `from app.database import get_db_session` (async); `app/db.py` does not exist.
  - Fixed §9.4: `app/core/logging.py` does not exist; logging is configured in `main_fastapi.py`.
  - Updated test count from ~168 to ~170.
  - Added note that `deploy-frontend.sh` does not yet have a health probe.
  - Added frontend source-path clarification (homelab vs VPS).
  - Added Implementation Status callout.
  - Reconciled flake deletion threshold with policy doc (§10.4 is the contract: 1 re-flake after quarantine → delete).
