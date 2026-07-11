"""TDD tests for T28: v2 /critiques router (Critic Inspection API).

Plan reference: D30-60, T28 — two read-only endpoints on
``/api/v2/critiques`` (``GET /critiques`` and ``GET /critiques/{id}``)
plus a Pydantic schema module and an extended ``CritiqueService.list``
method.

The router is a thin envelope-wrapping layer over ``CritiqueService``
— every assertion here is HTTP-level (status code, envelope shape,
payload keys), service-level (filter passing, isolation enforcement),
or schema-level (ORM round-trip, enum values). The DB write paths
are exercised in ``tests/test_critique_service.py``; this file owns
the HTTP contract.

Test strategy
-------------
* Schema tests: pure-Python, no DB.
* Router tests: ``TestClient`` against the real FastAPI ``app`` with
  ``get_current_user`` and ``get_workspace_id`` overridden (mirrors the
  ``test_personal_memory_router.py`` pattern). ``CritiqueService`` is
  PATCHED in the route module so no live DB calls happen.
* Service-list tests: mocked ``AsyncSession`` (mirrors
  ``test_critique_service.py`` pattern) — no live DB.

Cases
-----
* Schemas
  1.  ``CritiqueResponse`` is ORM-backed (``from_attributes=True``)
  2.  ``CritiqueResponse`` round-trips a real ``Critique`` instance
  3.  ``CritiqueListResponse`` defaults
  4.  ``CriticKind`` enum values match ``ALL_CRITIC_KINDS``
* Router — list
  5.  List delegates to ``service.list`` with the request's
      ``(user_id, workspace_id)`` (security guardrail)
  6.  List passes ``mission_id`` filter
  7.  List passes ``program_id`` filter
  8.  List passes ``critic_kind`` filter
  9.  List passes ``min_score_overall`` filter
  10. List passes ``page`` / ``per_page`` (converted to offset/limit)
  11. List rejects invalid ``critic_kind`` with 422 envelope
  12. List returns the paginated envelope shape
* Router — get
  13. Get delegates to ``service.get`` with the request's
      ``(user_id, workspace_id)`` + ``critique_id``
  14. Get returns the ok envelope
  15. Get returns 404 envelope on ``CritiqueNotFound``
  16. Get returns 422 envelope on invalid UUID
* Service — list
  17. List filters by ``(user_id, workspace_id)`` (security guardrail)
  18. List validates ``critic_kind`` against ``ALL_CRITIC_KINDS``
  19. List validates ``min_score_overall`` range
  20. List returns items + total (paginated)
  21. List does NOT call ``db.commit()`` (services/AGENTS.md rule 3)

Run from ``/opt/flowmanner/backend``::

    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_critique_router.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# Ensure DATABASE_URL is set BEFORE importing app modules.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)

# Late imports so env var is honored.
from app.api.deps import get_current_user, get_db, get_workspace_id  # noqa: E402
from app.api.v2 import critiques as critiques_module  # noqa: E402
from app.main_fastapi import app  # noqa: E402
from app.models.critique_models import ALL_CRITIC_KINDS, Critique  # noqa: E402
from app.models.user import User  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Test data helpers
# ═══════════════════════════════════════════════════════════════════════════


def _new_id() -> int:
    """Unique user ID (unlikely to collide with real users)."""
    return uuid.uuid4().int % 900_000_000 + 100_000


def _new_workspace_id() -> str:
    return f"ws-crit-router-{uuid.uuid4().hex[:21]}"


def _make_user_sync() -> User:
    """Build a User with no DB write (test will not commit it)."""
    user_id = _new_id()
    return User(
        id=user_id,
        email=f"crit-router-{user_id}@test.flowmanner.example",
        username=f"crit_router_{user_id}",
        full_name=f"Crit Router Test {user_id}",
        hashed_password="test-hash-not-real",
        is_active=True,
        is_admin=False,
        role="free",
    )


def _make_critique_instance(
    *,
    user_id: int,
    workspace_id: str,
    mission_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    critic_kind: str = "critic",
    score_overall: float | None = 0.7,
    score_alignment: float | None = 0.8,
    score_safety: float | None = 0.9,
    score_completeness: float | None = 0.6,
    summary: str | None = "ok plan",
    misses: list[Any] | None = None,
    risks: list[Any] | None = None,
    improvements: list[Any] | None = None,
    alternatives: list[Any] | None = None,
    raw_response: dict[str, Any] | None = None,
    model_id: str | None = "deepseek-chat",
    tokens_in: int | None = 100,
    tokens_out: int | None = 50,
    duration_ms: int | None = 200,
    critique_id: uuid.UUID | None = None,
) -> Critique:
    """Build a Critique instance (NOT persisted to DB)."""
    if misses is None:
        misses = ["missed edge case"]
    if risks is None:
        risks = ["timeout risk"]
    if improvements is None:
        improvements = [{"description": "add retry", "confidence": 0.7}]
    if alternatives is None:
        alternatives = [{"approach": "queue", "tradeoffs": "more deps", "score": 0.6}]
    if raw_response is None:
        raw_response = {"raw": "..."}
    if mission_id is None:
        mission_id = uuid.uuid4()
    if critique_id is None:
        critique_id = uuid.uuid4()
    c = Critique(
        id=critique_id,
        user_id=user_id,
        workspace_id=workspace_id,
        mission_id=mission_id,
        program_id=program_id,
        critic_kind=critic_kind,
        score_overall=score_overall,
        score_alignment=score_alignment,
        score_safety=score_safety,
        score_completeness=score_completeness,
        summary=summary,
        misses=misses,
        risks=risks,
        improvements=improvements,
        alternatives=alternatives,
        raw_response=raw_response,
        model_id=model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        duration_ms=duration_ms,
    )
    # TimestampMixin columns — populate manually since the DB doesn't.
    c.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    c.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return c


# ═══════════════════════════════════════════════════════════════════════════
# (A) Schema tests — pure Python
# ═══════════════════════════════════════════════════════════════════════════


class TestCritiqueResponseSchema:
    def test_response_is_orm_backed(self) -> None:
        """``CritiqueResponse`` has ``from_attributes=True``."""
        from app.schemas.critique import CritiqueResponse

        cfg = CritiqueResponse.model_config
        assert cfg.get("from_attributes") is True

    def test_response_round_trip_real_critique_instance(self) -> None:
        """Build a real ``Critique`` instance and ``model_validate`` it."""
        from app.schemas.critique import CritiqueResponse

        user_id = _new_id()
        workspace_id = _new_workspace_id()
        c = _make_critique_instance(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        # model_validate(orm) must succeed (from_attributes=True).
        resp = CritiqueResponse.model_validate(c)
        d = resp.model_dump(mode="json")
        # Identity fields.
        assert d["id"] == str(c.id)
        assert d["user_id"] == user_id
        assert d["workspace_id"] == workspace_id
        assert d["mission_id"] == str(c.mission_id)
        # Critic taxonomy.
        assert d["critic_kind"] == "critic"
        # Scores.
        assert d["score_overall"] == 0.7
        assert d["score_alignment"] == 0.8
        assert d["score_safety"] == 0.9
        assert d["score_completeness"] == 0.6
        # Summary.
        assert d["summary"] == "ok plan"
        # Structured findings — present even if critique instance defaults.
        assert d["misses"] == ["missed edge case"]
        assert d["risks"] == ["timeout risk"]
        assert isinstance(d["improvements"], list)
        assert isinstance(d["alternatives"], list)
        # Provenance.
        assert d["model_id"] == "deepseek-chat"
        assert d["tokens_in"] == 100
        assert d["tokens_out"] == 50
        assert d["duration_ms"] == 200
        # Timestamps.
        assert d["created_at"] is not None
        assert d["updated_at"] is not None

    def test_response_handles_null_scores(self) -> None:
        """All score columns may be None (partial critic run)."""
        from app.schemas.critique import CritiqueResponse

        user_id = _new_id()
        workspace_id = _new_workspace_id()
        c = _make_critique_instance(
            user_id=user_id,
            workspace_id=workspace_id,
            score_overall=None,
            score_alignment=None,
            score_safety=None,
            score_completeness=None,
        )
        resp = CritiqueResponse.model_validate(c)
        d = resp.model_dump(mode="json")
        assert d["score_overall"] is None
        assert d["score_alignment"] is None
        assert d["score_safety"] is None
        assert d["score_completeness"] is None

    def test_list_response_defaults(self) -> None:
        """``CritiqueListResponse`` accepts the canonical envelope shape."""
        from app.schemas.critique import CritiqueListResponse, CritiqueResponse

        items = [
            CritiqueResponse.model_validate(
                _make_critique_instance(
                    user_id=_new_id(),
                    workspace_id=_new_workspace_id(),
                )
            )
        ]
        resp = CritiqueListResponse(
            items=items, total=1, page=1, per_page=50
        )
        d = resp.model_dump()
        assert d["total"] == 1
        assert d["page"] == 1
        assert d["per_page"] == 50
        assert len(d["items"]) == 1
        # Each item is a CritiqueResponse dict with the canonical fields.
        item = d["items"][0]
        assert "id" in item
        assert "score_overall" in item
        assert "critic_kind" in item


class TestCriticKindEnum:
    def test_enum_values_match_all_critic_kinds(self) -> None:
        """``CriticKind`` members must mirror ``ALL_CRITIC_KINDS``."""
        from app.schemas.critique import CriticKind

        enum_values = {member.value for member in CriticKind}
        assert enum_values == set(ALL_CRITIC_KINDS)

    def test_enum_is_str_subclass(self) -> None:
        """``CriticKind`` is a ``str, Enum`` so .value is a plain string."""
        from app.schemas.critique import CriticKind

        assert issubclass(CriticKind, str)
        # str equality at API boundary.
        assert CriticKind.RED_TEAM == "red_team"
        assert CriticKind.CRITIC == "critic"
        assert CriticKind.IMPROVEMENT_GENERATOR == "improvement_generator"


# ═══════════════════════════════════════════════════════════════════════════
# (B) Router tests — TestClient with PATCHED CritiqueService (no DB)
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def client_ctx():
    """Yield a TestClient with a mocked CritiqueService.

    Patches ``CritiqueService`` in ``app.api.v2.critiques`` so the
    router's ``_get_service`` dependency returns a mock. Overrides
    ``get_current_user`` + ``get_workspace_id`` so the request
    runs as a synthetic user/workspace — no JWT, no DB.
    """
    user = _make_user_sync()
    workspace_id = _new_workspace_id()

    # Build a mock service instance.
    mock_service = MagicMock()
    mock_service.list = AsyncMock(return_value=([], 0))
    mock_service.get = AsyncMock()

    # Patch the service class so _get_service() returns our mock.
    with patch.object(critiques_module, "CritiqueService") as mock_cls:
        mock_cls.return_value = mock_service

        async def _override_current_user():
            return user

        async def _override_workspace_id():
            return workspace_id

        async def _override_get_db():
            # Return a stub async session — the route never uses it
            # because CritiqueService is patched.
            yield MagicMock()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_workspace_id] = _override_workspace_id
        app.dependency_overrides[get_db] = _override_get_db

        with TestClient(app) as c:
            yield {
                "client": c,
                "user": user,
                "workspace_id": workspace_id,
                "service": mock_service,
            }

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_workspace_id, None)
        app.dependency_overrides.pop(get_db, None)


# ── List endpoint ──────────────────────────────────────────────────────────


class TestRouterListFilters:
    def test_list_filters_by_user_workspace(self, client_ctx) -> None:
        """The route must pass the request's (user_id, workspace_id) to
        the service — the workspace isolation guardrail."""
        client = client_ctx["client"]
        user = client_ctx["user"]
        ws = client_ctx["workspace_id"]
        service = client_ctx["service"]

        resp = client.get("/api/v2/critiques")
        assert resp.status_code == 200, resp.text
        service.list.assert_awaited_once()
        kwargs = service.list.await_args.kwargs
        assert kwargs["user_id"] == user.id
        assert kwargs["workspace_id"] == ws

    def test_list_passes_mission_id_filter(self, client_ctx) -> None:
        client = client_ctx["client"]
        service = client_ctx["service"]
        mission_id = uuid.uuid4()
        resp = client.get(
            f"/api/v2/critiques?mission_id={mission_id}"
        )
        assert resp.status_code == 200, resp.text
        kwargs = service.list.await_args.kwargs
        assert kwargs["mission_id"] == mission_id

    def test_list_passes_program_id_filter(self, client_ctx) -> None:
        client = client_ctx["client"]
        service = client_ctx["service"]
        program_id = uuid.uuid4()
        resp = client.get(
            f"/api/v2/critiques?program_id={program_id}"
        )
        assert resp.status_code == 200, resp.text
        kwargs = service.list.await_args.kwargs
        assert kwargs["program_id"] == program_id

    def test_list_passes_critic_kind_filter(self, client_ctx) -> None:
        client = client_ctx["client"]
        service = client_ctx["service"]
        resp = client.get(
            "/api/v2/critiques?critic_kind=red_team"
        )
        assert resp.status_code == 200, resp.text
        kwargs = service.list.await_args.kwargs
        assert kwargs["critic_kind"] == "red_team"

    def test_list_passes_min_score_filter(self, client_ctx) -> None:
        client = client_ctx["client"]
        service = client_ctx["service"]
        resp = client.get(
            "/api/v2/critiques?min_score_overall=0.7"
        )
        assert resp.status_code == 200, resp.text
        kwargs = service.list.await_args.kwargs
        assert kwargs["min_score_overall"] == 0.7

    def test_list_passes_pagination(self, client_ctx) -> None:
        """page=2, per_page=25 → offset=25, limit=25 in the service call."""
        client = client_ctx["client"]
        service = client_ctx["service"]
        resp = client.get(
            "/api/v2/critiques?page=2&per_page=25"
        )
        assert resp.status_code == 200, resp.text
        kwargs = service.list.await_args.kwargs
        # page 2, per_page 25 → offset (2-1)*25 = 25, limit 25
        assert kwargs["offset"] == 25
        assert kwargs["limit"] == 25

    def test_list_passes_pagination_default(self, client_ctx) -> None:
        """Defaults: page=1, per_page=50 → offset=0, limit=50."""
        client = client_ctx["client"]
        service = client_ctx["service"]
        resp = client.get("/api/v2/critiques")
        assert resp.status_code == 200, resp.text
        kwargs = service.list.await_args.kwargs
        assert kwargs["offset"] == 0
        assert kwargs["limit"] == 50

    def test_list_invalid_critic_kind_returns_422_envelope(
        self, client_ctx
    ) -> None:
        """Service raises CritiqueValidationError → route 422 envelope."""
        from app.services.critique_service import CritiqueValidationError

        client = client_ctx["client"]
        service = client_ctx["service"]
        service.list = AsyncMock(
            side_effect=CritiqueValidationError("invalid critic_kind='bogus'")
        )

        resp = client.get("/api/v2/critiques?critic_kind=bogus")
        # Pydantic Query() would 422 first for an out-of-enum value, but
        # "bogus" is a valid Query string — the validation happens in
        # the service. The route catches the service exception.
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["data"] is None
        assert body["error"] is not None
        assert body["error"]["code"] == "CRITIQUES_VALIDATION_ERROR"
        # The mock raised — the call was made (the service is responsible
        # for the value check).
        assert service.list.await_count == 1

    def test_list_envelope_shape(self, client_ctx) -> None:
        """The list endpoint returns the paginated envelope with all
        canonical keys (items, total, page, per_page, pages)."""
        from app.services.critique_service import CritiqueService

        client = client_ctx["client"]
        service = client_ctx["service"]
        # Seed the mock with 3 fake items.
        user = client_ctx["user"]
        ws = client_ctx["workspace_id"]
        items = [
            _make_critique_instance(
                user_id=user.id,
                workspace_id=ws,
                critic_kind="critic",
                score_overall=0.7,
            )
            for _ in range(3)
        ]
        service.list = AsyncMock(return_value=(items, 3))

        resp = client.get("/api/v2/critiques?page=1&per_page=10")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["error"] is None
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["per_page"] == 10
        # paginated() helper computes pages = ceil(total/per_page) = 1
        assert data["pages"] == 1
        assert len(data["items"]) == 3
        # Each item is a CritiqueResponse with the canonical fields.
        for it in data["items"]:
            assert "id" in it
            assert "score_overall" in it
            assert "critic_kind" in it


# ── Get endpoint ────────────────────────────────────────────────────────────


class TestRouterGet:
    def test_get_calls_service_get(self, client_ctx) -> None:
        """Get delegates to ``service.get`` with (user_id, workspace_id, critique_id)."""
        client = client_ctx["client"]
        service = client_ctx["service"]
        user = client_ctx["user"]
        ws = client_ctx["workspace_id"]
        critique_id = uuid.uuid4()
        # Mock the .get return value.
        service.get = AsyncMock(
            return_value=_make_critique_instance(
                user_id=user.id,
                workspace_id=ws,
                critique_id=critique_id,
            )
        )
        resp = client.get(f"/api/v2/critiques/{critique_id}")
        assert resp.status_code == 200, resp.text
        service.get.assert_awaited_once()
        await_args = service.get.await_args
        assert await_args is not None
        kwargs = await_args.kwargs
        assert kwargs["user_id"] == user.id
        assert kwargs["workspace_id"] == ws
        assert kwargs["critique_id"] == critique_id

    def test_get_returns_ok_envelope(self, client_ctx) -> None:
        """Successful get returns the ok envelope with a CritiqueResponse payload."""
        from app.services.critique_service import CritiqueService

        client = client_ctx["client"]
        service = client_ctx["service"]
        user = client_ctx["user"]
        ws = client_ctx["workspace_id"]
        critique_id = uuid.uuid4()
        service.get = AsyncMock(
            return_value=_make_critique_instance(
                user_id=user.id,
                workspace_id=ws,
                critique_id=critique_id,
                score_overall=0.85,
            )
        )
        resp = client.get(f"/api/v2/critiques/{critique_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["error"] is None
        assert body["data"] is not None
        assert body["data"]["id"] == str(critique_id)
        assert body["data"]["score_overall"] == 0.85

    def test_get_404_returns_envelope(self, client_ctx) -> None:
        """Unknown id returns 404 with code=CRITIQUE_NOT_FOUND (leak-avoidance)."""
        from app.services.critique_service import (
            CritiqueNotFound,
            CritiqueService,
        )

        client = client_ctx["client"]
        service = client_ctx["service"]
        service.get = AsyncMock(
            side_effect=CritiqueNotFound("critique not found")
        )
        critique_id = uuid.uuid4()
        resp = client.get(f"/api/v2/critiques/{critique_id}")
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["data"] is None
        assert body["error"] is not None
        assert body["error"]["code"] == "CRITIQUE_NOT_FOUND"
        # Envelope shape — meta present, no FastAPI {"detail"} leak.
        assert "meta" in body

    def test_get_invalid_uuid_returns_422(self, client_ctx) -> None:
        """Non-UUID critique_id is rejected at the route layer (Pydantic)."""
        client = client_ctx["client"]
        resp = client.get("/api/v2/critiques/not-a-uuid")
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["data"] is None
        assert body["error"] is not None
        # The domain-specific handler is registered, so the code must
        # be CRITIQUES_VALIDATION_ERROR (not the generic VALIDATION_ERROR).
        assert body["error"]["code"] == "CRITIQUES_VALIDATION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════
# (C) Service-level list tests — mocked AsyncSession, no live DB
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_db_for_list() -> MagicMock:
    """Build a mock DB for service.list tests.

    Two ``execute`` calls are expected: one for the count, one for the
    items. We return a flexible result that supports both via
    ``side_effect`` set per-test.
    """
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = MagicMock()  # MUST NOT be called (rule 3)
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


class TestServiceList:
    async def test_list_filters_by_user_workspace(self) -> None:
        """The mandatory (user_id, workspace_id) predicate is in the WHERE."""
        from app.services.critique_service import CritiqueService

        db = _make_mock_db_for_list()
        # execute() will be called twice (count + items). Both return
        # an empty result.
        empty_result = MagicMock()
        empty_result.scalar_one.return_value = 0
        empty_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)
        svc = CritiqueService(db)
        await svc.list(
            user_id=42,
            workspace_id="ws-99",
        )
        # Inspect the WHERE clause of the FIRST execute call (count).
        stmt = db.execute.await_args_list[0][0][0]
        compiled = str(
            stmt.compile(compile_kwargs={"literal_binds": True})
        )
        # (user_id, workspace_id) must appear in the WHERE clause.
        assert "user_id" in compiled
        assert "workspace_id" in compiled
        assert "42" in compiled
        assert "ws-99" in compiled

    async def test_list_validates_critic_kind(self) -> None:
        """An invalid critic_kind raises CritiqueValidationError."""
        from app.services.critique_service import (
            CritiqueService,
            CritiqueValidationError,
        )

        db = _make_mock_db_for_list()
        svc = CritiqueService(db)
        with pytest.raises(CritiqueValidationError):
            await svc.list(
                user_id=1,
                workspace_id="ws",
                critic_kind="bogus_kind",
            )
        # And no DB call was made.
        assert not db.execute.await_count

    async def test_list_accepts_all_critic_kinds(self) -> None:
        """Every value in ALL_CRITIC_KINDS passes validation."""
        from app.services.critique_service import CritiqueService

        db = _make_mock_db_for_list()
        empty_result = MagicMock()
        empty_result.scalar_one.return_value = 0
        empty_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)
        svc = CritiqueService(db)
        for kind in ALL_CRITIC_KINDS:
            await svc.list(
                user_id=1,
                workspace_id="ws",
                critic_kind=kind,
            )
        # Each kind triggered two execute() calls (count + items).
        assert db.execute.await_count == 2 * len(ALL_CRITIC_KINDS)

    async def test_list_validates_min_score_range_below(self) -> None:
        """min_score_overall < 0.0 raises CritiqueValidationError."""
        from app.services.critique_service import (
            CritiqueService,
            CritiqueValidationError,
        )

        db = _make_mock_db_for_list()
        svc = CritiqueService(db)
        with pytest.raises(CritiqueValidationError):
            await svc.list(
                user_id=1,
                workspace_id="ws",
                min_score_overall=-0.1,
            )

    async def test_list_validates_min_score_range_above(self) -> None:
        """min_score_overall > 1.0 raises CritiqueValidationError."""
        from app.services.critique_service import (
            CritiqueService,
            CritiqueValidationError,
        )

        db = _make_mock_db_for_list()
        svc = CritiqueService(db)
        with pytest.raises(CritiqueValidationError):
            await svc.list(
                user_id=1,
                workspace_id="ws",
                min_score_overall=1.5,
            )

    async def test_list_accepts_min_score_boundaries(self) -> None:
        """min_score_overall=0.0 and =1.0 are accepted (inclusive)."""
        from app.services.critique_service import CritiqueService

        db = _make_mock_db_for_list()
        empty_result = MagicMock()
        empty_result.scalar_one.return_value = 0
        empty_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)
        svc = CritiqueService(db)
        for boundary in (0.0, 1.0):
            await svc.list(
                user_id=1,
                workspace_id="ws",
                min_score_overall=boundary,
            )
        # No exception raised.

    async def test_list_pagination(self) -> None:
        """list() returns (items, total). total comes from the count stmt."""
        from app.services.critique_service import CritiqueService

        db = _make_mock_db_for_list()
        # Two distinct execute() results: count=7, items=3 rows.
        user_id = 1
        ws = "ws-paginate"
        items = [
            _make_critique_instance(
                user_id=user_id, workspace_id=ws
            )
            for _ in range(3)
        ]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 7
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        svc = CritiqueService(db)
        result_items, total = await svc.list(
            user_id=user_id,
            workspace_id=ws,
            limit=3,
            offset=0,
        )
        assert total == 7
        assert len(result_items) == 3
        # Two execute calls: count, then items.
        assert db.execute.await_count == 2

    async def test_list_does_not_commit(self) -> None:
        """Per services/AGENTS.md rule 3: list() must NOT call db.commit()."""
        from app.services.critique_service import CritiqueService

        db = _make_mock_db_for_list()
        empty_result = MagicMock()
        empty_result.scalar_one.return_value = 0
        empty_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)
        svc = CritiqueService(db)
        await svc.list(user_id=1, workspace_id="ws")
        assert not db.commit.called, (
            "service.list() must NOT call db.commit() — caller owns "
            "the transaction (services/AGENTS.md rule 3)"
        )

    async def test_list_optional_filters_in_where(self) -> None:
        """mission_id / program_id / critic_kind / min_score all appear in
        the WHERE clause when provided."""
        from app.services.critique_service import CritiqueService

        db = _make_mock_db_for_list()
        empty_result = MagicMock()
        empty_result.scalar_one.return_value = 0
        empty_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)
        svc = CritiqueService(db)
        mission_id = uuid.uuid4()
        program_id = uuid.uuid4()
        await svc.list(
            user_id=1,
            workspace_id="ws",
            mission_id=mission_id,
            program_id=program_id,
            critic_kind="red_team",
            min_score_overall=0.5,
        )
        # Inspect the count WHERE clause.
        stmt = db.execute.await_args_list[0][0][0]
        compiled = str(
            stmt.compile(compile_kwargs={"literal_binds": True})
        )
        # Mandatory isolation.
        assert "user_id" in compiled
        assert "workspace_id" in compiled
        # Optional filters.
        assert "mission_id" in compiled
        assert "program_id" in compiled
        assert "critic_kind" in compiled
        assert "red_team" in compiled
        assert "score_overall" in compiled
        # min_score 0.5 must show up (the bound).
        assert "0.5" in compiled
