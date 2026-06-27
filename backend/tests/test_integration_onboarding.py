"""Tests for Phase 6: Integration Onboarding (TTFC Optimization).

Covers:
- Template workflow definitions (structure, completeness)
- GET /api/integrations/onboarding/templates (listing, filtering)
- POST /api/integrations/onboarding/create-from-template (creation, 404)
- Alembic migration file existence and structure
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Template definitions ─────────────────────────────────────────────────


class TestTemplateDefinitions:
    """Verify the TEMPLATE_WORKFLOWS list is well-formed."""

    def test_templates_importable(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        assert isinstance(TEMPLATE_WORKFLOWS, list)
        assert len(TEMPLATE_WORKFLOWS) >= 4

    def test_each_template_has_required_fields(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        required = {
            "id",
            "name",
            "description",
            "icon",
            "required_integrations",
            "category",
            "difficulty",
            "estimated_time",
            "default_mission",
            "steps",
        }
        for t in TEMPLATE_WORKFLOWS:
            missing = required - set(t.keys())
            assert not missing, f"Template '{t.get('id')}' missing: {missing}"

    def test_each_template_has_steps(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        for t in TEMPLATE_WORKFLOWS:
            assert len(t["steps"]) >= 1, f"Template '{t['id']}' has no steps"
            for step in t["steps"]:
                assert "order" in step
                assert "title" in step
                assert "description" in step

    def test_template_ids_unique(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        ids = [t["id"] for t in TEMPLATE_WORKFLOWS]
        assert len(ids) == len(set(ids)), "Duplicate template IDs found"

    def test_default_mission_has_title(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        for t in TEMPLATE_WORKFLOWS:
            assert "title" in t["default_mission"], f"Template '{t['id']}' default_mission missing title"

    def test_required_integrations_non_empty(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        for t in TEMPLATE_WORKFLOWS:
            assert len(t["required_integrations"]) >= 1, f"Template '{t['id']}' has no required_integrations"

    def test_four_specific_templates_exist(self):
        from app.api.v1.integrations_onboarding import TEMPLATE_WORKFLOWS

        ids = {t["id"] for t in TEMPLATE_WORKFLOWS}
        expected = {"star-your-repos", "slack-daily-digest", "notion-meeting-notes", "error-alert-to-slack"}
        assert expected.issubset(ids), f"Missing templates: {expected - ids}"


# ── List templates endpoint ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestListOnboardingTemplates:
    """Tests for GET /api/integrations/onboarding/templates."""

    async def test_returns_all_templates_without_filter(self):
        from app.api.v1.integrations_onboarding import (
            TEMPLATE_WORKFLOWS,
            list_onboarding_templates,
        )

        mock_user = MagicMock()
        result = await list_onboarding_templates(integrations=None, user=mock_user)

        assert result.total == len(TEMPLATE_WORKFLOWS)
        assert len(result.templates) == len(TEMPLATE_WORKFLOWS)

    async def test_filters_by_connected_integrations(self):
        from app.api.v1.integrations_onboarding import list_onboarding_templates

        mock_user = MagicMock()
        # Only github is connected — should return "star-your-repos" (github only)
        # and "error-alert-to-slack" (github + slack) only if slack is also connected
        result = await list_onboarding_templates(integrations="github", user=mock_user)

        # star-your-repos requires only github
        template_ids = [t.id for t in result.templates]
        assert "star-your-repos" in template_ids
        # slack-daily-digest requires slack AND github — should NOT be in results
        assert "slack-daily-digest" not in template_ids
        assert "error-alert-to-slack" not in template_ids

    async def test_filters_with_multiple_integrations(self):
        from app.api.v1.integrations_onboarding import list_onboarding_templates

        mock_user = MagicMock()
        result = await list_onboarding_templates(integrations="github,slack", user=mock_user)

        template_ids = [t.id for t in result.templates]
        assert "star-your-repos" in template_ids
        assert "slack-daily-digest" in template_ids
        assert "error-alert-to-slack" in template_ids

    async def test_empty_filter_returns_nothing(self):
        from app.api.v1.integrations_onboarding import list_onboarding_templates

        mock_user = MagicMock()
        result = await list_onboarding_templates(integrations="nonexistent-service", user=mock_user)

        assert result.total == 0
        assert len(result.templates) == 0

    async def test_response_schema_matches_pydantic(self):
        from app.api.v1.integrations_onboarding import (
            TemplateListResponse,
            list_onboarding_templates,
        )

        mock_user = MagicMock()
        result = await list_onboarding_templates(integrations=None, user=mock_user)

        assert isinstance(result, TemplateListResponse)
        # Verify it serializes without error
        serialized = result.model_dump()
        assert "templates" in serialized
        assert "total" in serialized


# ── Create from template endpoint ─────────────────────────────────────────


@pytest.mark.asyncio
class TestCreateFromTemplate:
    """Tests for POST /api/integrations/onboarding/create-from-template."""

    async def test_creates_mission_from_template(self):
        from app.api.v1.integrations_onboarding import (
            CreateFromTemplateRequest,
            create_mission_from_template,
        )

        mock_user = MagicMock()
        mock_user.id = 42
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is sync in SQLAlchemy
        mock_db.refresh = AsyncMock(return_value=None)

        payload = CreateFromTemplateRequest(template_id="star-your-repos")
        result = await create_mission_from_template(payload=payload, user=mock_user, db=mock_db)

        assert result.template_id == "star-your-repos"
        assert result.title == "Star repos in organization"
        assert result.status == "pending"
        assert result.mission_id  # UUID string
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_returns_404_for_unknown_template(self):
        from fastapi import HTTPException

        from app.api.v1.integrations_onboarding import (
            CreateFromTemplateRequest,
            create_mission_from_template,
        )

        mock_user = MagicMock()
        mock_db = AsyncMock()

        payload = CreateFromTemplateRequest(template_id="nonexistent-template")
        with pytest.raises(HTTPException) as exc_info:
            await create_mission_from_template(payload=payload, user=mock_user, db=mock_db)
        assert exc_info.value.status_code == 404
        assert "nonexistent-template" in str(exc_info.value.detail)

    async def test_mission_has_template_metadata_in_constraints(self):
        from app.api.v1.integrations_onboarding import (
            CreateFromTemplateRequest,
            create_mission_from_template,
        )

        mock_user = MagicMock()
        mock_user.id = 42
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is sync in SQLAlchemy
        mock_db.refresh = AsyncMock(return_value=None)

        payload = CreateFromTemplateRequest(template_id="slack-daily-digest")
        await create_mission_from_template(payload=payload, user=mock_user, db=mock_db)

        mission = mock_db.add.call_args[0][0]
        assert mission.constraints is not None
        assert mission.constraints["template_id"] == "slack-daily-digest"
        assert "github" in mission.constraints["required_integrations"]
        assert "slack" in mission.constraints["required_integrations"]
        assert len(mission.constraints["steps"]) == 3


# ── Router registration ──────────────────────────────────────────────────


class TestRouterRegistration:
    """Verify the onboarding router is registered in the v1 API."""

    def test_router_importable(self):
        from app.api.v1.integrations_onboarding import router

        assert router is not None

    def test_router_has_expected_prefix(self):
        from app.api.v1.integrations_onboarding import router

        assert router.prefix == "/integrations/onboarding"

    def test_router_imported_in_init(self):
        """The __init__.py should have a variable for the onboarding router."""
        init_path = Path(__file__).parent.parent / "app" / "api" / "v1" / "__init__.py"
        source = init_path.read_text()
        assert "integrations_onboarding" in source


# ── Migration ─────────────────────────────────────────────────────────────


class TestOnboardingFlagMigration:
    """Verify the feature flag migration exists and is well-formed."""

    MIGRATION_FILE = "20260627_integration_onboarding_flag.py"

    def test_migration_file_exists(self):
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / self.MIGRATION_FILE
        assert migration_path.exists(), f"Migration file not found at {migration_path}"

    def test_migration_has_correct_structure(self):
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / self.MIGRATION_FILE
        source = migration_path.read_text()
        assert "revision: str = " in source
        assert "down_revision: str | None = " in source
        assert "def upgrade()" in source
        assert "def downgrade()" in source
        assert "integration_onboarding_v1" in source
        assert "ON CONFLICT" in source  # idempotent
        assert "DELETE FROM feature_flags" in source  # downgrade

    def test_migration_down_revision_matches_latest(self):
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / self.MIGRATION_FILE
        source = migration_path.read_text()
        assert "integration_status_page_001" in source  # down_revision
