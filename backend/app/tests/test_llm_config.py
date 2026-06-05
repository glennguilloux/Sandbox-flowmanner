"""Tests for LLMManager.get_model() — model instantiation with LRU cache."""

from unittest.mock import MagicMock, patch

import pytest

import app.services.langgraph.llm_config as _mod
from app.services.langgraph.llm_config import MAX_CACHE_SIZE, LLMManager


@pytest.fixture(autouse=True)
def _clear_cache():
    LLMManager.clear_cache()
    yield
    LLMManager.clear_cache()


@patch.object(_mod, "ChatOpenAI", autospec=True)
def test_llamacpp_model_instantiation(mock_openai_cls):
    openai_instance = MagicMock()
    mock_openai_cls.return_value = openai_instance

    mgr = LLMManager()
    result = mgr.get_model("llamacpp-qwen2.5-14b")

    from app.config import settings

    mock_openai_cls.assert_called_once_with(
        model="qwen2.5:14b",
        base_url=settings.LLAMACPP_URL + "/v1",
        api_key="not-needed",
    )
    assert result is openai_instance


@patch.object(_mod, "ChatOpenAI", autospec=True)
def test_cloud_model_instantiation(mock_openai_cls):
    openai_instance = MagicMock()
    mock_openai_cls.return_value = openai_instance

    mgr = LLMManager()
    result = mgr.get_model("claude-3-5-sonnet")

    from app.config import settings

    mock_openai_cls.assert_called_once_with(
        model="anthropic/claude-3-5-sonnet-20241022",
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
    )
    assert result is openai_instance


@patch.object(_mod, "ChatOpenAI", autospec=True)
def test_cache_hit(mock_openai_cls):
    llamacpp_instance = MagicMock()
    mock_openai_cls.return_value = llamacpp_instance

    mgr = LLMManager()
    first = mgr.get_model("llamacpp-qwen2.5-14b")
    second = mgr.get_model("llamacpp-qwen2.5-14b")

    assert first is second
    mock_openai_cls.assert_called_once()


@patch.object(_mod, "ChatOpenAI", autospec=True)
def test_cache_eviction(mock_openai_cls):
    count = 0

    def _make(**kwargs):
        nonlocal count
        count += 1
        return MagicMock(name=f"llamacpp-{count}")

    mock_openai_cls.side_effect = _make

    mgr = LLMManager()

    first_key = "llamacpp-qwen2.5-14b"
    mgr.get_model(first_key)

    for k in [
        "llamacpp-qwen2.5-coder-7b",
        "llamacpp-qwen2.5-1.5b",
        "llamacpp-qwen2.5vl-7b",
        "llamacpp-qwen3.6-latest",
    ]:
        mgr.get_model(k)

    for i in range(5):
        mgr.get_model(f"llamacpp-unknown-{i}:tag")

    assert len(LLMManager._instances) == MAX_CACHE_SIZE
    assert first_key in LLMManager._instances

    mgr.get_model("llamacpp-evict-trigger:tag")
    assert first_key not in LLMManager._instances


@patch.object(_mod, "ChatOpenAI", autospec=True)
def test_unknown_model_with_colon_is_local(mock_openai_cls):
    llamacpp_instance = MagicMock()
    mock_openai_cls.return_value = llamacpp_instance

    mgr = LLMManager()
    result = mgr.get_model("some-unknown:model")

    mock_openai_cls.assert_called_once()
    assert result is llamacpp_instance


def test_import_error_returns_none():
    LLMManager.clear_cache()

    with patch.object(_mod, "ChatOpenAI", None):
        mgr = LLMManager()
        result = mgr.get_model("llamacpp-qwen2.5-14b")
        assert result is None
