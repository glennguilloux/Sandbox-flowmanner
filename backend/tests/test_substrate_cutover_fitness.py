"""ADR-002 (v1 → substrate cutover) — architectural fitness functions.

The card asked for "parity/regression tests that would catch behavior change."
Ground truth (verified 2026-07-17): there is now exactly ONE execution engine —
the substrate ``UnifiedExecutor``. All 7 legacy executors were deleted and the
``FLOWMANNER_UNIFIED_EXECUTOR`` flag is vestigial (read by no source module).

Literal A/B parity between two live engines is therefore not buildable. Instead
these fitness functions protect the *invariant* the parity test was meant to
defend: **one engine, dead flag, no resurrected legacy executors.** They fail
loudly if a future change re-imports an old executor or re-wires the flag into a
code path.

Pure static tests — no DB, no app boot.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# The 7 legacy executor modules deleted during the H5.1 collapse (commit
# e6d6d19b et al.). Re-introducing any of them is a cutover regression.
DELETED_EXECUTOR_MODULES = [
    "app.services.mission_executor",
    "app.services.graph_executor",
    "app.services.dag_executor",
    "app.services.swarm.orchestrator",
    "app.services.swarm_pipeline.orchestrator",
    "app.services.langgraph.agent",
    "app.services.nexus.meta_loop_orchestrator",
]

# Repo layout: this file lives at backend/tests/, so backend/app is ../app.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_APP_DIR = _BACKEND_ROOT / "app"


class TestLegacyExecutorsStayDeleted:
    @pytest.mark.parametrize("module_name", DELETED_EXECUTOR_MODULES)
    def test_legacy_executor_module_is_unimportable(self, module_name):
        """Each deleted legacy executor must remain unimportable.

        If someone re-adds one of these files, this test fails — a signal that
        the single-engine invariant has been violated.
        """
        with pytest.raises((ModuleNotFoundError, ImportError)):
            importlib.import_module(module_name)

    @pytest.mark.parametrize("module_name", DELETED_EXECUTOR_MODULES)
    def test_legacy_executor_file_is_absent_on_disk(self, module_name):
        rel = module_name.removeprefix("app.").replace(".", "/") + ".py"
        assert not (_APP_DIR / rel).exists(), f"{rel} was deleted in the cutover; it must not return"


class TestUnifiedExecutorFlagIsDead:
    def test_no_source_module_reads_the_flag(self):
        """No Python source under app/ (excluding tests) may read
        FLOWMANNER_UNIFIED_EXECUTOR.

        The flag is documentation-only now. Reading it in code would resurrect a
        dead gate and reintroduce the branching the cutover removed.
        """
        offenders: list[str] = []
        for py in _APP_DIR.rglob("*.py"):
            # Skip test files if any live under app/ (canonical tests are in backend/tests/).
            if "tests" in py.parts:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "FLOWMANNER_UNIFIED_EXECUTOR" in text:
                # Two files are allowed to name the var — they ARE the guard:
                #   - app/config.py: the env-var NAME constant + warning method.
                #   - app/lifespan.py: the boot-time call site that logs the warning.
                # Both only reference the var to WARN about it; neither branches
                # execution on it. Anything else is a cutover regression.
                rel = py.relative_to(_APP_DIR)
                if str(rel) in ("config.py", "lifespan.py"):
                    continue
                offenders.append(str(py.relative_to(_BACKEND_ROOT)))
        assert not offenders, (
            "FLOWMANNER_UNIFIED_EXECUTOR is vestigial (ADR-002) and must not be read "
            f"by source code. Offending files: {offenders}"
        )


class TestSingleExecutionEntryPoint:
    def test_get_unified_executor_is_the_exported_entry_point(self):
        """The substrate package must still export the single execution entry
        point. If this import breaks, the sole engine's public surface regressed.
        """
        from app.services import substrate
        from app.services.substrate.executor import get_unified_executor

        assert hasattr(substrate, "UnifiedExecutor")
        assert callable(get_unified_executor)
