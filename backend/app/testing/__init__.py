"""Test-only helpers for the Flowmanner backend.

This subpackage groups test utilities that ship with the ``app`` package
but are NOT used by production code. The leading underscore on module
names (e.g., ``_env_guard``) signals "private / test-only" — these
helpers are imported by conftest.py files and test modules, not by
``app.*`` production code.

Public API:
    * ``pop_config_overrides`` — pops shell env overrides of config
      defaults before tests run, preventing the "shell env var silently
      overrides the code default" class of bug. Import via the short
      form: ``from app.testing import pop_config_overrides``.

Internal modules:
    * ``_env_guard`` — the implementation. Import the private name
      lists (``_NAMED_OVERRIDES``, ``_PREFIX_OVERRIDES``) from here if
      you need to extend the set of guarded prefixes (e.g., add
      ``QDRANT_*``, ``RAG_*``, ``SENTRY_*``).

Add new test-only helpers here as a sibling module, not nested deeper.
"""

# Convenience re-export — see __all__ below.
from app.testing._env_guard import pop_config_overrides

__all__ = ("pop_config_overrides",)
