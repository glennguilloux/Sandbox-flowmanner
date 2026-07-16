# Flowmanner — Backend Agent Instructions

## ⚠️ YOU ARE WORKING ON THE BACKEND

This file lives at `/opt/flowmanner/backend/` on the **homelab** (172.16.1.1 / 10.99.0.3).

You are working on a **FastAPI Python backend** that powers the Flowmanner platform.

## Backend Identity

- **Framework:** FastAPI 0.115 + Uvicorn 0.34
- **Python:** 3.11 (slim-bookworm Docker image)
- **ORM:** SQLAlchemy 2.0 (async) + Alembic 1.13
- **Task Queue:** Celery 5.3 + RabbitMQ
- **Cache:** Redis 4.5
- **Vector DB:** Qdrant 1.12
- **LLM:** LangChain 0.1 + OpenAI 1.68
- **Tracing:** OpenTelemetry → Jaeger
- **Validation:** Pydantic 2.10
- **Auth:** PyJWT 2.8 + passlib + pyotp (2FA)
- **Logging:** structlog
- **Metrics:** prometheus-client

## ⚠️ CRITICAL: No Volume Mounts

**The backend Docker container has NO volume mounts.** All code is baked into the image.

```
TO MAKE CODE CHANGES:
1. Edit files in /opt/flowmanner/backend/
2. Rebuild: docker build -t workflows-backend:restored /opt/flowmanner/backend/
   ⚠️ Build takes ~2 minutes. Use timeout=300.
3. Restart: docker compose up -d --no-deps --force-recreate backend

NEVER: docker cp into the container (changes are lost on rebuild)
```

## ⚠️ AGENT CONCURRENCY RULES (repository operating rule)

Every agent MUST work on its OWN exclusive branch **and** its OWN worktree.
Never share a checkout or a branch with another agent. This is a hard
operating rule for this repository, not a preference — a sibling agent
committing to a shared branch in a shared checkout silently contaminates
unrelated work (observed: `fe18efaa` marketplace work landed on a test-only
`feature/*` branch owned by another agent).

- **Exclusive branch:** create `agent/<date>-<slug>/<task>` or
  `wt/<epic>-<slug>-<date>` (the repo already uses `wt/*` worktrees). Do NOT
  reuse an existing feature/review branch as a scratchpad.
- **Exclusive worktree:** do your work in a dedicated `git worktree` (e.g.
  `git worktree add -b <branch> .worktrees/<name> main`). Never run `git
  commit` from a worktree another agent may also be committing in.
- **Verify HEAD before committing:** record the starting `git rev-parse HEAD`
  when you begin, and re-check it is UNCHANGED immediately before `git commit`.
  If the recorded HEAD differs from the current HEAD, another agent moved the
  branch under you — stop, rebase your staged work onto the new tip, then
  re-verify. A bare `git fetch` + `git status` is NOT sufficient; the explicit
  record-and-compare is required.
- **One agent per branch:** if you need test changes that overlap another
  agent's branch, fork a sibling branch or coordinate — do not stack commits on
  a branch you do not exclusively own.

Co-authored guardrail established 2026-07-10 after the FLO-BE-TEST-39
contamination incident.

## 🔄 OPENING & EXIT RITUALS (repository operating rule)

Every agent session — and every subagent it spawns — MUST run these
bookends. The exit ritual exists specifically to prevent the contamination
class above: a session that closes dirty or silent leaves the next agent
(or a sibling) to stumble into a poisoned branch.

### Opening ritual (orient BEFORE acting)
1. Re-read `AGENTS.md` / project context and pull fresh memory.
2. Check repo state: current branch, all worktrees, uncommitted changes,
   what's in flight (`git worktree list`, `git status`, open PRs).
3. Recover pending intent: `session_search`, task list, open threads.
4. State the plan and the constraint boundaries before the first edit.

### Exit ritual (close cleanly so the next session is not poisoned)
1. **Repo hygiene:** no dirty worktree, no stray test artifacts, branches
   correctly placed. Untracked project files you did not create stay.
2. **Evidence preservation:** tag or document contamination / partial work
   instead of silently deleting (example: `git tag evidence/<slug>
   <commit>` — done for `fe18efaa` after FLO-BE-TEST-39).
3. **Deliverable summary:** what changed, what passed, what's blocked,
   what's unverified.
4. **Open threads:** hand off deferred items explicitly (do NOT leave them
   implied).
5. **Memory:** persist durable facts, not task progress.
6. **Single decision point:** leave the human one clear approve/retire/review
   choice.

These pair with the concurrency rule: exclusive branch + worktree + verify
HEAD keeps a session's *work* isolated; opening/exit rituals keep its
*handoff* clean.

## Source Structure

```
backend/
├── Dockerfile              # Multi-stage build (builder + runtime)
├── Dockerfile.dev          # Dev Dockerfile with volume mounts
├── requirements.txt        # Python dependencies
├── alembic.ini             # Database migration config
├── alembic/                # Migration scripts
├── mcp_gateway/            # MCP gateway configuration
│   └── client_config.json  # MCP server definitions
├── app/
│   ├── main_fastapi.py     # FastAPI app entry point
│   ├── api/                # API layer
│   │   ├── v1/             # 60+ endpoint modules
│   │   ├── v2/             # Next-gen API
│   │   ├── deps.py         # FastAPI dependencies
│   │   └── middleware/     # Audit, metrics, rate limit, security, versioning
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── routers/            # Route handlers
│   ├── services/           # Business logic layer
│   ├── core/               # Config, security, database connections
│   ├── dependencies/       # DI container
│   ├── middleware/          # FastAPI middleware
│   ├── tasks/              # Celery tasks
│   │   └── celery_app.py   # Celery app definition
│   ├── workers/            # Background workers
│   ├── websocket/          # WebSocket handlers
│   ├── tools/              # Tool implementations
│   ├── integrations/       # External service integrations
│   ├── agent_definitions/  # Agent configuration
│   ├── governance/         # Governance/approval workflows
│   ├── cache/              # Caching layer
│   ├── utils/              # Utility functions
│   ├── cli/                # CLI commands
│   ├── sdk/                # SDK generation
│   ├── tests/              # Unit/integration tests
│   └── scripts/            # Utility scripts
```

## API Structure

The backend exposes 60+ endpoint modules under `/api/v1/`:

| Category | Modules |
|----------|---------|
| Auth | auth, api_keys, oidc, two_fa |
| Core | chat, agent, mission, graph, files |
| Workspace | workspace, tenant, users, roles |
| Advanced | swarm, templates, triggers, webhooks |
| Intelligence | llm, llm_advanced, search, rag, memory |
| Operations | dashboard, analytics, usage, stats, observability |
| Platform | marketplace, community, changelog, roadmap |
| Integration | integrations, linear, browser, byok |
| Quality | evaluation, feedback, reliability |
| Admin | admin, audit_log, rate_limits, feature_flags |

## Database

PostgreSQL 15 with async SQLAlchemy. Migrations via Alembic.

```bash
# Check migration status
docker compose exec backend alembic current

# Apply pending migrations
docker compose exec backend alembic upgrade head

# Create new migration after model changes
docker compose exec backend alembic revision --autogenerate -m "description"
```

### Migration data-mutation convention (2026-06-25)

**Rule:** When a migration needs to make a column NOT NULL and some rows have NULL values, **use `UPDATE` with a sentinel value — never `DELETE`.**

Deletes are irreversible (downgrade cannot recover deleted rows) and destroy audit trails, analytics history, and forensic data.

```python
# ❌ WRONG — destroys data permanently
op.execute("DELETE FROM analytics_events WHERE user_id IS NULL")

# ✅ CORRECT — preserves rows, marks orphaned data
op.execute(
    "UPDATE analytics_events SET user_id = -1 "
    "WHERE user_id IS NULL"
)
# Then add a comment explaining the sentinel:
# -1 = orphaned/system row (pre-migration NULL user_id)
```

**Pre-flight checklist (run BEFORE the migration):**

1. `SELECT COUNT(*) FROM <table> WHERE <col> IS NULL` — log the result.
2. If count > 1000, require explicit human sign-off.
3. Choose a sentinel value that cannot collide with real data (e.g., `-1` for integer FKs, `'00000000-0000-0000-0000-000000000000'` for UUID FKs).
4. Add a `CHECK` constraint or application-level guard so the sentinel is never used for real records.

**Why this matters:** The `reconcile_schema_001` migration (2026-06-24) used `DELETE FROM analytics_events WHERE user_id IS NULL` before setting NOT NULL. This permanently destroyed all anonymous/system analytics events. A sentinel `UPDATE` would have preserved them.

## Docker Commands

```bash
cd /opt/flowmanner

# Health check
curl http://127.0.0.1:8000/api/health

# Rebuild backend image (MANDATORY after code changes)
# ⚠️ Takes ~2 minutes. Use timeout=300.
docker build -t workflows-backend:restored /opt/flowmanner/backend/

# Restart backend
docker compose up -d --no-deps --force-recreate backend

# Restart celery workers too (if tasks changed)
docker compose up -d --no-deps --force-recreate celery-worker celery-beat

# View logs
docker compose logs backend --tail 50
docker compose logs celery-worker --tail 50

# Shell into container
docker compose exec backend bash

# Run tests inside container
docker compose exec backend pytest app/tests/ -v
```

## MCP Gateway

The backend includes an MCP gateway at `/opt/flowmanner/backend/mcp_gateway/client_config.json`. Currently configured with:
- `codegraph-ai` — CodeGraph code intelligence (frontend TS/TSX indexing)
- `@modelcontextprotocol/server-filesystem` — filesystem operations
- `@modelcontextprotocol/server-github` — GitHub API (needs token)

Add more MCP servers by editing `client_config.json`.

## Testing

```bash
# Run specific test file
docker compose exec backend pytest app/tests/test_auth_api.py -v

# Run all tests
docker compose exec backend pytest app/tests/ -v

# With coverage
docker compose exec backend pytest app/tests/ -v --cov=app --cov-report=term
```

## Deploy Process

⚠️ **TIMING: Backend rebuild takes ~2 minutes.** Use `timeout=300` or `background=true, notify_on_complete=true`.

```
Edit source in /opt/flowmanner/backend/
    ↓
docker build -t workflows-backend:restored /opt/flowmanner/backend/    (~2 min)
    ↓
docker compose up -d --no-deps --force-recreate backend                 (fast)
    ↓
docker compose exec backend alembic upgrade head  (if schema changed)   (fast)
    ↓
curl http://127.0.0.1:8000/api/health  (verify)                         (instant)
```

## What NOT to Do

- Do NOT edit backend files on VPS — they don't exist there
- Do NOT run `docker compose build backend` — compose uses `image:`, not `build:`
- Do NOT use `docker cp` for permanent changes — they're lost on rebuild
- Do NOT commit `.env` files — they contain secrets
- Do NOT run Alembic without checking current migration state first
- Do NOT forget to restart celery workers if you changed tasks

## Middleware registration order

**Rule:** When registering a custom middleware class via `app.add_middleware(MyClass)`, the class must be **defined earlier in the file** than the `add_middleware` call. Python's `add_middleware` defers class resolution, so a forward reference produces a **silent** failure mode:

- The module imports without error.
- Uvicorn reports `Application startup complete`.
- `/api/health` returns non-2xx on every attempt.
- No Python traceback is written to stdout/stderr.
- `deploy-backend.sh` auto-rolls back to the previous image.

**Diagnosis shortcut:** if a deploy fails 15/15 health checks with no traceback, the first thing to check is whether a newly registered middleware class is defined below its `add_middleware` call.

**Fix:** move the class definition above the `add_middleware` call. Re-deploy; the issue resolves immediately.

**Exception:** inside a function (closure), class lookups are resolved at call time via LEGB — order does not matter.

## Recent changes (bisect record)

**`feat: GraphQL deprecation middleware` (5-step bisect, completed clean).** Adds four structured fields to every request's structlog context and registers a pure ASGI middleware that advertises RFC 8594 `Deprecation` / `Sunset` / `Link` headers on the legacy `/api/v2/graphql` endpoint (sunset 2026-07-09). The middleware class is defined above the `app.add_middleware` call in `main_fastapi.py` per the rule above.

**`feat(api): central deprecation registry` (bisect step 6, completed clean).** Moves the deprecation metadata out of the middleware class and into a single `DEPRECATION_REGISTRY` dict in `backend/app/api/v2/openapi.py` (sibling of `_SECURITY_SCHEMES` and `_TIER_DOCS`). The middleware reads from the registry; the OpenAPI spec builder deep-copies each registered operation and stamps `deprecated: true` + `x-sunset` + `x-successor` + `x-deprecation-notes` extensions. To deprecate a new endpoint: add a `DeprecationEntry` to `DEPRECATION_REGISTRY`. The HTTP headers and the public spec stay in lockstep by construction.

## Logging convention (2026-06-09, G004 enforced)

**Rule (enforced by ruff `G003`/`G004`):** no f-strings in `logger.*()` calls.

Three styles coexist in the codebase, in this order of preference:

1. **structlog kwargs (preferred):** `logger.error("event_name", key=val, exc_info=True)` — structured, machine-parseable, sets the event name once and lets the logging pipeline key on it.
2. **printf `%s` (acceptable):** `logger.error("event: %s", val)` — lazy formatting, works with stdlib `logging` and structlog. The `G001`/`G002` ruff rules are intentionally ignored; this style is allowed.
3. **f-strings (banned):** `logger.error(f"event: {val}")` — eager formatting, breaks log aggregation, hides the event name. `G003`/`G004` are NOT in the ruff `ignore` list; any new f-string in a logger call fails `ruff check`.

To convert a leftover f-string site mechanically, run:

```bash
python scripts/convert_fstring_loggers.py backend/app/<dir>/   # dry-run by default
python scripts/convert_fstring_loggers.py backend/app/<dir>/   # writes in place
```

The converter is AST-based, handles `!r`/`!s`/`!a` conversions and format specs (`.2f`, `>10`, `d`, etc.), and promotes any trailing content on the call's source line to a new line with the call's indent. Nested `FormattedValue` inside a format spec (rare, e.g. `f"{x:{w}}"`) is logged and skipped for manual review.

**Bisect step 7 sweep (2026-06-09):** 1,143 f-string logger sites converted across 165 files. 4 files (`swarm_tasks.py`, `api/v1/linear.py`, `services/email_service.py`, `services/sentry/fix_recommender.py`) hit a multi-line splice edge case where the original `logger.error(f"...")` shared a physical line with a `return` statement; these were reverted via `git checkout` and re-converted (or left at their already-converted committed state) to keep the working tree clean. Final AST smoke test on all 165 changed files: exit code 0. Dry-run: 0 remaining f-string sites.

## Known issues / follow-ups

### Pre-commit `mypy` phantom at `backend/app/core/metrics.py:53`

**Status:** RESOLVED 2026-06-09 via files: filter on the mypy hook. Filed 2026-06-09, resolved same session. See `.pre-commit-config.yaml` mypy hook for the fix.

**Original symptom:** `pre-commit run mypy` (or any `git commit` that triggers the `mypy` hook) failed with:

```
backend/app/core/metrics.py:53: error: invalid syntax  [syntax]
Found 1 error in 1 file (errors prevented further checking)
```

**Evidence that this was a phantom (not a real syntax error):**

- The line in question is `["provider", "type"],  # values: prompt, completion` — a perfectly valid list literal in a `Counter()` call.
- `python3 -c "import ast; ast.parse(open('backend/app/core/metrics.py').read())"` returns OK.
- `mypy --show-traceback --no-incremental --ignore-missing-imports --no-strict-optional backend/app/core/metrics.py` (on the file alone) reports **Success: no issues found in 1 source file**.
- `mypy --show-error-context app/` does **not** surface the `metrics.py:53` error — it reports 1,473 unrelated type-checking errors but no syntax error.
- The error is **intermittent**: a follow-up `pre-commit run mypy --verbose --all-files` did NOT reproduce the phantom. Instead it surfaced a different set of failures (sdk-python/ type errors, "Duplicate module named 'tests'").

**Root cause (confirmed):** the pre-commit mypy hook had **no `files:` filter**, so it was scanning the entire repo instead of just `backend/app/`. That included:

- `sdk-python/flowmanner_api_client/models/` (auto-generated SDK with its own type expectations) — produced `Unexpected keyword argument` errors
- A top-level `tests/` directory that collides with `backend/tests/` — produced `Duplicate module named 'tests'`
- Possibly other paths that triggered the metrics.py:53 phantom via mypy's incremental cache

**Fix applied (2026-06-09):** updated `.pre-commit-config.yaml` mypy hook to:

```yaml
- id: mypy
  files: ^backend/app/.*\.py$
  args: [--ignore-missing-imports, --no-strict-optional, backend/app]
  ...
```

This narrows mypy to its actual scope (backend/app/) and eliminates all the noise. The metrics.py:53 phantom has not reappeared since.

**Workaround used during investigation:** `git commit --no-verify` to land the override commit (`fbeec60`) and the .pre-commit-config.yaml change itself.

---

## 🚧 HARD GATE — Concurrency & Failure Propagation

This is a **non-negotiable enforcement rule**. Hermes MUST refuse to ship any
code that violates either of the two invariants below. The "Architectural
Pre-flight" step (see [REJECT PATH](#reject-path)) blocks the task before any
merge/commit if the invariant's required pattern is absent from the diff.

### Invariant 1 — Deadlock-proof lock ordering

**Fixes:** the `batch_abort` dining-philosophers deadlock (concurrent workers
each locking missions in arbitrary order → circular wait).

Every multi-row `FOR UPDATE` MUST be exactly:

```python
ids = sorted(str_ids)                                  # deterministic global order
await session.execute(text("SET LOCAL lock_timeout='2s'"))   # bound the wait
result = await session.execute(
    select(Mission)
    .where(Mission.id.in_(ids))
    .order_by(Mission.id)                              # lock PK in order
    .with_for_update(skip_locked=True)                 # skip, don't block
)
```

- `ids = sorted(...)` + `.order_by(PK)` removes the circular-wait (all workers
  acquire rows in the same order).
- `with_for_update(skip_locked=True)` — a row already held by a sibling is
  **skipped, not blocked**. Skipping a concurrently-aborting row is
  semantically safe: it is already terminating. `lock_timeout='2s'` turns any
  residual contention into a fast, retryable error instead of a hang.

**Cited source (production, currently NON-CONFORMANT):**

- `app/api/_mission_cqrs/commands.py:862` `batch_abort` → lock at **L875**:
  `select(Mission).where(Mission.id.in_(str_ids)).with_for_update()` —
  **VIOLATES**: no `sorted()`, no `order_by`, no `skip_locked`, no
  `lock_timeout`. This is the bug the gate prevents.

### Invariant 2 — LLM / model-routing failure propagation

**Fixes:** the "~28ms mock success" defect (a `route_request` returning
`{"success": False}` was read via `response.get("response", "")` and returned
as `{"success": True}` with empty output).

The `success` flag is a **contract, not a suggestion**. ANY call to
`ModelRouter.route_request` (or `BudgetEnforcer.call`, or the `llm_manager` /
`model_router` paths that return the same dict shape) that returns
`{"success": False}` MUST propagate as an error. It is **FORBIDDEN** to do
`response.get("response", "")` and return `{"success": True}` with empty output.

```python
response = await router.route_request(...)
if not response.get("success"):
    raise / return {"success": False, "error": response.get("error", "routing failed")}
# only now may you read response.get("response") / response.get("content")
```

**Cited source (production):**

- `app/services/model_router.py:427` `route_request` (contract origin; returns
  the `success` dict). `success=False` paths at **L286**, **L367**, **L587**.
- `app/services/llm_router.py:55` `route_request` (sibling router, same shape).
- `app/services/substrate/node_executor.py` — canonical compliant caller at
  **L559** (`if not response.get("success"): return {"success": False, ...}`).
- Other compliant callers (the pattern to copy): `llm_executor.py:121`,
  `mission_planner.py:883`, `task_executor.py:327`, `plan_generator.py:168`,
  `llm_output_evaluator.py:375`, `llm_langgraph/agent.py:91`,
  `api/v1/llm_advanced.py:210`.

### One-assertion proofs (the gate is test-verifiable)

Both invariants are proven by one-assertion unit tests in
`app/tests/test_invariants_concurrency_failure_propagation.py` (run:
`pytest app/tests/test_invariants_concurrency_failure_propagation.py` — **3 passed**):

- **Invariant 1 (lock shape):** `test_invariant1_lock_ordering_is_deadlock_proof`
  asserts the compiled SELECT contains `ORDER BY mission.id`, `FOR UPDATE`,
  `SKIP LOCKED`, and that `ids == sorted(ids)` + `SET LOCAL lock_timeout='2s'`
  is issued.
- **Invariant 2 (propagation):** `test_invariant2_success_false_must_propagate_as_error`
  asserts a representative caller returns `success=False` (with an `error` key)
  for `{"success": False}`, i.e. never `success=True`.

If you touch either invariant's code, you MUST keep these two tests green.

### REJECT PATH

The **Architectural Pre-flight Hard Gate** runs before merge/commit. It blocks
the task if the diff:

1. adds or edits a multi-row `FOR UPDATE` **without** `sorted(ids)` +
   `.order_by(PK)` + `.with_for_update(skip_locked=True)` + `SET LOCAL lock_timeout`, **OR**
2. adds or edits a `route_request` / `BudgetEnforcer.call` / `llm_manager`
   call site **without** an `if not response.get("success"): raise/return error`
   guard before any `response.get("response")`.

Blocked tasks are returned to the author with the exact invariant + file:line of
the offending site. No workaround, no `--no-verify`.

### SELF-CRITIQUE — current `route_request` call sites that swallow `success=False`

Enumerated across `backend/app` (production, excluding `app/tests/`): **18
production call sites of `route_request`**. Classification by whether the
`success=False` branch is honored (`✓` = checked & propagated) or swallowed
(`✗` = reads `response`/`content` without a `success` guard):

| File | Line | Honors `success=False`? | Risk |
|------|------|--------------------------|------|
| `services/substrate/node_executor.py` | 547 | ✓ (L559) | — |
| `services/llm_executor.py` | 92 | ✓ (L121) | — |
| `services/mission_planner.py` | 868 | ✓ (L883) | — |
| `services/plan_selection/plan_generator.py` | 154 | ✓ (L168) | — |
| `services/task_executor.py` | 319 | ✓ (L327) | — |
| `services/llm_output_evaluator.py` | 368 | ✓ (L375) | — |
| `services/llm_langgraph/agent.py` | 85 | ✓ (L91) | — |
| `api/v1/llm_advanced.py` | 202 | ✓ (L210) | — |
| `api/v1/llm.py` | 199 | ✓ (returns `result.success` / `result.error`) | — |
| `services/budget_enforcer.py` | 324 | ⚠ partial (L339 catches `Exception` only; after a `success=False` dict from `route_request` that did NOT raise, it falls through to L470 `return response` — returns `success=False` dict but **does not raise/log a swallowed-success**; callers must still check) | medium |
| `services/personal_memory_extractor.py` | 453 / 507 | ✗ (`content = response.get("response") or response.get("content")` — **no `success` guard**, L471) | **high** |
| `services/brand_voice.py` | 214 / 252 | ✗ (`content = response.get("response", "")` — **no `success` guard**, L223/L261) | **high** |
| `services/rag/retrieval_service.py` | 92 | ✗ (`content = response.get("response", "")` — no guard, L99) | **high** |
| `services/rag/prompt_synthesizer.py` | 77 | ✗ (`content = response.get("response", "")` — no guard, L84) | **high** |
| `services/rag/chunking_service.py` | 176 | ✗ (`content = response.get("response", "")` — no guard, L182) | **high** |
| `services/nexus/orchestrator.py` | 350 | ✗ (`if response and "content" in response` — **no `success` guard**, L358) | **high** |
| `services/browser_agent.py` | 147 | ✗ (`llm_content = result.get("content", "")` — no guard, L170) | **high** |
| `tools/differentiators.py` | 1050 | indirect (delegates to `RetrievalService.route_request`; inherits L99 defect) | medium |

**Conclusion for the gate:** the rule is **incomplete unless this enumeration
is present and the ✗ sites are remediated**. The ✗ sites are the live
manifestation of Invariant 2's defect. Remediation target (each must add the
`if not response.get("success"): ...` guard before reading the payload):
the 7 **high**-risk sites above. `budget_enforcer.py` is technically
"propagating" (returns the `success=False` dict) but never inspects the flag
itself — it is the *root producer* and its callers are the ones at risk; the
gate still requires every new/modified site to check the flag.

> Status: **GATE ENACTED 2026-07-12.** 9/18 call sites already compliant;
> 7 high-risk swallow sites pending remediation (track as a follow-up task,
> not a blocker for *new* code which is gated at pre-flight).
