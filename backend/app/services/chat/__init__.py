# ─────────────────────────────────────────────────────────────────────────
# Auto-decomposed from app/services/chat_service.py (CARD 3 refactor).
# Part of the `chat` package. Sibling cross-references and original imports
# are preserved so behavior/signatures stay byte-for-byte identical.
# ─────────────────────────────────────────────────────────────────────────

from .byok import *
from .messages import *
from .prompts import *
from .streaming import *
from .substrate_client import (
    SubstrateClient,
    build_solo_workflow,
    execute_solo_run,
    new_run_id,
    run_substrate_turn_sse,
)
from .threads import *
from .toolcall import *

__all__ = [
    "TURN_HARD_CAP_S",
    "_HARD_TOOL_CALL_CAP_S",
    "_MAX_TOOL_ROUNDS",
    "_PROMPT_CACHE_TTL",
    "_SANDBOXD_SYSTEM_GUIDANCE",
    "_SSE_KEEPALIVE_INTERVAL",
    "_SSE_KEEPALIVE_PING",
    "_STREAM_READ_TIMEOUT",
    "_build_chat_messages",
    "_execute_tool_call",
    "_get_active_prompt_content",
    "_get_chat_openai_tools",
    "_get_client",
    "_get_model_preference",
    "_get_prompt_redis",
    "_inject_web_search",
    "_lookup_stored_byok_key",
    "_maybe_extract_memory_claims",
    "_prepare_step_inject",
    "_process_attachments",
    "_prompt_cache_key",
    "_record_tool_cost_fire_and_forget",
    "_safe_effective_base_url",
    "_safe_fire_and_forget",
    "_sse_keepalive_merge",
    "_sse_keepalive_spawn",
    "_sse_keepalive_timer",
    "_stream_message_to_llm_body",
    "_validate_byok_key_matches_model",
    "create_chat_branch",
    "create_chat_file",
    "create_chat_message",
    "create_chat_message_fresh_session",
    "create_chat_thread",
    "delete_chat_branch",
    "delete_chat_message",
    "delete_chat_thread",
    "generate_thread_title",
    "get_chat_branch",
    "get_chat_files",
    "get_chat_messages",
    "get_chat_thread",
    "invalidate_prompt_version_cache",
    "list_chat_branches",
    "list_chat_threads",
    "require_chat_thread_access",
    "send_message_to_llm",
    "stream_message_to_llm",
    "update_chat_message",
    "update_chat_thread",
]
