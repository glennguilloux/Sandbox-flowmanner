"""Contract tests for ``app.testing._env_guard.pop_config_overrides()``.

Locks in the four contracts the helper guarantees:
  1. Pops the 4 named config-overridable vars (DATABASE_URL, REDIS_URL,
     CELERY_BROKER_URL, CELERY_RESULT_BACKEND) when set.
  2. Pops all wildcard-prefix vars (any var matching one of the prefixes
     in :data:`_PREFIX_OVERRIDES`) when set. Tested across three
     categories of names: arbitrary_suffix (``PREFIX_EXAMPLE``),
     realistic_suffix (``PREFIX_URL``), and real_config_vars from
     ``app/config.py``. Iterates over the constant itself so test
     coverage auto-extends when a new prefix is added. The combined
     list is deduped before parametrizing (e.g., ``QDRANT_URL`` appears
     in both realistic_suffix and real_config_vars).
  3. Leaves unrelated env vars alone (OPENAI_API_KEY, PATH, etc.).
  4. Is idempotent — calling twice is safe.

Uses pytest's ``monkeypatch`` fixture to set/restore env vars per test
without polluting the test runner's environment.
"""

from __future__ import annotations

import os

import pytest

# Private but imported for test coverage — auto-extends when a new prefix
# is added to the helper. See test_pops_wildcard_vars below.
from app.testing._env_guard import _PREFIX_OVERRIDES, pop_config_overrides

# Real env var names pulled from app/config.py. Adding one of these to
# the test mix proves the helper catches actual env vars in this
# codebase, not just synthetic shapes. Keep in sync with the prefixes
# in _PREFIX_OVERRIDES.
_REAL_ENV_VARS_FROM_CONFIG: tuple[str, ...] = (
    "SANDBOXD_DEFAULT_TEMPLATE",
    "LLM_API_KEY",
    "QDRANT_URL",
    "RAG_EMBEDDING_MODEL",
    "SENTRY_DSN",
    "MISSION_RESOURCE_CPU_SECONDS",
)

# Three categories of test vars for the wildcard contract:
#   1. arbitrary_suffix: arbitrary suffix per prefix (e.g.
#      ``SANDBOXD_EXAMPLE``) — proves startswith works on any shape.
#   2. realistic_suffix: real-world ``*_URL`` suffix per prefix — most
#      infra services have a ``*_URL`` config var (DATABASE_URL,
#      REDIS_URL, QDRANT_URL, LLM_URL, MISSION_URL).
#      Note: Sentry's canonical env var is ``SENTRY_DSN`` (in
#      real_config_vars), so ``SENTRY_URL`` is a stretch.
#   3. real_config_vars: actual env var names from app/config.py (see
#      constant above) — proves the helper catches real env vars in
#      this codebase, not just synthetic shapes.
#
# Deduped via ``dict.fromkeys`` (first occurrence wins); e.g.,
# ``QDRANT_URL`` is attributed to realistic_suffix since it appears
# in both categories.
_PARAMETRIZE_VARS: list[str] = list(dict.fromkeys(
    [f"{prefix}EXAMPLE" for prefix in _PREFIX_OVERRIDES]
    + [f"{prefix}URL" for prefix in _PREFIX_OVERRIDES]
    + list(_REAL_ENV_VARS_FROM_CONFIG)
))


def test_pops_named_vars(monkeypatch):
    for var in ("DATABASE_URL", "REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        monkeypatch.setenv(var, "should-be-popped")
    pop_config_overrides()
    for var in ("DATABASE_URL", "REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        assert var not in os.environ


@pytest.mark.parametrize("var_name", _PARAMETRIZE_VARS)
def test_pops_wildcard_vars(monkeypatch, var_name):
    monkeypatch.setenv(var_name, "should-be-popped")
    pop_config_overrides()
    assert var_name not in os.environ


def test_leaves_unrelated_vars_alone(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "should-remain")
    monkeypatch.setenv("PATH", "/should/remain")
    pop_config_overrides()
    assert os.environ.get("OPENAI_API_KEY") == "should-remain"
    assert os.environ.get("PATH") == "/should/remain"


def test_is_idempotent(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "x")
    pop_config_overrides()
    pop_config_overrides()  # second call must not raise
    assert "DATABASE_URL" not in os.environ
