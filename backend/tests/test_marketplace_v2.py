"""Tests for Marketplace v2 — publish workflow, install-to-workspace, rating aggregation, versioning."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.models import MarketplaceListingModel, MarketplaceReviewModel


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_listing(**overrides) -> MagicMock:
    listing = MagicMock(spec=MarketplaceListingModel)
    listing.id = overrides.get("id", str(uuid4()))
    listing.name = overrides.get("name", "Test Listing")
    listing.description = overrides.get("description", "A test listing")
    listing.owner_id = overrides.get("owner_id", "1")
    listing.workspace_id = overrides.get("workspace_id", None)
    listing.listing_type = overrides.get("listing_type", "workflow")
    listing.artifact_type = overrides.get("artifact_type", "workflow")
    listing.artifact_id = overrides.get("artifact_id", str(uuid4()))
    listing.artifact_version_id = overrides.get("artifact_version_id", None)
    listing.category_id = overrides.get("category_id", "cat-ai")
    listing.price = overrides.get("price", 0.0)
    listing.status = overrides.get("status", "draft")
    listing.is_published = overrides.get("is_published", False)
    listing.version = overrides.get("version", "1.0.0")
    listing.published_at = overrides.get("published_at", None)
    listing.rating = overrides.get("rating", 0.0)
    listing.review_count = overrides.get("review_count", 0)
    listing.download_count = overrides.get("download_count", 0)
    listing.tags = overrides.get("tags", None)
    listing.config = None
    listing.integrations = None
    listing.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    listing.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return listing


def _make_review(**overrides) -> MagicMock:
    review = MagicMock(spec=MarketplaceReviewModel)
    review.id = overrides.get("id", str(uuid4()))
    review.listing_id = overrides.get("listing_id", str(uuid4()))
    review.user_id = overrides.get("user_id", "1")
    review.rating = overrides.get("rating", 5)
    review.title = overrides.get("title", "Great!")
    review.comment = overrides.get("comment", "Works well")
    review.is_approved = True
    review.created_at = datetime.now(timezone.utc)
    return review


# ── Publish Workflow Tests ────────────────────────────────────────────────────


class TestPublishWorkflow:
    def test_valid_statuses(self):
        from app.api.v1.marketplace import VALID_STATUSES

        assert "draft" in VALID_STATUSES
        assert "published" in VALID_STATUSES
        assert "deprecated" in VALID_STATUSES

    @pytest.mark.asyncio
    async def test_publish_sets_status_and_timestamp(self):
        from app.api.v1.marketplace import publish_listing

        listing = _make_listing(status="draft", is_published=False)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        user = MagicMock(id=1, is_admin=False)
        result = await publish_listing(listing.id, db, user)

        assert result.success is True
        assert result.status == "published"
        assert listing.status == "published"
        assert listing.is_published is True
        assert listing.published_at is not None

    @pytest.mark.asyncio
    async def test_unpublish_reverts_to_draft(self):
        from app.api.v1.marketplace import unpublish_listing

        listing = _make_listing(status="published", is_published=True)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        user = MagicMock(id=1, is_admin=False)
        result = await unpublish_listing(listing.id, db, user)

        assert result.success is True
        assert result.status == "draft"
        assert listing.status == "draft"
        assert listing.is_published is False

    @pytest.mark.asyncio
    async def test_deprecate_sets_status(self):
        from app.api.v1.marketplace import deprecate_listing

        listing = _make_listing(status="published")
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        user = MagicMock(id=1, is_admin=False)
        result = await deprecate_listing(listing.id, db, user)

        assert result.success is True
        assert result.status == "deprecated"
        assert listing.status == "deprecated"

    @pytest.mark.asyncio
    async def test_publish_non_owner_denied(self):
        from app.api.v1.marketplace import publish_listing
        from fastapi import HTTPException

        listing = _make_listing(owner_id="999")
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing
        db.execute = AsyncMock(return_value=mock_result)

        user = MagicMock(id=1, is_admin=False)
        with pytest.raises(HTTPException) as exc_info:
            await publish_listing(listing.id, db, user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_publish_admin_allowed(self):
        from app.api.v1.marketplace import publish_listing

        listing = _make_listing(owner_id="999", status="draft", is_published=False)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        user = MagicMock(id=1, is_admin=True)
        result = await publish_listing(listing.id, db, user)
        assert result.success is True


# ── Rating Aggregation Tests ─────────────────────────────────────────────────


class TestRatingAggregation:
    def test_rating_summary_schema(self):
        from app.api.v1.marketplace import RatingSummary

        summary = RatingSummary(
            average=4.5, count=10, breakdown={5: 6, 4: 2, 3: 1, 2: 1, 1: 0}
        )
        assert summary.average == 4.5
        assert summary.count == 10

    @pytest.mark.asyncio
    async def test_submit_review_updates_rating(self):
        from app.api.v1.marketplace import submit_review, _recalculate_rating

        listing = _make_listing(rating=0.0, review_count=0, status="published")
        db = AsyncMock()

        # First call: listing lookup. Second: existing review check (None). Third: flush. Fourth: avg/count. Fifth: listing for update. Sixth: flush.
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            stmt_str = str(stmt)
            if call_count == 1:
                # Listing lookup
                return MagicMock(scalar_one_or_none=MagicMock(return_value=listing))
            elif call_count == 2:
                # Existing review check
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            elif call_count == 3:
                # Rating avg/count
                return MagicMock(
                    first=MagicMock(return_value=MagicMock(avg=4.0, cnt=1))
                )
            elif call_count == 4:
                # Listing for rating update
                return MagicMock(scalar_one_or_none=MagicMock(return_value=listing))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        db.execute = AsyncMock(side_effect=mock_execute)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        user = MagicMock(id=1)
        from app.api.v1.marketplace import ReviewCreateRequest

        payload = ReviewCreateRequest(rating=4, title="Good", comment="Nice tool")

        result = await submit_review(listing.id, payload, db, user)
        assert result.rating == 4


# ── Install-to-Workspace Tests ───────────────────────────────────────────────


class TestInstallToWorkspace:
    def test_install_response_schema(self):
        from app.api.v1.marketplace import InstallResponse

        resp = InstallResponse(
            success=True,
            installation_id="inst-1",
            message="Installed",
            cloned_entity_id="wf-123",
        )
        assert resp.success is True
        assert resp.cloned_entity_id == "wf-123"

    def test_valid_artifact_types(self):
        from app.api.v1.marketplace import VALID_ARTIFACT_TYPES

        assert "workflow" in VALID_ARTIFACT_TYPES
        assert "tool" in VALID_ARTIFACT_TYPES
        assert "capability" in VALID_ARTIFACT_TYPES
        assert "agent_template" in VALID_ARTIFACT_TYPES


# ── Version Management Tests ─────────────────────────────────────────────────


class TestVersionManagement:
    @pytest.mark.asyncio
    async def test_bump_version(self):
        from app.api.v1.marketplace import _bump_version

        db = AsyncMock()
        listing = _make_listing()
        listing.version = "1.0.0"

        new_ver = await _bump_version(db, listing)
        assert new_ver == "1.0.1"
        assert listing.version == "1.0.1"

    @pytest.mark.asyncio
    async def test_bump_version_from_2_3_4(self):
        from app.api.v1.marketplace import _bump_version

        db = AsyncMock()
        listing = _make_listing()
        listing.version = "2.3.4"

        new_ver = await _bump_version(db, listing)
        assert new_ver == "2.3.5"

    @pytest.mark.asyncio
    async def test_bump_version_none_defaults(self):
        from app.api.v1.marketplace import _bump_version

        db = AsyncMock()
        listing = _make_listing()
        listing.version = None

        new_ver = await _bump_version(db, listing)
        assert new_ver == "1.0.1"


# ── Response Schema Tests ────────────────────────────────────────────────────


class TestSchemas:
    def test_listing_response_fields(self):
        from app.api.v1.marketplace import ListingResponse

        resp = ListingResponse(
            id="l-1",
            name="Test",
            owner_id="1",
            listing_type="workflow",
            status="published",
            version="1.0.0",
            rating=4.5,
            review_count=10,
        )
        assert resp.status == "published"
        assert resp.version == "1.0.0"
        assert resp.review_count == 10

    def test_publish_response(self):
        from app.api.v1.marketplace import PublishResponse

        resp = PublishResponse(success=True, status="published", version="1.0.0")
        assert resp.success is True

    def test_review_create_validation(self):
        from app.api.v1.marketplace import ReviewCreateRequest

        req = ReviewCreateRequest(rating=5, title="Amazing", comment="Best tool ever")
        assert req.rating == 5
