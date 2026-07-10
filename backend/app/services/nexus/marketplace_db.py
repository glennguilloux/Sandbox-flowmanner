# mypy: disable-error-code=attr-defined
"""
Marketplace - Database-Backed Tool and Capability Marketplace Service

Enables sharing, discovery, and installation of tools and capabilities
across users and organizations with PostgreSQL persistence.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ListingType(str, Enum):
    """Type of marketplace listing"""

    TOOL = "tool"
    CAPABILITY = "capability"
    COMPOSED = "composed"
    AGENT = "agent"


class ListingStatus(str, Enum):
    """Status of a listing"""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class PricingModel(str, Enum):
    """Pricing model for listings"""

    FREE = "free"
    ONE_TIME = "one_time"
    SUBSCRIPTION = "subscription"
    USAGE_BASED = "usage_based"


@dataclass
class MarketplaceListing:
    """Represents a tool or capability listing in the marketplace"""

    id: str
    name: str
    description: str
    listing_type: ListingType
    item_id: str
    author_id: str
    version: str = "1.0.0"
    status: ListingStatus = ListingStatus.PUBLISHED
    pricing_model: PricingModel = PricingModel.FREE
    price: float = 0.0
    currency: str = "USD"
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    documentation_url: str | None = None
    repository_url: str | None = None
    icon_url: str | None = None
    screenshots: list[str] = field(default_factory=list)
    requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    install_count: int = 0
    view_count: int = 0
    average_rating: float = 0.0
    review_count: int = 0
    featured: bool = False
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "listing_type": (
                self.listing_type.value if isinstance(self.listing_type, ListingType) else self.listing_type
            ),
            "item_id": self.item_id,
            "author_id": self.author_id,
            "version": self.version,
            "status": (self.status.value if isinstance(self.status, ListingStatus) else self.status),
            "pricing_model": (
                self.pricing_model.value if isinstance(self.pricing_model, PricingModel) else self.pricing_model
            ),
            "price": self.price,
            "currency": self.currency,
            "category": self.category,
            "tags": self.tags or [],
            "documentation_url": self.documentation_url,
            "repository_url": self.repository_url,
            "icon_url": self.icon_url,
            "screenshots": self.screenshots or [],
            "requirements": self.requirements or {},
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_at": (self.published_at.isoformat() if self.published_at else None),
            "install_count": self.install_count,
            "view_count": self.view_count,
            "average_rating": self.average_rating,
            "review_count": self.review_count,
            "featured": self.featured,
            "verified": self.verified,
        }


@dataclass
class MarketplaceReview:
    """User review for a marketplace listing"""

    id: str
    listing_id: str
    user_id: str
    rating: int
    title: str
    content: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    helpful_count: int = 0
    verified_purchase: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    response: str | None = None
    response_date: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "listing_id": self.listing_id,
            "user_id": self.user_id,
            "rating": self.rating,
            "title": self.title,
            "content": self.content,
            "pros": self.pros or [],
            "cons": self.cons or [],
            "helpful_count": self.helpful_count,
            "verified_purchase": self.verified_purchase,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "response": self.response,
            "response_date": (self.response_date.isoformat() if self.response_date else None),
        }


@dataclass
class MarketplaceCategory:
    """Category for organizing listings"""

    id: str
    name: str
    description: str
    parent_id: str | None = None
    icon: str | None = None
    listing_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_id": self.parent_id,
            "icon": self.icon,
            "listing_count": self.listing_count,
        }


def _model_to_listing(model) -> MarketplaceListing:
    """Convert database model to dataclass"""
    return MarketplaceListing(
        id=model.id,
        name=model.name,
        description=model.description or "",
        listing_type=ListingType(model.listing_type),
        item_id=model.item_id,
        author_id=model.author_id,
        version=model.version,
        status=ListingStatus(model.status),
        pricing_model=PricingModel(model.pricing_model),
        price=model.price,
        currency=model.currency,
        category=model.category,
        tags=model.tags or [],
        documentation_url=model.documentation_url,
        repository_url=model.repository_url,
        icon_url=model.icon_url,
        screenshots=model.screenshots or [],
        requirements=model.requirements or {},
        metadata=model.listing_metadata or {},
        created_at=model.created_at,
        updated_at=model.updated_at,
        published_at=model.published_at,
        install_count=model.install_count,
        view_count=model.view_count,
        average_rating=model.average_rating,
        review_count=model.review_count,
        featured=model.featured,
        verified=model.verified,
    )


def _model_to_review(model) -> MarketplaceReview:
    """Convert database model to dataclass"""
    return MarketplaceReview(
        id=model.id,
        listing_id=model.listing_id,
        user_id=model.user_id,
        rating=model.rating,
        title=model.title,
        content=model.content or "",
        pros=model.pros or [],
        cons=model.cons or [],
        helpful_count=model.helpful_count,
        verified_purchase=model.verified_purchase,
        created_at=model.created_at,
        updated_at=model.updated_at,
        response=model.response,
        response_date=model.response_date,
    )


def _model_to_category(model) -> MarketplaceCategory:
    """Convert database model to dataclass"""
    return MarketplaceCategory(
        id=model.id,
        name=model.name,
        description=model.description or "",
        parent_id=model.parent_id,
        icon=model.icon,
        listing_count=model.listing_count,
    )


class MarketplaceService:
    """
    Database-backed service for managing the tool and capability marketplace.
    """

    def __init__(self, db: Session = None):
        self._db = db
        self._sync_engine = None
        self._categories_cache: dict[str, MarketplaceCategory] = {}
        self._init_default_categories()

    def _get_db(self):
        """Get database session"""
        if self._db:
            return self._db
        if not hasattr(self, "_sync_engine") or self._sync_engine is None:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker as _sessionmaker

            from app.config import settings

            sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
            self._sync_engine = create_engine(sync_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        sync_session_factory = _sessionmaker(bind=self._sync_engine)
        return sync_session_factory()

    def _init_default_categories(self):
        """Initialize default marketplace categories in database"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceCategoryModel

            default_categories = [
                (
                    "knowledge",
                    "Knowledge & RAG",
                    "Tools for knowledge retrieval and RAG operations",
                    "brain",
                ),
                (
                    "agent",
                    "Agent Tools",
                    "Tools for agent orchestration and management",
                    "robot",
                ),
                (
                    "data",
                    "Data Processing",
                    "Data transformation and processing tools",
                    "database",
                ),
                (
                    "integration",
                    "Integrations",
                    "External service integrations",
                    "plug",
                ),
                ("automation", "Automation", "Workflow automation tools", "cogs"),
                (
                    "analytics",
                    "Analytics",
                    "Analytics and reporting tools",
                    "chart-bar",
                ),
                ("security", "Security", "Security and compliance tools", "shield"),
                ("utilities", "Utilities", "General utility tools", "wrench"),
            ]

            for cat_id, name, desc, _icon in default_categories:
                existing = db.query(MarketplaceCategoryModel).filter(MarketplaceCategoryModel.id == cat_id).first()
                if not existing:
                    category = MarketplaceCategoryModel(id=cat_id, name=name, description=desc)
                    db.add(category)

            db.commit()

            # Load categories into cache
            for cat in db.query(MarketplaceCategoryModel).all():
                self._categories_cache[cat.id] = _model_to_category(cat)

        except Exception as e:
            db.rollback()
            logger.error("Error initializing categories: %s", e)
        finally:
            if not self._db:
                db.close()

    async def list_tool(
        self,
        tool_id: str,
        metadata: dict[str, Any],
        price: float = 0.0,
        pricing_model: str = "free",
        author_id: str = None,
        **kwargs,
    ) -> MarketplaceListing:
        """List a tool in the marketplace."""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            listing_id = f"listing:{uuid.uuid4().hex[:8]}"

            try:
                pm = PricingModel(pricing_model)
            except ValueError:
                pm = PricingModel.FREE

            listing = MarketplaceListingModel(
                id=listing_id,
                name=metadata.get("name", tool_id),
                description=metadata.get("description", ""),
                listing_type=ListingType.TOOL.value,
                item_id=tool_id,
                author_id=author_id or "unknown",
                version=metadata.get("version", "1.0.0"),
                pricing_model=pm.value,
                price=price,
                currency=metadata.get("currency", "USD"),
                category=metadata.get("category", "utilities"),
                tags=metadata.get("tags", []),
                documentation_url=metadata.get("documentation_url"),
                repository_url=metadata.get("repository_url"),
                icon_url=metadata.get("icon_url"),
                requirements=metadata.get("requirements", {}),
                listing_metadata=metadata,
                published_at=datetime.now(UTC),
                status=ListingStatus.PUBLISHED.value,
            )

            db.add(listing)
            db.commit()
            db.refresh(listing)

            # Update category count
            self._update_category_count(listing.category, 1, db)

            logger.info("Listed tool in marketplace: %s (%s)", listing_id, tool_id)
            return _model_to_listing(listing)

        except Exception as e:
            db.rollback()
            logger.error("Error listing tool: %s", e)
            raise
        finally:
            if not self._db:
                db.close()

    async def list_capability(
        self,
        capability_id: str,
        metadata: dict[str, Any],
        price: float = 0.0,
        pricing_model: str = "free",
        author_id: str = None,
        **kwargs,
    ) -> MarketplaceListing:
        """List a capability in the marketplace."""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            listing_id = f"listing:{uuid.uuid4().hex[:8]}"

            try:
                pm = PricingModel(pricing_model)
            except ValueError:
                pm = PricingModel.FREE

            listing = MarketplaceListingModel(
                id=listing_id,
                name=metadata.get("name", capability_id),
                description=metadata.get("description", ""),
                listing_type=ListingType.CAPABILITY.value,
                item_id=capability_id,
                author_id=author_id or "unknown",
                version=metadata.get("version", "1.0.0"),
                pricing_model=pm.value,
                price=price,
                currency=metadata.get("currency", "USD"),
                category=metadata.get("category", "utilities"),
                tags=metadata.get("tags", []),
                documentation_url=metadata.get("documentation_url"),
                repository_url=metadata.get("repository_url"),
                requirements=metadata.get("requirements", {}),
                listing_metadata=metadata,
                published_at=datetime.now(UTC),
                status=ListingStatus.PUBLISHED.value,
            )

            db.add(listing)
            db.commit()
            db.refresh(listing)

            self._update_category_count(listing.category, 1, db)

            logger.info("Listed capability in marketplace: %s (%s)", listing_id, capability_id)
            return _model_to_listing(listing)

        except Exception as e:
            db.rollback()
            logger.error("Error listing capability: %s", e)
            raise
        finally:
            if not self._db:
                db.close()

    def _update_category_count(self, category_id: str, delta: int, db):
        """Update category listing count"""
        from app.models.models import MarketplaceCategoryModel

        cat = db.query(MarketplaceCategoryModel).filter(MarketplaceCategoryModel.id == category_id).first()
        if cat:
            cat.listing_count = max(0, cat.listing_count + delta)
            db.commit()

    async def search(
        self,
        query: str = None,
        filters: dict[str, Any] = None,
        sort_by: str = "relevance",
        limit: int = 20,
        offset: int = 0,
    ) -> list[MarketplaceListing]:
        """Search the marketplace."""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            q = db.query(MarketplaceListingModel).filter(
                MarketplaceListingModel.status == ListingStatus.PUBLISHED.value
            )

            # Apply filters
            if filters:
                q = self._apply_filters_db(q, filters)

            # Apply text search
            if query:
                q = self._apply_search_db(q, query)

            # Sort results
            q = self._apply_sort_db(q, sort_by)

            # Get results and update view counts
            results = q.offset(offset).limit(limit).all()

            listings = []
            for model in results:
                model.view_count += 1
                listings.append(_model_to_listing(model))

            db.commit()
            return listings

        except Exception as e:
            db.rollback()
            logger.error("Error searching marketplace: %s", e)
            return []
        finally:
            if not self._db:
                db.close()

    def _apply_filters_db(self, query, filters: dict[str, Any]):
        """Apply filters to SQLAlchemy query"""
        from app.models.models import MarketplaceListingModel

        if "category" in filters:
            query = query.filter(MarketplaceListingModel.category == filters["category"])

        if "listing_type" in filters:
            query = query.filter(MarketplaceListingModel.listing_type == filters["listing_type"])

        if "pricing_model" in filters:
            query = query.filter(MarketplaceListingModel.pricing_model == filters["pricing_model"])

        if "author_id" in filters:
            query = query.filter(MarketplaceListingModel.author_id == filters["author_id"])

        if "price_min" in filters:
            query = query.filter(MarketplaceListingModel.price >= filters["price_min"])

        if "price_max" in filters:
            query = query.filter(MarketplaceListingModel.price <= filters["price_max"])

        if "verified" in filters:
            query = query.filter(MarketplaceListingModel.verified == filters["verified"])

        if "featured" in filters:
            query = query.filter(MarketplaceListingModel.featured == filters["featured"])

        return query

    def _apply_search_db(self, query, search_query: str):
        """Apply text search to SQLAlchemy query"""
        from app.models.models import MarketplaceListingModel

        search_term = f"%{search_query.lower()}%"
        return query.filter(
            or_(
                MarketplaceListingModel.name.ilike(search_term),
                MarketplaceListingModel.description.ilike(search_term),
                MarketplaceListingModel.category.ilike(search_term),
            )
        )

    def _apply_sort_db(self, query, sort_by: str):
        """Apply sorting to SQLAlchemy query"""
        from app.models.models import MarketplaceListingModel

        if sort_by == "popularity":
            return query.order_by(desc(MarketplaceListingModel.install_count))
        elif sort_by == "rating":
            return query.order_by(desc(MarketplaceListingModel.average_rating))
        elif sort_by == "newest":
            return query.order_by(desc(MarketplaceListingModel.created_at))
        elif sort_by == "price_low":
            return query.order_by(asc(MarketplaceListingModel.price))
        elif sort_by == "price_high":
            return query.order_by(desc(MarketplaceListingModel.price))
        else:  # relevance
            return query.order_by(
                desc(MarketplaceListingModel.featured),
                desc(MarketplaceListingModel.verified),
                desc(MarketplaceListingModel.average_rating),
                desc(MarketplaceListingModel.install_count),
            )

    async def install(self, listing_id: str, user_id: str) -> dict[str, Any]:
        """Install a listing to a user's registry."""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel, UserInstallationModel

            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()

            if not listing:
                return {"success": False, "error": f"Listing not found: {listing_id}"}

            if listing.status != ListingStatus.PUBLISHED.value:
                return {
                    "success": False,
                    "error": f"Listing not available: {listing.status}",
                }

            # Check if already installed
            existing = (
                db.query(UserInstallationModel)
                .filter(
                    UserInstallationModel.user_id == user_id,
                    UserInstallationModel.listing_id == listing_id,
                )
                .first()
            )

            if not existing:
                # Track installation
                installation = UserInstallationModel(user_id=user_id, listing_id=listing_id)
                db.add(installation)
                listing.install_count += 1
                db.commit()

            # Register in user's capability registry
            try:
                listing_data = _model_to_listing(listing)

                if listing.listing_type == ListingType.TOOL.value:
                    from app.tools import get_tool

                    tool = get_tool(listing.item_id)
                    if tool:
                        from app.services.nexus.capability_registry import (
                            Capability,
                            get_capability_registry,
                        )

                        registry = get_capability_registry()
                        cap = Capability(
                            id=f"user:{user_id}:tool:{listing.item_id}",
                            name=listing.name,
                            description=listing.description or "",
                            category=listing.category,
                            handler=tool.execute,
                            metadata={"installed_from": listing_id, "user_id": user_id},
                        )
                        registry.register(cap)

                elif listing.listing_type == ListingType.CAPABILITY.value:
                    from app.services.nexus.capability_registry import (
                        Capability,
                        get_capability_registry,
                    )

                    registry = get_capability_registry()
                    original_cap = registry.get(listing.item_id)
                    if original_cap:
                        cap = Capability(
                            id=f"user:{user_id}:cap:{listing.item_id}",
                            name=listing.name,
                            description=listing.description or "",
                            category=listing.category,
                            handler=original_cap.handler,
                            metadata={"installed_from": listing_id, "user_id": user_id},
                        )
                        registry.register(cap)

                logger.info("Installed %s for user %s", listing_id, user_id)

                return {
                    "success": True,
                    "listing_id": listing_id,
                    "item_id": listing.item_id,
                    "user_id": user_id,
                    "installed_at": datetime.now(UTC).isoformat(),
                }

            except Exception as e:
                logger.error("Installation registration failed: %s", e)
                return {"success": False, "error": str(e)}

        except Exception as e:
            db.rollback()
            logger.error("Installation failed: %s", e)
            return {"success": False, "error": str(e)}
        finally:
            if not self._db:
                db.close()

    def uninstall(self, listing_id: str, user_id: str) -> dict:
        """Uninstall a listing - delete the UserInstallationModel row."""
        from app.models.models import MarketplaceListingModel, UserInstallationModel

        db = self._get_db()
        try:
            installation = (
                db.query(UserInstallationModel)
                .filter(
                    UserInstallationModel.user_id == user_id,
                    UserInstallationModel.listing_id == listing_id,
                )
                .first()
            )
            if not installation:
                return {"success": False, "error": "Not installed"}
            db.delete(installation)
            # Decrement install count on listing
            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()
            if listing and listing.install_count and listing.install_count > 0:
                listing.install_count -= 1
            db.commit()
            return {"success": True, "message": "Uninstalled"}
        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        finally:
            if not self._db:
                db.close()

    # ── Transaction lifecycle (MARKETPLACE-2) ──────────────────────────
    # Internal credit/wallet only — NO external payment service provider.
    # State machine: pending -> completed | failed; completed -> refunded.

    def _get_or_create_wallet(self, user_id: str, db):
        from app.models.marketplace_txn_models import MarketplaceWalletModel

        wallet = db.query(MarketplaceWalletModel).filter(MarketplaceWalletModel.user_id == user_id).first()
        if wallet is None:
            wallet = MarketplaceWalletModel(user_id=user_id, balance=0.0, currency="USD")
            db.add(wallet)
            db.flush()
        return wallet

    def credit_wallet(self, user_id: str, amount: float, db=None) -> dict[str, Any]:
        """Add credits to a user's internal wallet (settlement / top-up).

        Used by refund() and by operator top-ups. Returns the new balance.
        """
        if amount < 0:
            return {"success": False, "error": "amount must be non-negative"}
        own = db is None
        db = db or self._get_db()
        try:
            wallet = self._get_or_create_wallet(user_id, db)
            wallet.balance = round(float(wallet.balance) + float(amount), 2)
            db.commit()
            db.refresh(wallet)
            return {"success": True, "balance": wallet.balance, "currency": wallet.currency}
        except Exception as e:
            db.rollback()
            logger.error("Wallet credit failed for %s: %s", user_id, e)
            return {"success": False, "error": str(e)}
        finally:
            if own:
                db.close()

    def get_wallet(self, user_id: str, db=None) -> dict[str, Any]:
        own = db is None
        db = db or self._get_db()
        try:
            wallet = self._get_or_create_wallet(user_id, db)
            return {
                "success": True,
                "user_id": user_id,
                "balance": wallet.balance,
                "currency": wallet.currency,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if own:
                db.close()

    def purchase(self, listing_id: str, user_id: str, db=None) -> dict[str, Any]:
        """Purchase/install a listing, settling against the buyer's wallet.

        Free listings (price <= 0) complete immediately with no wallet debit.
        Paid listings require sufficient wallet balance; otherwise the
        transaction is recorded as `failed` (insufficient balance) and no
        funds move.
        """
        from app.models.marketplace_txn_models import (
            MarketplaceTransactionModel,
            TransactionStatus,
        )
        from app.models.models import MarketplaceListingModel

        own = db is None
        db = db or self._get_db()
        try:
            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()
            if not listing:
                return {"success": False, "error": f"Listing not found: {listing_id}"}
            if listing.status != ListingStatus.PUBLISHED.value:
                return {"success": False, "error": f"Listing not available: {listing.status}"}

            amount = float(listing.price or 0.0)
            # Internal wallet is USD-only for now — the listing model has no
            # currency column, so we settle in USD. A real PSP integration
            # would carry the listing's currency here.
            currency = "USD"
            txn = MarketplaceTransactionModel(
                user_id=str(user_id),
                listing_id=listing_id,
                amount=amount,
                currency=currency,
                status=TransactionStatus.PENDING,
            )
            db.add(txn)
            db.flush()

            if amount <= 0:
                # Free listing — nothing to charge.
                txn.status = TransactionStatus.COMPLETED
                db.commit()
                db.refresh(txn)
                return {
                    "success": True,
                    "transaction_id": txn.id,
                    "status": txn.status,
                    "amount": amount,
                    "currency": currency,
                    "listing_id": listing_id,
                }

            wallet = self._get_or_create_wallet(user_id, db)
            if float(wallet.balance) < amount:
                txn.status = TransactionStatus.FAILED
                txn.error = "insufficient_balance"
                db.commit()
                db.refresh(txn)
                return {
                    "success": False,
                    "transaction_id": txn.id,
                    "status": txn.status,
                    "error": "insufficient_balance",
                    "required": amount,
                    "balance": wallet.balance,
                }

            # Debit wallet atomically with the transaction record.
            wallet.balance = round(float(wallet.balance) - amount, 2)
            txn.status = TransactionStatus.COMPLETED
            txn.payment_ref = f"wallet:{wallet.id}"
            db.commit()
            db.refresh(txn)
            return {
                "success": True,
                "transaction_id": txn.id,
                "status": txn.status,
                "amount": amount,
                "currency": currency,
                "balance": wallet.balance,
                "listing_id": listing_id,
            }
        except Exception as e:
            db.rollback()
            logger.error("Purchase failed for %s/%s: %s", user_id, listing_id, e)
            return {"success": False, "error": str(e)}
        finally:
            if own:
                db.close()

    def get_transaction(self, txn_id: str, db=None) -> dict[str, Any] | None:
        from app.models.marketplace_txn_models import MarketplaceTransactionModel

        own = db is None
        db = db or self._get_db()
        try:
            txn = db.query(MarketplaceTransactionModel).filter(MarketplaceTransactionModel.id == txn_id).first()
            if not txn:
                return None
            return {
                "transaction_id": txn.id,
                "user_id": txn.user_id,
                "listing_id": txn.listing_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "status": txn.status,
                "payment_ref": txn.payment_ref,
                "refunded_from": txn.refunded_from,
                "error": txn.error,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
                "updated_at": txn.updated_at.isoformat() if txn.updated_at else None,
            }
        except Exception as e:
            logger.error("get_transaction failed for %s: %s", txn_id, e)
            return None
        finally:
            if own:
                db.close()

    def list_transactions(self, user_id: str, db=None, status: str = None) -> list[dict[str, Any]]:
        from app.models.marketplace_txn_models import MarketplaceTransactionModel

        own = db is None
        db = db or self._get_db()
        try:
            q = db.query(MarketplaceTransactionModel).filter(MarketplaceTransactionModel.user_id == str(user_id))
            if status:
                q = q.filter(MarketplaceTransactionModel.status == status)
            rows = q.order_by(MarketplaceTransactionModel.created_at.desc()).all()
            return [
                {
                    "transaction_id": r.id,
                    "listing_id": r.listing_id,
                    "amount": r.amount,
                    "currency": r.currency,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("list_transactions failed for %s: %s", user_id, e)
            return []
        finally:
            if own:
                db.close()

    def refund(self, txn_id: str, user_id: str, db=None) -> dict[str, Any]:
        """Refund a completed purchase, crediting the buyer's wallet.

        Only `completed` transactions may be refunded. A refund is itself a
        new `refunded` transaction row that credits the wallet, linked via
        `refunded_from` so the audit trail is intact.
        """
        from app.models.marketplace_txn_models import (
            MarketplaceTransactionModel,
            MarketplaceWalletModel,
            TransactionStatus,
        )

        own = db is None
        db = db or self._get_db()
        try:
            txn = db.query(MarketplaceTransactionModel).filter(MarketplaceTransactionModel.id == txn_id).first()
            if not txn:
                return {"success": False, "error": "Transaction not found", "status_code": 404}
            if txn.user_id != str(user_id):
                return {"success": False, "error": "Forbidden", "status_code": 403}
            if txn.status != TransactionStatus.COMPLETED:
                return {
                    "success": False,
                    "error": f"Cannot refund transaction in state: {txn.status}",
                    "status_code": 400,
                }

            wallet = db.query(MarketplaceWalletModel).filter(MarketplaceWalletModel.user_id == str(user_id)).first()
            if not wallet:
                return {"success": False, "error": "Wallet not found", "status_code": 400}

            wallet.balance = round(float(wallet.balance) + float(txn.amount), 2)
            txn.status = TransactionStatus.REFUNDED

            refund_txn = MarketplaceTransactionModel(
                user_id=str(user_id),
                listing_id=txn.listing_id,
                amount=float(txn.amount),
                currency=txn.currency or "USD",
                status=TransactionStatus.COMPLETED,
                payment_ref=f"refund:wallet:{wallet.id}",
                refunded_from=txn.id,
            )
            db.add(refund_txn)
            db.commit()
            db.refresh(refund_txn)
            return {
                "success": True,
                "refund_transaction_id": refund_txn.id,
                "original_transaction_id": txn.id,
                "status": TransactionStatus.REFUNDED,
                "amount": float(txn.amount),
                "balance": wallet.balance,
            }
        except Exception as e:
            db.rollback()
            logger.error("Refund failed for %s/%s: %s", user_id, txn_id, e)
            return {"success": False, "error": str(e), "status_code": 400}
        finally:
            if own:
                db.close()

    async def rate(
        self,
        listing_id: str,
        user_id: str,
        rating: int,
        review: str = None,
        title: str = None,
        pros: list[str] = None,
        cons: list[str] = None,
    ) -> MarketplaceReview:
        """Add a review to a listing."""
        db = self._get_db()
        try:
            from app.models.models import (
                MarketplaceListingModel,
                MarketplaceReviewModel,
                UserInstallationModel,
            )

            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()

            if not listing:
                raise ValueError(f"Listing not found: {listing_id}")

            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5")

            # Check if user already reviewed
            existing = (
                db.query(MarketplaceReviewModel)
                .filter(
                    MarketplaceReviewModel.listing_id == listing_id,
                    MarketplaceReviewModel.user_id == user_id,
                )
                .first()
            )

            if existing:
                # Update existing review
                existing.rating = rating
                existing.content = review or existing.content
                existing.title = title or existing.title
                existing.pros = pros or existing.pros
                existing.cons = cons or existing.cons
                existing.updated_at = datetime.now(UTC)
                db.commit()
                self._update_listing_rating(listing_id, db)
                return _model_to_review(existing)

            # Check if verified purchase
            verified = (
                db.query(UserInstallationModel)
                .filter(
                    UserInstallationModel.user_id == user_id,
                    UserInstallationModel.listing_id == listing_id,
                )
                .first()
                is not None
            )

            # Create new review
            review_id = f"review:{uuid.uuid4().hex[:8]}"

            new_review = MarketplaceReviewModel(
                id=review_id,
                listing_id=listing_id,
                user_id=user_id,
                rating=rating,
                title=title or f"Rating: {rating}/5",
                content=review or "",
                pros=pros or [],
                cons=cons or [],
                verified_purchase=verified,
            )

            db.add(new_review)
            db.commit()

            self._update_listing_rating(listing_id, db)

            logger.info("Added review %s for listing %s", review_id, listing_id)
            return _model_to_review(new_review)

        except Exception as e:
            db.rollback()
            logger.error("Error adding review: %s", e)
            raise
        finally:
            if not self._db:
                db.close()

    def _update_listing_rating(self, listing_id: str, db):
        """Update average rating for a listing"""
        from sqlalchemy import func

        from app.models.models import MarketplaceListingModel, MarketplaceReviewModel

        result = (
            db.query(
                func.avg(MarketplaceReviewModel.rating).label("avg_rating"),
                func.count(MarketplaceReviewModel.id).label("count"),
            )
            .filter(MarketplaceReviewModel.listing_id == listing_id)
            .first()
        )

        listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()

        if listing and result:
            listing.average_rating = round(result.avg_rating or 0, 2)
            listing.review_count = result.count
            db.commit()

    def get_popular(self, category: str = None, limit: int = 10) -> list[MarketplaceListing]:
        """Get popular listings."""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            q = db.query(MarketplaceListingModel).filter(
                MarketplaceListingModel.status == ListingStatus.PUBLISHED.value
            )

            if category:
                q = q.filter(MarketplaceListingModel.category == category)

            results = (
                q.order_by(
                    desc(MarketplaceListingModel.install_count),
                    desc(MarketplaceListingModel.average_rating),
                )
                .limit(limit)
                .all()
            )

            return [_model_to_listing(r) for r in results]

        finally:
            if not self._db:
                db.close()

    def get_by_author(self, author_id: str) -> list[MarketplaceListing]:
        """Get all listings by an author."""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            results = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.author_id == author_id).all()

            return [_model_to_listing(r) for r in results]

        finally:
            if not self._db:
                db.close()

    def get_listing(self, listing_id: str) -> MarketplaceListing | None:
        """Get a specific listing by ID"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()

            return _model_to_listing(listing) if listing else None

        finally:
            if not self._db:
                db.close()

    def get_reviews(self, listing_id: str) -> list[MarketplaceReview]:
        """Get all reviews for a listing"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceReviewModel

            results = (
                db.query(MarketplaceReviewModel)
                .filter(MarketplaceReviewModel.listing_id == listing_id)
                .order_by(desc(MarketplaceReviewModel.created_at))
                .all()
            )

            return [_model_to_review(r) for r in results]

        finally:
            if not self._db:
                db.close()

    def get_categories(self) -> list[MarketplaceCategory]:
        """Get all marketplace categories"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceCategoryModel

            results = db.query(MarketplaceCategoryModel).order_by(MarketplaceCategoryModel.sort_order).all()

            return [_model_to_category(r) for r in results]

        finally:
            if not self._db:
                db.close()

    def get_user_installations(self, user_id: str) -> list[MarketplaceListing]:
        """Get all listings installed by a user"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel, UserInstallationModel

            results = (
                db.query(MarketplaceListingModel)
                .join(
                    UserInstallationModel,
                    MarketplaceListingModel.id == UserInstallationModel.listing_id,
                )
                .filter(
                    UserInstallationModel.user_id == user_id,
                    UserInstallationModel.is_active == True,
                )
                .all()
            )

            return [_model_to_listing(r) for r in results]

        finally:
            if not self._db:
                db.close()

    async def update_listing(self, listing_id: str, updates: dict[str, Any]) -> MarketplaceListing | None:
        """Update a listing"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()

            if not listing:
                return None

            # Update allowed fields
            for field in [
                "name",
                "description",
                "price",
                "category",
                "tags",
                "documentation_url",
                "repository_url",
                "icon_url",
            ]:
                if field in updates:
                    setattr(listing, field, updates[field])

            if "metadata" in updates:
                listing.listing_metadata = updates["metadata"]

            listing.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(listing)

            logger.info("Updated listing %s", listing_id)
            return _model_to_listing(listing)

        except Exception as e:
            db.rollback()
            logger.error("Error updating listing: %s", e)
            return None
        finally:
            if not self._db:
                db.close()

    async def delete_listing(self, listing_id: str) -> bool:
        """Delete a listing"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            listing = db.query(MarketplaceListingModel).filter(MarketplaceListingModel.id == listing_id).first()

            if listing:
                category = listing.category
                db.delete(listing)
                db.commit()

                self._update_category_count(category, -1, db)

                logger.info("Deleted listing %s", listing_id)
                return True
            return False

        except Exception as e:
            db.rollback()
            logger.error("Error deleting listing: %s", e)
            return False
        finally:
            if not self._db:
                db.close()

    def get_featured(self, limit: int = 5) -> list[MarketplaceListing]:
        """Get featured listings"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            results = (
                db.query(MarketplaceListingModel)
                .filter(
                    MarketplaceListingModel.status == ListingStatus.PUBLISHED.value,
                    MarketplaceListingModel.featured == True,
                )
                .order_by(desc(MarketplaceListingModel.average_rating))
                .limit(limit)
                .all()
            )

            return [_model_to_listing(r) for r in results]

        finally:
            if not self._db:
                db.close()

    def get_trending(self, days: int = 7, limit: int = 10) -> list[MarketplaceListing]:
        """Get trending listings based on recent activity"""
        db = self._get_db()
        try:
            from app.models.models import MarketplaceListingModel

            # Simple trending score based on views and installs
            results = (
                db.query(MarketplaceListingModel)
                .filter(MarketplaceListingModel.status == ListingStatus.PUBLISHED.value)
                .order_by(desc(MarketplaceListingModel.view_count + MarketplaceListingModel.install_count * 10))
                .limit(limit)
                .all()
            )

            return [_model_to_listing(r) for r in results]

        finally:
            if not self._db:
                db.close()

    def to_dict(self) -> dict[str, Any]:
        """Export marketplace state"""
        db = self._get_db()
        try:
            from sqlalchemy import func

            from app.models.models import (
                MarketplaceCategoryModel,
                MarketplaceListingModel,
                MarketplaceReviewModel,
                UserInstallationModel,
            )

            total_listings = db.query(func.count(MarketplaceListingModel.id)).scalar() or 0
            total_reviews = db.query(func.count(MarketplaceReviewModel.id)).scalar() or 0
            total_installations = db.query(func.count(UserInstallationModel.id)).scalar() or 0

            listings = db.query(MarketplaceListingModel).limit(100).all()
            categories = db.query(MarketplaceCategoryModel).all()

            return {
                "listings": [_model_to_listing(l).to_dict() for l in listings],
                "categories": [_model_to_category(c).to_dict() for c in categories],
                "total_listings": total_listings,
                "total_reviews": total_reviews,
                "total_installations": total_installations,
            }

        finally:
            if not self._db:
                db.close()


# Singleton instance
_marketplace_service: Optional["MarketplaceService"] = None


def get_marketplace_service(db: Session = None) -> MarketplaceService:
    """Get or create the marketplace service singleton"""
    global _marketplace_service
    if db:
        return MarketplaceService(db)
    if _marketplace_service is None:
        _marketplace_service = MarketplaceService()
    return _marketplace_service
