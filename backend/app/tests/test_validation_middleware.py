"""Unit tests for app/api/v2/validation_middleware.py — StrictValidationMiddleware."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_request(
    path: str = "/api/v2/missions",
    method: str = "GET",
    body: bytes | None = None,
    content_type: str = "application/json",
    headers: dict | None = None,
) -> MagicMock:
    """Create a mock Starlette Request for middleware testing."""
    req = MagicMock(spec=Request)
    req.url.path = path
    req.method = method
    req.headers = {"content-type": content_type, **(headers or {})}

    async def _body():
        return body or b""

    req.body = _body
    req.state = MagicMock()
    return req


def _make_json_response(data: dict, status_code: int = 200):
    """Create a JSONResponse with body attribute."""
    content = json.dumps(data).encode("utf-8")
    resp = JSONResponse(content=data, status_code=status_code)
    # Simulate body attribute added by middleware
    resp.body = content
    resp.headers["content-type"] = "application/json"
    return resp


# ── _is_json_serializable ─────────────────────────────────────────────────────


class TestIsJsonSerializable:
    """_is_json_serializable: deep JSON serializability check."""

    def test_primitives_pass(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        assert _is_json_serializable("hello") == []
        assert _is_json_serializable(42) == []
        assert _is_json_serializable(3.14) == []
        assert _is_json_serializable(True) == []
        assert _is_json_serializable(False) == []
        assert _is_json_serializable(None) == []

    def test_nested_dicts_pass(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        data = {"a": 1, "b": {"c": "nested", "d": [1, 2, 3]}, "e": None}
        assert _is_json_serializable(data) == []

    def test_nested_lists_pass(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        data = [1, "two", {"three": 3}, [4, 5]]
        assert _is_json_serializable(data) == []

    def test_datetime_passes(self):
        from datetime import datetime

        from app.api.v2.validation_middleware import _is_json_serializable

        assert _is_json_serializable({"ts": datetime.now()}) == []

    def test_date_passes(self):
        from datetime import date

        from app.api.v2.validation_middleware import _is_json_serializable

        assert _is_json_serializable({"d": date.today()}) == []

    def test_uuid_passes(self):
        from uuid import UUID

        from app.api.v2.validation_middleware import _is_json_serializable

        assert (
            _is_json_serializable({"id": UUID("12345678-1234-5678-1234-567812345678")})
            == []
        )

    def test_class_instance_fails(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        class MyClass:
            pass

        obj = MyClass()
        errors = _is_json_serializable({"obj": obj})
        assert len(errors) == 1
        assert "MyClass" in errors[0]

    def test_enum_fails(self):
        from enum import Enum

        from app.api.v2.validation_middleware import _is_json_serializable

        class Color(Enum):
            RED = 1

        errors = _is_json_serializable({"color": Color.RED})
        assert len(errors) == 1
        assert "Color" in errors[0]

    def test_function_fails(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        errors = _is_json_serializable({"fn": lambda: None})
        assert len(errors) == 1

    def test_nested_non_serializable(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        class Secret:
            pass

        data = {"outer": {"inner": Secret()}}
        errors = _is_json_serializable(data)
        assert len(errors) == 1
        assert "Secret" in errors[0]

    def test_sets_fail(self):
        from app.api.v2.validation_middleware import _is_json_serializable

        # set is iterable but not JSON-serializable
        errors = _is_json_serializable({"myset": {1, 2, 3}})
        assert len(errors) == 1


# ── StrictValidationMiddleware ────────────────────────────────────────────────


class TestStrictValidationMiddleware:
    """StrictValidationMiddleware: request/response validation."""

    @pytest.mark.asyncio
    async def test_skips_non_v2_paths(self):
        from app.api.v2.validation_middleware import StrictValidationMiddleware

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(path="/api/v1/something")

        async def call_next(request):
            return JSONResponse(content={"ok": True}, status_code=200)

        resp = await middleware.dispatch(req, call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_skips_streaming_responses(self):
        from app.api.v2.validation_middleware import StrictValidationMiddleware

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(path="/api/v2/missions/stream")

        async def call_next(request):
            return StreamingResponse(
                content=iter([b"data: test\n\n"]),
                media_type="text/event-stream",
            )

        resp = await middleware.dispatch(req, call_next)
        assert isinstance(resp, StreamingResponse)

    @pytest.mark.asyncio
    async def test_passes_valid_json_response(self):
        from app.api.v2.validation_middleware import StrictValidationMiddleware

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(path="/api/v2/missions", headers={"X-Request-ID": "req-1"})

        async def call_next(request):
            return _make_json_response(
                {"data": {"items": [1, 2, 3]}, "meta": {}, "error": None}
            )

        resp = await middleware.dispatch(req, call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_catches_non_serializable_response(self):
        from app.api.v2.validation_middleware import (
            StrictValidationMiddleware,
        )

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(
            path="/api/v2/missions", headers={"X-Request-ID": "req-test-123"}
        )

        async def call_next(request):
            return _make_json_response(
                {"data": {"items": [1, 2, 3]}, "meta": {}, "error": None}
            )

        with patch(
            "app.api.v2.validation_middleware._is_json_serializable",
            return_value=["$.data.leak: LeakedObject"],
        ):
            resp = await middleware.dispatch(req, call_next)
            assert resp.status_code == 500
            body = json.loads(resp.body)
            assert body["error"]["code"] == "RESPONSE_SERIALIZATION_ERROR"
            assert "leak" in str(body["error"]["details"]["fields"])

    @pytest.mark.asyncio
    async def test_skips_error_responses(self):
        """Error responses (status >= 400) are returned as-is."""
        from app.api.v2.validation_middleware import StrictValidationMiddleware

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(path="/api/v2/missions")

        async def call_next(request):
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        resp = await middleware.dispatch(req, call_next)
        # Error responses missing body attribute should be returned as-is
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_skips_non_json_responses(self):
        from app.api.v2.validation_middleware import StrictValidationMiddleware

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(path="/api/v2/missions")

        async def call_next(request):
            resp = JSONResponse(content={"ok": True})
            resp.headers["content-type"] = "text/html"
            return resp

        resp = await middleware.dispatch(req, call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(self):
        from app.api.v2.validation_middleware import StrictValidationMiddleware

        middleware = StrictValidationMiddleware(app=MagicMock())
        req = _make_request(path="/api/v2/missions")

        async def call_next(request):
            resp = JSONResponse(content={})
            resp.body = b"not valid json!!!"
            resp.headers["content-type"] = "application/json"
            return resp

        # Should not crash — logs warning and returns response as-is
        resp = await middleware.dispatch(req, call_next)
        assert resp is not None


# ── register_strict_validation ────────────────────────────────────────────────


class TestRegisterStrictValidation:
    """register_strict_validation: middleware registration."""

    def test_adds_middleware_to_app(self):
        from app.api.v2.validation_middleware import register_strict_validation

        mock_app = MagicMock(spec=FastAPI)
        mock_app.add_middleware = MagicMock()

        register_strict_validation(mock_app)
        mock_app.add_middleware.assert_called_once()
