"""Unit tests for the flowmanner CLI entry point.

Tests call main(argv=...) directly with mocked FlowmannerClient to avoid real HTTP.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from flowmanner_api_client.cli import main


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure env vars don't leak between tests."""
    monkeypatch.delenv("FLOWMANNER_API_KEY", raising=False)
    monkeypatch.delenv("FLOWMANNER_URL", raising=False)


@pytest.fixture
def mock_fm():
    """Patch FlowmannerClient so no real HTTP is made."""
    with patch("flowmanner_api_client.high_level.FlowmannerClient") as MockClient:
        instance = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        yield instance


# ── No command / help ───────────────────────────────────────────────────────


class TestNoCommand:
    def test_no_command_returns_zero(self, capsys):
        result = main(argv=[])
        assert result == 0

    def test_no_command_prints_help(self, capsys):
        main(argv=[])
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "flowmanner" in captured.out.lower()


# ── Missing key ─────────────────────────────────────────────────────────────


class TestMissingKey:
    def test_status_without_key_returns_one(self, capsys):
        result = main(argv=["status"])
        assert result == 1

    def test_status_without_key_prints_error(self, capsys):
        main(argv=["status"])
        captured = capsys.readouterr()
        assert "API_KEY" in captured.err

    def test_missions_without_key_returns_one(self, capsys):
        result = main(argv=["missions"])
        assert result == 1

    def test_costs_without_key_returns_one(self, capsys):
        result = main(argv=["costs"])
        assert result == 1


# ── Status command ──────────────────────────────────────────────────────────


class TestStatusCommand:
    def test_status_success(self, capsys, mock_fm):
        mock_fm.health_check.return_value = {"status": "healthy"}
        result = main(argv=["--key", "sk-test", "status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Connected to https://flowmanner.com" in captured.out
        assert "Status: healthy" in captured.out

    def test_status_custom_url(self, capsys, mock_fm):
        mock_fm.health_check.return_value = {"status": "ok"}
        result = main(
            argv=["--url", "http://localhost:8000", "--key", "sk-test", "status"]
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Connected to http://localhost:8000" in captured.out

    def test_status_missing_status_key(self, capsys, mock_fm):
        mock_fm.health_check.return_value = {}
        result = main(argv=["--key", "sk-test", "status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Status: unknown" in captured.out

    def test_status_api_error(self, capsys, mock_fm):
        mock_fm.health_check.side_effect = Exception("Connection refused")
        result = main(argv=["--key", "sk-test", "status"])
        assert result == 1
        captured = capsys.readouterr()
        assert "Connection refused" in captured.err


# ── Missions command ────────────────────────────────────────────────────────


class TestMissionsCommand:
    def test_missions_lists_items(self, capsys, mock_fm):
        mock_fm.list_missions.return_value = [
            {"id": "abc-1234-5678", "status": "completed", "title": "Research Task"},
            {"id": "def-9012-3456", "status": "running", "title": "Code Review"},
        ]
        result = main(argv=["--key", "sk-test", "missions"])
        assert result == 0
        captured = capsys.readouterr()
        assert "abc-1234" in captured.out
        assert "completed" in captured.out
        assert "Research Task" in captured.out
        assert "def-9012" in captured.out

    def test_missions_empty(self, capsys, mock_fm):
        mock_fm.list_missions.return_value = []
        result = main(argv=["--key", "sk-test", "missions"])
        assert result == 0
        captured = capsys.readouterr()
        assert "No missions found" in captured.out

    def test_missions_api_error(self, capsys, mock_fm):
        mock_fm.list_missions.side_effect = Exception("500 Internal Server Error")
        result = main(argv=["--key", "sk-test", "missions"])
        assert result == 1
        captured = capsys.readouterr()
        assert "500" in captured.err

    def test_missions_missing_status_and_title(self, capsys, mock_fm):
        mock_fm.list_missions.return_value = [
            {"id": "xyz-1234-5678"},
        ]
        result = main(argv=["--key", "sk-test", "missions"])
        assert result == 0
        captured = capsys.readouterr()
        assert "xyz-1234" in captured.out
        assert "?" in captured.out  # missing status defaults to '?'
        assert "Untitled" in captured.out  # missing title defaults to 'Untitled'


# ── Costs command ───────────────────────────────────────────────────────────


class TestCostsCommand:
    def test_costs_success(self, capsys, mock_fm):
        mock_fm.get_usage_summary.return_value = {
            "total_tokens": 125000,
            "total_cost": 0.0625,
        }
        result = main(argv=["--key", "sk-test", "costs"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Period: month" in captured.out
        assert "125,000" in captured.out
        assert "$0.0625" in captured.out

    def test_costs_custom_period(self, capsys, mock_fm):
        mock_fm.get_usage_summary.return_value = {
            "total_tokens": 500,
            "total_cost": 0.01,
        }
        result = main(argv=["--key", "sk-test", "costs", "--period", "7d"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Period: 7d" in captured.out

    def test_costs_missing_keys(self, capsys, mock_fm):
        mock_fm.get_usage_summary.return_value = {}
        result = main(argv=["--key", "sk-test", "costs"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Total tokens: 0" in captured.out
        assert "$0.0000" in captured.out

    def test_costs_api_error(self, capsys, mock_fm):
        mock_fm.get_usage_summary.side_effect = Exception("Unauthorized")
        result = main(argv=["--key", "sk-test", "costs"])
        assert result == 1
        captured = capsys.readouterr()
        assert "Unauthorized" in captured.err


# ── Env var support ─────────────────────────────────────────────────────────


class TestEnvVarSupport:
    def test_key_from_env(self, monkeypatch, capsys, mock_fm):
        monkeypatch.setenv("FLOWMANNER_API_KEY", "sk-env-key")
        mock_fm.health_check.return_value = {"status": "ok"}
        result = main(argv=["status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Status: ok" in captured.out

    def test_url_from_env(self, monkeypatch, capsys, mock_fm):
        monkeypatch.setenv("FLOWMANNER_API_KEY", "sk-env")
        monkeypatch.setenv("FLOWMANNER_URL", "http://custom.host:9000")
        mock_fm.health_check.return_value = {"status": "ok"}
        result = main(argv=["status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Connected to http://custom.host:9000" in captured.out

    def test_cli_key_overrides_env(self, monkeypatch, capsys, mock_fm):
        monkeypatch.setenv("FLOWMANNER_API_KEY", "sk-env")
        mock_fm.health_check.return_value = {"status": "ok"}
        result = main(argv=["--key", "sk-cli", "status"])
        assert result == 0
