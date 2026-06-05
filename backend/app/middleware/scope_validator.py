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

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return await call_next(request)

        import jwt

        from app.config import settings

        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        except Exception:
            return await call_next(request)

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
