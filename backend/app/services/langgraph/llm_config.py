import logging
import threading
from collections import OrderedDict
from typing import Any

from pydantic import SecretStr

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 10

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore[misc]


# Per-model base URL overrides for llamacpp variants served by separate
# llama-server instances. Keys are the public model_id (e.g. "llamacpp-qwen2.5-1.5b"),
# values are the base URL of the llama-server *without* the trailing "/v1".
# Used by the background review task's fast-path for short, structured JSON
# extraction (memory entries, supersede decisions) where the 27B is overkill.
_LLAMACPP_MODEL_URL_OVERRIDES: dict[str, str] = {}


def _init_llamacpp_overrides() -> None:
    """Populate the per-model URL override map from settings.

    Called lazily on first instantiation so settings are resolved at runtime
    (Settings uses pydantic-settings which reads from env at import time, but
    tests may override the env after import).
    """
    if _LLAMACPP_MODEL_URL_OVERRIDES:
        return
    from app.config import settings

    _LLAMACPP_MODEL_URL_OVERRIDES["llamacpp-qwen2.5-1.5b"] = settings.LLAMACPP_LIGHT_URL


def get_llamacpp_base_url(model_id: str) -> str:
    """Return the base URL (no trailing /v1) for a llamacpp model_id.

    Falls back to settings.LLAMACPP_URL (the primary 27B server) if no
    per-model override is registered.
    """
    from app.config import settings

    _init_llamacpp_overrides()
    return _LLAMACPP_MODEL_URL_OVERRIDES.get(model_id) or settings.LLAMACPP_URL


class LLMManager:
    _instances: OrderedDict[str, Any] = OrderedDict()
    _lock = threading.Lock()

    # MODEL_MAP is no longer hard-coded (Comment 5). The authoritative model
    # catalog (app/services/model_catalog) owns provider -> upstream model name
    # mappings, pricing, and availability. We expose it as a property so legacy
    # callers (memory services, meta_review, etc.) that read
    # ``manager.MODEL_MAP.get(model_id, model_id)`` keep working unchanged.

    @property
    def MODEL_MAP(self) -> dict[str, str]:
        from app.services.model_catalog import get_model_catalog

        catalog = get_model_catalog()
        return {spec.model_id: spec.upstream_model_name for spec in catalog.all()}

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
            base_url = get_llamacpp_base_url(model_id) + "/v1"
            return ChatOpenAI(
                model=mapped,
                base_url=base_url,
                api_key=SecretStr("not-needed"),
            )

        return ChatOpenAI(
            model=mapped,
            api_key=SecretStr(settings.LLM_API_KEY),
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
