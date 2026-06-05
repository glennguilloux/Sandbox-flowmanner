"""
Marketplace - Tool and Capability Marketplace Service

This module provides the marketplace service interface.
The actual implementation is in marketplace_db.py which uses PostgreSQL persistence.
"""

# Re-export everything from the database-backed implementation
from app.services.nexus.marketplace_db import (
    ListingStatus,
    ListingType,
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceReview,
    MarketplaceService,
    PricingModel,
    get_marketplace_service,
)

__all__ = [
    "ListingStatus",
    "ListingType",
    "MarketplaceCategory",
    "MarketplaceListing",
    "MarketplaceReview",
    "MarketplaceService",
    "PricingModel",
    "get_marketplace_service",
]
