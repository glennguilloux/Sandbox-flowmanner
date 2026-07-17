"""ADR-002 (v1 → substrate cutover) — guard unit tests.

Covers ``Settings.warn_vestigial_executor_flag`` across the value/env matrix.
The guard must:
- return ``None`` when the var is unset, empty, or ``all`` (any case),
- return ``None`` in a ``development`` APP_ENV regardless of value,
- return a warning string for ``off`` / ``run`` / garbage in a non-dev env,
- NEVER raise, NEVER touch execution behavior.

These are pure unit tests (no DB, no app boot).
"""

from __future__ import annotations

import pytest

from app.config import Settings


def _settings(app_env: str) -> Settings:
    # extra="ignore" on the model means unrelated env vars won't break construction.
    return Settings(APP_ENV=app_env)


class TestWarnVestigialExecutorFlagUnset:
    def test_unset_returns_none_in_production(self):
        s = _settings("production")
        assert s.warn_vestigial_executor_flag(env={}) is None

    def test_empty_string_returns_none_in_production(self):
        s = _settings("production")
        assert s.warn_vestigial_executor_flag(env={"FLOWMANNER_UNIFIED_EXECUTOR": ""}) is None

    def test_whitespace_only_returns_none_in_production(self):
        s = _settings("production")
        assert s.warn_vestigial_executor_flag(env={"FLOWMANNER_UNIFIED_EXECUTOR": "   "}) is None


class TestWarnVestigialExecutorFlagAll:
    @pytest.mark.parametrize("value", ["all", "ALL", "All", " all ", "aLl"])
    def test_all_is_accepted_case_insensitive(self, value):
        s = _settings("production")
        assert s.warn_vestigial_executor_flag(env={"FLOWMANNER_UNIFIED_EXECUTOR": value}) is None


class TestWarnVestigialExecutorFlagMisleadingValues:
    @pytest.mark.parametrize("value", ["off", "run", "OFF", "Run", "true", "1", "garbage"])
    def test_non_all_values_warn_in_production(self, value):
        s = _settings("production")
        warning = s.warn_vestigial_executor_flag(env={"FLOWMANNER_UNIFIED_EXECUTOR": value})
        assert warning is not None
        # The warning must name the var and point at the ADR so an operator can act.
        assert "FLOWMANNER_UNIFIED_EXECUTOR" in warning
        assert "VESTIGIAL" in warning
        assert "ADR-002" in warning

    @pytest.mark.parametrize("value", ["off", "run", "garbage"])
    def test_non_all_values_warn_in_staging(self, value):
        s = _settings("staging")
        assert s.warn_vestigial_executor_flag(env={"FLOWMANNER_UNIFIED_EXECUTOR": value}) is not None


class TestWarnVestigialExecutorFlagDevelopment:
    @pytest.mark.parametrize("value", ["off", "run", "garbage", "all"])
    def test_development_never_warns(self, value):
        s = _settings("development")
        assert s.warn_vestigial_executor_flag(env={"FLOWMANNER_UNIFIED_EXECUTOR": value}) is None


class TestGuardNeverRaises:
    def test_reads_real_os_environ_without_raising(self):
        # Default call path (env=None) must read os.environ and never raise,
        # regardless of what the ambient environment holds.
        s = _settings("production")
        result = s.warn_vestigial_executor_flag()
        assert result is None or isinstance(result, str)
