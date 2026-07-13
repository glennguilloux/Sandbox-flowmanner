"""Comment 7: DepthPolicy output consumed for model/reasoning selection."""

import os

import pytest

from app.services.providers.anthropic_adapter import opus_enabled
from app.services.substrate.depth_selection import select_model_for_depth
from app.services.substrate.workflow_models import ReasoningProfile


def test_shallow_selects_local_no_reasoning():
    sel = select_model_for_depth(ReasoningProfile.SHALLOW)
    assert sel.profile == ReasoningProfile.SHALLOW
    assert sel.reflection_iterations == 0
    # Local model chosen.
    assert sel.model_id.startswith("llamacpp")
    assert sel.reasoning.depth == "shallow"
    assert sel.reasoning.reasoning_budget is None


def test_normal_selects_cloud_path():
    sel = select_model_for_depth(ReasoningProfile.NORMAL)
    assert sel.profile == ReasoningProfile.NORMAL
    assert not sel.model_id.startswith("llamacpp")


def test_deep_without_premium_degrades_not_opus():
    # Opus disabled by default (no key + flags) -> deep must NOT pick opus.
    assert opus_enabled() is False
    sel = select_model_for_depth(ReasoningProfile.DEEP)
    assert sel.model_id != "claude-3-opus"
    # Either degraded (premium unavailable) or a reasoning cloud fallback.
    assert sel.reflection_iterations >= 1


def test_low_budget_forces_shallow():
    sel = select_model_for_depth(ReasoningProfile.DEEP, budget_remaining_usd=0.05)
    # Busted budget overrides deep -> shallow/local.
    assert sel.profile == ReasoningProfile.SHALLOW
    assert sel.model_id.startswith("llamacpp")


def test_deep_with_opus_enabled_picks_opus(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_NATIVE_ANTHROPIC", True)
    monkeypatch.setattr(settings, "ENABLE_PREMIUM_MODELS", True)
    from app.services.model_catalog import get_model_catalog

    spec = get_model_catalog().get("claude-3-opus")
    object.__setattr__(spec, "enabled", True)
    assert opus_enabled() is True
    sel = select_model_for_depth(ReasoningProfile.DEEP)
    assert sel.model_id == "claude-3-opus"
    assert sel.reasoning.depth == "deep"
    assert sel.reasoning.reasoning_budget and sel.reasoning.reasoning_budget > 0
