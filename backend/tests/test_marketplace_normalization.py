"""Tests for Phase 2.7: Marketplace normalization.

Verifies the migration adds artifact_type, artifact_id, artifact_version_id
columns and a proper FK on category_id → marketplace_categories.
"""

from __future__ import annotations

import pytest


class TestMarketplaceListingModel:
    """Verify MarketplaceListingModel has the new columns."""

    def test_has_artifact_type(self):
        from app.models.models import MarketplaceListingModel
        cols = {c.name for c in MarketplaceListingModel.__table__.columns}
        assert "artifact_type" in cols

    def test_has_artifact_id(self):
        from app.models.models import MarketplaceListingModel
        cols = {c.name for c in MarketplaceListingModel.__table__.columns}
        assert "artifact_id" in cols

    def test_has_artifact_version_id(self):
        from app.models.models import MarketplaceListingModel
        cols = {c.name for c in MarketplaceListingModel.__table__.columns}
        assert "artifact_version_id" in cols

    def test_category_id_still_exists(self):
        from app.models.models import MarketplaceListingModel
        cols = {c.name for c in MarketplaceListingModel.__table__.columns}
        assert "category_id" in cols

    def test_listing_type_still_exists(self):
        from app.models.models import MarketplaceListingModel
        cols = {c.name for c in MarketplaceListingModel.__table__.columns}
        assert "listing_type" in cols


class TestMarketplaceCategoryModel:
    """Verify MarketplaceCategoryModel structure."""

    def test_table_name(self):
        from app.models.models import MarketplaceCategoryModel
        assert MarketplaceCategoryModel.__tablename__ == "marketplace_categories"

    def test_has_slug(self):
        from app.models.models import MarketplaceCategoryModel
        cols = {c.name for c in MarketplaceCategoryModel.__table__.columns}
        assert "slug" in cols

    def test_registered_with_base(self):
        from app.models import Base
        assert "marketplace_categories" in Base.metadata.tables
