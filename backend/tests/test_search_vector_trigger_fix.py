"""Test the orphaned search_vector trigger fix.

Background
----------
The ``reconcile_schema_001_additions`` migration dropped the
``search_vector`` column (and its GIN index) from ``chat_messages`` but
left behind the BEFORE INSERT/UPDATE trigger ``trg_chat_messages_search_vector``
and its trigger function ``chat_messages_search_update()``, which references
``NEW.search_vector``. Every subsequent INSERT/UPDATE on ``chat_messages``
crashed with::

    asyncpg.exceptions.UndefinedColumnError: record "new" has no field "search_vector"

The fix is in
``backend/alembic/versions/20260627_fix_orphaned_search_vector_trigger.py``.
This test verifies that:

1. The migration file announces the expected revision + down_revision
   (chain integrity — should chain after ``integration_onboarding_flag_001_enable``).
2. The migration file's ``upgrade()`` removes the trigger and function.

These assertions do NOT depend on a live database — they validate the
migration *file* itself. The live-DB verification (running ``alembic upgrade``
and asserting the trigger is gone) is documented in
``.sisyphus/plans/PLAN-fix-search-vector-orphan-trigger.md`` and run as
part of the Phase 6 deploy sequence.

Run via::

    cd /opt/flowmanner && pytest backend/tests/test_search_vector_trigger_fix.py -v
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
MIGRATION_FILE = BACKEND_ROOT / "alembic" / "versions" / "20260627_fix_orphaned_search_vector_trigger.py"
REVISION = "fix_search_vector_trigger_001"
DOWN_REVISION = "integration_onboarding_flag_001_enable"


def _load_migration_module():
    """Import the migration file as a Python module without registering it."""
    spec = importlib.util.spec_from_file_location("fix_search_vector_trigger_001", MIGRATION_FILE)
    if spec is None or spec.loader is None:
        pytest.fail(f"Could not load migration spec from {MIGRATION_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_file_exists() -> None:
    """The migration file must be present at its expected path."""
    assert MIGRATION_FILE.exists(), f"Migration missing: {MIGRATION_FILE}"


def test_migration_chains_after_source_head() -> None:
    """``down_revision`` must point at the current source head so the bug fix
    applies after Phase 6 deploys (and doesn't block the Phase 6 rollout).
    """
    module = _load_migration_module()
    assert module.revision == REVISION, f"Expected revision={REVISION}, got {module.revision!r}"
    assert module.down_revision == DOWN_REVISION, (
        f"Expected down_revision={DOWN_REVISION} (current source head), "
        f"got {module.down_revision!r}. This mismatch will create "
        f"a multi-head Alembic state or block Phase 6 rollout."
    )


def test_upgrade_drops_trigger_and_function() -> None:
    """The upgrade must DROP both the orphaned trigger and the orphaned function.

    Drop order: trigger first, then function. Both reference NEW.search_vector
    which the reconciliation migration removed.
    """
    module = _load_migration_module()
    # Collect the SQL executed by upgrade() by inspecting the source.
    # We don't actually run op.execute (no DB), so parse the function body.
    import inspect

    source = inspect.getsource(module.upgrade)
    assert (
        "DROP TRIGGER IF EXISTS trg_chat_messages_search_vector" in source
    ), "upgrade() must drop the orphaned trigger"
    assert (
        "DROP FUNCTION IF EXISTS chat_messages_search_update()" in source
    ), "upgrade() must drop the orphaned function"
    # Ensure trigger DROP comes before function DROP (drop ordering matters
    # because the function is referenced by the trigger).
    assert source.index("DROP TRIGGER") < source.index(
        "DROP FUNCTION"
    ), "trigger must be dropped before function (function is referenced by trigger)"


@pytest.mark.integration
def test_post_deploy_db_state_has_no_trigger() -> None:
    """Optional integration test: after ``alembic upgrade`` applies the fix,
    ``pg_trigger`` must NOT list ``trg_chat_messages_search_vector`` on
    ``chat_messages``.

    Skips if:
      - docker CLI unavailable
      - workflow-postgres container is not running
      - alembic_version != fix_search_vector_trigger_001 (i.e., the fix has
        not been applied yet in this environment)
    """
    # Check current alembic head
    try:
        head_result = subprocess.run(
            [
                "docker",
                "exec",
                "-T",
                "workflow-postgres",
                "psql",
                "-U",
                "flowmanner",
                "-t",
                "-A",
                "-c",
                "SELECT version_num FROM alembic_version;",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        pytest.skip("docker CLI not available")

    if head_result.returncode != 0:
        pytest.skip(f"psql failed: {head_result.stderr}")

    head = head_result.stdout.strip()
    if head != REVISION:
        pytest.skip(
            f"DB alembic head is {head!r}; "
            f"fix migration applies when chain extends to {REVISION!r}. "
            f"This test runs in environments where the fix is already applied."
        )

    # Verify trigger is gone
    trigger_result = subprocess.run(
        [
            "docker",
            "exec",
            "-T",
            "workflow-postgres",
            "psql",
            "-U",
            "flowmanner",
            "-t",
            "-A",
            "-c",
            (
                "SELECT tgname FROM pg_trigger "
                "WHERE tgrelid = 'chat_messages'::regclass "
                "AND tgname = 'trg_chat_messages_search_vector';"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert trigger_result.returncode == 0, trigger_result.stderr
    assert not trigger_result.stdout.strip(), f"Orphaned trigger still present: {trigger_result.stdout!r}"


@pytest.mark.integration
def test_post_deploy_db_state_has_no_function() -> None:
    """Optional integration test: after the fix, ``pg_proc`` must NOT list
    ``chat_messages_search_update``.

    Skips if the fix hasn\u0027t been applied to this DB yet (same conditions
    as ``test_post_deploy_db_state_has_no_trigger``).
    """
    try:
        head_result = subprocess.run(
            [
                "docker",
                "exec",
                "-T",
                "workflow-postgres",
                "psql",
                "-U",
                "flowmanner",
                "-t",
                "-A",
                "-c",
                "SELECT version_num FROM alembic_version;",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        pytest.skip("docker CLI not available")

    if head_result.returncode != 0:
        pytest.skip(f"psql failed: {head_result.stderr}")

    head = head_result.stdout.strip()
    if head != REVISION:
        pytest.skip(f"DB alembic head is {head!r}; fix migration not yet applied.")

    func_result = subprocess.run(
        [
            "docker",
            "exec",
            "-T",
            "workflow-postgres",
            "psql",
            "-U",
            "flowmanner",
            "-t",
            "-A",
            "-c",
            "SELECT proname FROM pg_proc WHERE proname = 'chat_messages_search_update';",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert func_result.returncode == 0, func_result.stderr
    assert not func_result.stdout.strip(), f"Orphaned function still present: {func_result.stdout!r}"
