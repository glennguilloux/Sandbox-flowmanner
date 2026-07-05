"""Phase 3.5 cutover — B6 regression tests.

B6 (new): ``commands.py::_dual_write_blueprint`` must create blueprints with
``Blueprint.id = str(mission.id)`` so that the dual-write linkage is
1-to-1 and deterministic.  Creating blueprints with fresh ``uuid4()`` IDs
and only storing the mission ID in ``definition['_source_mission_id']``
produces a second parallel ID space and prevents the backfill idempotency
guard from working.

FIX: pass ``blueprint_id=str(result.id)`` to ``BlueprintService.create``
from the dual-write path.

These tests should fail before the fix and pass after it.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# parents[1] = backend/ dir on homelab, /app in Docker.
# Both layouts place app/ directly under this root.
COMMANDS_FILE = REPO_ROOT / "app" / "api" / "_mission_cqrs" / "commands.py"
BLUEPRINT_SERVICE_FILE = REPO_ROOT / "app" / "services" / "blueprint_service.py"


def _read_commands_dual_write_block() -> str:
    src = COMMANDS_FILE.read_text()
    start = src.index("async def _dual_write_blueprint")
    end = src.find("_schedule_fire_and_forget(_dual_write_blueprint)", start)
    return src[start:end]


def _read_blueprint_service_create() -> str:
    src = BLUEPRINT_SERVICE_FILE.read_text()
    start = src.index("async def create(")
    end = src.index("async def get(", start)
    return src[start:end]


class TestDualWriteDeterministicId:
    """Test-first regression for B6."""

    def test_dual_write_passes_mission_id_as_blueprint_id(self):
        """FIX: _dual_write_blueprint must pass ``blueprint_id=str(result.id)``.

        Without this, every mission gets a blueprint with a random UUID,
        breaking the 1-to-1 deterministic linkage the cutover plan requires.
        """
        block = _read_commands_dual_write_block()
        assert "blueprint_id=str(result.id)" in block, (
            "B6 FIX MISSING: _dual_write_blueprint must pass "
            "blueprint_id=str(result.id) to BlueprintService.create. "
            "See plans/blueprint-run-phase3.5-cutover-plan.md §0 row B1/B6."
        )

    def test_blueprint_service_create_accepts_optional_id(self):
        """FIX: BlueprintService.create must accept an optional ``blueprint_id``."""
        block = _read_blueprint_service_create()
        assert "blueprint_id: str | None = None" in block, (
            "B6 FIX MISSING: BlueprintService.create must accept an optional "
            "blueprint_id parameter so the dual-write path can pass the "
            "deterministic mission ID."
        )

    def test_blueprint_service_uses_passed_id(self):
        """FIX: BlueprintService.create must use ``blueprint_id`` when provided."""
        block = _read_blueprint_service_create()
        assert "id=blueprint_id if blueprint_id is not None else str(uuid4())" in block, (
            "B6 FIX MISSING: BlueprintService.create must use the provided "
            "blueprint_id, falling back to uuid4() only when omitted."
        )
