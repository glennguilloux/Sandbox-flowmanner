"""Unit tests for ``backend/scripts/regression_watchdog.py``.

These tests exercise the watchdog without a live database by injecting mock
``BaselineExtractor`` / ``ReplayAssertionEngine`` instances and fake database
sessions. Webhook POSTs are also mocked so no network calls are made.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.substrate.assertion_engine import AssertionResult, Severity
from scripts.regression_watchdog import (
    _check_run,
    _extract_baseline,
    _send_alert,
    _validate_args,
)


def _make_fake_extractor(*, cost: float = 0.05, duration: int = 2) -> AsyncMock:
    """Return a mock BaselineExtractor that returns deterministic behaviors."""
    extractor = AsyncMock()
    extractor.extract_from_run.return_value = [
        {
            "type": "cost_ceiling",
            "max_cost_usd": round(cost * 1.15, 4),
            "warn_at_pct": 80,
        },
        {
            "type": "latency",
            "max_duration_seconds": int(duration * 1.5),
            "warn_at_pct": 80,
        },
        {"type": "task_completion", "min_tasks_completed": 1, "max_tasks_failed": 0},
    ]
    return extractor


def _make_fake_engine(*, actual_cost: float, actual_latency: float) -> AsyncMock:
    """Return a mock ReplayAssertionEngine returning cost/latency results."""
    engine = AsyncMock()
    engine.evaluate.return_value = [
        AssertionResult(
            assertion_type="cost_ceiling",
            passed=True,
            severity=Severity.INFO,
            actual={"cost_usd": actual_cost, "pct_used": 50.0},
            expected={"max_cost_usd": actual_cost * 2, "warn_at_pct": 80},
            message="cost ok",
        ),
        AssertionResult(
            assertion_type="latency",
            passed=True,
            severity=Severity.INFO,
            actual={"duration_seconds": actual_latency, "pct_used": 50.0},
            expected={"max_duration_seconds": actual_latency * 2, "warn_at_pct": 80},
            message="latency ok",
        ),
        AssertionResult(
            assertion_type="task_completion",
            passed=True,
            severity=Severity.INFO,
            actual={"completed": 1, "failed": 0},
            expected={"min_tasks_completed": 1, "max_tasks_failed": 0},
            message="1 tasks completed, 0 failed",
        ),
    ]
    return engine


def _write_baseline_file(
    *,
    raw_cost: float = 0.05,
    raw_latency: float = 2.0,
    include_meta: bool = True,
) -> str:
    """Write a baseline JSON file and return its path."""
    doc: dict[str, Any] = {
        "expected_behaviors": [
            {"type": "cost_ceiling", "max_cost_usd": 0.0575, "warn_at_pct": 80},
            {"type": "latency", "max_duration_seconds": 3, "warn_at_pct": 80},
        ]
    }
    if include_meta:
        doc["meta"] = {
            "run_id": "run-known-good",
            "extracted_at": datetime.now(UTC).isoformat(),
            "cost_headroom": 1.15,
            "latency_headroom": 1.5,
            "raw_cost_usd": raw_cost,
            "raw_duration_seconds": raw_latency,
        }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
        return f.name


@pytest.mark.asyncio
async def test_extract_baseline_returns_doc_with_raw_metrics() -> None:
    """Extraction builds expected_behaviors plus raw metric metadata."""
    fake_db = MagicMock()
    extractor = _make_fake_extractor(cost=0.05, duration=2)

    doc = await _extract_baseline(
        "run-known-good",
        cost_headroom=1.15,
        latency_headroom=1.5,
        _db=fake_db,
        _extractor=extractor,
    )

    assert "expected_behaviors" in doc
    assert "meta" in doc
    assert doc["meta"]["run_id"] == "run-known-good"
    # 0.05 * 1.15 = 0.0575, reversed gives 0.05
    assert doc["meta"]["raw_cost_usd"] == pytest.approx(0.05, abs=1e-6)
    assert doc["meta"]["raw_duration_seconds"] == pytest.approx(2.0, abs=1e-3)


@pytest.mark.asyncio
async def test_check_run_passes_when_within_bounds() -> None:
    """No drift when actual cost/latency are below the 1.5x/2x thresholds."""
    baseline_path = _write_baseline_file(raw_cost=0.05, raw_latency=2.0)
    fake_db = MagicMock()
    # actuals well within 1.5x cost (0.075) and 2x latency (4s)
    engine = _make_fake_engine(actual_cost=0.06, actual_latency=3.0)

    summary = await _check_run(
        "run-new",
        baseline_path,
        _db=fake_db,
        _engine=engine,
    )

    assert summary["drift"] is False
    assert summary["cost_drift"] is False
    assert summary["latency_drift"] is False
    assert summary["actual_cost"] == 0.06
    assert summary["actual_latency"] == 3.0


@pytest.mark.asyncio
async def test_check_run_drifts_on_cost() -> None:
    """Drift is reported when actual cost exceeds 1.5× the baseline."""
    baseline_path = _write_baseline_file(raw_cost=0.05, raw_latency=2.0)
    fake_db = MagicMock()
    # 0.10 > 0.05 * 1.5 => drift
    engine = _make_fake_engine(actual_cost=0.10, actual_latency=3.0)

    summary = await _check_run(
        "run-expensive",
        baseline_path,
        _db=fake_db,
        _engine=engine,
    )

    assert summary["drift"] is True
    assert summary["cost_drift"] is True
    assert summary["latency_drift"] is False


@pytest.mark.asyncio
async def test_check_run_drifts_on_latency() -> None:
    """Drift is reported when actual latency exceeds 2× the baseline."""
    baseline_path = _write_baseline_file(raw_cost=0.05, raw_latency=2.0)
    fake_db = MagicMock()
    # 5.0 > 2.0 * 2 => drift
    engine = _make_fake_engine(actual_cost=0.06, actual_latency=5.0)

    summary = await _check_run(
        "run-slow",
        baseline_path,
        _db=fake_db,
        _engine=engine,
    )

    assert summary["drift"] is True
    assert summary["cost_drift"] is False
    assert summary["latency_drift"] is True


@pytest.mark.asyncio
async def test_check_run_uses_ceiling_fallback_when_meta_missing() -> None:
    """If the baseline file has no meta block, thresholds fall back to ceilings."""
    baseline_path = _write_baseline_file(include_meta=False)
    fake_db = MagicMock()
    # max_cost_usd=0.0575 * 1.5 = 0.08625; 0.09 exceeds it
    engine = _make_fake_engine(actual_cost=0.09, actual_latency=2.0)

    summary = await _check_run(
        "run-no-meta",
        baseline_path,
        _db=fake_db,
        _engine=engine,
    )

    assert summary["drift"] is True
    assert summary["cost_drift"] is True


@pytest.mark.asyncio
async def test_check_run_fails_on_assertion_failure() -> None:
    """Any failing baseline assertion counts as drift."""
    baseline_path = _write_baseline_file()
    fake_db = MagicMock()
    engine = _make_fake_engine(actual_cost=0.06, actual_latency=3.0)
    # Force one assertion to fail (cost ceiling).
    engine.evaluate.return_value[0].passed = False
    engine.evaluate.return_value[0].severity = Severity.FAILURE
    engine.evaluate.return_value[0].message = "cost exceeded"

    summary = await _check_run(
        "run-assert-fail",
        baseline_path,
        _db=fake_db,
        _engine=engine,
    )

    assert summary["drift"] is True
    assert len(summary["assertion_failures"]) == 1


def test_validate_args_rejects_extract_and_check() -> None:
    """--extract and --check cannot be used together."""
    import argparse

    from argparse import Namespace

    args = Namespace(extract_run_id="run-1", check_run_id="run-2", baseline_path="/tmp/x.json")
    with pytest.raises(argparse.ArgumentError):
        _validate_args(args)


@pytest.mark.asyncio
async def test_send_alert_dry_run_prints_to_stderr(capsys: pytest.CaptureFixture) -> None:
    """In dry-run mode the alert is printed to stderr, not POSTed."""
    payload = {"status": "DRIFT", "run_id": "r"}
    await _send_alert(payload, dry_run=True)
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.err
    assert "DRIFT" in captured.err


@pytest.mark.asyncio
async def test_send_alert_posts_to_webhook() -> None:
    """When REGRESSION_WEBHOOK_URL is set, the alert is POSTed via httpx."""
    payload = {"status": "DRIFT", "run_id": "r"}
    with patch.dict(os.environ, {"REGRESSION_WEBHOOK_URL": "https://example.com/hook"}):
        with patch("scripts.regression_watchdog.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await _send_alert(payload, dry_run=False)

            mock_client.post.assert_awaited_once()
