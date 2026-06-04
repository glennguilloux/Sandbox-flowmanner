# DEEPSEEK TASK 12: Backend BYOK Pipeline Fix — PROVIDER_MAP, Key Detection, Stored-Key Lookup

## Files
- `/opt/flowmanner/backend/app/services/chat_service.py` (615 lines) — PROVIDER_MAP, key detection, stored-key lookup
- `/opt/flowmanner/backend/app/services/llm_router.py` (288 lines) — provider-aware BYOK key selection (imports from chat_service.py)
- `/opt/flowmanner/backend/app/models/byok_models.py` (39 lines) — UserAPIKey model (for reference)
- `/opt/flowmanner/backend/app/api/v1/byok.py` line 121-133 — `get_decrypted_key()` helper (for reference)

## Why This Is Urgent

The pipeline trace revealed 3 blocking gaps in `chat_service.py` that make BYOK keys invisible or misrouted:

1. **PROVIDER_MAP has only 5 entries** — any model from Anthropic, Google, Groq, Together, Fireworks, DeepInfra, or xAI resolves to DeepSeek's API key and base URL. The call goes to the wrong endpoint with the wrong key.
2. **`_detect_provider_from_key()` misses 4 prefixes** — Groq (`gsk_`), Fireworks (`fw_`), xAI (`xai-`), Together (`tgp_`) keys are detected as "openai" (sk- fallthrough), causing provider mismatch false positives.
3. **Chat and missions/swarm never use stored BYOK keys correctly** — `send_message_to_llm()` and `stream_message_to_llm()` only use the `X-User-API-Key` header. Meanwhile `llm_router.py` (used by missions, browser agent, graph workflows, swarm) has `_get_byok_key()` but returns the FIRST active key regardless of what model/provider was requested — if you have OpenAI + OpenRouter keys and request `openrouter/owl-alpha`, it might use your OpenAI key.

## Architecture Note

`llm_router.py` line 19-25 **imports** `PROVIDER_MAP` and `_resolve_provider()` from `chat_service.py`. So Steps 1-2 below automatically fix BOTH files. Steps 6-7 specifically fix the provider-agnostic key selection in `llm_router.py`.

`model_router.py` is a separate system (uses LangChain's `LLMManager`, not `PROVIDER_MAP`) — not covered here. It has its own provider config and JSON containment lookup.

## What to Do

### Step 1: Expand PROVIDER_MAP (lines 19-25)

Replace the current 5-entry map with the full 12-entry list:

```python
PROVIDER_MAP = {
    "deepseek":   ("https://api.deepseek.com/v1",            "DEEPSEEK_API_KEY"),
    "openai":     ("https://api.openai.com/v1",              "OPENAI_API_KEY"),
    "anthropic":  ("https://api.anthropic.com/v1",           "ANTHROPIC_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",           "OPENROUTER_API_KEY"),
    "google":     ("https://generativelanguage.googleapis.com/v1beta", "GOOGLE_API_KEY"),
    "groq":       ("https://api.groq.com/openai/v1",        "GROQ_API_KEY"),
    "together":   ("https://api.together.xyz/v1",            "TOGETHER_API_KEY"),
    "fireworks":  ("https://api.fireworks.ai/inference/v1",  "FIREWORKS_API_KEY"),
    "deepinfra":  ("https://api.deepinfra.com/v1/openai",    "DEEPINFRA_API_KEY"),
    "xai":        ("https://api.x.ai/v1",                    "XAI_API_KEY"),
    "zhipuai":    ("https://open.bigmodel.cn/api/paas/v4",   "ZHIPUAI_API_KEY"),
    "llamacpp":   (f"{settings.LLAMACPP_URL}/v1",            None),
}
```

### Step 2: Expand _detect_provider_from_key (lines 103-118)

Add detection for the 4 missing key prefixes BEFORE the `sk-` fallthrough:

```python
def _detect_provider_from_key(api_key: str) -> Optional[str]:
    """Detect provider from BYOK key format."""
    if not api_key:
        return None
    key_lower = api_key.lower()
    if key_lower.startswith("sk-or-"):
        return "openrouter"
    if key_lower.startswith("sk-ds-"):
        return "deepseek"
    if key_lower.startswith("sk-ant-"):
        return "anthropic"
    if key_lower.startswith("aiza"):
        return "google"
    if key_lower.startswith("gsk_"):
        return "groq"
    if key_lower.startswith("fw_"):
        return "fireworks"
    if key_lower.startswith("xai-"):
        return "xai"
    if key_lower.startswith("tgp_"):
        return "together"
    if key_lower.startswith("sk-"):
        return "openai"
    return None
```

### Step 3: Add stored BYOK key lookup function

Add a new function after `_validate_byok_key_matches_model` (around line 160):

```python
async def _lookup_stored_byok_key(
    db: AsyncSession,
    user_id: int,
    provider: str,
) -> Optional[str]:
    """Look up a stored BYOK key for a user and provider.

    Returns the decrypted API key string if found, None otherwise.
    Used as fallback when no X-User-API-Key header is present.
    """
    try:
        from app.models.byok_models import UserAPIKey

        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.user_id == user_id,
                UserAPIKey.provider == provider.lower(),
                UserAPIKey.is_active == True,
            )
        )
        key_record = result.scalars().first()
        if key_record:
            return key_record.get_api_key()
    except Exception as e:
        logger.warning("Stored BYOK key lookup failed for user %s, provider %s: %s", user_id, provider, e)

    return None
```

### Step 4: Integrate stored-key lookup in send_message_to_llm (lines 328-427)

After line 353 (mismatch_error check), add stored-key fallback:

```python
    # ── BYOK: stored-key fallback ──
    effective_user_key = user_api_key
    effective_user_base = user_base_url

    if not effective_user_key:
        # No X-User-API-Key header — try stored keys
        provider = _get_provider_for_model(raw_model)
        if provider:
            stored_key = await _lookup_stored_byok_key(db, user_id, provider)
            if stored_key:
                effective_user_key = stored_key
                # Look up stored base_url too
                from app.models.byok_models import UserAPIKey
                key_result = await db.execute(
                    select(UserAPIKey).where(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.provider == provider.lower(),
                        UserAPIKey.is_active == True,
                    )
                )
                stored_record = key_result.scalars().first()
                if stored_record and stored_record.base_url:
                    effective_user_base = stored_record.base_url
                elif not effective_user_base:
                    effective_user_base = base_url

    if raw_model and raw_model.startswith("llamacpp/"):
        effective_user_key = None

    if effective_user_key:
        client = AsyncOpenAI(api_key=effective_user_key, base_url=effective_user_base or base_url)
    elif base_url != _LLM_API_BASE or api_key != _LLM_API_KEY:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        client = _client
```

Make sure to also update the `provider` variable for usage recording — it should say "byok" when using stored keys:

```python
    # Update usage recording (line 407):
    provider="byok" if (user_api_key or effective_user_key != user_api_key) else "system",
```

### Step 5: Apply the same stored-key lookup to stream_message_to_llm (lines 439-544)

Apply the identical change after line 460 (the mismatch_error check in stream_message_to_llm):

```python
    # ── BYOK: stored-key fallback ──
    effective_user_key = user_api_key
    effective_user_base = user_base_url

    if not effective_user_key:
        provider = _get_provider_for_model(raw_model)
        if provider:
            stored_key = await _lookup_stored_byok_key(db, user_id, provider)
            if stored_key:
                effective_user_key = stored_key
                from app.models.byok_models import UserAPIKey
                key_result = await db.execute(
                    select(UserAPIKey).where(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.provider == provider.lower(),
                        UserAPIKey.is_active == True,
                    )
                )
                stored_record = key_result.scalars().first()
                if stored_record and stored_record.base_url:
                    effective_user_base = stored_record.base_url
                elif not effective_user_base:
                    effective_user_base = base_url

    if raw_model and raw_model.startswith("llamacpp/"):
        effective_user_key = None

    if effective_user_key:
        client = AsyncOpenAI(api_key=effective_user_key, base_url=effective_user_base or base_url)
    elif base_url != _LLM_API_BASE or api_key != _LLM_API_KEY:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        client = _client
```

And the usage recording at line 518:
```python
    provider="byok" if (user_api_key or effective_user_key != user_api_key) else "system",
```

### Step 6: Fix llm_router.py — provider-aware BYOK key selection (lines 247-276)

`llm_router.py:_get_byok_key()` currently returns the FIRST active key for a user without checking if it matches the requested model's provider. Fix it to prefer keys matching the requested provider:

```python
    async def _get_byok_key(self, user_id: str, db=None, model_id: Optional[str] = None) -> Optional[str]:
        """Look up user's BYOK API key from UserAPIKey table.

        If model_id is provided, prefer a key matching that model's provider.
        Falls back to any active key if no provider match found.
        Returns the raw API key string if found, else None.
        """
        effective_db = db or self.db
        if not effective_db or not user_id or user_id == "system":
            return None

        try:
            from sqlalchemy import select
            from app.models.byok_models import UserAPIKey

            uid = int(user_id) if str(user_id).isdigit() else None
            if uid is None:
                return None

            # Extract provider from model_id if available
            target_provider = None
            if model_id:
                target_provider = _get_provider_for_model(model_id)

            # Get all active keys for user
            stmt = (
                select(UserAPIKey)
                .where(UserAPIKey.user_id == uid)
                .where(UserAPIKey.is_active == True)
            )
            result = await effective_db.execute(stmt)
            all_keys = result.scalars().all()

            if not all_keys:
                return None

            # If we have a target provider, prefer matching key
            if target_provider:
                for key in all_keys:
                    if key.provider.lower() == target_provider.lower():
                        return key.get_api_key()
                # No exact match — try compatible providers
                for key in all_keys:
                    if _providers_compatible(key.provider, target_provider):
                        return key.get_api_key()

            # Fallback: return first available key
            return all_keys[0].get_api_key()
        except Exception as e:
            logger.warning("BYOK key lookup failed for user %s: %s", user_id, e)

        return None
```

Also update the call site at line 75 to pass `model_id`:

```python
    # OLD (line 75):
    byok_key = await self._get_byok_key(effective_user_id, db=effective_db)

    # NEW:
    byok_key = await self._get_byok_key(effective_user_id, db=effective_db, model_id=raw_model)
```

### Step 7: Fix llm_router.py — use stored key's base_url (lines 76-80)

Currently `_detect_base_url()` guesses the base URL from the model_id. But the stored key record has an explicit `base_url` field. Use that instead:

```python
    # OLD (lines 76-80):
    if byok_key:
        api_key = byok_key
        byok_base = self._detect_base_url(byok_key, raw_model)
        if byok_base:
            base_url = byok_base

    # NEW:
    if byok_key:
        api_key = byok_key
        # Use stored key's base_url if available, else detect from model
        stored_base = await self._get_byok_base_url(effective_user_id, db=effective_db, model_id=raw_model)
        if stored_base:
            base_url = stored_base
        else:
            byok_base = self._detect_base_url(byok_key, raw_model)
            if byok_base:
                base_url = byok_base
```

Add the helper method to the ModelRouter class (after `_get_byok_key`):

```python
    async def _get_byok_base_url(self, user_id: str, db=None, model_id: Optional[str] = None) -> Optional[str]:
        """Look up the base_url from the user's stored BYOK key."""
        effective_db = db or self.db
        if not effective_db or not user_id or user_id == "system":
            return None
        try:
            from sqlalchemy import select
            from app.models.byok_models import UserAPIKey

            uid = int(user_id) if str(user_id).isdigit() else None
            if uid is None:
                return None

            target_provider = _get_provider_for_model(model_id) if model_id else None

            result = await effective_db.execute(
                select(UserAPIKey)
                .where(UserAPIKey.user_id == uid)
                .where(UserAPIKey.is_active == True)
            )
            all_keys = result.scalars().all()

            # Prefer key matching the target provider
            if target_provider:
                for key in all_keys:
                    if key.provider.lower() == target_provider.lower() and key.base_url:
                        return key.base_url
                for key in all_keys:
                    if _providers_compatible(key.provider, target_provider) and key.base_url:
                        return key.base_url

            # Fallback: first key with a base_url
            for key in all_keys:
                if key.base_url:
                    return key.base_url

            return None
        except Exception as e:
            logger.warning("BYOK base_url lookup failed: %s", e)
            return None
```

## Constraints
- Do NOT change the function signatures of `send_message_to_llm` or `stream_message_to_llm` — they're called from `chat.py` and must stay compatible
- The `X-User-API-Key` header path MUST still take priority over stored keys — the header check comes first
- Do NOT import `UserAPIKey` at the top of the file — use lazy imports inside functions (follows existing pattern)
- The stored-key lookup queries the database TWICE (once for the key, once for base_url). This is intentional — simplifies the logic. Acceptable since it's only 2 queries on a cached table
- Provider names in `UserAPIKey.provider` are lowercase (e.g. "openai", "openrouter") — both the lookup and PROVIDER_MAP use lowercase
- Memory: the current `_lookup_stored_byok_key` function only opens the DB session it's given — no new sessions created
- `llm_router.py` imports `PROVIDER_MAP` from `chat_service.py` (line 19) — Steps 1-2 automatically apply to both files
- For Step 6: add `_providers_compatible` to the chat_service.py imports in `llm_router.py` line 19-25. Import `Optional` from typing if not already present (line 15)

## Verification
1. Rebuild backend: `docker build -t workflows-backend:restored /opt/flowmanner/backend/ && docker compose up -d --no-deps --force-recreate backend` (timeout=300)
2. Save a BYOK key for "openrouter" via the API keys page
3. In chat, select "openrouter/owl-alpha" and send a message
4. Check backend logs: `docker logs backend --tail 20 | grep -i byok` — should show `provider":"byok"` in usage recording
5. Test without a stored key → should fall back to platform key (OPENROUTER_API_KEY env var)
6. Test with X-User-API-Key header → should use header key, not stored key
7. Run: `cd /opt/flowmanner/backend && python3 -c "from app.services.chat_service import PROVIDER_MAP; print(len(PROVIDER_MAP))"` — should print 12
8. Unit test: `cd /opt/flowmanner/backend && python3 -c "
from app.services.chat_service import _detect_provider_from_key
assert _detect_provider_from_key('gsk_test123') == 'groq'
assert _detect_provider_from_key('fw_test123') == 'fireworks'
assert _detect_provider_from_key('xai-test123') == 'xai'
assert _detect_provider_from_key('tgp_test123') == 'together'
print('ALL 4 new key prefixes detected correctly')
"` — should pass
9. Verify `llm_router.py` receives the changes: `grep -c "model_id=" /opt/flowmanner/backend/app/services/llm_router.py` — the `_get_byok_key` call at line 75 should include `model_id=raw_model`
