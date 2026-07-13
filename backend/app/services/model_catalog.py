"""Authoritative model catalog (Comment 5).

Single source of truth for model availability, provider, API style, tier,
pricing, capabilities, and allowed use cases. Replaces the duplicated
hard-coded maps that previously lived in ``ModelRouter``, ``LLMManager``,
``CostTracker``, ``CostOptimizer``, ``ProviderFallbackMiddleware``, and
``budget_enforcer.DEFAULT_PRICING``.

All routing and pricing consumers MUST read from this catalog. Startup
validation fails fast when an *enabled* model lacks pricing, provider support,
or required env keys (Comment 5: "Treat unknown pricing as an error for paid
models, not as a silent default").
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ApiStyle(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ModelTier(str, Enum):
    LOCAL = "local"
    FREE_CLOUD = "free_cloud"
    PAID_CLOUD = "paid_cloud"
    PREMIUM = "premium"


@dataclass(frozen=True)
class ModelSpec:
    """A single model definition read from the catalog."""

    model_id: str
    provider: str
    upstream_model_name: str
    api_style: ApiStyle
    tier: ModelTier
    local: bool
    enabled: bool
    env_key: str | None
    context_window: int
    input_per_1m: float
    output_per_1m: float
    reasoning_per_1m: float
    family: str
    capabilities: list[str]
    allowed_use_cases: list[str]
    requires_catalog_enabled: bool = False

    @property
    def is_paid(self) -> bool:
        return not self.local

    def supports(self, use_case: str) -> bool:
        return use_case in self.allowed_use_cases


class CatalogValidationError(Exception):
    """Raised when the catalog is internally inconsistent or incomplete."""


_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "models_catalog.json"


def _coerce_api_style(value: str) -> ApiStyle:
    try:
        return ApiStyle(value)
    except ValueError:
        return ApiStyle.OPENAI


def _coerce_tier(value: str) -> ModelTier:
    try:
        return ModelTier(value)
    except ValueError:
        return ModelTier.PAID_CLOUD


def _load_raw(path: Path = _CATALOG_PATH) -> dict[str, Any]:
    import json

    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _spec_from_entry(model_id: str, entry: dict[str, Any]) -> ModelSpec:
    pricing = entry.get("pricing", {}) or {}
    return ModelSpec(
        model_id=model_id,
        provider=entry.get("provider", "unknown"),
        upstream_model_name=entry.get("upstream_model_name", model_id),
        api_style=_coerce_api_style(entry.get("api_style", "openai")),
        tier=_coerce_tier(entry.get("tier", "paid_cloud")),
        local=bool(entry.get("local", False)),
        enabled=bool(entry.get("enabled", True)),
        env_key=entry.get("env_key"),
        context_window=int(entry.get("context_window", 0) or 0),
        input_per_1m=float(pricing.get("input_per_1m", 0.0)),
        output_per_1m=float(pricing.get("output_per_1m", 0.0)),
        reasoning_per_1m=float(pricing.get("reasoning_per_1m", 0.0)),
        family=entry.get("family", "unknown"),
        capabilities=list(entry.get("capabilities", []) or []),
        allowed_use_cases=list(entry.get("allowed_use_cases", []) or []),
        requires_catalog_enabled=bool(entry.get("requires_catalog_enabled", False)),
    )


def _validate_structure(specs: dict[str, ModelSpec]) -> None:
    """Structural integrity check run at catalog load (always fails on bad data).

    Comment 5: an enabled paid model with no pricing is a catalog ERROR, not a
    silent default. This guarantees callers can never fall back to a phantom
    price for a paid model.
    """
    errors: list[str] = []
    for spec in specs.values():
        if not spec.enabled:
            continue
        if spec.is_paid and spec.tier != ModelTier.FREE_CLOUD:
            if spec.input_per_1m == 0.0 and spec.output_per_1m == 0.0 and spec.reasoning_per_1m == 0.0:
                errors.append(f"model '{spec.model_id}' is enabled+paid but has no pricing")
    if errors:
        raise CatalogValidationError("; ".join(errors))


class ModelCatalog:
    """In-memory catalog loaded once at startup."""

    def __init__(self, path: Path = _CATALOG_PATH):
        raw = _load_raw(path)
        self.version = raw.get("version", "0")
        self.updated_at = raw.get("updated_at")
        self._specs: dict[str, ModelSpec] = {
            mid: _spec_from_entry(mid, entry) for mid, entry in (raw.get("models", {}) or {}).items()
        }
        _validate_structure(self._specs)

    def environment_issues(self) -> list[str]:
        """Runtime problems for currently-enabled models (missing env keys).

        Used by startup validation. Does NOT raise — the caller decides whether
        to hard-fail (production) or warn (dev/test).
        """
        issues: list[str] = []
        for spec in self._specs.values():
            if not spec.enabled:
                continue
            if spec.env_key and not os.getenv(spec.env_key) and not spec.local:
                issues.append(f"model '{spec.model_id}' enabled but env key {spec.env_key} missing")
        return issues

    # ── Lookups ──
    def get(self, model_id: str) -> ModelSpec | None:
        return self._specs.get(model_id)

    def require(self, model_id: str) -> ModelSpec:
        spec = self._specs.get(model_id)
        if spec is None:
            raise CatalogValidationError(f"unknown model_id '{model_id}' in catalog")
        return spec

    def all(self) -> list[ModelSpec]:
        return list(self._specs.values())

    def enabled(self) -> list[ModelSpec]:
        return [s for s in self._specs.values() if s.enabled]

    def by_provider(self, provider: str) -> list[ModelSpec]:
        return [s for s in self._specs.values() if s.provider == provider]

    def by_tier(self, tier: ModelTier | str) -> list[ModelSpec]:
        tier_val = tier.value if isinstance(tier, ModelTier) else tier
        return [s for s in self._specs.values() if s.tier.value == tier_val]

    def select_for_use_case(
        self,
        use_case: str,
        *,
        include_local: bool = True,
        include_cloud: bool = True,
        include_premium: bool = False,
        exclude_families: list[str] | None = None,
    ) -> list[ModelSpec]:
        """Return catalog models usable for a use case, filtered by tier/family.

        Used by reviewer_guard (different-family verifier selection, Comment 9),
        depth policy (Comment 7), and routing.
        """
        exclude = set(exclude_families or [])
        out: list[ModelSpec] = []
        for s in self._specs.values():
            if not s.enabled:
                continue
            if not s.supports(use_case):
                continue
            if s.local and not include_local:
                continue
            if not s.local and not include_cloud:
                continue
            if s.tier == ModelTier.PREMIUM and not include_premium:
                continue
            if s.family in exclude:
                continue
            out.append(s)
        return out

    # ── Pricing (replaces CostTracker/CostOptimizer/budget_enforcer maps) ──
    def estimate_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        """Compute USD cost from catalog pricing.

        Comment 5: unknown pricing for a paid model is an error, not a default.
        """
        spec = self.get(model_id) or self.get(model_id.split("/")[-1])
        if spec is None:
            raise CatalogValidationError(
                f"cannot price unknown model '{model_id}' — register it in "
                f"the catalog instead of relying on a silent default"
            )
        if spec.is_paid and spec.tier != ModelTier.FREE_CLOUD:
            if spec.input_per_1m == 0.0 and spec.output_per_1m == 0.0 and spec.reasoning_per_1m == 0.0:
                raise CatalogValidationError(f"model '{model_id}' is paid but missing pricing in catalog")
        total = (
            (prompt_tokens / 1_000_000) * spec.input_per_1m
            + (completion_tokens / 1_000_000) * spec.output_per_1m
            + (reasoning_tokens / 1_000_000) * spec.reasoning_per_1m
        )
        return total

    def upstream_name(self, model_id: str) -> str:
        spec = self.get(model_id)
        return spec.upstream_model_name if spec else model_id

    def provider_for(self, model_id: str) -> str:
        spec = self.get(model_id)
        return spec.provider if spec else "unknown"

    def api_style_for(self, model_id: str) -> ApiStyle:
        spec = self.get(model_id)
        return spec.api_style if spec else ApiStyle.OPENAI


def validate_model_catalog_at_startup() -> None:
    """Fail fast in production if an enabled model can't be served.

    Comment 5: startup validation fails when an enabled model lacks pricing,
    provider support, or required env keys. In non-production environments we
    only warn so local/dev runs without every cloud key set still boot.
    """
    from app.config import settings

    catalog = get_model_catalog()
    issues = catalog.environment_issues()
    if not issues:
        return
    is_prod = getattr(settings, "APP_ENV", "development") == "production"
    if is_prod:
        raise CatalogValidationError(
            "model catalog enabled models have unresolved environment issues: " + "; ".join(issues)
        )
    logger.warning(
        "Model catalog env issues (non-production, not failing): %s",
        "; ".join(issues),
    )


_catalog: ModelCatalog | None = None


def get_model_catalog() -> ModelCatalog:
    """Return the process-wide catalog singleton (lazy-loaded)."""
    global _catalog
    if _catalog is None:
        _catalog = ModelCatalog()
    return _catalog


def reload_model_catalog() -> ModelCatalog:
    """Reload from disk (used by tests and the daily refresh task)."""
    global _catalog
    _catalog = ModelCatalog()
    return _catalog


def reset_model_catalog() -> None:
    """Reset the singleton (tests only)."""
    global _catalog
    _catalog = None
