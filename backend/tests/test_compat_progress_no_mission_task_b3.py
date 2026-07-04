"""Phase 3.5 cutover — B3 regression tests.

B3: ``backend/app/api/_mission_cqrs/compat.py::active_missions_from_blueprints``
computes progress/ETA by querying ``MissionTask`` from the OLD missions
schema (line 241-253 of compat.py as of the plan creation date).

After ``phase103_drop_old_tables`` runs, the ``mission_tasks`` table
no longer exists, so this code will raise ``UndefinedTableError`` on
every request when ``USE_NEW_READS=1`` is enabled in production.

FIX (per ``plans/blueprint-run-phase3.5-cutover-plan.md`` §0 row B3,
option B3-A): derive progress from ``substrate_events`` for the run,
counting ``TASK_COMPLETED`` events vs the node count in
``blueprint.definition.nodes``. This decouples from ``mission_tasks``
without losing data fidelity because substrate events are already the
canonical audit source.

These tests MUST FAIL on the current code.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
COMPAT = BACKEND_ROOT / "app" / "api" / "_mission_cqrs" / "compat.py"


def _extract_active_missions_from_blueprints_body() -> str:
    """Return the source for ``async def active_missions_from_blueprints``
    (start through the next ``async def`` or end of file).
    """
    src = COMPAT.read_text()
    pattern = re.compile(r"^async def active_missions_from_blueprints\b", re.M)
    match = pattern.search(src)
    assert match, "active_missions_from_blueprints not found in compat.py"
    start = match.start()
    rest = src[start + 1 :]
    next_def = re.search(r"^async def \w+\b|^def \w+\b|^class \w+\b", rest, re.M)
    end = start + 1 + (next_def.start() if next_def else len(rest))
    return src[start:end]


class TestActiveMissionsReadsNoMissionTask:
    """Test-first regression for B3."""

    def test_active_missions_from_blueprints_does_not_import_mission_task(self):
        """FIX: ``active_missions_from_blueprints`` must NOT import
        ``MissionTask`` from the legacy missions schema. Progress/ETA
        must derive from ``substrate_events`` so the function survives
        ``phase103_drop_old_tables``.
        """
        body = _extract_active_missions_from_blueprints_body()
        assert "MissionTask" not in body, (
            "B3 FIX MISSING: active_missions_from_blueprints still references "
            "MissionTask. Phase 103 drops mission_tasks, so this code will "
            "crash with UndefinedTableError once phase103 is applied. "
            "Compute progress from substrate_events instead."
        )

    def test_active_missions_from_blueprints_uses_substrate_events_for_progress(self):
        """FIX: must query ``substrate_events`` to compute progress.

        Per the plan (option B3-A), the progress value must be derived from
        substrate event counts, NOT hardcoded. Tightening: a fix that
        returns ``progress=0`` unconditionally (e.g., the B3-C
        "temporarily return 0/None" deferral) would still pass the
        earlier "no MissionTask import" test but is NOT the intended fix.
        Therefore this test asserts an event-driven computation.
        """
        body = _extract_active_missions_from_blueprints_body()
        # Must import or use substrate event symbols.
        uses_substrate = "substrate_events" in body or "SubstrateEvent" in body or "SubstrateEventType" in body
        assert uses_substrate, (
            "B3 FIX MISSING: active_missions_from_blueprints must read "
            "substrate_events to compute progress/ETA. (Option B3-C in the "
            "plan — return progress=0 — does NOT satisfy this invariant.)"
        )
        # Must NOT have a fallback that discards progress entirely. Tightened
        # to require substrate_events-specific aggregation, so a fix that
        # just renames a function containing "count" without actually
        # counting substrate events still fails. This rejects the B3-C
        # "return progress=0" deferral.
        # Tolerant to refactors: ``select(func.count()).select_from(...)``
        # OR ``func.count(...)`` OR ``func.sum(case(...))``.
        substrate_aggregation_present = re.search(r"substrate_events", body) is not None and (
            re.search(r"func\.count\s*\(", body, re.S) is not None
            or re.search(r"\bsum\s*\(.*substrate_events", body, re.S) is not None
            or re.search(r"count\s*\(.*substrate_events", body, re.S) is not None
            or re.search(r"select_from\s*\(\s*SubstrateEvent", body, re.S) is not None
            or re.search(r"select_from\s*\(\s*\w+\)\.select_from\s*\(\s*[Ss]ubstrate", body, re.S) is not None
        )
        assert substrate_aggregation_present, (
            "B3 FIX MISSING: progress must aggregate substrate_events "
            "(e.g. func.count(SubstrateEvent) filtered by TASK_COMPLETED). "
            "The B3-C deferral ('return progress=0') does NOT satisfy this."
        )
