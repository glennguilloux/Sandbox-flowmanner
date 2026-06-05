"""Marketplace v2 API — publish workflow, install-to-workspace, ratings, versioning.

Changes from v1:
- Publish workflow: draft → published → deprecated (owner-only)
- Install-to-workspace: clones workflow artifact into user's workspace
- Rating aggregation: auto-computes avg from reviews
- Version management: tracks listing versions, bumps on artifact update
- Workspace scoping: listings belong to a workspace
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.models import (
    MarketplaceCategoryModel,
    MarketplaceListingModel,
    MarketplaceReviewModel,
    UserInstallationModel,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

VALID_STATUSES = ("draft", "published", "deprecated")
VALID_ARTIFACT_TYPES = ("tool", "capability", "agent_template", "workflow", "plugin")


# ── Schemas ──────────────────────────────────────────────────────────────────


class ListingResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    owner_id: str
    workspace_id: str | None = None
    listing_type: str
    artifact_type: str | None = None
    artifact_id: str | None = None
    artifact_version_id: str | None = None
    category_id: str | None = None
    price: float = 0.0
    status: str = "draft"
    version: str | None = None
    published_at: str | None = None
    rating: float = 0.0
    review_count: int = 0
    download_count: int = 0
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""


class ListingCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    listing_type: str = "template"
    artifact_type: str | None = None
    artifact_id: str | None = None
    category_id: str | None = None
    price: float = 0.0
    tags: list[str] = []


class ListingUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: str | None = None
    price: float | None = None
    tags: list[str] | None = None


class ReviewResponse(BaseModel):
    id: str
    listing_id: str
    user_id: str
    rating: int
    title: str | None = None
    comment: str | None = None
    created_at: str = ""


class ReviewCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str | None = None
    comment: str | None = None


class ListResponse(BaseModel):
    items: list[ListingResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class InstallResponse(BaseModel):
    success: bool
    installation_id: str
    message: str | None = None
    cloned_entity_id: str | None = None


class PublishResponse(BaseModel):
    success: bool
    status: str
    published_at: str | None = None
    version: str | None = None


class RatingSummary(BaseModel):
    average: float
    count: int
    breakdown: dict[int, int] = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_listing_response(m: MarketplaceListingModel) -> ListingResponse:
    tags = []
    if m.tags:
        try:
            tags = json.loads(m.tags) if isinstance(m.tags, str) else m.tags
        except (json.JSONDecodeError, TypeError):
            tags = []
    return ListingResponse(
        id=m.id,
        name=m.name,
        description=m.description,
        owner_id=m.owner_id,
        workspace_id=m.workspace_id,
        listing_type=m.listing_type,
        artifact_type=m.artifact_type,
        artifact_id=m.artifact_id,
        artifact_version_id=m.artifact_version_id,
        category_id=m.category_id,
        price=m.price,
        status=m.status or ("published" if m.is_published else "draft"),
        version=m.version,
        published_at=m.published_at.isoformat() if m.published_at else None,
        rating=m.rating,
        review_count=m.review_count,
        download_count=m.download_count,
        tags=tags,
        created_at=m.created_at.isoformat() if m.created_at else "",
        updated_at=m.updated_at.isoformat() if m.updated_at else "",
    )


async def _recalculate_rating(db: AsyncSession, listing_id: str) -> None:
    """Recalculate average rating and review count for a listing."""
    result = await db.execute(
        select(
            func.avg(MarketplaceReviewModel.rating).label("avg"),
            func.count(MarketplaceReviewModel.id).label("cnt"),
        ).where(MarketplaceReviewModel.listing_id == listing_id)
    )
    row = result.first()
    listing = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = listing.scalar_one_or_none()
    if listing:
        listing.rating = round(float(row.avg or 0), 2)
        listing.review_count = int(row.cnt or 0)
        await db.flush()


async def _bump_version(db: AsyncSession, listing: MarketplaceListingModel) -> str:
    """Bump the patch version of a listing (e.g. 1.0.0 → 1.0.1)."""
    current = listing.version or "1.0.0"
    parts = current.split(".")
    try:
        patch = int(parts[2]) + 1 if len(parts) >= 3 else 1
        parts = (
            (parts[0], parts[1], str(patch))
            if len(parts) >= 2
            else ("1", "0", str(patch))
        )
    except (ValueError, IndexError):
        parts = ("1", "0", "1")
    new_version = ".".join(parts)
    listing.version = new_version
    return new_version


# ── Listings CRUD ────────────────────────────────────────────────────────────


@router.get("/listings", response_model=ListResponse)
async def list_listings(
    search: str | None = None,
    listing_type: str | None = None,
    category: str | None = None,
    status: str | None = None,
    sort: str = "newest",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List marketplace listings with filtering and sorting."""
    base = select(MarketplaceListingModel)
    count_base = select(func.count(MarketplaceListingModel.id))

    # Default: only published for non-owners
    filter_status = status or "published"
    base = base.where(MarketplaceListingModel.status == filter_status)
    count_base = count_base.where(MarketplaceListingModel.status == filter_status)

    if search:
        base = base.where(MarketplaceListingModel.name.ilike(f"%{search}%"))
        count_base = count_base.where(MarketplaceListingModel.name.ilike(f"%{search}%"))
    if listing_type:
        base = base.where(MarketplaceListingModel.listing_type == listing_type)
        count_base = count_base.where(
            MarketplaceListingModel.listing_type == listing_type
        )
    if category:
        base = base.where(MarketplaceListingModel.category_id == category)
        count_base = count_base.where(MarketplaceListingModel.category_id == category)

    total = (await db.execute(count_base)).scalar() or 0

    # Sort
    if sort == "rating":
        base = base.order_by(MarketplaceListingModel.rating.desc())
    elif sort == "popular":
        base = base.order_by(MarketplaceListingModel.download_count.desc())
    elif sort == "name":
        base = base.order_by(MarketplaceListingModel.name.asc())
    else:
        base = base.order_by(MarketplaceListingModel.created_at.desc())

    offset = (page - 1) * per_page
    result = await db.execute(base.offset(offset).limit(per_page))
    items = [_to_listing_response(m) for m in result.scalars().all()]

    return ListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
    )


@router.get("/listings/featured", response_model=list[ListingResponse])
async def get_featured_listings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get top published listings by rating."""
    result = await db.execute(
        select(MarketplaceListingModel)
        .where(MarketplaceListingModel.status == "published")
        .order_by(MarketplaceListingModel.rating.desc())
        .limit(6)
    )
    return [_to_listing_response(m) for m in result.scalars().all()]


@router.get("/listings/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single listing by ID."""
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _to_listing_response(listing)


@router.post(
    "/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED
)
async def create_listing(
    payload: ListingCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """Create a new marketplace listing (starts as draft)."""
    if payload.artifact_type and payload.artifact_type not in VALID_ARTIFACT_TYPES:
        raise HTTPException(400, f"Invalid artifact_type: {VALID_ARTIFACT_TYPES}")

    listing = MarketplaceListingModel(
        id=str(uuid4()),
        name=payload.name,
        description=payload.description,
        owner_id=str(user.id),
        workspace_id=workspace_id,
        listing_type=payload.listing_type,
        artifact_type=payload.artifact_type,
        artifact_id=payload.artifact_id,
        category_id=payload.category_id,
        price=payload.price,
        status="draft",
        is_published=False,
        version="1.0.0",
        tags=json.dumps(payload.tags) if payload.tags else None,
    )
    db.add(listing)
    await db.flush()
    await db.refresh(listing)
    return _to_listing_response(listing)


@router.patch("/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: str,
    payload: ListingUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a listing. Only the owner or admin can update."""
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.owner_id != str(user.id) and not user.is_admin:
        raise HTTPException(403, detail="Not authorized")

    changed = False
    if payload.name is not None:
        listing.name = payload.name
        changed = True
    if payload.description is not None:
        listing.description = payload.description
        changed = True
    if payload.category_id is not None:
        listing.category_id = payload.category_id
        changed = True
    if payload.price is not None:
        listing.price = payload.price
        changed = True
    if payload.tags is not None:
        listing.tags = json.dumps(payload.tags)
        changed = True

    # Bump version only on actual content change
    if changed:
        await _bump_version(db, listing)

    await db.flush()
    await db.refresh(listing)
    return _to_listing_response(listing)


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a listing. Only the owner or admin can delete."""
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.owner_id != str(user.id) and not user.is_admin:
        raise HTTPException(403, detail="Not authorized")

    await db.delete(listing)
    await db.flush()
    return {"status": "deleted"}


# ── Publish Workflow ─────────────────────────────────────────────────────────


@router.post("/listings/{listing_id}/publish", response_model=PublishResponse)
async def publish_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Publish a listing (draft → published). Owner-only."""
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.owner_id != str(user.id) and not user.is_admin:
        raise HTTPException(403, detail="Not authorized")
    if listing.status == "published":
        return PublishResponse(
            success=True,
            status="published",
            published_at=(
                listing.published_at.isoformat() if listing.published_at else None
            ),
            version=listing.version,
        )

    listing.status = "published"
    listing.is_published = True
    listing.published_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(listing)

    logger.info(
        "marketplace_listing_published listing_id=%s version=%s",
        listing_id,
        listing.version,
    )
    return PublishResponse(
        success=True,
        status="published",
        published_at=listing.published_at.isoformat(),
        version=listing.version,
    )


@router.post("/listings/{listing_id}/unpublish", response_model=PublishResponse)
async def unpublish_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Unpublish a listing (published → draft). Owner-only."""
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.owner_id != str(user.id) and not user.is_admin:
        raise HTTPException(403, detail="Not authorized")

    listing.status = "draft"
    listing.is_published = False
    await db.flush()
    await db.refresh(listing)

    return PublishResponse(success=True, status="draft", version=listing.version)


@router.post("/listings/{listing_id}/deprecate", response_model=PublishResponse)
async def deprecate_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Deprecate a listing (published → deprecated). Owner-only."""
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.owner_id != str(user.id) and not user.is_admin:
        raise HTTPException(403, detail="Not authorized")

    listing.status = "deprecated"
    await db.flush()
    await db.refresh(listing)

    return PublishResponse(success=True, status="deprecated", version=listing.version)


# ── Install-to-Workspace ─────────────────────────────────────────────────────


@router.post("/listings/{listing_id}/install", response_model=InstallResponse)
async def install_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    """Install a listing into the user's workspace.

    For workflow artifacts: clones the workflow into the workspace.
    For other artifacts: records the installation.
    """
    result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.status != "published":
        raise HTTPException(400, detail="Listing is not published")

    # Check existing installation
    existing = await db.execute(
        select(UserInstallationModel).where(
            UserInstallationModel.user_id == str(user.id),
            UserInstallationModel.listing_id == listing.id,
        )
    )
    if existing.scalar_one_or_none():
        return InstallResponse(
            success=True,
            installation_id="",
            message="Already installed",
        )

    cloned_entity_id = None
    plugin_id = None

    # Clone workflow artifact into workspace
    if listing.artifact_type == "workflow" and listing.artifact_id:
        from app.models.graph import GraphWorkflow
        from app.services.graph_service import get_graph_workflow

        source_wf = await get_graph_workflow(db, listing.artifact_id)
        if source_wf:
            new_wf = GraphWorkflow(
                id=str(uuid4()),
                name=f"{source_wf.name} (from marketplace)",
                description=source_wf.description,
                graph_definition=source_wf.graph_definition,
                user_id=user.id,
                workspace_id=workspace_id,
            )
            db.add(new_wf)
            await db.flush()
            cloned_entity_id = new_wf.id

    # Install plugin artifact via PluginRuntime (Phase 9.3)
    if listing.artifact_type == "plugin":
        from pathlib import Path as _Path

        from app.models.plugin_models import InstalledPlugin as _IP
        from app.services.plugin_runtime import get_plugin_runtime

        runtime = get_plugin_runtime()
        ws = workspace_id or str(user.id)

        # Check if plugin already installed from this listing in this workspace
        already = await db.execute(
            select(_IP).where(
                _IP.listing_id == listing.id,
                _IP.workspace_id == ws,
            )
        )
        existing_plugin = already.scalar_one_or_none()
        if existing_plugin:
            plugin_id = existing_plugin.id
        else:
            # The listing.artifact_id stores the path to the .fmp package
            storage_path = listing.artifact_id
            if storage_path and _Path(storage_path).exists():
                try:
                    plugin_row = await runtime.install(
                        db,
                        fmp_path=_Path(storage_path),
                        workspace_id=ws,
                        source="marketplace",
                        listing_id=listing.id,
                    )
                    plugin_id = plugin_row.id
                    logger.info(
                        "marketplace_plugin_installed listing_id=%s plugin_id=%s",
                        listing_id,
                        plugin_id,
                    )
                except Exception as e:
                    logger.error(
                        "Plugin install failed for listing %s: %s", listing_id, e
                    )
                    raise HTTPException(400, f"Plugin install failed: {e}")
            else:
                raise HTTPException(
                    400,
                    "Plugin package not available. "
                    "The publisher must upload a .fmp before install is possible.",
                )

    # Record installation
    installation = UserInstallationModel(
        id=str(uuid4()),
        user_id=str(user.id),
        listing_id=listing.id,
    )
    db.add(installation)
    listing.download_count += 1
    await db.flush()
    await db.refresh(installation)

    logger.info(
        "marketplace_install listing_id=%s user_id=%s cloned=%s plugin=%s",
        listing_id,
        user.id,
        cloned_entity_id,
        plugin_id,
    )
    return InstallResponse(
        success=True,
        installation_id=installation.id,
        message="Installed successfully",
        cloned_entity_id=cloned_entity_id,
    )


@router.delete("/listings/{listing_id}/install")
async def uninstall_listing(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Uninstall a listing."""
    result = await db.execute(
        select(UserInstallationModel).where(
            UserInstallationModel.user_id == str(user.id),
            UserInstallationModel.listing_id == listing_id,
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        raise HTTPException(404, detail="Installation not found")

    await db.delete(installation)

    # Decrement download count
    listing_result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = listing_result.scalar_one_or_none()
    if listing:
        listing.download_count = max(0, listing.download_count - 1)

    await db.flush()
    return {"status": "uninstalled"}


@router.get("/my-listings", response_model=ListResponse)
async def get_my_listings(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List current user's marketplace listings (any status)."""
    base = select(MarketplaceListingModel).where(
        MarketplaceListingModel.owner_id == str(user.id)
    )
    count_base = select(func.count(MarketplaceListingModel.id)).where(
        MarketplaceListingModel.owner_id == str(user.id)
    )
    total = (await db.execute(count_base)).scalar() or 0
    offset = (page - 1) * per_page
    result = await db.execute(
        base.order_by(MarketplaceListingModel.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = [_to_listing_response(m) for m in result.scalars().all()]
    return ListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
    )


@router.get("/my-installations")
async def get_my_installations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List current user's installations."""
    count_base = select(func.count(UserInstallationModel.id)).where(
        UserInstallationModel.user_id == str(user.id)
    )
    total = (await db.execute(count_base)).scalar() or 0

    base = (
        select(UserInstallationModel)
        .where(UserInstallationModel.user_id == str(user.id))
        .order_by(UserInstallationModel.installed_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(base)
    installations = []
    for inst in result.scalars().all():
        lr = await db.execute(
            select(MarketplaceListingModel).where(
                MarketplaceListingModel.id == inst.listing_id
            )
        )
        listing = lr.scalar_one_or_none()
        installations.append(
            {
                "id": inst.id,
                "listing_id": inst.listing_id,
                "listing_name": listing.name if listing else "Unknown",
                "installed_at": (
                    inst.installed_at.isoformat() if inst.installed_at else ""
                ),
                "version": listing.version if listing else None,
            }
        )

    return {
        "installations": installations,
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_more": (page * per_page) < total,
    }


# ── Reviews & Ratings ────────────────────────────────────────────────────────


@router.get("/listings/{listing_id}/reviews")
async def get_reviews(
    listing_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get reviews for a listing with rating breakdown."""
    listing_result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    if not listing_result.scalar_one_or_none():
        raise HTTPException(404, detail="Listing not found")

    count_q = select(func.count(MarketplaceReviewModel.id)).where(
        MarketplaceReviewModel.listing_id == listing_id
    )
    total = (await db.execute(count_q)).scalar() or 0

    # Rating breakdown
    breakdown_result = await db.execute(
        select(MarketplaceReviewModel.rating, func.count(MarketplaceReviewModel.id))
        .where(MarketplaceReviewModel.listing_id == listing_id)
        .group_by(MarketplaceReviewModel.rating)
    )
    breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for rating_val, count in breakdown_result.all():
        breakdown[int(rating_val)] = int(count)

    result = await db.execute(
        select(MarketplaceReviewModel)
        .where(MarketplaceReviewModel.listing_id == listing_id)
        .order_by(MarketplaceReviewModel.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    reviews = []
    for r in result.scalars().all():
        reviews.append(
            ReviewResponse(
                id=r.id,
                listing_id=r.listing_id,
                user_id=r.user_id,
                rating=r.rating,
                title=getattr(r, "title", None),
                comment=r.comment,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
        )

    return {
        "reviews": reviews,
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_more": (page * per_page) < total,
        "rating_breakdown": breakdown,
    }


@router.get("/listings/{listing_id}/rating", response_model=RatingSummary)
async def get_rating_summary(
    listing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get aggregated rating summary for a listing."""
    result = await db.execute(
        select(
            func.avg(MarketplaceReviewModel.rating).label("avg"),
            func.count(MarketplaceReviewModel.id).label("cnt"),
        ).where(MarketplaceReviewModel.listing_id == listing_id)
    )
    row = result.first()
    avg_rating = round(float(row.avg or 0), 2)
    count = int(row.cnt or 0)

    breakdown_result = await db.execute(
        select(MarketplaceReviewModel.rating, func.count(MarketplaceReviewModel.id))
        .where(MarketplaceReviewModel.listing_id == listing_id)
        .group_by(MarketplaceReviewModel.rating)
    )
    breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for rating_val, cnt in breakdown_result.all():
        breakdown[int(rating_val)] = int(cnt)

    return RatingSummary(average=avg_rating, count=count, breakdown=breakdown)


@router.post(
    "/listings/{listing_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_review(
    listing_id: str,
    payload: ReviewCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit or update a review for a listing. Auto-aggregates rating."""
    listing_result = await db.execute(
        select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
    )
    listing = listing_result.scalar_one_or_none()
    if not listing:
        raise HTTPException(404, detail="Listing not found")
    if listing.status != "published":
        raise HTTPException(400, detail="Can only review published listings")

    # Check for existing review by this user
    existing_result = await db.execute(
        select(MarketplaceReviewModel).where(
            MarketplaceReviewModel.listing_id == listing_id,
            MarketplaceReviewModel.user_id == str(user.id),
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.rating = payload.rating
        existing.title = payload.title
        existing.comment = payload.comment
        existing.is_approved = True
        review = existing
    else:
        review = MarketplaceReviewModel(
            id=str(uuid4()),
            listing_id=listing_id,
            user_id=str(user.id),
            rating=payload.rating,
            title=payload.title,
            comment=payload.comment,
            is_approved=True,
        )
        db.add(review)

    await db.flush()

    # Auto-aggregate rating
    await _recalculate_rating(db, listing_id)
    await db.refresh(review)

    return ReviewResponse(
        id=review.id,
        listing_id=review.listing_id,
        user_id=review.user_id,
        rating=review.rating,
        title=getattr(review, "title", None),
        comment=review.comment,
        created_at=review.created_at.isoformat() if review.created_at else "",
    )


# ── Categories ───────────────────────────────────────────────────────────────


@router.get("/categories")
async def get_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get marketplace categories with listing counts."""
    result = await db.execute(
        select(
            MarketplaceCategoryModel.id,
            MarketplaceCategoryModel.name,
            MarketplaceCategoryModel.slug,
            MarketplaceCategoryModel.listing_count,
        )
    )
    return [
        {"id": row[0], "name": row[1], "slug": row[2], "count": row[3]}
        for row in result.all()
    ]
