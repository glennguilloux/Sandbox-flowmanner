"""V3 exception-handler registration.

Historically this module defined a private ``_make_error_response`` plus a
path-guarded ``HTTPException`` / ``Exception`` pair registered via
``app.exception_handler(...)``. The v2 module did the same, and because
FastAPI keys handlers by exception class (a dict), the *last* registration
per class won and the two tiers only produced the right shape because each
guarded on ``request.url.path.startswith(...)``. That made correctness
depend on fragile, implicit registration order.

The single path-aware dispatcher now lives in ``app/api/_shared_errors.py``
and is registered once in ``app/main_fastapi.py``. This module keeps the
``register_v3_exception_handlers(app)`` entrypoint (still used by the
``v3_test_app`` test fixture) but delegates to the shared dispatcher so a
v3-only app still gets the correct v3 envelope.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api._shared_errors import register_unified_exception_handlers


def register_v3_exception_handlers(app: FastAPI) -> None:
    """Register v3 error handling (delegates to the unified dispatcher).

    Kept for backward compatibility with the ``v3_test_app`` fixture in
    ``tests/conftest.py``. The dispatcher is path-aware, so a v3-only app
    still produces the v3 envelope for ``/api/v3/*`` paths.
    """
    register_unified_exception_handlers(app)
