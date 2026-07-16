# Backend Models / Migrations / DB-Core Audit — Findings

**Branch under audit:** `agent/2026-07-11-intent-execution-architecture`
**Worktree:** `/opt/flowmanner/.worktrees/t_9d182a99` (HEAD `f6fc3637`)
**Scope:** `backend/app/models/` (68 files), `backend/alembic/versions/` (148 migration files), `backend/app/core/` (11 files), `backend/app/database.py`
**Mode:** READ-ONLY. No source files were edited, created, or deleted.
**Verification performed:** `git rev-parse --show-toplevel` (guard ✓), programmatic `down_revision` chain parse over all 148 revisions, `sqlalchemy.orm.configure_mappers()` over all 68 models, static scan of every migration for NOT-NULL / DELETE / raw-SQL patterns, and targeted reads of the suspicious migrations + `database.py` + `config.py` + `core/oauth.py` + `core/demo_credentials.py`.

---

## 🔴 Blocker findings

### 🔴 DELETE-on-NULL violates the repo's no-DELETE-on-NOT-NULL convention — `alembic/versions/reconcile_schema_001_additions.py:624`

```python
    # Delete orphaned rows with NULL user_id before setting NOT NULL
    op.execute("DELETE FROM analytics_events WHERE user_id IS NULL")
    ...
    with op.batch_alter_table("analytics_events", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.INTEGER(), nullable=False)
```

**Why it is an error:** The repo convention (AGENTS.md §Migration data-mutation, 2026-06-25) explicitly forbids `DELETE` when making a column NOT NULL and requires a sentinel `UPDATE` instead. This migration permanently destroys every `analytics_events` row that has a NULL `user_id` — irreversibly, even on `downgrade`. If any historical rows exist with a NULL FK (very common for anonymous/guest events or pre-auth telemetry), they are wiped, taking analytics history and audit forensic data with them. The correct form per the convention is a sentinel UPDATE.

**Suggested fix:**
```python
    # Preserve orphaned rows with a sentinel user_id instead of deleting them.
    op.execute(
        "UPDATE analytics_events SET user_id = -1 WHERE user_id IS NULL"
    )
    # -1 = orphaned/system row (pre-migration NULL user_id); documented in a comment.
    ...
    batch_op.alter_column("user_id", existing_type=sa.INTEGER(), nullable=False)
```
(NOTE: the same migration sets `nullable=False` on ~437 columns via `batch_alter_table`; the `analytics_events.user_id` case is the only one paired with a `DELETE` rather than a backfill. The other `alter_column(..., nullable=False)` calls in this file target columns that have `existing_server_default` set, so they are safe — only the raw `DELETE` is a convention violation.)

---

## 🟡 Suggestion findings

### 🟡 agent_templates dedup DELETE can drop user-authored templates — `alembic/versions/20260603_tools_capabilities.py:126-136`

```python
    # Deduplicate: if multiple rows share a slug, keep the newest
    op.execute(
        """
        DELETE FROM agent_templates
        WHERE template_id NOT IN (
            SELECT DISTINCT ON (slug) template_id
            FROM agent_templates
            WHERE slug IS NOT NULL
            ORDER BY slug, created_at DESC
        ) AND slug IS NOT NULL
    """
    )
```

**Why it is a latent bug:** The dedup rule "keep the NEWEST by `created_at`" keeps whichever row was inserted last — not the one a user may have actively edited or marked canonical. For user-created templates this is non-deterministic data loss: two rows with the same `slug` (e.g. a system seed plus a user fork) will silently drop one. The order tie-break is `created_at DESC` only; two rows created in the same transaction share a timestamp and Postgres `DISTINCT ON` picks an arbitrary winner. Not a hard crash, but it destroys rows that real users may depend on, and it is unrecoverable on `downgrade`.

**Suggested fix:** Add an explicit, stable priority (e.g. prefer `source = 'db'` / user-owned rows, then `created_at DESC`, then `template_id` as a final tie-break) so the kept row is deterministic, or skip the DELETE entirely and resolve the slug collision at the application layer.

### 🟡 `config.py` secret defaults are live placeholders that pass in `development` but disable auth silently — `backend/app/config.py:13,30,34`

```python
    SECRET_KEY: str = "change-me-in-production"
    JWT_SECRET_KEY: str = "change-me-in-production"
    AES_ENCRYPTION_KEY: str = "change-me-in-production"
```

**Why it is a latent bug:** `assert_production_ready()` only raises if `APP_ENV != "development"`. If an operator forgets to set `APP_ENV=production` (or sets it but leaves a secret at the placeholder), the app boots and signs JWTs / encrypts API keys with the literal `"change-me-in-production"` secret, which is public and identical across every install. The `validate_secrets()` method exists but is never called at startup (only `assert_production_ready` is), so the warning path is dead code in the critical path. This is the classic "runs fine, is completely insecure" failure.

**Suggested fix:** Call `validate_secrets()` from `assert_production_ready()` (and log warnings even in development), and consider failing fast on placeholder secrets in any non-test environment, not only strict `production`. At minimum wire `validate_secrets()` into lifespan startup so the warning is surfaced.

---

## 🟢 Nit findings

### 🟢 `alembic/versions/` vs `app/migrations/versions/` — two migration trees, one unused — `backend/alembic.ini:8` + `backend/app/migrations/versions/`

**Why it is minor:** `alembic.ini` sets `script_location = %(here)s/alembic`, so only `backend/alembic/versions/` (148 files) is authoritative. `backend/app/migrations/versions/` (12 legacy files, e.g. `2026_02_01_1200_add_agent_model_preferences.py`) are dead — Alembic never reads them, and they duplicate tables the real tree already creates. They cannot break a running migrate, but they are a foot-gun: a developer running `alembic revision` from the wrong directory, or a future refactor that repoints `script_location`, could either double-apply (idempotent `CREATE TABLE IF NOT EXISTS` aside) or produce a divergent head. Not a runtime error today.

**Suggested fix:** Delete `backend/app/migrations/` (or move it under `tests/`/`archive/`) so there is a single migration source of truth, and add a CI check that `alembic heads` returns exactly one revision.

### 🟢 `compare_type` cosmetic-group includes `BIGINT/INTEGER` as equivalent — `backend/alembic/env.py:53-58`

```python
    _groups = (
        {"TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP WITH TIME ZONE", "DATETIME"},
        {"DOUBLE PRECISION", "FLOAT", "FLOAT8", "DOUBLE"},
        {"BIGINT", "INTEGER", "INT8", "INT4"},   # <-- size-mismatched equivalence
        {"BYTEA", "BLOB"},
    )
```

**Why it is minor:** Treating `BIGINT` (8 bytes) and `INTEGER` (4 bytes) as cosmetically identical hides genuine column-width mismatches between a model and the DB. A model column declared `BigInteger` while the table holds `INTEGER` will silently never be ALTERed, and an `INTEGER` value that overflows can't be stored once the model expects BIGINT — this is a latent data-loss/shaping bug, but only triggers on values > 2^31. The comment in the file documents the trade-off (it was added to surface 14 drift items), so this is a conscious, bounded decision rather than an accident. Flagging for awareness.

**Suggested fix:** Drop `INTEGER`/`INT4` from the BIGINT equivalence group (keep `INT8`/`BIGINT` only) so genuine width mismatches are surfaced, or add a `mypy`-style allowlist for the specific known-equivalent columns.

---

## ✅ Verified CLEAN (no error found)

- **Migration chain integrity:** 148 revisions, exactly **one head** (`20260712_substrate_idem_unique`), 0 broken `down_revision` links, 0 duplicate revision IDs, 0 orphaned nodes (full reachability from head confirmed). All 4 roots (`202605051230`, `eval_001`, `83699f85a14e`, `add_missing_tables_001`) merge into the single head. ✔️
- **SQLAlchemy mappers:** `import app.models; sqlalchemy.orm.configure_mappers()` succeeds with **zero errors** over all 68 models — no ambiguous join conditions, no missing `back_populates`, no recursion, no `Mapped[...]` type mismatches. All `cascade="all, delete-orphan"` relationships are correctly paired with `back_populates` (workspace_models, chat, knowledge_graph, user, etc.). ✔️
- **Async sessions (`app/database.py`):** `create_async_engine` is correctly configured (NullPool not used here — good for a pooled API server; `pool_pre_ping`/`pool_recycle` set). `async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)` is correct. `get_db_session` / `get_db` / `fresh_session` all use `async with AsyncSessionLocal() as session:` and `await session.commit()`/`rollback()` — no missing `await`, no use-after-close, no wrong-event-loop binding. ✔️
- **`h4_6_drop_cancelled_status.py`:** correctly converts `cancelled` → `aborted` rows BEFORE dropping the CHECK constraint (line 28 then 31), so existing rows are preserved. ✔️
- **`fk_type_alignment_001`:** defensively NULLs out non-numeric / non-UUID values before casting (`... !~ '^[0-9]+$'`), and only re-applies NOT NULL when zero NULLs remain — safe data-preserving cast. ✔️
- **Secrets `core/oauth.py` / `core/demo_credentials.py`:** read via `os.getenv(...)` returning `None` when unset (graceful mock-fallback), scoped to sandbox workspaces, not committed. ✔️

---

## VERDICT

- **🔴 Blockers: 1** — `reconcile_schema_001_additions.py:624` uses `DELETE FROM analytics_events WHERE user_id IS NULL` to satisfy a NOT-NULL alter, directly violating the repo's mandated sentinel-UPDATE convention and permanently destroying data (unrecoverable on downgrade).
- **🟡 Suggestions: 2** — (1) non-deterministic `agent_templates` dedup `DELETE` can silently drop user-authored rows; (2) `config.py` placeholder secrets are accepted in any non-`production` env and `validate_secrets()` is never invoked at startup, so a mis-set `APP_ENV` yields silently-insecure JWT/encryption keys.
- **🟢 Nits: 2** — duplicate dead migration tree at `app/migrations/versions/`; and the `compare_type` BIGINT/INTEGER equivalence in `env.py` masks genuine column-width drift.
- **Migration head status:** Contiguous and single-headed — 148 nodes, 1 head (`20260712_substrate_idem_unique`), 0 gaps, 0 duplicates, 0 orphans. The chain itself is healthy.
- **Single highest-risk error:** The `DELETE FROM analytics_events WHERE user_id IS NULL` at `alembic/versions/reconcile_schema_001_additions.py:624`. It is the only migration in the entire tree that deletes real (non-seed, non-config) rows to satisfy a NOT-NULL constraint, it contradicts the project's own written data-mutation rule, and because it is in a migration that has already been applied to production, any attempt to "fix" it must be a *new* compensating migration (re-seed from a backup or use a sentinel), not an edit to the existing file.
