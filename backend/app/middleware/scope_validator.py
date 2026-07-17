from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request

SCOPE_REQUIREMENTS: dict[str, dict[str, list[str]]] = {}


def register_scope_requirement(path: str, method: str, scopes: list[str]) -> None:
    key = f"{method.upper()}:{path}"
    SCOPE_REQUIREMENTS[key] = {"path": path, "method": method.upper(), "scopes": scopes}


class ScopeValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v3/"):
            return await call_next(request)

        # ── Fail-closed auth gate for /api/v3/* ──────────────────────────────
        # Every request under /api/v3/* REQUIRES a valid Bearer token. The
        # previous implementation was fail-OPEN: a missing header or a decode
        # error silently fell through to call_next(), exposing any v3 route
        # that forgot its Depends(get_current_session) as an unauthenticated
        # endpoint. We now reject up front.
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "data": None,
                    "meta": {},
                    "error": {
                        "code": "UNAUTHENTICATED",
                        "message": "Missing or malformed Authorization header — "
                        "expected 'Bearer <token>'",
                        "details": {},
                        "trace_id": "",
                    },
                },
            )

        import jwt

        from app.config import settings

        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        except Exception:
            # Invalid / expired / tampered token — reject. Never fall through.
            return JSONResponse(
                status_code=401,
                content={
                    "data": None,
                    "meta": {},
                    "error": {
                        "code": "UNAUTHENTICATED",
                        "message": "Invalid or expired token",
                        "details": {},
                        "trace_id": "",
                    },
                },
            )

        session_scopes = set(payload.get("scopes") or [])

        if payload.get("role") in ("admin", "owner"):
            return await call_next(request)

        method = request.method.upper()
        path = request.url.path
        key = f"{method}:{path}"

        if key in SCOPE_REQUIREMENTS:
            required = set(SCOPE_REQUIREMENTS[key]["scopes"])
            if not required.issubset(session_scopes):
                missing = required - session_scopes
                return JSONResponse(
                    status_code=403,
                    content={
                        "data": None,
                        "meta": {},
                        "error": {
                            "code": "SCOPE_INSUFFICIENT",
                            "message": f"Missing required scopes: {', '.join(sorted(missing))}",
                            "details": {"missing": sorted(missing)},
                            "trace_id": "",
                        },
                    },
                )

        return await call_next(request)
