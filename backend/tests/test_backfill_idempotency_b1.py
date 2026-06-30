"""Phase 3.5 cutover — B1 regression tests.

B1: ``scripts/backfill_blueprints_runs.backfill_blueprints`` generates
``Blueprint.id = str(uuid4())`` on every run, so re-running backfill
creates DUPLICATE blueprints for every mission (one per run).

FIX (documented in
``plans/blueprint-run-phase3.5-cutover-plan.md`` §0 table row B1):
Set ``Blueprint.id = str(mission.id)`` AND write the corresponding
``_source_mission_id`` into ``Blueprint.definition``. Then ``Mission.id
NOT IN (Blueprint.id)`` correctly excludes already-backfilled missions.
The script becomes idempotent.

These tests MUST FAIL on the current code. They are the test-first
discipline from chunk 4 — written BEFORE the fix lands.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# parents[1] = backend/ dir on homelab, /app in Docker.
# Both layouts place scripts/ directly under this root.
BACKFILL_SCRIPT = REPO_ROOT / "scripts" / "backfill_blueprints_runs.py"


def _read_backfill_blueprints_body() -> str:
    """Return the source for ``async def backfill_blueprints`` (until backfill_runs or end)."""
    src = BACKFILL_SCRIPT.read_text()
    start = src.index("async def backfill_blueprints")
    end_marker = src.find("async def backfill_runs", start)
    end = end_marker if end_marker > 0 else len(src)
    return src[start:end]


class TestBackfillIdempotency:
    """Test-first regression for B1."""

    def test_backfill_uses_mission_id_as_blueprint_id(self):
        """FIX: Blueprint.id must equal str(mission.id), not a fresh uuid4().

        Without this, ``Mission.id NOT IN (SELECT id FROM blueprints)``
        never matches (Blueprint ids are random UUIDs that don't intersect
        with Mission ids), so re-running backfill duplicates every row.

        Current code: ``Blueprint(id=str(uuid4()), ...)`` -> DUPLICATES.
        Fixed code:  ``Blueprint(id=str(mission.id), ...)`` -> IDEMPOTENT.

        Uses a regex (not a literal string) so the test tolerates benign
        reformatting (different indentation, single-line vs multi-line
        Blueprint() constructor).
        """
        body = _read_backfill_blueprints_body()
        pattern = re.compile(
            r"Blueprint\s*\(\s*\n?\s*id\s*=\s*str\s*\(\s*mission\.id\s*\)",
            re.MULTILINE,
        )
        assert pattern.search(body), (
            "B1 FIX MISSING: backfill_blueprints must set id=str(mission.id), "
            "not str(uuid4()). See plans/blueprint-run-phase3.5-cutover-plan.md §0 row B1."
        )

    def test_backfill_writes_source_mission_id_into_definition(self):
        """FIX: ``Blueprint.definition`` must carry ``_source_mission_id``
        whose value is ``str(mission.id)``, not a placeholder.

        A fix that writes ``"_source_mission_id": str(mission.id)`` passes.
        A fix that writes ``"_source_mission_id": None`` (lazy placeholder)
        or omits the key entirely fails. Required for
        ``compat._find_blueprint`` fallback lookup AND for the
        consistency-check script (``verify_backfill_consistency.py``).
        """
        body = _read_backfill_blueprints_body()
        # Both forms are valid Python literals. Match the value being
        # ``str(mission.id)`` rather than a hardcoded string.
        key_pattern = re.compile(r"""(['"]_source_mission_id['"]\s*:\s*)str\s*\(\s*mission\.id\s*\)""")
        assert key_pattern.search(body), (
            "B1 FIX MISSING: backfill_blueprints must write the source "
            "mission id into Blueprint.definition['_source_mission_id'] as "
            "str(mission.id), not as None or a static placeholder."
        )

    def test_backfill_does_not_generate_fresh_uuid_for_blueprint_id(self):
        """Anti-regression guard: ``id=str(uuid4())`` MUST NOT appear near
        the ``Blueprint(...)`` call in backfill_blueprints. Catches the
        bug pattern (``Blueprisnt.id`` derived from uuid4) directly so a
        future refactor cannot reintroduce non-idempotent id assignment.

        Scoped to the exact bug pattern ``id=str(uuid4())`` rather than
        bare ``uuid4()`` because ``BlueprintVersion(...)`` (later in the
        same function body) legitimately keeps uuid4() for its own new
        row — uniqueness is desired there because each backfilled
        blueprint creates exactly one BlueprintVersion.
        """
        body = _read_backfill_blueprints_body()
        bp_idx = body.find("Blueprint(")
        if bp_idx < 0:
            return  # No Blueprint() call found; structural fix — accept
        blob = body[bp_idx : bp_idx + 500]
        # Match ONLY the bug pattern `id=str(uuid4())` — not other uuid4()
        # calls (BlueprintVersion's own id, comment text, etc.).
        bug_pattern = re.compile(r"id\s*=\s*str\s*\(\s*uuid4\s*\(\s*\)\s*\)")
        assert not bug_pattern.search(blob), (
            "B1 BUG STILL PRESENT: a `id=str(uuid4())` pattern is near the "
            "Blueprint(...) call in backfill_blueprints. This makes every "
            "backfill run produce new UUIDs for the Blueprint, breaking "
            "idempotency. Fix: set Blueprint.id = str(mission.id). "
            "(BlueprintVersion may legitimately keep UUID4() — it is a "
            "new row per Blueprint, not a duplication concern.)"
        )
