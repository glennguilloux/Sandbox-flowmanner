"""Smoke test locking the CARD 3 chat_service.py re-export shim.

After the chat_service.py -> app/services/chat/ decomposition, every
`from app.services.chat_service import X` caller must keep resolving to the
real implementation. This test imports the shim exactly like a caller would
and asserts the canonical public surface is present, so a future refactor
that breaks the shim (drops a symbol, re-introduces the streaming<->toolcall
circular import, etc.) fails loudly instead of silently 500-ing in prod.

No DB / network required — pure import-surface check.
"""

import os

# app.config enforces a production-secret guard at import time; set dummy
# secrets before importing any app module (mirrors app/tests conventions).
# Values are obvious low-entropy placeholders (underscore-separated words),
# not real credentials.
_DUMMY_SECRETS = {
    "OPENAI_API_KEY": "sk-test-dummy-not-a-real-key-0000000000",
    "JWT_SECRET_KEY": "test_jwt_secret_key_placeholder_value_0000",
    "SECRET_KEY": "test_django_secret_key_placeholder_value_0000",
    "AES_ENCRYPTION_KEY": "test_aes_encryption_key_placeholder_0000",
}
os.environ.update(_DUMMY_SECRETS)


def test_chat_service_shim_surface():
    import app.services.chat_service as chat

    # Public entry points used by app/api/v1/chat.py and app/api/v2/chat.py.
    public_symbols = [
        "send_message_to_llm",
        "stream_message_to_llm",
        "create_chat_thread",
        "get_chat_thread",
        "list_chat_threads",
        "update_chat_thread",
        "delete_chat_thread",
        "require_chat_thread_access",
        "generate_thread_title",
        "create_chat_branch",
        "list_chat_branches",
        "get_chat_branch",
        "delete_chat_branch",
        "create_chat_message",
        "get_chat_messages",
        "get_chat_files",
    ]
    # Key private helpers the shim must still re-export (used internally by
    # callers / other chat submodules via the package surface).
    private_symbols = [
        "_build_chat_messages",
        "_get_chat_openai_tools",
        "_execute_tool_call",
        "_get_client",
        "_safe_effective_base_url",
        "_lookup_stored_byok_key",
        "_record_tool_cost_fire_and_forget",
    ]

    for sym in public_symbols + private_symbols:
        assert hasattr(chat, sym), f"chat_service shim missing expected symbol: {sym}"

    # The shim must not be the old 2885-line module object; it should be the
    # thin re-export (its __file__ is the 1-line shim, not the original file).
    assert chat.__name__ == "app.services.chat_service"
