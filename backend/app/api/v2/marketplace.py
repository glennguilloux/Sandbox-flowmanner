"""V2 Marketplace router — exposes the existing MarketplaceService over HTTP.

The MarketplaceService (nexus/marketplace_db.py) is synchronous. This router
bridges async FastAPI routes to sync service methods via asyncio.to_thread.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
from app.services.nexus.marketplace_db import get_marketplace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace", tags=["v2-marketplace"])


# ── Request schemas ─────────────────────────────────────────────────────


class ListingCreateRequest(BaseModel):
    name: str
    description: str = ""
    listing_type: str = "tool"
    item_id: str = ""
    price: float = 0.0
    category: str = "general"
    tags: list[str] = []
    documentation_url: str | None = None
    repository_url: str | None = None
    icon_url: str | None = None


class ListingUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    category: str | None = None
    tags: list[str] | None = None
    documentation_url: str | None = None
    repository_url: str | None = None
    icon_url: str | None = None


class ReviewCreateRequest(BaseModel):
    rating: int
    title: str | None = None
    content: str | None = None
    pros: list[str] | None = None
    cons: list[str] | None = None


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/listings")
async def list_listings(
    listing_type: str | None = Query(
        None, alias="type", description="Filter by listing type: tool, capability, integration, agent"
    ),
    category: str | None = Query(None, description="Filter by category"),
    q: str | None = Query(None, description="Search query"),
    featured: bool | None = Query(None, description="Filter featured only"),
    sort: str = Query("relevance", description="Sort: relevance, popularity, rating, newest, price_low, price_high"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
):
    """List marketplace listings with filtering, search, and pagination."""
    service = get_marketplace_service()
    offset = (page - 1) * per_page

    filters: dict[str, Any] = {}
    if listing_type:
        filters["listing_type"] = listing_type
    if category:
        filters["category"] = category
    if featured is not None:
        filters["featured"] = featured

    listings = await asyncio.to_thread(
        service.search, query=q, filters=filters, sort_by=sort, limit=per_page, offset=offset
    )

    # Get total count for pagination (separate query, same filters)
    count_listings = await asyncio.to_thread(
        service.search, query=q, filters=filters, sort_by=sort, limit=10000, offset=0
    )
    total = len(count_listings)

    return ok(
        {
            "listings": [l.to_dict() for l in listings],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    )


@router.get("/listings/featured")
async def list_featured(
    limit: int = Query(5, ge=1, le=20),
    user=Depends(get_current_user),
):
    """Get featured marketplace listings."""
    service = get_marketplace_service()
    listings = await asyncio.to_thread(service.get_featured, limit=limit)
    return ok({"listings": [l.to_dict() for l in listings]})


@router.get("/listings/{listing_id}")
async def get_listing(
    listing_id: str,
    user=Depends(get_current_user),
):
    """Get a single marketplace listing by ID."""
    service = get_marketplace_service()
    listing = await asyncio.to_thread(service.get_listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing not found: {listing_id}")
    return ok(listing.to_dict())


@router.post("/listings", status_code=201)
async def create_listing(
    body: ListingCreateRequest,
    user=Depends(get_current_user),
):
    """Create a new marketplace listing."""
    service = get_marketplace_service()

    metadata = {
        "name": body.name,
        "description": body.description,
        "category": body.category,
        "tags": body.tags,
        "documentation_url": body.documentation_url,
        "repository_url": body.repository_url,
        "icon_url": body.icon_url,
    }

    try:
        if body.listing_type == "capability":
            listing = await asyncio.to_thread(
                service.list_capability,
                capability_id=body.item_id,
                metadata=metadata,
                price=body.price,
                author_id=str(user.id),
            )
        else:
            listing = await asyncio.to_thread(
                service.list_tool,
                tool_id=body.item_id,
                metadata=metadata,
                price=body.price,
                author_id=str(user.id),
            )
        return ok(listing.to_dict())
    except Exception as e:
        logger.error("Failed to create listing: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/listings/{listing_id}")
async def update_listing(
    listing_id: str,
    body: ListingUpdateRequest,
    user=Depends(get_current_user),
):
    """Update an existing marketplace listing."""
    service = get_marketplace_service()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    listing = await asyncio.to_thread(service.update_listing, listing_id, updates)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing not found: {listing_id}")
    return ok(listing.to_dict())


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: str,
    user=Depends(get_current_user),
):
    """Delete a marketplace listing."""
    service = get_marketplace_service()
    success = await asyncio.to_thread(service.delete_listing, listing_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Listing not found: {listing_id}")
    return ok({"deleted": True, "listing_id": listing_id})


@router.get("/categories")
async def list_categories(
    user=Depends(get_current_user),
):
    """Get all marketplace categories."""
    service = get_marketplace_service()
    categories = await asyncio.to_thread(service.get_categories)
    return ok({"categories": [c.to_dict() for c in categories]})


@router.post("/listings/{listing_id}/install")
async def install_listing(
    listing_id: str,
    user=Depends(get_current_user),
):
    """Install a marketplace listing for the current user."""
    service = get_marketplace_service()
    result = await asyncio.to_thread(service.install, listing_id, str(user.id))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Install failed"))
    return ok(result)


@router.delete("/listings/{listing_id}/install")
async def uninstall_listing(
    listing_id: str,
    user=Depends(get_current_user),
):
    """Uninstall a marketplace listing (placeholder — full uninstall logic TBD)."""
    # The MarketplaceService doesn't have an uninstall method yet.
    # Return 501 so the frontend knows this isn't real.
    raise HTTPException(status_code=501, detail="Uninstall not yet implemented")


@router.get("/listings/{listing_id}/reviews")
async def list_reviews(
    listing_id: str,
    user=Depends(get_current_user),
):
    """Get all reviews for a listing."""
    service = get_marketplace_service()
    reviews = await asyncio.to_thread(service.get_reviews, listing_id)
    return ok({"reviews": [r.to_dict() for r in reviews]})


@router.post("/listings/{listing_id}/reviews")
async def create_review(
    listing_id: str,
    body: ReviewCreateRequest,
    user=Depends(get_current_user),
):
    """Add a review for a listing."""
    service = get_marketplace_service()
    try:
        review = await asyncio.to_thread(
            service.rate,
            listing_id=listing_id,
            user_id=str(user.id),
            rating=body.rating,
            review=body.content,
            title=body.title,
            pros=body.pros,
            cons=body.cons,
        )
        return ok(review.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to create review: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-listings")
async def my_listings(
    user=Depends(get_current_user),
):
    """Get listings owned by the current user."""
    service = get_marketplace_service()
    listings = await asyncio.to_thread(service.get_by_author, str(user.id))
    return ok({"listings": [l.to_dict() for l in listings]})


@router.get("/my-installations")
async def my_installations(
    user=Depends(get_current_user),
):
    """Get listings installed by the current user."""
    service = get_marketplace_service()
    installations = await asyncio.to_thread(service.get_user_installations, str(user.id))
    return ok({"installations": [l.to_dict() for l in installations]})
