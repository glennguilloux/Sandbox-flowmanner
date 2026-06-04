# TASK-BE-STUB-12 — Alembic Migration: Rename Graph Tables + Remove Dead Router Imports

## Current State
Two migration-gap issues:
1. `/opt/flowmanner/backend/app/models/graph.py`: Three tables have TODO rename comments:
   - Line 14: `__tablename__ = "graph_workflows"  # TODO: rename to "workflows"`
   - Line 26: `__tablename__ = "graph_executions"  # TODO: rename to "workflow_executions"`
   - Line 43: `__tablename__ = "graph_states"  # TODO: rename to "workflow_states"`
2. `/opt/flowmanner/backend/app/api/v1/__init__.py`: 20+ router imports for non-existent modules.

## Problem
- **HIGH**: Table names don't match current naming conventions; confusion for new developers.
- **MEDIUM**: 20+ router imports fail silently every startup, creating log noise.

## Exact Files
- **Read:** `/opt/flowmanner/backend/app/models/graph.py` (table definitions)
- **Search:** All files referencing `graph_workflows`, `graph_executions`, `graph_states` (SQLAlchemy queries, raw SQL)
- **Read:** `/opt/flowmanner/backend/app/api/v1/__init__.py` (router imports)
- **Create:** `/opt/flowmanner/backend/alembic/versions/YYYY_MM_DD_rename_graph_tables.py`
- **Modify:** `/opt/flowmanner/backend/app/api/v1/__init__.py`

## Exact Implementation Steps

### Part A: Table Renames
1. Search for all references to the old table names:
   ```bash
   grep -rn "graph_workflows\|graph_executions\|graph_states" app/ --include="*.py"
   ```
2. Create Alembic migration:
   ```python
   # alembic/versions/rename_graph_tables.py
   def upgrade():
       op.rename_table('graph_workflows', 'workflows')
       op.rename_table('graph_executions', 'workflow_executions')
       op.rename_table('graph_states', 'workflow_states')
   
   def downgrade():
       op.rename_table('workflows', 'graph_workflows')
       op.rename_table('workflow_executions', 'graph_executions')
       op.rename_table('workflow_states', 'graph_states')
   ```
3. Update model `__tablename__` values in `graph.py`.
4. Update all SQLAlchemy queries that reference old table names.
5. Update any raw SQL or migration version files.

### Part B: Dead Router Import Cleanup
1. Verify which modules exist:
   ```bash
   ls app/api/v1/*.py | sed 's|.*/||;s|\.py||' | sort > /tmp/existing.txt
   ```
2. Cross-reference with `_safe_import` list in `__init__.py`.
3. Remove imports for non-existent modules (community, domain_agents, file, flow_compat, llm, llm_advanced, memory, mission_advanced_routes, mission_decomposition_routes, delegations, feedback_routes, blog, admin, integrations, marketplace, linear, data_export, feature_flags, changelog, agent_capabilities, agent_personalities).
4. Add a comment for each removed import: `# REMOVED: module does not exist — planned for future release`

## Constraints
- Migration must be reversible (downgrade works).
- Must not break existing data.
- Router import cleanup must not remove any working endpoint.

## Verification
```bash
cd /opt/flowmanner/backend
# Test migration
alembic upgrade head
alembic downgrade -1
alembic upgrade head
# Verify table renames
python -c "
from app.database import engine
from sqlalchemy import inspect
inspector = inspect(engine.sync_engine)
tables = inspector.get_table_names()
assert 'workflows' in tables
assert 'graph_workflows' not in tables
print('Table renames verified')
"
# Verify no dead imports
python -c "from app.api.v1 import api_v1_router; print('Router import OK')"
```
