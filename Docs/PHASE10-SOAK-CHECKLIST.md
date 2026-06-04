# Phase 10 Soak Verification Checklist

**Purpose:** Gate document for applying Phase 10.2–10.4 migrations after the
2-week soak period of Phase 10.1 (blueprints/runs/blueprint_versions tables).

**Target apply date:** 2026-06-23 (14 days after Phase 10.1 deployment on 2026-06-09)

**To unlock:** `export PHASE10_SOAK_COMPLETE=1` before running `alembic upgrade head`

**Migration chain:**
| Phase | Revision ID | Description | Risk |
|-------|-------------|-------------|------|
| 10.2 | `phase102_compat_views` | Create compat views (missions → blueprints) | Low |
| 10.3 | `phase103_drop_old_tables` | Drop old execution tables (**no downgrade**) | **High** |
| 10.4 | `phase104_retarget_aux_tables` | Retarget aux table FKs to blueprints/runs | Medium |

---

## Pre-Apply Checklist

Every item below must be checked before setting `PHASE10_SOAK_COMPLETE=1`.

### 1. Zero Error Rate on V2 Endpoints (14 days)

```bash
# Check backend logs for 500 errors on V2 endpoints over the last 14 days
docker compose logs backend --since=336h 2>&1 \
  | grep -c '500.*api/v2/blueprints\|500.*api/v2/runs'
```

- [ ] Zero 500 errors on `POST /api/v2/blueprints` (create)
- [ ] Zero 500 errors on `GET /api/v2/blueprints/{id}` (read)
- [ ] Zero 500 errors on `PATCH /api/v2/blueprints/{id}` (update)
- [ ] Zero 500 errors on `POST /api/v2/blueprints/{id}/publish`
- [ ] Zero 500 errors on `POST /api/v2/blueprints/{id}/run`
- [ ] Zero 500 errors on `GET /api/v2/runs` (list)
- [ ] Zero 500 errors on `GET /api/v2/runs/{id}` (read)
- [ ] Zero 500 errors on `POST /api/v2/runs/{id}/abort`
- [ ] Zero 500 errors on `POST /api/v2/runs/{id}/retry`
- [ ] Zero 500 errors on `GET /api/v2/runs/{id}/events`
- [ ] Zero `InFailedSQLTransactionError` in logs
- [ ] Zero `MissingGreenlet` errors in logs

**Signed off by:** _____________ **Date:** _____________

### 2. Data Integrity

```bash
# Check for orphaned or inconsistent rows
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    # Orphaned runs (blueprint deleted but run still references it)
    r = c.execute(text('''
        SELECT count(*) FROM runs r
        LEFT JOIN blueprints b ON r.blueprint_id = b.id
        WHERE r.blueprint_id IS NOT NULL AND b.id IS NULL
    ''')).scalar()
    print(f'Orphaned runs (FK mismatch): {r}')

    # Runs with NULL blueprint_id (should be 0 unless blueprint was deleted)
    r = c.execute(text('SELECT count(*) FROM runs WHERE blueprint_id IS NULL')).scalar()
    print(f'Runs with NULL blueprint_id: {r}')

    # Orphaned blueprint versions
    r = c.execute(text('''
        SELECT count(*) FROM blueprint_versions bv
        LEFT JOIN blueprints b ON bv.blueprint_id = b.id
        WHERE b.id IS NULL
    ''')).scalar()
    print(f'Orphaned blueprint versions: {r}')

    # Blueprints with zero versions
    r = c.execute(text('''
        SELECT count(*) FROM blueprints b
        WHERE NOT EXISTS (SELECT 1 FROM blueprint_versions bv WHERE bv.blueprint_id = b.id)
        AND b.deleted_at IS NULL
    ''')).scalar()
    print(f'Blueprints with no versions: {r}')

    # Total counts
    for t in ['blueprints', 'runs', 'blueprint_versions']:
        count = c.execute(text(f'SELECT count(*) FROM {t}')).scalar()
        print(f'{t}: {count} rows')
"
```

- [ ] Zero orphaned runs (runs referencing non-existent blueprints)
- [ ] Zero orphaned blueprint versions
- [ ] All active blueprints have at least 1 version
- [ ] `substrate_events.blueprint_id` column populated for new events
- [ ] No duplicate entries in `blueprint_versions(blueprint_id, version)`

**Signed off by:** _____________ **Date:** _____________

### 3. Execution Health

```bash
# Check run status distribution
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    rows = c.execute(text('''
        SELECT status, count(*) FROM runs
        GROUP BY status ORDER BY count DESC
    ''')).fetchall()
    for status, count in rows:
        print(f'  {status}: {count}')
"
```

- [ ] All runs that entered `executing` status eventually reached a terminal state
      (`completed`, `failed`, or `aborted`)
- [ ] No runs stuck in `executing` status for > 1 hour
- [ ] Run creation → execution flow works without errors
- [ ] Event log append operations succeed (no `DataError` from UUID coercion)

**Signed off by:** _____________ **Date:** _____________

### 4. Compat View Smoke Tests

These tests verify the Phase 10.2 compat views will work correctly after
they're applied. Run these queries against the **current** (pre-views) schema
to validate the SQL logic.

```bash
# Validate compat view SQL logic against current data
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    # Test missions_compat view logic (blueprints + latest run)
    r = c.execute(text('''
        SELECT b.id, b.title, b.blueprint_type, b.status,
               latest_run.total_tokens, latest_run.total_cost_usd
        FROM blueprints b
        LEFT JOIN LATERAL (
            SELECT r.total_tokens, r.total_cost_usd
            FROM runs r WHERE r.blueprint_id = b.id
            ORDER BY r.created_at DESC LIMIT 1
        ) latest_run ON true
        WHERE b.deleted_at IS NULL
        LIMIT 5
    ''')).fetchall()
    print(f'missions_compat logic: {len(r)} rows returned')
    for row in r:
        print(f'  {row[0]}: {row[1]} ({row[2]}, {row[3]})')

    # Test workflows_compat view logic
    r = c.execute(text('''
        SELECT b.id, b.title, b.status
        FROM blueprints b
        WHERE b.blueprint_type IN (\'graph\', \'dag\') AND b.deleted_at IS NULL
        LIMIT 5
    ''')).fetchall()
    print(f'workflows_compat logic: {len(r)} rows returned')

    # Test workflow_executions_compat view logic
    r = c.execute(text('''
        SELECT r.id, r.blueprint_id, r.status
        FROM runs r LIMIT 5
    ''')).fetchall()
    print(f'workflow_executions_compat logic: {len(r)} rows returned')
"
```

- [ ] `missions_compat` view logic returns correct data (blueprints + latest run)
- [ ] `workflows_compat` view logic returns graph/dag blueprints
- [ ] `workflow_executions_compat` view logic returns all runs
- [ ] No duplicate rows from `LEFT JOIN LATERAL` (one row per blueprint)

**Signed off by:** _____________ **Date:** _____________

### 5. Test Suite Green

```bash
# Run all Blueprint/Run integration tests
cd /opt/flowmanner/backend
python -m pytest tests/integration/test_blueprint_run_lifecycle.py \
                 tests/integration/test_blueprint_run_api.py -v --tb=short
```

- [ ] All service-level tests pass (62 tests)
- [ ] All API-level tests pass (30 tests)
- [ ] No regressions in existing test suite

**Signed off by:** _____________ **Date:** _____________

### 6. Database Backup

```bash
# Take a full backup immediately before applying Phase 10.3
# Phase 10.3 has NO DOWNGRADE — this backup is the only rollback path
pg_dump -h localhost -U workflow_user workflow_db \
  > /opt/flowmanner/backups/pre_phase103_$(date +%Y%m%d_%H%M%S).sql
```

- [ ] Full database backup taken and verified
- [ ] Backup stored in `/opt/flowmanner/backups/`
- [ ] Backup size is reasonable (not truncated)
- [ ] Backup retention: keep for **30 days** minimum after Phase 10.3
- [ ] ⚠️ Phase 10.3 drops `missions` table — `mission_improvements` rows with
      `ON DELETE CASCADE` will be lost. Count affected rows before backup:
      `SELECT count(*) FROM mission_improvements;`

**Signed off by:** _____________ **Date:** _____________

---

## Apply Procedure

Once all checklist items are signed off:

```bash
# 1. Take backup (checklist item #6)
# ⚠️ Phase 10.3 has NO DOWNGRADE — this backup is the only rollback path
pg_dump -h localhost -U workflow_user workflow_db \
  > /opt/flowmanner/backups/pre_phase103_$(date +%Y%m%d_%H%M%S).sql

# 2. Apply all remaining migrations
# ⚠️ Do NOT use deploy-backend.sh --migrate — it doesn't pass
# the PHASE10_SOAK_COMPLETE env var into the container.
cd /opt/flowmanner
docker compose exec -T -e PHASE10_SOAK_COMPLETE=1 backend \
  alembic upgrade head

# 3. Verify new revision
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    r = c.execute(text('SELECT version_num FROM alembic_version')).fetchone()
    print(f'DB revision: {r[0]}')
"

# 4. Verify backend health after migration
docker compose restart backend
sleep 10
curl -sf http://localhost:8000/health && echo 'Backend healthy ✅' || echo 'Backend unhealthy ❌'

# 5. Verify compat views exist
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, inspect
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
insp = inspect(e)
views = insp.get_view_names()
for v in ['missions_compat', 'workflows_compat', 'workflow_executions_compat']:
    print(f'{v}: {\"EXISTS\" if v in views else \"MISSING\"}')" 

# 6. Verify compat view column mappings
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    # Verify missions_compat column aliases
    r = c.execute(text('SELECT mission_type, tokens_used, actual_cost FROM missions_compat LIMIT 1')).fetchone()
    print(f'missions_compat columns: mission_type={r[0] if r else "N/A"}, tokens={r[1] if r else "N/A"}')

    # Verify workflows_compat column aliases  
    r = c.execute(text('SELECT name, graph_definition FROM workflows_compat LIMIT 1')).fetchone()
    print(f'workflows_compat columns: name={r[0] if r else "N/A"}')

    # Verify workflow_executions_compat column aliases
    r = c.execute(text('SELECT workflow_id, status FROM workflow_executions_compat LIMIT 1')).fetchone()
    print(f'workflow_executions_compat columns: workflow_id={r[0] if r else "N/A"}')
"

# 7. Verify old tables are dropped (Phase 10.3)
docker compose exec -T backend python3 -c "
from sqlalchemy import create_engine, inspect
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
insp = inspect(e)
tables = insp.get_table_names()
for t in ['missions', 'mission_tasks', 'mission_logs', 'workflows', 
          'workflow_executions', 'workflow_states', 'orchestrator_executions']:
    print(f'{t}: {\"EXISTS (⚠️)\" if t in tables else \"DROPPED ✅\"}')"

# 8. Run tests
cd /opt/flowmanner/backend
python -m pytest tests/ -v --tb=short
```

---

## Rollback Plan

### Phase 10.2 rollback (compat views)
```bash
docker compose exec -T backend alembic downgrade phase101_blueprints_runs
```

### Phase 10.3 rollback (**no downgrade — restore from backup**)
```bash
# Restore from backup taken in checklist item #6
bash /opt/flowmanner/scripts/restore-db.sh /opt/flowmanner/backups/pre_phase103_*.sql
docker compose exec -T backend alembic stamp phase102_compat_views
```

### Phase 10.4 rollback
```bash
docker compose exec -T backend alembic downgrade phase103_drop_old_tables
```

---

## Post-Apply Cleanup

After Phase 10.2-10.4 are applied and verified:

- [ ] Remove the soak reminder cron job:
  `crontab -l | grep -v phase10 | crontab -`
- [ ] Remove the HOLD safety guards from migration files
- [ ] Update `deploy-backend.sh` to no longer need `PHASE10_SOAK_COMPLETE`
- [ ] Monitor for 48 hours after apply; keep backup for 30 days
- [ ] Delete this checklist or mark as **COMPLETE**

---

**Last updated:** 2026-06-04  
**Created by:** Buffy (AI assistant)
