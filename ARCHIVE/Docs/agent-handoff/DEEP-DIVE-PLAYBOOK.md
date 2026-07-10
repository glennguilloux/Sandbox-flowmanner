# Deep-Dive Playbook

Use this when a topic is too large to safely change from memory alone. The goal is not a pretty architecture essay. The goal is a grounded working map that prevents the next agent from guessing.

## 0. Guardrails

- Start with `git status --short && git branch --show-current && git rev-parse --short HEAD`.
- Do not claim runtime behavior unless you checked logs, tests, or live endpoints.
- Do not deploy during a deep-dive. Deep-dives produce docs and a next-step plan.
- If the user asks for serious backend work, update the matching dossier before touching code.
- English only.

## 1. Choose the dossier type

| Dossier type | Use when |
|---|---|
| Topic dossier | Backend/domain/infrastructure area, e.g. agent runtime, substrate, migrations. |
| Feature deep-dive | User-facing feature spanning frontend route, backend API, DB models, tests. |
| Session handoff | Work is unfinished and another agent must resume. |

## 2. Minimum source grounding

For a backend topic, inspect at least:

- `backend/app/api/...` route or CQRS package.
- `backend/app/services/...` service layer.
- `backend/app/models/...` ORM model.
- `backend/app/schemas/...` request/response schema if present.
- `backend/alembic/versions/...` migration if model/DB behavior changed.
- `backend/tests/...` tests for the area.

For a frontend feature, inspect at least:

- Next.js route/component.
- API client or generated SDK call.
- Backend endpoint contract.
- Zustand store or server state hook.
- Relevant tests.

## 3. Discovery commands

Backend structure:

```bash
python - <<'PY'
from pathlib import Path
root = Path('backend/app')
for name in ['api','services','models','schemas','tools','tasks','middleware','websocket','integrations','governance','sdk','tests']:
    p = root / name
    print(f'{name}: {len(list(p.rglob("*.py"))) if p.exists() else 0} files')
PY
```

Route inventory:

```bash
python - <<'PY'
from pathlib import Path
for root in ['backend/app/api/v1', 'backend/app/api/v2', 'backend/app/api/v3']:
    p = Path(root)
    if p.exists():
        print(root, len(list(p.glob('*.py'))), 'route/module files')
PY
```

Find TODO/stub markers in a target area:

```bash
grep -RInE 'TODO|stub|Stub|placeholder|coming soon|pass$|raise NotImplemented' backend/app/<area>
```

Find tests for a target area:

```bash
grep -RInE '<area keyword>|<model name>|<route name>' backend/tests backend/app/tests
```

If touching data model or migrations:

```bash
grep -RIn '__tablename__' backend/app/models
grep -RIn 'class .*Model\|class .*Base' backend/app/models
grep -RIn 'alembic' backend/alembic/versions | head
```

If touching frontend feature:

```bash
grep -RIn '<feature name or API client>' /home/glenn/FlowmannerV2-frontend/src
grep -RIn '<api method name>' /home/glenn/FlowmannerV2-frontend/src
```

## 4. What every dossier must capture

- Current status: `Draft`, `Grounded`, `Ready`, or `Archived`.
- Exact files and line ranges.
- Current API route(s), method(s), auth/scope expectations.
- DB models, migrations, and any overlapping concepts.
- Tests that exist and tests missing.
- Known risks and deployment caveats.
- Next safe action, not a giant phase plan.

## 5. Verification gates before code changes

Run the relevant gate before editing:

| Area | Gate |
|---|---|
| API route | Import or test the route path; confirm status/response shape. |
| DB model | Confirm model, migration, and `__tablename__`. |
| Execution engine | Run the smallest existing test for the strategy/executor. |
| Frontend feature | Run route build/typecheck or targeted vitest/playwright. |
| Deployment-sensitive change | Confirm deploy script and rollback behavior from `AGENTS.md`. |

## 6. Output contract

A good deep-dive ends with one of:

1. `Ready to implement` — exact files and next change are known.
2. `Blocked` — missing model/route/test/auth context prevents safe implementation.
3. `Needs user decision` — trade-off or scope choice is required.
4. `No code needed` — existing implementation already satisfies the ask.
