"""Shared test-environment guard — pop shell env overrides of config defaults.

pydantic-settings gives shell env precedence over both ``.env`` and the
code default. A stray env var in the test runner's shell (e.g., a leftover
from a previous session) would silently override the corresponding
config default and cause confusing test failures that "work on my
machine" but fail in CI / new dev environments.

Single source of truth for the env-guard logic. Both
``backend/tests/conftest.py`` (primary) and ``backend/app/tests/conftest.py``
(secondary) call :func:`pop_config_overrides` in their Section 1b.

Pops two classes of env vars:

* **Named** (exact match): ``DATABASE_URL``, ``REDIS_URL``,
  ``CELERY_BROKER_URL``, ``CELERY_RESULT_BACKEND``
* **Prefix wildcards**: ``SANDBOXD_*``, ``LLM_*``, ``QDRANT_*``,
  ``RAG_*``, ``SENTRY_*``, ``MISSION_*``

Covers the most common high-risk prefixes. Extend ``_PREFIX_OVERRIDES``
(or ``_NAMED_OVERRIDES``) when adding new infrastructure dependencies
(database, cache, vector store, error tracker).
"""


from __future__ import annotations

import os

__all__ = ("pop_config_overrides",)

# Named env vars that override config defaults (exact match).
_NAMED_OVERRIDES: tuple[str, ...] = (
    "DATABASE_URL",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
)

# Wildcard prefixes for env vars that override config defaults.
_PREFIX_OVERRIDES: tuple[str, ...] = (
    "SANDBOXD_",
    "LLM_",
    "QDRANT_",
    "RAG_",
    "SENTRY_",
    "MISSION_",
)


def pop_config_overrides() -> None:
    """Pop shell env overrides of config defaults.

    Removes env vars in two passes:

    1. Named env vars (exact match against :data:`_NAMED_OVERRIDES`)
    2. Prefix-based wildcards (startswith against :data:`_PREFIX_OVERRIDES`)

    Safe to call multiple times (idempotent). Safe to call before any
    imports — only touches :data:`os.environ`.
    """
    for _var in _NAMED_OVERRIDES:
        os.environ.pop(_var, None)
    for _var in list(os.environ.keys()):
        if any(_var.startswith(prefix) for prefix in _PREFIX_OVERRIDES):
            os.environ.pop(_var, None)
