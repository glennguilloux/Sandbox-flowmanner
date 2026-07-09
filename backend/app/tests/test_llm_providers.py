"""Tests for app.services.llm_providers — Phase 0.1 leaf extraction.

Verifies signature preservation and behaviour of the moved functions.
"""

from app.services.llm_providers import (
    OPENAI_PROVIDER_FAMILIES,
    PROVIDER_MAP,
    _detect_provider_from_key,
    _get_base_url_for_provider,
    _get_provider_for_model,
    _get_upstream_model_name,
    _normalize_provider,
    _providers_compatible,
    _resolve_provider,
)


class TestNormalizeProvider:
    def test_lowercase_passthrough(self):
        assert _normalize_provider("openai") == "openai"

    def test_case_insensitive(self):
        assert _normalize_provider("OpenAI") == "openai"
        assert _normalize_provider("DEEPSEEK") == "deepseek"

    def test_hyphen_to_underscore(self):
        assert _normalize_provider("openai-compatible") == "openai_compatible"
        assert _normalize_provider("OPENAI-COMPATIBLE") == "openai_compatible"

    def test_empty_string(self):
        assert _normalize_provider("") == ""

    def test_none_passthrough(self):
        # _normalize_provider returns None for falsy input
        assert _normalize_provider(None) is None


class TestResolveProvider:
    def test_openai_prefix(self):
        base_url, _api_key, model = _resolve_provider("openai/gpt-4o")
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o"

    def test_deepseek_prefix(self):
        base_url, _api_key, model = _resolve_provider("deepseek/deepseek-chat")
        assert base_url == "https://api.deepseek.com/v1"
        assert model == "deepseek-chat"

    def test_no_prefix_returns_defaults(self):
        base_url, _api_key, model = _resolve_provider("gpt-4o-mini")
        assert model == "gpt-4o-mini"
        # Falls back to _LLM_API_BASE
        assert "deepseek" in base_url or "openai" in base_url

    def test_openrouter_nested_path(self):
        base_url, _api_key, model = _resolve_provider("openrouter/anthropic/claude-3.5-sonnet")
        assert base_url == "https://openrouter.ai/api/v1"
        assert model == "anthropic/claude-3.5-sonnet"

    def test_llamacpp_model(self):
        base_url, api_key, model = _resolve_provider("llamacpp/qwen3.6-27b")
        assert "11434" in base_url
        assert api_key == "not-needed"
        assert model == "qwen3.6-27b"


class TestDetectProviderFromKey:
    def test_openrouter_key(self):
        assert _detect_provider_from_key("sk-or-abc123") == "openrouter"

    def test_deepseek_key(self):
        assert _detect_provider_from_key("sk-ds-abc123") == "deepseek"

    def test_anthropic_key(self):
        assert _detect_provider_from_key("sk-ant-abc123") == "anthropic"

    def test_openai_project_key(self):
        assert _detect_provider_from_key("sk-proj-abc123") == "openai"

    def test_google_key(self):
        assert _detect_provider_from_key("aiza-abc123") == "google"

    def test_groq_key(self):
        assert _detect_provider_from_key("gsk_abc123") == "groq"

    def test_fireworks_key(self):
        assert _detect_provider_from_key("fw_abc123") == "fireworks"

    def test_xai_key(self):
        assert _detect_provider_from_key("xai-abc123") == "xai"

    def test_ambiguous_generic_sk_returns_none(self):
        """Generic sk- prefix shared by OpenAI, Together, DeepInfra."""
        assert _detect_provider_from_key("sk-abc123") is None

    def test_empty_key(self):
        assert _detect_provider_from_key("") is None

    def test_none_key(self):
        assert _detect_provider_from_key(None) is None


class TestProvidersCompatible:
    def test_both_none(self):
        assert _providers_compatible(None, None) is True

    def test_key_none(self):
        assert _providers_compatible(None, "openai") is True

    def test_model_none(self):
        assert _providers_compatible("openai", None) is True

    def test_same_provider(self):
        assert _providers_compatible("openai", "openai") is True

    def test_llamacpp_always_compatible(self):
        assert _providers_compatible("openai", "llamacpp") is True
        assert _providers_compatible(None, "llamacpp") is True

    def test_openai_compatible_family(self):
        """openai and openai_compatible are in the same family."""
        assert _providers_compatible("openai", "openai_compatible") is True
        assert _providers_compatible("openai_compatible", "openai") is True

    def test_mismatch(self):
        assert _providers_compatible("anthropic", "openai") is False


class TestGetProviderForModel:
    def test_with_prefix(self):
        assert _get_provider_for_model("openai/gpt-4o") == "openai"

    def test_no_prefix(self):
        assert _get_provider_for_model("gpt-4o") is None

    def test_nested_prefix(self):
        assert _get_provider_for_model("openrouter/anthropic/claude") == "openrouter"


class TestGetUpstreamModelName:
    def test_strips_prefix(self):
        assert _get_upstream_model_name("openai/gpt-4o-mini") == "gpt-4o-mini"

    def test_preserves_nested_path(self):
        assert _get_upstream_model_name("openrouter/anthropic/claude-3.5-sonnet") == "anthropic/claude-3.5-sonnet"

    def test_no_prefix(self):
        assert _get_upstream_model_name("gpt-4o-mini") == "gpt-4o-mini"


class TestGetBaseUrlForProvider:
    def test_known_provider(self):
        assert _get_base_url_for_provider("openai") == "https://api.openai.com/v1"

    def test_openai_compatible(self):
        assert _get_base_url_for_provider("openai_compatible") == "https://api.openai.com/v1"

    def test_unknown_falls_back(self):
        url = _get_base_url_for_provider("nonexistent")
        assert url  # falls back to _LLM_API_BASE


class TestConstants:
    def test_provider_map_has_expected_keys(self):
        expected = {"deepseek", "openai", "openrouter", "llamacpp", "anthropic", "groq"}
        assert expected.issubset(set(PROVIDER_MAP.keys()))

    def test_openai_families(self):
        assert "openai" in OPENAI_PROVIDER_FAMILIES
        assert "openai_compatible" in OPENAI_PROVIDER_FAMILIES
