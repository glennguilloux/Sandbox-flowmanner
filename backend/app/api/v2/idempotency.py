"""Async SQLAlchemy 2.0 idempotency — scoped lookup + finalization middleware.

Scoped lookup: (user_id, method, endpoint, idempotency_key)
Behaviour:
- Same key + same hash → replay cached response (Idempotency-Replay: cache)
- Same key + different hash → 409 CONFLICT (v2 envelope)
- No key → pass through (idempotency is opt-in)
- Concurrent duplicate handled safely (is_processing race via unique index)

Finalization: a Starlette middleware persists response body/status/headers
after successful handler execution so replays are reliable.
"""

from __future__ import annotations

import hashlib
import json as _json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v2.base import ErrorDetail, ResponseMeta
from app.database import get_db_session
from app.models.idempotency import IdempotencyKey

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = structlog.get_logger(__name__)

DEFAULT_IDEMPOTENCY_TTL_HOURS = 24
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_REPLAY_HEADER = "Idempotency-Replay"


def idempotency(ttl_hours: int = DEFAULT_IDEMPOTENCY_TTL_HOURS):
    """FastAPI dependency factory for scoped idempotent mutation endpoints.

    Returns a cached JSONResponse on replay/conflict, or None on pass-through.
    Stores the new IdempotencyKey on request.state._idempotency_record so
    the IdempotencyFinalizationMiddleware can persist the response.
    """

    async def _check(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: User = Depends(get_current_user),
    ) -> JSONResponse | None:
        key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        if not key:
            return None

        if not _validate_key(key):
            return _make_error_response(
                400,
                "INVALID_IDEMPOTENCY_KEY",
                "Idempotency-Key must be 1-255 alphanumeric/dash/underscore chars",
            )

        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8") if body_bytes else ""
        request_hash = _hash_request(request.method, request.url.path, body_str)
        now = datetime.now(UTC)

        # SCOPED lookup: (user_id, method, endpoint, idempotency_key)
        result = await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.idempotency_key == key,
                IdempotencyKey.user_id == user.id,
                IdempotencyKey.method == request.method,
                IdempotencyKey.endpoint == request.url.path,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            if existing.expires_at and existing.expires_at < now:
                await session.delete(existing)
                await session.flush()
                existing = None
            else:
                if existing.request_hash != request_hash:
                    return _make_error_response(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key reused with different request payload",
                        details={
                            "idempotency_key": key,
                            "original_endpoint": existing.endpoint,
                        },
                    )

                existing.cache_hits = (existing.cache_hits or 0) + 1
                existing.last_accessed_at = now
                await session.flush()
                logger.debug("idempotency_replay", key=key, hits=existing.cache_hits)
                return _build_cached_response(existing)

        if existing is None:
            expires_at = now + timedelta(hours=ttl_hours)
            record = IdempotencyKey(
                idempotency_key=key,
                user_id=user.id,
                method=request.method,
                endpoint=request.url.path,
                request_hash=request_hash,
                is_processing=True,
                is_completed=False,
                expires_at=expires_at,
            )
            session.add(record)
            await session.flush()
            request.state._idempotency_record = record
            return None

    return _check


# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_key(key: str) -> bool:
    import re

    return bool(key and 1 <= len(key) <= 255 and re.match(r"^[\w\-]+$", key))


def _hash_request(method: str, path: str, body: str) -> str:
    return hashlib.sha256(f"{method}:{path}:{body}".encode()).hexdigest()


def _is_204_no_content(status: int) -> bool:
    return status == 204


def _make_error_response(
    status: int, code: str, msg: str, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "data": None,
            "meta": ResponseMeta().model_dump(),
            "error": ErrorDetail(code=code, message=msg, details=details).model_dump(),
        },
    )


def _build_cached_response(record: IdempotencyKey) -> JSONResponse:
    body = record.response_body or {}
    status = record.response_status or 200
    headers = dict(record.response_headers or {})
    headers[IDEMPOTENCY_REPLAY_HEADER] = "cache"
    return JSONResponse(content=body, status_code=status, headers=headers)


# ── Finalization Middleware ───────────────────────────────────────────────────


class IdempotencyFinalizationMiddleware:
    """Starlette ASGI middleware — persists response into idempotency record.

    After the handler returns, if request.state has an _idempotency_record,
    this middleware reads the response and stores status/headers/body so
    future replays return the exact same data.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Call downstream
        response_body_chunks: list[bytes] = []
        response_status: list[int] = [200]
        response_headers: list[list[tuple]] = [[]]

        async def _capture_send(message):
            if message["type"] == "http.response.start":
                response_status[0] = message["status"]
                response_headers[0] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_body_chunks.append(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, _capture_send)

        # Finalize idempotency record if one was stashed
        record = getattr(request.state, "_idempotency_record", None)
        if record is not None:
            await self._finalize(
                record,
                response_status[0],
                response_headers[0],
                b"".join(response_body_chunks),
            )

    async def _finalize(
        self, record: IdempotencyKey, status: int, headers: list, body_bytes: bytes
    ):
        try:
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                from sqlalchemy import select as sa_select

                result = await session.execute(
                    sa_select(IdempotencyKey).where(IdempotencyKey.id == record.id)
                )
                fresh = result.scalar_one_or_none()
                if fresh is None:
                    return

                fresh.response_status = status
                fresh.response_headers = _safe_headers(headers)
                if body_bytes and not _is_204_no_content(status):
                    try:
                        fresh.response_body = _json.loads(body_bytes.decode("utf-8"))
                    except Exception:
                        fresh.response_body = None
                fresh.is_processing = False
                fresh.is_completed = True
                fresh.last_accessed_at = datetime.now(UTC)
                await session.commit()
        except Exception:
            logger.warning(
                "idempotency_finalize_failed", record_id=record.id, exc_info=True
            )


def _safe_headers(headers: list) -> dict[str, str]:
    """Filter headers to a safe subset for caching."""
    SAFE = {"content-type", "x-request-id", "idempotency-replay"}
    out: dict[str, str] = {}
    for k, v in headers:
        key = k.decode("latin-1").lower() if isinstance(k, bytes) else k.lower()
        if key in SAFE or key.startswith("x-"):
            val = v.decode("latin-1") if isinstance(v, bytes) else v
            out[key] = val
    return out
