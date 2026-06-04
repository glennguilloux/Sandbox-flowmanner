# DEEPSEEK TASK 13: BYOK Guardrails — Debug Logs Everywhere + Duplicate Key Fix + Models Page

## Files
- `/opt/flowmanner/backend/app/api/v1/byok.py` (149 lines) — fix 500, add logs
- `/opt/flowmanner/backend/app/api/v1/llm.py` (156 lines) — add BYOK models to models/frontend
- `/opt/flowmanner/backend/app/services/chat_service.py` (615 lines) — add logs to stored-key lookup
- `/opt/flowmanner/backend/app/services/llm_router.py` (288 lines) — add logs to BYOK key selection
- `/opt/flowmanner/backend/app/services/model_router.py` (608 lines) — add logs to BYOK execution
- `/opt/flowmanner/backend/app/utils/encryption.py` — add logs to encrypt/decrypt/validate

## Why This Matters

BYOK is THE core feature of FlowManner. Currently:
1. **Zero debug logging** — when a key fails, there's no way to trace why
2. **Duplicate key = ugly 500 SQL dump** — unique constraint `(user_id, provider) WHERE is_active=true` means one key per provider, but the error message is raw SQL
3. **Models page ignores BYOK** — shows only 2 platform models, user's stored keys invisible
4. **Non-chat paths have NO logging** — missions/swarm/browser silent when BYOK fails

## What to Do

### Step 1: Fix duplicate key handling in byok.py

Add proper exception handling for the unique constraint. Add `IntegrityError` import and a `logger`:

```python
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError  # NEW
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)  # NEW
```

In `create_api_key()`, replace the broad `except Exception` with specific handlers:

```python
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"You already have an active {data.provider} key. Delete the existing one first."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("BYOK create failed: user=%s provider=%s error=%s", user.id, data.provider, e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save API key")
```

### Step 2: Add debug logs to every BYOK step in byok.py

In `create_api_key()`:
```python
    logger.debug("BYOK create: user=%s provider=%s has_models=%s has_base_url=%s",
                 user.id, data.provider, bool(data.models), bool(data.base_url))
    
    if not validate_provider(data.provider):
        logger.warning("BYOK create: unsupported provider=%s user=%s", data.provider, user.id)
        raise HTTPException(...)
    
    logger.debug("BYOK create: provider validated, encrypting key...")
    encrypted = encrypt_api_key(data.api_key)
    logger.debug("BYOK create: key encrypted (len=%d), inserting to DB...", len(encrypted))
    
    # ... insert ...
    await db.commit()
    logger.info("BYOK created: user=%s provider=%s key_id=%s models=%s",
                user.id, data.provider, key.id, data.models)
```

In `list_api_keys()`:
```python
    logger.debug("BYOK list: user=%s", user.id)
    # ... execute ...
    logger.debug("BYOK list: user=%s returned %d keys", user.id, len(keys))
```

In `delete_api_key()`:
```python
    logger.info("BYOK deleted: user=%s provider=%s key_id=%s", user.id, key.provider, key_id)
```

### Step 3: Add logs to chat_service.py stored-key lookup

In `_lookup_stored_byok_key()`:
```python
    logger.debug("BYOK lookup: user=%s provider=%s", user_id, provider)
    # ... query ...
    if key_record:
        logger.info("BYOK lookup FOUND: user=%s provider=%s key_id=%s",
                    user_id, provider, key_record.id)
    else:
        logger.debug("BYOK lookup NOT FOUND: user=%s provider=%s", user_id, provider)
```

In `send_message_to_llm()` (around stored-key fallback):
```python
    if not effective_user_key:
        logger.debug("BYOK chat: no header key, trying stored keys for model=%s user=%s",
                     raw_model, user_id)
        # ... stored key lookup ...
        if effective_user_key:
            logger.info("BYOK chat: using stored key for provider=%s user=%s",
                        provider, user_id)
        else:
            logger.debug("BYOK chat: no stored key found, using platform key for model=%s",
                         raw_model)
```

### Step 4: Add logs to llm_router.py (covers: missions, browser agent, graph, swarm)

In `route_request()` around line 75:
```python
    logger.debug("BYOK llm_router: looking up keys for user=%s model=%s",
                 effective_user_id, raw_model)
    byok_key = await self._get_byok_key(effective_user_id, db=effective_db, model_id=raw_model)
    if byok_key:
        logger.info("BYOK llm_router: using stored key for user=%s model=%s (prefix=%s)",
                    effective_user_id, raw_model, byok_key[:7])
    else:
        logger.debug("BYOK llm_router: no stored key, using platform key for model=%s",
                     raw_model)
```

In `_get_byok_key()`:
```python
    if target_provider:
        logger.debug("BYOK key select: user=%s target=%s checking %d keys",
                     user_id, target_provider, len(all_keys))
    # When match found:
    logger.info("BYOK key select: MATCH user=%s provider=%s key_id=%s",
                user_id, target_provider, matched_key.id)
    # When no match:
    logger.warning("BYOK key select: NO MATCH user=%s target=%s available_providers=%s",
                   user_id, target_provider,
                   [k.provider for k in all_keys])
```

### Step 5: Add logs to model_router.py (covers: mission executor, graph nodes)

In `execute()` around line 444:
```python
    logger.debug("BYOK model_router: checking for model=%s user=%s",
                 target_model, user_id_int)
    byok_key = self._get_byok_key(target_model, user_id_int, db_session)
    if byok_key:
        logger.info("BYOK model_router: FOUND key_id=%s provider=%s — executing with BYOK",
                    byok_key.id, byok_key.provider)
    else:
        logger.debug("BYOK model_router: no key found, falling back to platform")
```

In `_execute_with_byok()`:
```python
    logger.info("BYOK execute START: model=%s user=%s key_id=%s base_url=%s",
                model_id, user_id, api_key_id, base_url)
    # ... execution ...
    logger.info("BYOK execute DONE: model=%s latency=%sms tokens_in=%s tokens_out=%s",
                model_id, latency_ms, input_tokens, output_tokens)
```

In `_get_byok_key()` (model_router version):
```python
    logger.debug("BYOK model_router lookup: user=%s model=%s", user_id, original_model_id)
    # ... query ...
    if result:
        logger.info("BYOK model_router lookup: MATCH key_id=%s provider=%s",
                    result.id, result.provider)
    else:
        logger.debug("BYOK model_router lookup: NO MATCH for model=%s", original_model_id)
```

### Step 6: Add logs to encryption.py

In `validate_provider()`:
```python
    logger.debug("BYOK validate: provider=%s valid=%s", provider, is_valid)
```

In `encrypt_api_key()`:
```python
    logger.debug("BYOK encrypt: key_len=%s", len(raw_key))
```

In `decrypt_api_key()`:
```python
    logger.debug("BYOK decrypt: encrypted_len=%s", len(encrypted))
```

### Step 7: Add BYOK models to models/frontend endpoint

In `llm.py:list_models_frontend()`, add BYOK models from the database:

```python
@router.get("/models/frontend", response_model=ModelListResponse)
async def list_models_frontend(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_optional),  # Allow unauthenticated
):
    from app.services.chat_service import PROVIDER_MAP
    from app.models.byok_models import UserAPIKey

    # ── Platform models ──
    provider_models = {
        "deepseek": ["deepseek-v4-flash"],
        "llamacpp": ["Qwen3.6-27B-Q5_K_M-mtp.gguf"],
    }
    # ... existing platform model loop ...

    # ── BYOK models ──
    if user and user.id:
        result = await db.execute(
            select(UserAPIKey)
            .where(UserAPIKey.user_id == user.id)
            .where(UserAPIKey.is_active == True)
        )
        byok_keys = result.scalars().all()
        for key in byok_keys:
            key_models = key.get_models_list()
            if key_models:
                for model_id in key_models:
                    # Don't duplicate if already in platform models
                    if not any(m.model_id == model_id for m in models):
                        models.append(FrontendModelInfo(
                            model_id=model_id,
                            display_name=model_id.split("/")[-1],
                            status="available",
                            provider=key.provider,
                            description=f"Your {key.provider.upper()} key · {key.key_label or 'BYOK'}",
                            context_length=None,  # Don't know
                        ))
            else:
                # User has a key but no specific models — show the provider
                models.append(FrontendModelInfo(
                    model_id=f"{key.provider}/*",
                    display_name=f"All {key.provider} models",
                    status="available",
                    provider=key.provider,
                    description=f"Your {key.provider.upper()} key · {key.key_label or 'BYOK'}",
                ))

    return ModelListResponse(models=models, total=len(models))
```

Also check `get_current_user_optional` exists in deps.py. If not, create it:
```python
async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of 401 for unauthenticated."""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
```

### Step 8: Frontend — "Activate" toggle on model cards

Once the backend returns BYOK models, the frontend models page needs to handle the BYOK models gracefully. The current `ModelsPageClient` already groups by provider and shows cards — BYOK models will appear with `provider: "openai"` etc.

Add a visual indicator for BYOK models. Check if the model comes from a BYOK key:

In `page-client.tsx`, add to the `AIModel` interface:
```typescript
interface AIModel {
  // ... existing fields ...
  is_byok?: boolean;  // NEW
}
```

In the model card, show a "Your Key" badge for BYOK models:
```tsx
{model.is_byok && (
  <span className="px-2 py-0.5 rounded-full bg-clay/10 text-clay text-xs font-medium">
    Your Key
  </span>
)}
```

The backend should set `is_byok: true` on models that come from stored keys. This requires adding `is_byok` to `FrontendModelInfo` in `llm.py`.

## Constraints
- Use `logger.debug()` for routine operations, `logger.info()` for successful key usage, `logger.warning()` for missing keys/mismatches, `logger.error()` for failures
- Log format: always include `user=X provider=Y` context so logs are greppable
- Never log the actual API key value — log only `key_id`, prefix (first 7 chars), or `len(encrypted)`
- For `model_router.py`: the `_get_byok_key` import of `UserAPIKey` must stay lazy (inside the function, not at top-level)
- The models/frontend endpoint must NOT return 401 for unauthenticated users — use the optional user dependency
- Don't break existing tests — logging changes are additive

## Verification
1. Save a BYOK key → check logs: `docker logs backend | grep "BYOK created"`
2. Send a chat message with that provider → check logs: `docker logs backend | grep "BYOK chat"`
3. Run a mission → check logs: `docker logs backend | grep "BYOK model_router\|BYOK llm_router"`
4. Visit models page → should see BYOK models with "Your Key" badge
5. Try saving duplicate key → should get HTTP 409 with friendly message, not 500 SQL dump
6. `grep -c "logger\.\(debug\|info\|warning\|error\).*BYOK" /opt/flowmanner/backend/app/` — count should be 30+
