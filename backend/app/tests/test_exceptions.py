"""Tests for the typed error hierarchy (Item #2 from Opus 4.8 Design-QA).

Verifies:
- Each AppError subclass carries the correct code and http_status
- MissionError inherits from AppError
- The unified exception handler returns the correct envelope shape for v1/v2/v3
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppError,
    AuthAppError,
    BudgetAppError,
    ConflictAppError,
    ForbiddenAppError,
    NotFoundAppError,
    ProviderAppError,
    RateLimitAppError,
    ValidationAppError,
)
from app.services.mission_errors import (
    GraphNotFoundError,
    MissionError,
    MissionForbiddenError,
    MissionNotFoundError,
    MissionTransitionConflictError,
    MissionValidationError,
    PermanentMissionError,
    RetryableMissionError,
)

# ── Hierarchy tests ─────────────────────────────────────────────────


class TestErrorHierarchy:
    """Each subclass has the correct code and http_status."""

    def test_app_error_defaults(self):
        exc = AppError("boom")
        assert exc.code == "APP_ERROR"
        assert exc.http_status == 400
        assert str(exc) == "boom"
        assert exc.details is None

    def test_app_error_with_details(self):
        exc = AppError("bad", details={"field": "x"})
        assert exc.details == {"field": "x"}

    def test_validation(self):
        assert ValidationAppError("v").http_status == 422
        assert ValidationAppError("v").code == "VALIDATION_ERROR"

    def test_not_found(self):
        assert NotFoundAppError("nf").http_status == 404
        assert NotFoundAppError("nf").code == "NOT_FOUND"

    def test_conflict(self):
        assert ConflictAppError("c").http_status == 409
        assert ConflictAppError("c").code == "CONFLICT"

    def test_auth(self):
        assert AuthAppError("a").http_status == 401
        assert AuthAppError("a").code == "UNAUTHORIZED"

    def test_forbidden(self):
        assert ForbiddenAppError("f").http_status == 403
        assert ForbiddenAppError("f").code == "FORBIDDEN"

    def test_budget(self):
        assert BudgetAppError("b").http_status == 402
        assert BudgetAppError("b").code == "BUDGET_EXHAUSTED"

    def test_provider(self):
        assert ProviderAppError("p").http_status == 502
        assert ProviderAppError("p").code == "PROVIDER_ERROR"

    def test_rate_limit(self):
        assert RateLimitAppError("r").http_status == 429
        assert RateLimitAppError("r").code == "RATE_LIMITED"


# ── MissionError inherits from AppError ─────────────────────────────


class TestMissionErrorHierarchy:
    """MissionError and its subclasses are AppError instances."""

    def test_mission_error_is_app_error(self):
        assert issubclass(MissionError, AppError)

    def test_retryable_is_app_error(self):
        exc = RetryableMissionError("overloaded")
        assert isinstance(exc, AppError)
        assert exc.http_status == 503

    def test_permanent_is_app_error(self):
        exc = PermanentMissionError("bad config")
        assert isinstance(exc, AppError)
        assert exc.http_status == 400

    def test_not_found_codes(self):
        exc = MissionNotFoundError("gone")
        assert isinstance(exc, AppError)
        assert isinstance(exc, NotFoundAppError)
        assert exc.code == "MISSION_NOT_FOUND"
        assert exc.http_status == 404

    def test_forbidden_codes(self):
        exc = MissionForbiddenError("nope")
        assert isinstance(exc, ForbiddenAppError)
        assert exc.code == "MISSION_FORBIDDEN"
        assert exc.http_status == 403

    def test_conflict_codes(self):
        exc = MissionTransitionConflictError("bad transition")
        assert isinstance(exc, ConflictAppError)
        assert exc.code == "MISSION_TRANSITION_CONFLICT"
        assert exc.http_status == 409

    def test_validation_codes(self):
        exc = MissionValidationError("bad input")
        assert isinstance(exc, ValidationAppError)
        assert exc.code == "MISSION_VALIDATION_ERROR"
        assert exc.http_status == 422

    def test_graph_not_found_codes(self):
        exc = GraphNotFoundError("graph gone")
        assert isinstance(exc, NotFoundAppError)
        assert exc.code == "GRAPH_NOT_FOUND"
        assert exc.http_status == 404

    def test_except_mission_error_still_works(self):
        """Existing ``except MissionError`` catch blocks continue to work."""
        with pytest.raises(MissionError):
            raise MissionNotFoundError("gone")

    def test_except_app_error_catches_mission_error(self):
        """MissionError is catchable as AppError."""
        with pytest.raises(AppError):
            raise MissionNotFoundError("gone")


# ── Unified handler envelope tests ──────────────────────────────────


class TestUnifiedHandler:
    """The AppError handler returns the correct envelope for each API version."""

    @pytest.fixture
    def app(self):
        from app.main_fastapi import app_error_handler

        _app = FastAPI()
        _app.add_exception_handler(AppError, app_error_handler)

        @_app.get("/api/v1/test")
        async def v1_test():
            raise NotFoundAppError("not here", details={"id": "42"})

        @_app.get("/api/v2/test")
        async def v2_test():
            raise ValidationAppError("bad field", details={"field": "name"})

        @_app.get("/api/v3/test")
        async def v3_test():
            raise ConflictAppError("duplicate")

        return _app

    @pytest.fixture
    def client(self, app):
        return TestClient(app, raise_server_exceptions=False)

    def test_v1_flat_envelope(self, client):
        resp = client.get("/api/v1/test")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert body["detail"] == "not here"

    def test_v2_envelope_shape(self, client):
        resp = client.get("/api/v2/test")
        assert resp.status_code == 422
        body = resp.json()
        assert body["data"] is None
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == "bad field"
        assert body["error"]["details"] == {"field": "name"}
        assert "meta" in body
        assert "request_id" in body["meta"]

    def test_v3_envelope_shape(self, client):
        resp = client.get("/api/v3/test")
        assert resp.status_code == 409
        body = resp.json()
        assert body["data"] is None
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["message"] == "duplicate"
        assert "trace_id" in body["error"]
        assert "meta" in body
