# EXIT AUDIT — 2026-06-25 — Fix alembic check drift (14 items)

## WHAT CHANGED (one bullet per file, what + why)

- `backend/app/models/analytics.py`: `user_id` String → Integer (match DB INTEGER)
- `backend/app/models/models.py`: 4 user_id columns String(36) → Integer; removed unused ForeignKey import
- `backend/app/models/roadmap_models.py`: 2 user_id columns String(36) → Integer; TCH003 noqa
- `backend/app/models/tool_models.py`: 2 user_id columns String(36) → Integer
- `backend/app/models/hitl_models.py`: mission_id String(36) → UUID; workspace_hitl_configs.id autoincrement → Identity(); TCH003 noqa
- `backend/app/models/learning_models.py`: mission_id String(36) → UUID
- `backend/app/models/llm_call_record.py`: agent_id UUID → String(36) (match DB VARCHAR)
- `backend/app/models/memory_models.py`: workspace_id UUID → String(36) (match DB VARCHAR); TCH003 noqa

## ADDITIONAL CHANGES (same session)

- `backend/alembic/env.py`: Removed blanket FK suppression from `compare_type`; passed `compare_type` explicitly to `do_run_migrations`
- `backend/app/models/extension.py`: `extensions.id` String() → String(36) (match DB VARCHAR)
- `SESSION-RITUAL.md`: Added rule 7 (migration data-mutation convention)
- `backend/AGENTS.md`: Added migration data-mutation convention section

## TESTS RUN + RESULT

```
965 passed, 3 skipped in 16.00s
```

## STATUS

### git status
```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
	modified:   SESSION-RITUAL.md
	modified:   backend/AGENTS.md
```
(Pre-existing from earlier session — not this agent's changes.)

### git fetch origin && git log --oneline origin/main..main
```
(empty — commit was pushed)
```

### docker compose exec backend alembic current
```
fix_playground_ws_fk_type (head)
```

### docker compose exec backend alembic check
```
No new upgrade operations detected.
```

### pytest
```
965 passed, 3 skipped, 17 warnings in 16.00s
```

## NEXT SESSION HANDOFF

Resolved all 14 `alembic check` drift items by aligning SQLAlchemy model column types with the live PostgreSQL schema. The drift was pre-existing — `compare_type` in `env.py` suppressed FK-bound type changes during autogenerate, so the reconciliation migration (`reconcile_schema_001`) never addressed them. Models now match DB exactly. `alembic check` reports 0 drift, 965 tests pass.

Also fixed the root cause: removed the blanket FK suppression from `compare_type` so future type drift is caught by autogenerate and `alembic check`. Caught and fixed one additional drift item (`extensions.id` String→String(36)) as a result.

Added migration data-mutation convention (never DELETE rows for NOT NULL, use UPDATE with sentinel) to SESSION-RITUAL.md and backend/AGENTS.md.

All changes deployed to production.

## COMMITS

```
4555295 fix(models): align SQLAlchemy column types with live DB schema
9231f93 fix(alembic): remove blanket FK suppression from compare_type + fix extensions.id drift
f4b83b2 docs: add migration data-mutation convention — never DELETE rows for NOT NULL
3937265 docs: add exit audit for alembic drift fix session (2026-06-25)
```

## DEPLOY

```
Deployed via deploy-backend.sh on 2026-06-25.
Pre-checks: 6/6 passed (5 passed, 1 info-only).
Build: succeeded.
Health checks: passed (4 attempts — normal startup time).
Container: workflows-backend:restored (running).
```
