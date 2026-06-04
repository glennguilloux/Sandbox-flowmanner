# DEEPSEEK TASK 09: Dynamic Model Selector in Chat (with BYOK)

## Files
- `/home/glenn/FlowmannerV2-frontend/src/components/chat/ChatSettings.tsx` (181 lines)
- `/home/glenn/FlowmannerV2-frontend/src/lib/chat-types.ts` (77 lines)
- `/home/glenn/FlowmannerV2-frontend/src/components/chat/SSEChat.tsx` (258 lines)
- `/home/glenn/FlowmannerV2-frontend/src/lib/sdk/services/ByokService.ts` (66 lines)

## Current State

The chat page has a model selector in `ChatSettings.tsx`, but it uses a **hardcoded** list:

```typescript
const AVAILABLE_MODELS: ModelInfo[] = [
  { id: "llamacpp/qwen-3.6-27b", name: "Qwen 3.6 27B", provider: "Local (llama.cpp)", maxTokens: 32768, supportsStreaming: true },
  { id: "deepseek/deepseek-v4-flash", name: "DeepSeek Chat", provider: "DeepSeek API", maxTokens: 8192, supportsStreaming: true },
  { id: "deepseek/deepseek-v4-pro", name: "DeepSeek Reasoner", provider: "DeepSeek API", maxTokens: 8192, supportsStreaming: true },
];
```

The user's **stored BYOK keys** (saved at Settings → API Keys) are never shown here. The user can't select a provider they've added a key for (e.g. OpenAI, Anthropic, OpenRouter).

The backend DOES use stored BYOK keys when chat calls go through `llm_router.py` or `model_router.py` — but the user has no way to pick which provider/model to use.

## Research Reference

See `/opt/flowmanner/plans/research/openai-compatible-providers.md` for the full list of OpenAI-compatible providers, base URLs, and models. The `PROVIDER_MODELS` mapping from TASK-10 should be reused here — **import or duplicate** the same model definitions.

## What to Do

### Step 1: Fetch user's BYOK keys and merge into model list

In `ChatSettings.tsx`, add a `useEffect` that:
1. Calls `Byok.listApiKeysApiByokGet()` to get the user's stored API keys
2. For each stored key, check if it has a `models` list. If yes, use those specific models. If `models` is null/empty, show ALL predefined models for that provider from `PROVIDER_MODELS`.
3. Merge BYOK models with the 3 hardcoded platform models

For example, if user has an OpenAI key with `models: ["openai/gpt-4o", "openai/o3-mini"]`, add just those two. If `models: null`, add all OpenAI models from the predefined list.

### Step 2: Known model list per provider

**Reuse the `PROVIDER_MODELS` constant from TASK-10** (copy or extract to a shared file). Do NOT hardcode a duplicate. The full list covers 11 providers:

| Provider | Example Models |
|----------|---------------|
| deepseek | deepseek-v4-flash, deepseek-v4-pro |
| openai | gpt-4o, gpt-4o-mini, gpt-4-turbo, o1, o3-mini |
| anthropic | claude-sonnet-4, claude-3.5-sonnet, claude-3.5-haiku |
| openrouter | claude-sonnet-4, gpt-4o, gemini-2.5-pro |
| google | gemini-2.5-pro, gemini-2.5-flash |
| groq | llama-4-maverick, llama-4-scout, deepseek-r1-distill, qwen-3-32b |
| together | llama-4-maverick, deepseek-r1, qwen-3-235b |
| fireworks | llama-4-maverick, qwen-3-32b |
| deepinfra | llama-4-maverick, qwen-3-32b |
| xai | grok-3, grok-3-mini |
| openai_compatible | no predefined models — shown only if user has a key with custom model IDs |

If extracting to a shared file, put it in `/src/lib/provider-models.ts` and import in both TASK-09 (ChatSettings) and TASK-10 (settings page).

### Step 3: Show BYOK badge

In the model dropdown, show a "BYOK" badge on models that use the user's key (vs platform models). This makes it clear which models will bill the user's own account.

Add to `ModelInfo` type:
```typescript
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  maxTokens?: number;
  supportsStreaming?: boolean;
  isBYOK?: boolean;  // NEW
}
```

### Step 4: Update SSEChat to pass model_id correctly

`SSEChat.tsx` line 113 already sends `body.model = settings.model`. This should work as-is since the backend's `chat_service.py` and `llm_router.py` receive the model ID and look up BYOK keys automatically.

No changes needed in SSEChat — just verify it works end-to-end after the model selector changes.

## Constraints
- Do NOT remove the 3 hardcoded platform models (llamacpp, deepseek flash/pro) — they're the fallback when no BYOK key exists
- BYOK keys must be fetched client-side only (no server component)
- Empty state: if user has no BYOK keys, only show the 3 platform models (current behavior)
- Keep the existing ChatSettings UI structure — just extend the model list dynamically
- Don't change the `ChatSettings` type — `model` is already a `string`

## Verification
1. `cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -20` — must build clean
2. Manually test: save a BYOK key → open chat → model dropdown shows provider's models with "BYOK" badge
3. Manually test: select a BYOK model → send message → verify response comes from the user's provider (check backend logs)
4. `grep -rn "isBYOK" src/components/chat/` — verify the new field is used
