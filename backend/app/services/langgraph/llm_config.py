import logging
import threading
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 10

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None


class LLMManager:
    _instances: OrderedDict[str, Any] = OrderedDict()
    _lock = threading.Lock()

    MODEL_MAP = {
        "llamacpp-qwen3.6-27b": "Qwen3.6-27B-Q5_K_M-mtp.gguf",
        "llamacpp-qwen2.5-14b": "qwen2.5:14b",
        "llamacpp-qwen2.5-coder-7b": "qwen2.5-coder:7b",
        "llamacpp-qwen2.5-1.5b": "qwen2.5:1.5b",
        "llamacpp-qwen3.6-latest": "qwen3.6:latest",
        "openrouter-gemma-2-9b-free": "openrouter/google/gemma-2-9b-it:free",
        "openrouter-claude-3.5-sonnet": "openrouter/anthropic/claude-3.5-sonnet",
        "openrouter-gpt-4o": "openrouter/openai/gpt-4o",
        "openrouter-gemini-2.0-flash": "openrouter/google/gemini-2.0-flash",
        "openrouter-deepseek-coder": "openrouter/deepseek/deepseek-coder",
        "claude-3-5-sonnet": "anthropic/claude-3-5-sonnet-20241022",
        "claude-3-haiku": "anthropic/claude-3-haiku-20240307",
    }

    @classmethod
    def clear_cache(cls):
        with cls._lock:
            cls._instances.clear()

    def get_model(self, model_id: str, user_id: str | None = None) -> Any:
        with self._lock:
            if model_id in self._instances:
                self._instances.move_to_end(model_id)
                return self._instances[model_id]

        instance = self._create_instance(model_id)
        if instance is None:
            return None

        with self._lock:
            self._instances[model_id] = instance
            while len(self._instances) > MAX_CACHE_SIZE:
                self._instances.popitem(last=False)

        return instance

    def _create_instance(self, model_id: str) -> Any:
        if ChatOpenAI is None:
            logger.error("LangChain not available: ChatOpenAI not importable")
            return None

        from app.config import settings

        mapped = self.MODEL_MAP.get(model_id, model_id)

        if self._is_local_heuristic(model_id) or mapped.endswith(".gguf"):
            return ChatOpenAI(
                model=mapped,
                base_url=settings.LLAMACPP_URL + "/v1",
                api_key="not-needed",
            )

        return ChatOpenAI(
            model=mapped,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
        )

    @staticmethod
    def _is_local_heuristic(name: str) -> bool:
        return ":" in name or name.startswith("qwen") or name.startswith("llama")


_llm_manager_instance: LLMManager | None = None


def get_llm_manager() -> LLMManager:
    global _llm_manager_instance
    if _llm_manager_instance is None:
        _llm_manager_instance = LLMManager()
    return _llm_manager_instance
