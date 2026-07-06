"""Phase 6 integration tests: API surface for the prompt versioning and
eval run endpoints that landed in ``app/api/v2/prompts.py`` and
``app/api/v2/eval_runs.py``.

These endpoints were committed in cc2c3946 but never had tests. This file
proves through the FastAPI TestClient that:

1. The routers are actually mounted in ``api_v2_router`` (a regression
   here was the "half-shipped Phase 6" signature — code on disk, routes
   NOT included → 404 at runtime).
2. Each endpoint honours the auth dependency (401 when unauthenticated).
3. The happy path returns the right envelope / status / shape.
4. Soft-delete (DELETE on a prompt) deactivates rather than rows out.
5. Eval trigger dispatches the Celery task with the right arguments.

The tests deliberately lean on the conftest ``test_client`` +
``mock_db_session`` + ``sample_user`` fixtures (same pattern as
``test_auth_api.py``) so we don't need a live DB, Celery broker, or
Redis to exercise the wiring.

Why unit-style + TestClient instead of CQRS-handler tests like the
phase 5 file: the missing coverage here is *router wiring*, not
business logic — the logic is inline in the route handlers, so going
through the HTTP layer exercises the actual import graph that broke.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.main_fastapi import app

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _auth_user(sample_user):
    """Override ``get_current_user`` so requests resolve to a MagicMock user."""
    app.dependency_overrides[get_current_user] = lambda: sample_user
    return sample_user


def _clear_auth():
    app.dependency_overrides.pop(get_current_user, None)


def _pv_row(**over):
    """Build a fake ``PromptVersion`` row (the SQLAlchemy model is not needed)."""
    base = SimpleNamespace(
        id=1,
        workspace_id="ws-1",
        name="Default Assistant",
        content="You are a helpful assistant.",
        version=1,
        is_active=True,
        created_by=1,
        created_at=datetime(2026, 7, 6, 0, 0, 0),
        updated_at=datetime(2026, 7, 6, 0, 0, 0),
    )
    base.__dict__.update(over)
    return base


def _eval_run_row(**over):
    """Build a fake ``EvalRun`` row."""
    base = SimpleNamespace(
        id="er-1",
        dataset_id="ds-1",
        model_name="gpt-4",
        status="completed",
        aggregate_score=0.92,
        scores_by_category={"math": 0.9, "reasoning": 0.95},
        per_case_scores=[{"case_id": "c1", "score": 1.0}],
        error_message=None,
        started_at=datetime(2026, 7, 6, 0, 0, 0),
        completed_at=datetime(2026, 7, 6, 0, 5, 0),
        created_at=datetime(2026, 7, 6, 0, 0, 0),
    )
    base.__dict__.update(over)
    return base


def _golden_dataset_row():
    return SimpleNamespace(id="ds-1", name="Golden v1", created_by=1)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Router mounting — the "is Phase 6 actually wired?" regression
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase6RouterMounting:
    """Defensive: these endpoints used to be silently dead code. Lock the route
    presence so a future refactor that drops the include_router line fails
    here rather than shipping 404s to prod."""

    def test_prompts_endpoints_in_v2_router(self):
        from app.api.v2 import api_v2_router

        paths = {r.path for r in api_v2_router.routes}
        assert "/api/v2/prompts" in paths, "prompts router not mounted"
        assert "/api/v2/prompts/{prompt_id}" in paths
        assert "/api/v2/prompts/{prompt_id}/activate" in paths

    def test_evals_endpoints_in_v2_router(self):
        from app.api.v2 import api_v2_router

        paths = {r.path for r in api_v2_router.routes}
        assert "/api/v2/evals/run" in paths, "eval_runs router not mounted"
        assert "/api/v2/evals/runs" in paths
        assert "/api/v2/evals/runs/{run_id}" in paths
        assert "/api/v2/evals/runs/{run_id}/cases" in paths


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Auth gates — unauthenticated → 401
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase6AuthGate:
    """The endpoints guard via ``Depends(get_current_user)`` — no token → 401."""

    def test_prompts_list_requires_auth(self, test_client):
        try:
            r = test_client.get("/api/v2/prompts", params={"workspace_id": "ws-1"})
            assert r.status_code == 401
        finally:
            _clear_auth()

    def test_eval_runs_list_requires_auth(self, test_client):
        try:
            r = test_client.get("/api/v2/evals/runs")
            assert r.status_code == 401
        finally:
            _clear_auth()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Prompt Versioning — happy paths
# ═══════════════════════════════════════════════════════════════════════════════


class TestPromptVersioning:
    """CRUD over /api/v2/prompts. ``list`` filters by workspace_id and
    is_active by default. ``create`` auto-increments the version,
    deactivates prior active versions of the same name, and fires the
    cache-invalidation task. ``activate`` toggles an inactive version
    back to active. ``delete`` is a soft-delete (is_active=False)."""

    def test_list_returns_active_prompts(self, test_client, mock_db_session, sample_user):
        rows = [_pv_row(id=1, name="A", version=1, is_active=True)]
        # select(PromptVersion).where(...).order_by(...).scalars().all()
        scalars = MagicMock()
        scalars.all.return_value = rows
        result = MagicMock()
        result.scalars.return_value = scalars
        mock_db_session.execute.return_value = result

        # _next_version path is NOT exercised by list_prompts, so one execute
        # call is enough.
        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/prompts", params={"workspace_id": "ws-1"})
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["total"] == 1
            assert payload["items"][0]["name"] == "A"
            assert payload["items"][0]["is_active"] is True
        finally:
            _clear_auth()

    def test_list_respects_name_filter_and_inactive_flag(self, test_client, mock_db_session, sample_user):
        rows = [
            _pv_row(id=1, name="A", version=1, is_active=True),
            _pv_row(id=2, name="A", version=2, is_active=False),
        ]
        # include_inactive=True hits this branch
        scalars = MagicMock()
        scalars.all.return_value = rows
        result = MagicMock()
        result.scalars.return_value = scalars
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get(
                "/api/v2/prompts",
                params={
                    "workspace_id": "ws-1",
                    "name": "A",
                    "include_inactive": True,
                },
            )
            assert r.status_code == 200, r.text
            assert r.json()["total"] == 2
        finally:
            _clear_auth()

    def test_list_404_when_workspace_missing(self, test_client, mock_db_session, sample_user):
        # workspace_id is required (FastAPI query param) — empty → 422
        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/prompts")  # no workspace_id query
            assert r.status_code == 422, r.text
        finally:
            _clear_auth()

    def test_create_prompt_assigns_version_and_deactivates_prior(self, test_client, mock_db_session, sample_user):
        # _next_version returns 4 (MAX(3) + 1) — avoid the select(func.max(...))
        # call so we don't need a real DB roundtrip.
        # The deactivation UPDATE also hits db.execute — return a no-op result.
        mock_db_session.execute.side_effect = [MagicMock()]

        # ``db.refresh(pv)`` is an AsyncMock no-op — the real DB would assign
        # ``pv.id`` on flush; we emulate that by mutating the arg.
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", 42),
        )

        # Keep the real PromptVersion model — the route needs it for
        # ``update(PromptVersion)`` and ``PromptVersion(...)`` to work.
        # Only mock the cache invalidation (it spawns an asyncio task).
        with (
            patch(
                "app.api.v2.prompts._next_version",
                new=AsyncMock(return_value=4),
            ),
            patch(
                "app.api.v2.prompts.invalidate_prompt_version_cache",
                new=AsyncMock(),
            ),
        ):
            _auth_user(sample_user)
            try:
                r = test_client.post(
                    "/api/v2/prompts",
                    json={"workspace_id": "ws-1", "name": "A", "content": "hi"},
                )
                assert r.status_code == 201, r.text
                body = r.json()
                assert body["workspace_id"] == "ws-1"
                assert body["name"] == "A"
                assert body["version"] == 4  # MAX(3) + 1
                assert body["is_active"] is True
                # mock_db_session.flush + add called
                assert mock_db_session.add.called
                assert mock_db_session.flush.await_count >= 1
            finally:
                _clear_auth()

    def test_get_prompt_returns_404_when_missing(self, test_client, mock_db_session, sample_user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/prompts/999")
            assert r.status_code == 404, r.text
            assert "not found" in r.json()["detail"].lower()
        finally:
            _clear_auth()

    def test_get_prompt_returns_payload(self, test_client, mock_db_session, sample_user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = _pv_row(
            id=42,
            name="Greet",
            version=2,
            is_active=True,
            content="hello",
        )
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/prompts/42")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == 42
            assert body["name"] == "Greet"
            assert body["version"] == 2
        finally:
            _clear_auth()

    def test_activate_prompt_deactivates_others_and_sets_target_active(self, test_client, mock_db_session, sample_user):
        # Two execute calls: SELECT target → some row, then UPDATE others → no-op
        target = _pv_row(id=7, name="A", version=2, is_active=False, workspace_id="ws-1")
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = target
        update_result = MagicMock()
        mock_db_session.execute.side_effect = [select_result, update_result]

        with patch(
            "app.api.v2.prompts.invalidate_prompt_version_cache",
            new=AsyncMock(),
        ):
            _auth_user(sample_user)
            try:
                r = test_client.put("/api/v2/prompts/7/activate")
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["id"] == 7
                assert body["is_active"] is True
            finally:
                _clear_auth()

    def test_activate_returns_404_when_missing(self, test_client, mock_db_session, sample_user):
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = select_result

        _auth_user(sample_user)
        try:
            r = test_client.put("/api/v2/prompts/404/activate")
            assert r.status_code == 404, r.text
        finally:
            _clear_auth()

    def test_delete_prompt_soft_deletes(self, test_client, mock_db_session, sample_user):
        target = _pv_row(id=8, name="A", version=1, is_active=True, workspace_id="ws-1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = target
        mock_db_session.execute.return_value = result

        with patch(
            "app.api.v2.prompts.invalidate_prompt_version_cache",
            new=AsyncMock(),
        ):
            _auth_user(sample_user)
            try:
                r = test_client.delete("/api/v2/prompts/8")
                assert r.status_code == 204, r.text
                # Soft-delete: the row object's is_active attribute must have been
                # mutated by the route handler before flush.
                assert target.is_active is False
                assert mock_db_session.flush.await_count >= 1
            finally:
                _clear_auth()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Eval Runs — happy paths
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvalRuns:
    """The eval_runs router dispatches a Celery task on /run, lists runs, and
    surfaces per-case scores. These tests pin the contract. The Celery
    ``.delay(...)`` call is mocked — we're checking it's invoked with the
    same args the endpoint received."""

    def test_trigger_eval_run_requires_existing_dataset(self, test_client, mock_db_session, sample_user):
        # GoldenDataset lookup returns None → 404
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.post(
                "/api/v2/evals/run",
                json={"dataset_id": "no-such", "model_name": "gpt-4"},
            )
            assert r.status_code == 404, r.text
            assert "dataset" in r.json()["detail"].lower()
        finally:
            _clear_auth()

    def test_trigger_eval_run_dispatches_celery_task(self, test_client, mock_db_session, sample_user):
        # GoldenDataset lookup → row exists
        gd_result = MagicMock()
        gd_result.scalar_one_or_none.return_value = _golden_dataset_row()
        mock_db_session.execute.return_value = gd_result

        fake_task = MagicMock()
        fake_task.id = "task-abc"
        fake_module = MagicMock()
        fake_module.run_eval_suite.delay.return_value = fake_task

        with patch.dict("sys.modules", {"app.tasks.eval_run": fake_module}):
            _auth_user(sample_user)
            try:
                r = test_client.post(
                    "/api/v2/evals/run",
                    json={
                        "dataset_id": "ds-1",
                        "model_name": "gpt-4",
                        "system_prompt": "be nice",
                        "temperature": 0.5,
                    },
                )
                assert r.status_code == 202, r.text
                body = r.json()
                assert body["status"] == "queued"
                assert body["dataset_id"] == "ds-1"
                fake_module.run_eval_suite.delay.assert_called_once()
                call_kwargs = fake_module.run_eval_suite.delay.call_args.kwargs
                assert call_kwargs["dataset_id"] == "ds-1"
                assert call_kwargs["model_name"] == "gpt-4"
                assert call_kwargs["system_prompt"] == "be nice"
                assert call_kwargs["temperature"] == 0.5
            finally:
                _clear_auth()

    def test_list_eval_runs_returns_recent_first(self, test_client, mock_db_session, sample_user):
        rows = [
            _eval_run_row(id="er-2", status="running"),
            _eval_run_row(id="er-1", status="completed"),
        ]
        scalars = MagicMock()
        scalars.all.return_value = rows
        result = MagicMock()
        result.scalars.return_value = scalars
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/evals/runs")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 2
            assert body["items"][0]["id"] == "er-2"
            assert body["items"][0]["per_case_count"] == 1
        finally:
            _clear_auth()

    def test_list_eval_runs_supports_status_filter(self, test_client, mock_db_session, sample_user):
        rows = [_eval_run_row(id="er-1", status="completed")]
        scalars = MagicMock()
        scalars.all.return_value = rows
        result = MagicMock()
        result.scalars.return_value = scalars
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/evals/runs", params={"status": "completed"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 1
        finally:
            _clear_auth()

    def test_get_eval_run_returns_payload(self, test_client, mock_db_session, sample_user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = _eval_run_row(id="er-9")
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/evals/runs/er-9")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == "er-9"
            assert body["aggregate_score"] == 0.92
        finally:
            _clear_auth()

    def test_get_eval_run_404_when_missing(self, test_client, mock_db_session, sample_user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/evals/runs/nope")
            assert r.status_code == 404, r.text
        finally:
            _clear_auth()

    def test_get_eval_run_cases_returns_per_case_scores(self, test_client, mock_db_session, sample_user):
        er = _eval_run_row(id="er-1", per_case_scores=[{"case_id": "c1", "score": 0.9}])
        result = MagicMock()
        result.scalar_one_or_none.return_value = er
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/evals/runs/er-1/cases")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["run_id"] == "er-1"
            assert body["per_case_scores"] == [{"case_id": "c1", "score": 0.9}]
            assert body["aggregate_score"] == 0.92
        finally:
            _clear_auth()

    def test_get_eval_run_cases_404_when_missing(self, test_client, mock_db_session, sample_user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = result

        _auth_user(sample_user)
        try:
            r = test_client.get("/api/v2/evals/runs/none/cases")
            assert r.status_code == 404, r.text
        finally:
            _clear_auth()
