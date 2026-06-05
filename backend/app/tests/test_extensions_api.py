"""Integration tests for Extensions API (Task 3.5).

Covers all CRUD endpoints: list, create, update, delete.
Uses mocked DB session and user from conftest.py fixtures.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.api.deps import get_current_user
from app.main_fastapi import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extension(**overrides):
    """Return a mock Extension model instance."""
    defaults = {
        "id": "ext-test-001",
        "name": "test-extension",
        "version": "1.0.0",
        "description": "A test extension",
        "author": "TestSuite",
        "manifest": {"tools": [], "capabilities": []},
        "status": "disabled",
        "workspace_id": "1",
        "config": None,
        "created_at": "2026-06-04T00:00:00",
        "updated_at": None,
    }
    defaults.update(overrides)
    ext = MagicMock()
    for k, v in defaults.items():
        setattr(ext, k, v)
    return ext


def _mock_scalars(items):
    """Build a mock result chain: result.scalars().all() -> items."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    return mock_result


def _mock_scalar_one(item):
    """Build a mock result chain: result.scalar_one_or_none() -> item."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    return mock_result


# ---------------------------------------------------------------------------
# Tests: GET /api/extensions (list)
# ---------------------------------------------------------------------------


class TestListExtensions:
    def test_list_empty(self, test_client, mock_db_session, sample_user):
        """GET /api/extensions returns empty list when no extensions exist."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            mock_db_session.execute = AsyncMock(return_value=_mock_scalars([]))
            response = test_client.get("/api/extensions")
            assert response.status_code == 200
            data = response.json()
            assert data["extensions"] == []
            assert data["total"] == 0
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_list_with_items(self, test_client, mock_db_session, sample_user):
        """GET /api/extensions returns extensions sorted by created_at desc."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            ext1 = _make_extension(id="ext-1", name="alpha")
            ext2 = _make_extension(id="ext-2", name="beta")
            mock_db_session.execute = AsyncMock(
                return_value=_mock_scalars([ext2, ext1])
            )
            response = test_client.get("/api/extensions")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["extensions"][0]["name"] == "beta"
            assert data["extensions"][1]["name"] == "alpha"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_list_unauthenticated(self, test_client):
        """GET /api/extensions without auth returns 401."""
        response = test_client.get("/api/extensions")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests: POST /api/extensions (create)
# ---------------------------------------------------------------------------


class TestCreateExtension:
    def test_create_success(self, test_client, mock_db_session, sample_user):
        """POST /api/extensions with valid body returns 201."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            created = _make_extension(
                id="ext-new-001",
                name="greeting-ext",
                status="disabled",
            )
            mock_db_session.execute = AsyncMock(return_value=_mock_scalars([]))
            mock_db_session.flush = AsyncMock()
            mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

            # Patch Extension constructor to return our mock
            with patch("app.api.v1.extensions.Extension", return_value=created):
                response = test_client.post(
                    "/api/extensions",
                    json={
                        "name": "greeting-ext",
                        "version": "1.0.0",
                        "description": "Says hello",
                        "author": "TestSuite",
                        "manifest": {"tools": [{"name": "greet"}]},
                    },
                )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "greeting-ext"
            assert data["status"] == "disabled"
            assert data["id"] == "ext-new-001"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_create_minimal(self, test_client, mock_db_session, sample_user):
        """POST /api/extensions with only name returns 201 (defaults applied)."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            created = _make_extension(name="minimal-ext", version="1.0.0")
            mock_db_session.flush = AsyncMock()
            mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

            with patch("app.api.v1.extensions.Extension", return_value=created):
                response = test_client.post(
                    "/api/extensions",
                    json={
                        "name": "minimal-ext",
                    },
                )
            assert response.status_code == 201
            data = response.json()
            assert data["version"] == "1.0.0"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_create_missing_name(self, test_client, mock_db_session, sample_user):
        """POST /api/extensions without name returns 422 validation error."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            response = test_client.post(
                "/api/extensions",
                json={
                    "version": "1.0.0",
                },
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_create_unauthenticated(self, test_client):
        """POST /api/extensions without auth returns 401."""
        response = test_client.post(
            "/api/extensions",
            json={
                "name": "no-auth-ext",
            },
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests: PATCH /api/extensions/{extension_id} (update)
# ---------------------------------------------------------------------------


class TestUpdateExtension:
    def test_update_status(self, test_client, mock_db_session, sample_user):
        """PATCH /api/extensions/{id} with status='enabled' returns 200."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            ext = _make_extension(id="ext-upd-001", status="disabled")
            mock_db_session.execute = AsyncMock(return_value=_mock_scalar_one(ext))
            mock_db_session.flush = AsyncMock()
            mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

            response = test_client.patch(
                "/api/extensions/ext-upd-001",
                json={
                    "status": "enabled",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "ext-upd-001"
            assert ext.status == "enabled"  # model was mutated
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_update_config(self, test_client, mock_db_session, sample_user):
        """PATCH /api/extensions/{id} with config updates the config field."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            ext = _make_extension(id="ext-upd-002")
            mock_db_session.execute = AsyncMock(return_value=_mock_scalar_one(ext))
            mock_db_session.flush = AsyncMock()
            mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

            response = test_client.patch(
                "/api/extensions/ext-upd-002",
                json={
                    "config": {"api_key": "sk-test-123"},
                },
            )
            assert response.status_code == 200
            assert ext.config == {"api_key": "sk-test-123"}
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_update_not_found(self, test_client, mock_db_session, sample_user):
        """PATCH /api/extensions/{id} with invalid id returns 404."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            mock_db_session.execute = AsyncMock(return_value=_mock_scalar_one(None))
            response = test_client.patch(
                "/api/extensions/nonexistent",
                json={
                    "status": "enabled",
                },
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "Extension not found"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_update_unauthenticated(self, test_client):
        """PATCH /api/extensions/{id} without auth returns 401."""
        response = test_client.patch(
            "/api/extensions/ext-001",
            json={
                "status": "enabled",
            },
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests: DELETE /api/extensions/{extension_id}
# ---------------------------------------------------------------------------


class TestDeleteExtension:
    def test_delete_success(self, test_client, mock_db_session, sample_user):
        """DELETE /api/extensions/{id} returns 204."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            ext = _make_extension(id="ext-del-001")
            mock_db_session.execute = AsyncMock(return_value=_mock_scalar_one(ext))
            mock_db_session.delete = AsyncMock()

            response = test_client.delete("/api/extensions/ext-del-001")
            assert response.status_code == 204
            mock_db_session.delete.assert_awaited_once_with(ext)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_delete_not_found(self, test_client, mock_db_session, sample_user):
        """DELETE /api/extensions/{id} with invalid id returns 404."""
        app.dependency_overrides[get_current_user] = lambda: sample_user
        try:
            mock_db_session.execute = AsyncMock(return_value=_mock_scalar_one(None))
            response = test_client.delete("/api/extensions/nonexistent")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_delete_unauthenticated(self, test_client):
        """DELETE /api/extensions/{id} without auth returns 401."""
        response = test_client.delete("/api/extensions/ext-001")
        assert response.status_code == 401
