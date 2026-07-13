"""Comment 5: single authoritative model catalog."""

import os

import pytest

from app.services import model_catalog
from app.services.model_catalog import (
    ApiStyle,
    CatalogValidationError,
    ModelTier,
    get_model_catalog,
    reload_model_catalog,
    reset_model_catalog,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_model_catalog()
    yield
    reset_model_catalog()


def test_catalog_is_single_source_for_known_models():
    cat = get_model_catalog()
    spec = cat.require("deepseek-v4-flash")
    assert spec.provider == "deepseek"
    assert spec.api_style == ApiStyle.OPENAI
    assert spec.tier == ModelTier.PAID_CLOUD
    # Upstream name is the catalog-mapped value, not the public id.
    assert spec.upstream_model_name == "deepseek/deepseek-v4-flash"


def test_pricing_reads_from_catalog_not_hardcoded_default():
    cat = get_model_catalog()
    # deepseek-v4-flash input $0.14/1M -> 1M prompt tokens == 0.14 USD.
    assert cat.estimate_cost("deepseek-v4-flash", 1_000_000, 0) == pytest.approx(0.14)
    # opus is enabled-only via catalog flag; pricing is present and real.
    opus = cat.require("claude-3-opus")
    assert opus.input_per_1m == 15.0
    assert opus.output_per_1m == 75.0


def test_unknown_paid_model_pricing_is_an_error():
    cat = get_model_catalog()
    with pytest.raises(CatalogValidationError):
        # Not in the catalog -> Comment 5 forbids a silent default price.
        cat.estimate_cost("some-unregistered-paid-model", 1_000_000, 0)


def test_model_router_derives_lists_from_catalog():
    from app.services.model_router import ModelRouter

    mr = ModelRouter()
    assert "deepseek-v4-flash" in mr.PAID_CLOUD_MODELS
    assert "llamacpp-qwen3.6-27b" in mr.LOCAL_MODELS
    # _get_model_name resolves through the catalog upstream name.
    assert mr._get_model_name("deepseek-v4-flash") == "deepseek/deepseek-v4-flash"


def test_llm_manager_model_map_derived_from_catalog():
    from app.services.langgraph.llm_config import get_llm_manager

    mgr = get_llm_manager()
    assert mgr.MODEL_MAP.get("claude-3-5-sonnet") == "anthropic/claude-3-5-sonnet-20241022"


def test_select_for_use_case_filters_anthropic_family_out():
    cat = get_model_catalog()
    # Comment 9 needs a different-family verifier relative to a primary model.
    candidates = cat.select_for_use_case(
        "review",
        include_premium=True,
        exclude_families=["anthropic"],
    )
    ids = {c.model_id for c in candidates}
    assert "claude-3-5-sonnet" not in ids
    assert "deepseek-v4-flash" in ids  # deepseek family allowed


def test_opus_disabled_until_catalog_flag_set():
    cat = get_model_catalog()
    assert cat.get("claude-3-opus").enabled is False
    assert cat.get("claude-3-opus").requires_catalog_enabled is True
