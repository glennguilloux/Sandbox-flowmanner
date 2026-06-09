"""Tests for mission advanced routes: templates, versions, export/import."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

pytestmark = pytest.mark.integration

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")

# ── Test IDs ──────────────────────────────────────────────────────────────────

MISSION_ID = UUID("014da489-b7f5-44f7-9e89-046a05a5ab56")
TEMPLATE_ID = UUID("114da489-b7f5-44f7-9e89-046a05a5ab56")
VERSION_ID = UUID("214da489-b7f5-44f7-9e89-046a05a5ab56")
GROUP_ID = UUID("314da489-b7f5-44f7-9e89-046a05a5ab56")

# ── Test-Data Factories ──────────────────────────────────────────────────────


def make_user(user_id=1):
    return SimpleNamespace(
        id=user_id,
        email="user@example.com",
        username="sample-user",
        full_name="Sample User",
        is_active=True,
        is_admin=False,
        is_superuser=False,
        role="user",
    )


def make_mission(user_id=1, status="draft"):
    return SimpleNamespace(
        id=MISSION_ID,
        user_id=user_id,
        title="Test Mission",
        description="Test mission description",
        mission_type="general",
        status=status,
        priority="medium",
        plan=None,
        results=None,
        error_message=None,
        tokens_used=0,
        estimated_cost=0.0,
        actual_cost=0.0,
        started_at=None,
        completed_at=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def make_template(user_id=1, is_public=False):
    return SimpleNamespace(
        id=TEMPLATE_ID,
        user_id=user_id,
        name="Test Template",
        description="A test template",
        category="automation",
        is_public=is_public,
        default_plan={"nodes": [{"id": "n1", "type": "task"}]},
        default_tasks=None,
        default_constraints=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def make_version(version_number=1):
    return SimpleNamespace(
        id=VERSION_ID,
        mission_id=MISSION_ID,
        version=version_number,
        snapshot={
            "title": "Snapshotted",
            "description": "desc",
            "status": "draft",
            "nodes": [],
            "edges": [],
        },
        change_summary="Initial version",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def make_node_group(owner_id=1):
    return SimpleNamespace(
        id=GROUP_ID,
        name="Test Group",
        description="A test node group",
        group_type="parallel",
        config={"nodes": 3},
        owner_id=owner_id,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

# The advanced routes use db.execute() → result.scalars().all() / scalar_one_or_none() / scalar()
# We mock these at the AsyncMock chain level.


def _mock_scalar_result(value):
    """Return a mock that has .scalar() returning `value`."""
    mock = MagicMock()
    mock.scalar.return_value = value
    return mock


def _mock_scalars_all(items):
    """Return a mock that has .scalars().all() returning `items`."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _mock_scalar_one(item):
    """Return a mock that has .scalar_one_or_none() returning `item`."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = item
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_user():
    return make_user()


@pytest.fixture()
def auth_client(mock_db_session, mock_user):
    """TestClient with auth (user id=1) and mocked DB."""

    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def unauth_client(mock_db_session):
    """TestClient without auth (no get_current_user override)."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════════════════


class TestTemplateList:
    """GET /api/missions/advanced/templates"""

    def test_list_returns_own_and_public(self, auth_client, mock_db_session):
        """Returns user's own templates and public templates."""
        own = make_template(user_id=1, is_public=False)
        public = make_template(user_id=2, is_public=True)
        public.id = uuid4()

        mock_db_session.execute.side_effect = [
            _mock_scalars_all([own, public]),
            _mock_scalar_result(2),
        ]

        response = auth_client.get("/api/missions/advanced/templates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_by_category(self, auth_client, mock_db_session):
        """Filters by category parameter."""
        tpl = make_template()
        mock_db_session.execute.side_effect = [
            _mock_scalars_all([tpl]),
            _mock_scalar_result(1),
        ]

        response = auth_client.get(
            "/api/missions/advanced/templates?category=automation"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_list_pagination(self, auth_client, mock_db_session):
        """Returns paginated results with correct metadata."""
        mock_db_session.execute.side_effect = [
            _mock_scalars_all([]),
            _mock_scalar_result(0),
        ]

        response = auth_client.get("/api/missions/advanced/templates?page=1&per_page=5")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 5
        assert data["pages"] == 0
        assert data["items"] == []

    def test_list_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.get("/api/missions/advanced/templates")
        assert response.status_code in (401, 403)


class TestTemplateCreate:
    """POST /api/missions/advanced/templates"""

    def test_create_success(self, auth_client, mock_db_session):
        """Creates a template and returns 201."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/templates",
            json={
                "name": "New Template",
                "description": "A new one",
                "category": "data",
                "is_public": False,
                "default_plan": {"nodes": []},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Template"
        assert data["category"] == "data"

    def test_create_minimal(self, auth_client, mock_db_session):
        """Creates a template with only required fields."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/templates",
            json={"name": "Minimal Template"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Minimal Template"

    def test_create_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.post(
            "/api/missions/advanced/templates",
            json={"name": "Unauthorized"},
        )
        assert response.status_code in (401, 403)


class TestTemplateGet:
    """GET /api/missions/advanced/templates/{id}"""

    def test_get_own_template(self, auth_client, mock_db_session):
        """Retrieves user's own template."""
        tpl = make_template(user_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)

        response = auth_client.get(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 200
        assert response.json()["name"] == "Test Template"

    def test_get_public_template(self, auth_client, mock_db_session):
        """Retrieves another user's public template."""
        tpl = make_template(user_id=2, is_public=True)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)

        response = auth_client.get(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 200

    def test_get_private_template_of_other_user_returns_404(
        self, auth_client, mock_db_session
    ):
        """Cannot see another user's private template."""
        tpl = make_template(user_id=2, is_public=False)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)

        response = auth_client.get(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 404

    def test_get_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent template."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.get(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 404

    def test_get_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.get(f"/api/missions/advanced/templates/{TEMPLATE_ID}")
        assert response.status_code in (401, 403)


class TestTemplateUpdate:
    """PATCH /api/missions/advanced/templates/{id}"""

    def test_update_own_template(self, auth_client, mock_db_session):
        """Updates user's own template."""
        tpl = make_template(user_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        response = auth_client.patch(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}",
            json={"name": "Updated Name", "is_public": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    def test_update_other_user_template_returns_404(self, auth_client, mock_db_session):
        """Cannot update another user's template (404)."""
        tpl = make_template(user_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)

        response = auth_client.patch(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}",
            json={"name": "Hacked"},
        )

        assert response.status_code == 404

    def test_update_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent template."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.patch(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}",
            json={"name": "Nope"},
        )

        assert response.status_code == 404

    def test_update_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.patch(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}",
            json={"name": "Unauthorized"},
        )
        assert response.status_code in (401, 403)


class TestTemplateDelete:
    """DELETE /api/missions/advanced/templates/{id}"""

    def test_delete_own_template(self, auth_client, mock_db_session):
        """Deletes user's own template, returns 204."""
        tpl = make_template(user_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)
        mock_db_session.delete = AsyncMock()
        mock_db_session.commit = AsyncMock()

        response = auth_client.delete(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 204
        mock_db_session.delete.assert_called_once_with(tpl)

    def test_delete_other_user_template_returns_404(self, auth_client, mock_db_session):
        """Cannot delete another user's template."""
        tpl = make_template(user_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)

        response = auth_client.delete(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 404

    def test_delete_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent template."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.delete(f"/api/missions/advanced/templates/{TEMPLATE_ID}")

        assert response.status_code == 404

    def test_delete_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.delete(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}"
        )
        assert response.status_code in (401, 403)


class TestTemplateUse:
    """POST /api/missions/advanced/templates/{id}/use"""

    def test_use_own_template(self, auth_client, mock_db_session):
        """Creates a mission from own template, returns 200."""
        tpl = make_template(user_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}/use"
        )

        assert response.status_code == 200
        data = response.json()
        assert "mission_id" in data
        assert data["title"] == "Test Template"

    def test_use_public_template(self, auth_client, mock_db_session):
        """Creates a mission from another user's public template."""
        tpl = make_template(user_id=2, is_public=True)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}/use"
        )

        assert response.status_code == 200

    def test_use_private_template_of_other_user_returns_404(
        self, auth_client, mock_db_session
    ):
        """Cannot use another user's private template."""
        tpl = make_template(user_id=2, is_public=False)
        mock_db_session.execute.return_value = _mock_scalar_one(tpl)

        response = auth_client.post(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}/use"
        )

        assert response.status_code == 404

    def test_use_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent template."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.post(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}/use"
        )

        assert response.status_code == 404

    def test_use_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.post(
            f"/api/missions/advanced/templates/{TEMPLATE_ID}/use"
        )
        assert response.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Versions
# ═══════════════════════════════════════════════════════════════════════════════


class TestVersionList:
    """GET /api/missions/advanced/missions/{mission_id}/versions"""

    def test_list_versions(self, auth_client, mock_db_session):
        """Lists versions for an owned mission."""
        mission = make_mission(user_id=1)
        v1 = make_version(1)
        v2 = make_version(2)
        v2.id = uuid4()

        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),  # mission ownership check
            _mock_scalars_all([v2, v1]),  # versions query
            _mock_scalar_result(2),  # count query
        ]

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # Should be ordered by version_number desc
        assert data["items"][0]["version_number"] == 2
        assert data["items"][1]["version_number"] == 1

    def test_list_versions_not_owned_mission(self, auth_client, mock_db_session):
        """Returns 404 for mission owned by another user."""
        mission = make_mission(user_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(mission)

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions"
        )

        assert response.status_code == 404

    def test_list_versions_mission_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent mission."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions"
        )

        assert response.status_code == 404

    def test_list_versions_empty(self, auth_client, mock_db_session):
        """Returns empty list when no versions exist."""
        mission = make_mission(user_id=1)
        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),
            _mock_scalars_all([]),
            _mock_scalar_result(0),
        ]

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_versions_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions"
        )
        assert response.status_code in (401, 403)


class TestVersionCreate:
    """POST /api/missions/advanced/missions/{mission_id}/versions"""

    def test_create_first_version(self, auth_client, mock_db_session):
        """Creates version 1 when no previous versions exist."""
        mission = make_mission(user_id=1)
        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),  # mission ownership check
            _mock_scalar_result(
                None
            ),  # max version_number → None (no previous versions)
        ]
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions",
            json={
                "change_summary": "First snapshot",
                "flow_data": {"nodes": [], "edges": []},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["version_number"] == 1

    def test_create_increments_version(self, auth_client, mock_db_session):
        """Creates version N+1 after existing version N."""
        mission = make_mission(user_id=1)
        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),  # mission check
            _mock_scalar_result(5),  # max version = 5
        ]
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions",
            json={"change_summary": "Version 6"},
        )

        assert response.status_code == 201
        assert response.json()["version_number"] == 6

    def test_create_not_owned_mission(self, auth_client, mock_db_session):
        """Returns 404 for mission owned by another user."""
        mission = make_mission(user_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(mission)

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions",
            json={"change_summary": "Nope"},
        )

        assert response.status_code == 404

    def test_create_mission_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent mission."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions",
            json={"change_summary": "Nope"},
        )

        assert response.status_code == 404

    def test_create_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions",
            json={"change_summary": "Unauthorized"},
        )
        assert response.status_code in (401, 403)


class TestVersionRestore:
    """POST /api/missions/advanced/missions/{mission_id}/versions/{version_id}/restore"""

    def test_restore_success(self, auth_client, mock_db_session):
        """Restores a mission snapshot successfully."""
        mission = make_mission(user_id=1)
        version = make_version(3)
        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),  # mission check
            _mock_scalar_one(version),  # version lookup
        ]
        mock_db_session.commit = AsyncMock()

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions/{VERSION_ID}/restore"
        )

        assert response.status_code == 200
        data = response.json()
        assert "Restored to version 3" in data["message"]
        assert data["version_number"] == 3
        assert data["snapshot"] is not None

    def test_restore_version_with_null_snapshot(self, auth_client, mock_db_session):
        """Restore handles null snapshot gracefully (guard covers it)."""
        mission = make_mission(user_id=1)
        version = make_version(1)
        version.snapshot = None
        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),
            _mock_scalar_one(version),
        ]
        mock_db_session.commit = AsyncMock()

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions/{VERSION_ID}/restore"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["snapshot"] is None

    def test_restore_not_owned_mission(self, auth_client, mock_db_session):
        """Returns 404 for mission owned by another user."""
        mission = make_mission(user_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(mission)

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions/{VERSION_ID}/restore"
        )

        assert response.status_code == 404

    def test_restore_mission_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent mission."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions/{VERSION_ID}/restore"
        )

        assert response.status_code == 404

    def test_restore_version_not_found(self, auth_client, mock_db_session):
        """Returns 404 when version doesn't exist."""
        mission = make_mission(user_id=1)
        mock_db_session.execute.side_effect = [
            _mock_scalar_one(mission),
            _mock_scalar_one(None),  # version not found
        ]

        response = auth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions/{VERSION_ID}/restore"
        )

        assert response.status_code == 404

    def test_restore_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.post(
            f"/api/missions/advanced/missions/{MISSION_ID}/versions/{VERSION_ID}/restore"
        )
        assert response.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Export / Import
# ═══════════════════════════════════════════════════════════════════════════════


class TestExport:
    """GET /api/missions/advanced/missions/{mission_id}/export"""

    def test_export_owned_mission(self, auth_client, mock_db_session):
        """Exports an owned mission with correct structure."""
        mission = make_mission(user_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(mission)

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/export"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert data["mission"]["id"] == str(MISSION_ID)
        assert data["mission"]["title"] == "Test Mission"
        assert data["mission"]["status"] == "draft"

    def test_export_not_owned_mission(self, auth_client, mock_db_session):
        """Returns 404 for mission owned by another user."""
        mission = make_mission(user_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(mission)

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/export"
        )

        assert response.status_code == 404

    def test_export_mission_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent mission."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/export"
        )

        assert response.status_code == 404

    def test_export_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.get(
            f"/api/missions/advanced/missions/{MISSION_ID}/export"
        )
        assert response.status_code in (401, 403)


class TestImport:
    """POST /api/missions/advanced/missions/import"""

    def test_import_with_full_data(self, auth_client, mock_db_session):
        """Imports a mission with full export data."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/missions/import",
            json={
                "data": {
                    "version": "1.0",
                    "mission": {
                        "id": str(MISSION_ID),
                        "title": "Exported Mission",
                        "description": "From export",
                        "status": "completed",
                    },
                    "tasks": [
                        {"id": "t1", "name": "Task 1"},
                        {"id": "t2", "name": "Task 2"},
                    ],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "mission_id" in data
        assert data["title"] == "Exported Mission"
        assert data["tasks_imported"] == 2
        mock_db_session.add.assert_called_once()

    def test_import_with_title_override(self, auth_client, mock_db_session):
        """Uses title_override over the data's mission title."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/missions/import",
            json={
                "data": {
                    "mission": {"title": "Original Title"},
                    "tasks": [],
                },
                "title_override": "Overridden Title",
            },
        )

        assert response.status_code == 201
        assert response.json()["title"] == "Overridden Title"
        mock_db_session.add.assert_called_once()

    def test_import_minimal_data(self, auth_client, mock_db_session):
        """Imports with minimal data (no mission key, no tasks)."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/missions/import",
            json={"data": {}},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Imported Mission"
        assert data["tasks_imported"] == 0
        mock_db_session.add.assert_called_once()

    def test_import_partial_mission_data(self, auth_client, mock_db_session):
        """Imports with empty tasks list — tasks_imported = 0."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/missions/import",
            json={
                "data": {
                    "mission": {"title": "Solo Mission"},
                    "tasks": [],
                },
            },
        )

        assert response.status_code == 201
        assert response.json()["tasks_imported"] == 0
        mock_db_session.add.assert_called_once()

    def test_import_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.post(
            "/api/missions/advanced/missions/import",
            json={"data": {}},
        )
        assert response.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Node Groups
# ═══════════════════════════════════════════════════════════════════════════════


class TestNodeGroupList:
    """GET /api/missions/advanced/node-groups"""

    def test_list_own_groups(self, auth_client, mock_db_session):
        """Lists user's own node groups."""
        ng = make_node_group()
        mock_db_session.execute.side_effect = [
            _mock_scalars_all([ng]),
            _mock_scalar_result(1),
        ]

        response = auth_client.get("/api/missions/advanced/node-groups")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Test Group"

    def test_list_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.get("/api/missions/advanced/node-groups")
        assert response.status_code in (401, 403)


class TestNodeGroupCreate:
    """POST /api/missions/advanced/node-groups"""

    def test_create_success(self, auth_client, mock_db_session):
        """Creates a node group and returns 201."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/node-groups",
            json={
                "name": "My Node Group",
                "description": "A group of nodes",
                "group_type": "parallel",
                "config": {"nodes": 5},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Node Group"
        assert data["group_type"] == "parallel"

    def test_create_minimal(self, auth_client, mock_db_session):
        """Creates a node group with only required fields."""
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", uuid4())
                if getattr(obj, "id", None) is None
                else None
            )
        )

        response = auth_client.post(
            "/api/missions/advanced/node-groups",
            json={"name": "Minimal Group"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Minimal Group"

    def test_create_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.post(
            "/api/missions/advanced/node-groups",
            json={"name": "Unauthorized"},
        )
        assert response.status_code in (401, 403)


class TestNodeGroupGet:
    """GET /api/missions/advanced/node-groups/{id}"""

    def test_get_own_group(self, auth_client, mock_db_session):
        """Retrieves user's own node group."""
        ng = make_node_group(owner_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(ng)

        response = auth_client.get(f"/api/missions/advanced/node-groups/{GROUP_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Group"
        assert data["group_type"] == "parallel"

    def test_get_other_user_group_returns_404(self, auth_client, mock_db_session):
        """Cannot see another user's node group."""
        ng = make_node_group(owner_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(ng)

        response = auth_client.get(f"/api/missions/advanced/node-groups/{GROUP_ID}")

        assert response.status_code == 404

    def test_get_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent node group."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.get(f"/api/missions/advanced/node-groups/{GROUP_ID}")

        assert response.status_code == 404

    def test_get_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.get(f"/api/missions/advanced/node-groups/{GROUP_ID}")
        assert response.status_code in (401, 403)


class TestNodeGroupUpdate:
    """PATCH /api/missions/advanced/node-groups/{id}"""

    def test_update_own_group(self, auth_client, mock_db_session):
        """Updates user's own node group."""
        ng = make_node_group(owner_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(ng)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        response = auth_client.patch(
            f"/api/missions/advanced/node-groups/{GROUP_ID}",
            json={"name": "Updated Group", "group_type": "sequential"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Group"

    def test_update_other_user_group_returns_404(self, auth_client, mock_db_session):
        """Cannot update another user's node group."""
        ng = make_node_group(owner_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(ng)

        response = auth_client.patch(
            f"/api/missions/advanced/node-groups/{GROUP_ID}",
            json={"name": "Hacked"},
        )

        assert response.status_code == 404

    def test_update_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent node group."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.patch(
            f"/api/missions/advanced/node-groups/{GROUP_ID}",
            json={"name": "Nope"},
        )

        assert response.status_code == 404

    def test_update_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.patch(
            f"/api/missions/advanced/node-groups/{GROUP_ID}",
            json={"name": "Unauthorized"},
        )
        assert response.status_code in (401, 403)


class TestNodeGroupDelete:
    """DELETE /api/missions/advanced/node-groups/{id}"""

    def test_delete_own_group(self, auth_client, mock_db_session):
        """Deletes user's own node group, returns 204."""
        ng = make_node_group(owner_id=1)
        mock_db_session.execute.return_value = _mock_scalar_one(ng)
        mock_db_session.delete = AsyncMock()
        mock_db_session.commit = AsyncMock()

        response = auth_client.delete(f"/api/missions/advanced/node-groups/{GROUP_ID}")

        assert response.status_code == 204
        mock_db_session.delete.assert_called_once_with(ng)

    def test_delete_other_user_group_returns_404(self, auth_client, mock_db_session):
        """Cannot delete another user's node group."""
        ng = make_node_group(owner_id=2)
        mock_db_session.execute.return_value = _mock_scalar_one(ng)

        response = auth_client.delete(f"/api/missions/advanced/node-groups/{GROUP_ID}")

        assert response.status_code == 404

    def test_delete_not_found(self, auth_client, mock_db_session):
        """Returns 404 for non-existent node group."""
        mock_db_session.execute.return_value = _mock_scalar_one(None)

        response = auth_client.delete(f"/api/missions/advanced/node-groups/{GROUP_ID}")

        assert response.status_code == 404

    def test_delete_requires_auth(self, unauth_client):
        """Returns 401/403 without authentication."""
        response = unauth_client.delete(
            f"/api/missions/advanced/node-groups/{GROUP_ID}"
        )
        assert response.status_code in (401, 403)
