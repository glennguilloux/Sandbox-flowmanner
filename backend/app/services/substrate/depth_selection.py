"""Depth -> model/reasoning selection (Comment 7).

Promotes the deterministic ``DepthPolicy`` output (shallow/normal/deep) into a
concrete model + ``ReasoningOptions`` choice for ``NodeExecutor._handle_llm``.

Policy:
- shallow  -> local/cheap model, no reasoning
- normal   -> default cloud path (catalog paid_cloud + free_cloud)
- deep     -> premium-reasoning tier (Opus) ONLY when budget + catalog policy
              allow it (ENABLE_PREMIUM_MODELS + opus_enabled). Otherwise falls
              back to the best non-local reasoning-capable cloud model.

The same profile also drives reflection iteration counts and provider-specific
``ReasoningOptions`` (see app.services.providers.anthropic_adapter).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.services.substrate.workflow_models import ReasoningProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectedModel:
    model_id: str
    reasoning: object  # ReasoningOptions
    profile: ReasoningProfile
    # Number of reflection iterations this depth maps to (HITL/planner use).
    reflection_iterations: int
    degraded: bool = False
    degradation_note: str | None = None


def _reflection_iterations(profile: ReasoningProfile) -> int:
    from app.models.depth_models import DepthLevel
    from app.services.depth_policy import REFLECTION_ITERATIONS

    mapping = {
        ReasoningProfile.SHALLOW: DepthLevel.SHALLOW,
        ReasoningProfile.NORMAL: DepthLevel.NORMAL,
        ReasoningProfile.DEEP: DepthLevel.DEEP,
    }
    return REFLECTION_ITERATIONS[mapping[profile]]


def select_model_for_depth(
    profile: ReasoningProfile,
    *,
    budget_remaining_usd: Decimal | float | None = None,
    explicit_model: str | None = None,
) -> SelectedModel:
    """Resolve a model + ReasoningOptions for a depth/profile.

    Args:
        profile: shallow/normal/deep.
        budget_remaining_usd: remaining budget; if too low, force shallow/local.
        explicit_model: a model already assigned to the node (kept unless the
            profile demands a premium-reasoning tier that the assigned model
            cannot satisfy).

    Returns:
        SelectedModel with the model id, ReasoningOptions, reflection count, and
        any degradation note (e.g. deep requested but premium disabled).
    """
    from app.config import settings
    from app.services.model_catalog import (
        ApiStyle,
        ModelTier,
        get_model_catalog,
    )
    from app.services.providers.anthropic_adapter import ReasoningOptions, opus_enabled

    catalog = get_model_catalog()
    budget_remaining = Decimal(str(budget_remaining_usd)) if budget_remaining_usd is not None else Decimal("9999")

    # Cheap/local override when clearly out of budget.
    if budget_remaining <= Decimal("0.10") and profile != ReasoningProfile.SHALLOW:
        profile = ReasoningProfile.SHALLOW

    if profile == ReasoningProfile.SHALLOW:
        local = catalog.by_tier(ModelTier.LOCAL)
        model = local[0].model_id if local else "llamacpp-qwen3.6-27b"
        return SelectedModel(
            model_id=model,
            reasoning=ReasoningOptions(depth="shallow", prompt_caching=False),
            profile=ReasoningProfile.SHALLOW,
            reflection_iterations=0,
        )

    if profile == ReasoningProfile.DEEP:
        # Prefer Opus (premium reasoning) only when enabled + affordable.
        if opus_enabled() and settings.ENABLE_PREMIUM_MODELS:
            opus = catalog.get("claude-3-opus")
            if opus is not None and opus.enabled:
                return SelectedModel(
                    model_id="claude-3-opus",
                    reasoning=ReasoningOptions(
                        depth="deep",
                        reasoning_budget=8000,
                        effort="high",
                        expose_chain_of_thought=False,
                    ),
                    profile=ReasoningProfile.DEEP,
                    reflection_iterations=_reflection_iterations(ReasoningProfile.DEEP),
                )
        # Fallback: best non-local reasoning-capable cloud model (deepseek-reasoner)
        # or any paid_cloud deep_dive model. Never silently pick a local model for
        # "deep" — record degradation if premium was requested but unavailable.
        deep_candidates = [
            s
            for s in catalog.select_for_use_case("deep_dive", include_local=False, include_premium=False)
            if s.family != "anthropic"
        ]
        if deep_candidates:
            chosen = deep_candidates[0]
            return SelectedModel(
                model_id=chosen.model_id,
                reasoning=ReasoningOptions(
                    depth="deep",
                    reasoning_budget=4096,
                    expose_chain_of_thought=False,
                ),
                profile=ReasoningProfile.DEEP,
                reflection_iterations=_reflection_iterations(ReasoningProfile.DEEP),
                degraded=bool(settings.ENABLE_PREMIUM_MODELS),
                degradation_note=(
                    "Opus premium-reasoning tier unavailable; used " f"{chosen.model_id} instead"
                    if settings.ENABLE_PREMIUM_MODELS
                    else None
                ),
            )
        # Last resort: downgrade to normal cloud path, flagged degraded.
        normal = select_model_for_depth(ReasoningProfile.NORMAL, budget_remaining_usd=budget_remaining)
        return SelectedModel(
            model_id=normal.model_id,
            reasoning=normal.reasoning,
            profile=ReasoningProfile.NORMAL,
            reflection_iterations=normal.reflection_iterations,
            degraded=True,
            degradation_note="deep requested but no premium/cloud reasoning model available",
        )

    # NORMAL -> default cloud path (paid_cloud + free_cloud, exclude local).
    normal_candidates = catalog.select_for_use_case(
        "chat", include_local=False, include_premium=False
    ) or catalog.select_for_use_case("planning", include_local=False, include_premium=False)
    if explicit_model and explicit_model in {s.model_id for s in normal_candidates}:
        chosen = next(s for s in normal_candidates if s.model_id == explicit_model)
    else:
        chosen = normal_candidates[0] if normal_candidates else catalog.by_tier(ModelTier.PAID_CLOUD)[0]
    return SelectedModel(
        model_id=chosen.model_id,
        reasoning=ReasoningOptions(depth="normal", prompt_caching=True),
        profile=ReasoningProfile.NORMAL,
        reflection_iterations=_reflection_iterations(ReasoningProfile.NORMAL),
    )
