"""Phase 3.5 cutover — B2 regression tests.

B2: ``backend/alembic/versions/20260609_phase104_retarget_aux_tables.py``
contains a retarget block for ``mission_improvements``. But
``20260609_phase103_drop_old_tables.py`` DROPS ``mission_improvements``
during its `upgrade()`. The ``_table_exists`` guard in phase104 prevents
the migration from erroring — but the retarget is silently a no-op.

FIX (per ``plans/blueprint-run-phase3.5-cutover-plan.md`` §0 row B2):
REMOVE the entire ``mission_improvements`` retarget block. The audit table
loses its FK but the substrate event log remains the canonical trace.

These tests MUST FAIL on the current code.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE104 = REPO_ROOT / "backend" / "alembic" / "versions" / "20260609_phase104_retarget_aux_tables.py"


class TestPhase104ExcludesDroppedMissionImprovements:
    """Test-first regression for B2."""

    def test_phase104_does_not_reference_mission_improvements_at_all(self):
        """FIX: ``mission_improvements`` must NOT appear anywhere in phase104.

        Phase 103 drops that table during its upgrade, so any reference in
        phase104 is dead code (silently no-op via ``_table_exists`` guard).
        The docstring, source code, and any conditional check must all drop
        this reference after the fix.
        """
        src = PHASE104.read_text()
        assert "mission_improvements" not in src, (
            "B2 FIX MISSING: phase104 still references mission_improvements "
            "(in code or docstring). phase103_drop_old_tables DROPped that "
            "table; the retarget block is dead code. Remove the entire "
            "'_table_exists(\"mission_improvements\")' block per "
            "plans/blueprint-run-phase3.5-cutover-plan.md §0 row B2."
        )
