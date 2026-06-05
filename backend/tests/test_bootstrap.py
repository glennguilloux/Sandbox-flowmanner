"""Tests for Phase 3.4: Deterministic bootstrap command.

Verifies the bootstrap module's structure, step functions, and report logic.

Usage (inside container):
    pytest /app/tests/test_bootstrap.py -v
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBootstrapReport:
    """Test the BootstrapReport dataclass."""

    def test_report_all_ok_when_all_ok(self):
        from app.cli.bootstrap import BootstrapReport, StepResult, StepStatus
        report = BootstrapReport(steps=[
            StepResult(name="step1", status=StepStatus.OK),
            StepResult(name="step2", status=StepStatus.SKIPPED),
        ])
        assert report.all_ok is True

    def test_report_not_ok_when_failed(self):
        from app.cli.bootstrap import BootstrapReport, StepResult, StepStatus
        report = BootstrapReport(steps=[
            StepResult(name="step1", status=StepStatus.OK),
            StepResult(name="step2", status=StepStatus.FAILED),
        ])
        assert report.all_ok is False

    def test_report_summary_contains_steps(self):
        from app.cli.bootstrap import BootstrapReport, StepResult, StepStatus
        report = BootstrapReport(steps=[
            StepResult(name="DB check", status=StepStatus.OK, message="connected", duration_ms=5.0),
        ], total_duration_ms=10.0)
        summary = report.summary()
        assert "DB check" in summary
        assert "ok" in summary
        assert "connected" in summary
        assert "ALL OK" in summary

    def test_report_summary_shows_failures(self):
        from app.cli.bootstrap import BootstrapReport, StepResult, StepStatus
        report = BootstrapReport(steps=[
            StepResult(name="failing step", status=StepStatus.FAILED, message="boom", duration_ms=1.0),
        ], total_duration_ms=1.0)
        summary = report.summary()
        assert "FAILURES DETECTED" in summary


class TestStepStatus:
    """Test StepStatus enum values."""

    def test_status_values(self):
        from app.cli.bootstrap import StepStatus
        assert StepStatus.PENDING == "pending"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.OK == "ok"
        assert StepStatus.SKIPPED == "skipped"
        assert StepStatus.FAILED == "failed"


class TestStepResult:
    """Test StepResult dataclass."""

    def test_default_status(self):
        from app.cli.bootstrap import StepResult, StepStatus
        r = StepResult(name="test")
        assert r.status == StepStatus.PENDING
        assert r.message == ""
        assert r.duration_ms == 0.0


class TestBootstrapDryRun:
    """Test dry-run mode."""

    @pytest.mark.asyncio
    async def test_dry_run_skips_all_steps(self):
        from app.cli.bootstrap import bootstrap, StepStatus
        report = await bootstrap(dry_run=True)
        assert report.all_ok is True
        for step in report.steps:
            assert step.status == StepStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_dry_run_has_all_steps(self):
        from app.cli.bootstrap import bootstrap
        report = await bootstrap(dry_run=True)
        step_names = [s.name for s in report.steps]
        assert len(step_names) == 9, f"Expected 9 steps, got {len(step_names)}: {step_names}"
        assert any("DB" in n for n in step_names)
        assert any("migration" in n.lower() for n in step_names)
        assert any("tool" in n.lower() for n in step_names)
        assert any("capabilit" in n.lower() for n in step_names), f"Missing capability step: {step_names}"
        assert any("topology" in n.lower() for n in step_names)
        assert any("qdrant" in n.lower() for n in step_names)
        assert any("health" in n.lower() for n in step_names)


class TestBootstrapSkips:
    """Test skip flags."""

    @pytest.mark.asyncio
    async def test_skip_migrations(self):
        from app.cli.bootstrap import bootstrap, StepStatus
        report = await bootstrap(skip_migrations=True, dry_run=True)
        migration_step = next(s for s in report.steps if "migration" in s.name.lower())
        assert migration_step.status == StepStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_skip_qdrant(self):
        from app.cli.bootstrap import bootstrap, StepStatus
        report = await bootstrap(skip_qdrant=True, dry_run=True)
        qdrant_step = next(s for s in report.steps if "qdrant" in s.name.lower())
        assert qdrant_step.status == StepStatus.SKIPPED


class TestBootstrapModuleStructure:
    """Verify the bootstrap module is importable and has expected symbols."""

    def test_bootstrap_importable(self):
        from app.cli import bootstrap
        assert hasattr(bootstrap, "bootstrap")
        assert hasattr(bootstrap, "main")
        assert callable(bootstrap.bootstrap)
        assert callable(bootstrap.main)

    def test_main_is_callable(self):
        from app.cli.bootstrap import main
        assert callable(main)

    def test_step_functions_exist(self):
        from app.cli import bootstrap
        expected = [
            "_step_verify_db",
            "_step_migrations",
            "_step_seed_agent_templates",
            "_step_import_tools",
            "_step_import_capabilities",
            "_step_import_bindings",
            "_step_seed_topology",
            "_step_rebuild_qdrant",
            "_step_verify_health",
        ]
        for fn_name in expected:
            assert hasattr(bootstrap, fn_name), f"Missing: {fn_name}"
            assert callable(getattr(bootstrap, fn_name))


class TestBootstrapMainModule:
    """Verify python -m app.cli.bootstrap entry point."""

    def test_main_module_exists(self):
        """The __main__.py should import and call main."""
        from pathlib import Path
        main_path = Path(__file__).parent.parent / "app" / "cli" / "__main__.py"
        assert main_path.exists()
        content = main_path.read_text()
        assert "from app.cli.bootstrap import main" in content
        assert "main()" in content
