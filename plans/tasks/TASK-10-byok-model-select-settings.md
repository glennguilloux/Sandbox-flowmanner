# DEEPSEEK TASK 10: Full BYOK Settings — Models, Base URL, OpenAI Compatible

## Files
- `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/settings/api-keys/page.tsx` (228 lines)
- `/opt/flowmanner/backend/app/api/v1/byok.py` lines 17-21 (APIKeyCreate schema has ALL fields we need)
- `/opt/flowmanner/backend/app/models/byok_models.py` line 22 (models column)

## Current State

The API Keys settings page lets users save a BYOK key with only:
- **Provider** (dropdown: deepseek, openai, anthropic, openrouter, google)
- **API Key** (password input)
- **Label** (optional text)

But the backend `APIKeyCreate` schema supports ALL of these:

```python
class APIKeyCreate(BaseModel):
    provider: str
    api_key: str
    label: str | None = None
    base_url: str | None = None       # <-- UNUSED in frontend
    models: list[str] | None = None    # <-- UNUSED in frontend
```

The `model_router.py` uses `models` for JSON containment matching AND `base_url` for custom endpoints. Both are critical:

1. **`models` field**: `model_router.py:203` uses `UserApiKey.models.op("@>")(f'["{model_id}"]')` to match BYOK keys to selected models. Without it, BYOK lookup fails silently.
2. **`base_url` field**: `model_router.py:449` uses `byok_key.base_url` to route to custom endpoints. Essential for self-hosted, Groq, Together, Fireworks, DeepInfra, etc.

The frontend is missing: model selection, base URL input, custom model IDs, and the "OpenAI Compatible" provider option.

## What to Do

### Step 1: Expand the PROVIDERS list

Add all major OpenAI-compatible providers. Replace the existing PROVIDERS constant:

```typescript
const PROVIDERS = [
  { id: "deepseek", name: "DeepSeek", placeholder: "sk-...", baseUrl: "https://api.deepseek.com/v1" },
  { id: "openai", name: "OpenAI", placeholder: "sk-...", baseUrl: "https://api.openai.com/v1" },
  { id: "anthropic", name: "Anthropic", placeholder: "sk-ant-...", baseUrl: "https://api.anthropic.com/v1" },
  { id: "openrouter", name: "OpenRouter", placeholder: "sk-or-...", baseUrl: "https://openrouter.ai/api/v1" },
  { id: "google", name: "Google AI", placeholder: "AIza...", baseUrl: "https://generativelanguage.googleapis.com/v1beta" },
  { id: "groq", name: "Groq", placeholder: "gsk_...", baseUrl: "https://api.groq.com/openai/v1" },
  { id: "together", name: "Together AI", placeholder: "sk-...", baseUrl: "https://api.together.xyz/v1" },
  { id: "fireworks", name: "Fireworks AI", placeholder: "fw_...", baseUrl: "https://api.fireworks.ai/inference/v1" },
  { id: "deepinfra", name: "DeepInfra", placeholder: "sk-...", baseUrl: "https://api.deepinfra.com/v1/openai" },
  { id: "xai", name: "xAI (Grok)", placeholder: "xai-...", baseUrl: "https://api.x.ai/v1" },
  { id: "openai_compatible", name: "OpenAI Compatible (Custom)", placeholder: "sk-...", baseUrl: "" },
];
```

### Step 2: Pre-fill base_url when provider is selected

When the user picks a provider, auto-fill the base URL from the default. If they pick "OpenAI Compatible", leave it blank for manual entry.

Update `setNewProvider`:
```typescript
const handleProviderChange = (providerId: string) => {
  setNewProvider(providerId);
  const provider = PROVIDERS.find(p => p.id === providerId);
  setNewBaseUrl(provider?.baseUrl || "");
};
```

### Step 3: Add Base URL input field

Add after the API Key input, before the Label field:

```tsx
<div>
  <label htmlFor="api-key-base-url" className="block text-sm font-medium text-charcoal/70 mb-1">
    Base URL
  </label>
  <input
    id="api-key-base-url"
    type="text"
    value={newBaseUrl}
    onChange={(e) => setNewBaseUrl(e.target.value)}
    placeholder={PROVIDERS.find(p => p.id === newProvider)?.baseUrl || "https://api.example.com/v1"}
    className="w-full border border-white/10 rounded-xl px-4 py-2.5 text-sm font-mono bg-white/5 text-charcoal"
  />
  <p className="text-xs text-charcoal/50 mt-1">
    API endpoint. Auto-filled for known providers. Change for proxies or self-hosted.
  </p>
</div>
```

Add state:
```typescript
const [newBaseUrl, setNewBaseUrl] = useState("");
```

### Step 4: Add predefined model checkboxes PLUS custom model ID input

Below the Label field, add both a checkbox list AND a free-text input:

```tsx
<div>
  <label className="block text-sm font-medium text-charcoal/70 mb-1">
    Models (optional)
  </label>
  <p className="text-xs text-charcoal/50 mb-2">
    Select models this key can access. Leave empty for all models from this provider.
  </p>
  
  {/* Predefined model checkboxes */}
  {PROVIDER_MODELS[newProvider] && PROVIDER_MODELS[newProvider].length > 0 && (
    <div className="space-y-1 max-h-40 overflow-y-auto border border-white/10 rounded-xl p-3 bg-white/5 mb-2">
      {PROVIDER_MODELS[newProvider].map((m) => (
        <label key={m.id} className="flex items-center gap-2 text-sm text-charcoal/80 cursor-pointer">
          <input type="checkbox"
            checked={newModels.includes(m.id)}
            onChange={(e) => {
              if (e.target.checked) setNewModels([...newModels, m.id]);
              else setNewModels(newModels.filter(id => id !== m.id));
            }}
            className="rounded accent-clay"
          />
          <span>{m.name}</span>
          <span className="text-xs text-charcoal/40 ml-auto">{m.maxTokens?.toLocaleString()} ctx</span>
        </label>
      ))}
    </div>
  )}
  
  {/* Custom model ID input */}
  <div className="flex gap-2">
    <input
      type="text"
      value={customModelId}
      onChange={(e) => setCustomModelId(e.target.value)}
      placeholder='e.g. openai/gpt-4o or my-org/custom-model'
      className="flex-1 border border-white/10 rounded-xl px-4 py-2.5 text-sm font-mono bg-white/5 text-charcoal"
    />
    <button
      onClick={() => {
        if (customModelId.trim() && !newModels.includes(customModelId.trim())) {
          setNewModels([...newModels, customModelId.trim()]);
          setCustomModelId("");
        }
      }}
      disabled={!customModelId.trim()}
      className="btn-clay px-3 py-2 text-sm disabled:opacity-50"
      type="button"
    >
      Add
    </button>
  </div>
  
  {/* Show custom-added models as removable tags */}
  {newModels.filter(m => !PROVIDER_MODELS[newProvider]?.some(pm => pm.id === m)).length > 0 && (
    <div className="flex flex-wrap gap-1 mt-2">
      {newModels.filter(m => !PROVIDER_MODELS[newProvider]?.some(pm => pm.id === m)).map(m => (
        <span key={m} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-clay/10 text-clay font-mono">
          {m}
          <button onClick={() => setNewModels(newModels.filter(id => id !== m))} className="hover:text-red-500">&times;</button>
        </span>
      ))}
    </div>
  )}
</div>
```

### Step 5: Define per-provider model lists

```typescript
const PROVIDER_MODELS: Record<string, { id: string; name: string; maxTokens?: number }[]> = {
  openai: [
    { id: "openai/gpt-4o", name: "GPT-4o", maxTokens: 128000 },
    { id: "openai/gpt-4o-mini", name: "GPT-4o Mini", maxTokens: 128000 },
    { id: "openai/gpt-4-turbo", name: "GPT-4 Turbo", maxTokens: 128000 },
    { id: "openai/o1", name: "o1", maxTokens: 200000 },
    { id: "openai/o3-mini", name: "o3 Mini", maxTokens: 200000 },
  ],
  anthropic: [
    { id: "anthropic/claude-sonnet-4-20250514", name: "Claude Sonnet 4", maxTokens: 200000 },
    { id: "anthropic/claude-3-5-sonnet-20241022", name: "Claude 3.5 Sonnet", maxTokens: 200000 },
    { id: "anthropic/claude-3-5-haiku-20241022", name: "Claude 3.5 Haiku", maxTokens: 200000 },
  ],
  openrouter: [
    { id: "openrouter/anthropic/claude-sonnet-4", name: "Claude Sonnet 4", maxTokens: 200000 },
    { id: "openrouter/openai/gpt-4o", name: "GPT-4o", maxTokens: 128000 },
    { id: "openrouter/google/gemini-2.5-pro", name: "Gemini 2.5 Pro", maxTokens: 1048576 },
  ],
  google: [
    { id: "google/gemini-2.5-pro", name: "Gemini 2.5 Pro", maxTokens: 1048576 },
    { id: "google/gemini-2.5-flash", name: "Gemini 2.5 Flash", maxTokens: 1048576 },
  ],
  deepseek: [
    { id: "deepseek/deepseek-v4-flash", name: "DeepSeek V4 Flash", maxTokens: 8192 },
    { id: "deepseek/deepseek-v4-pro", name: "DeepSeek V4 Pro", maxTokens: 8192 },
  ],
  groq: [
    { id: "groq/llama-4-maverick", name: "Llama 4 Maverick", maxTokens: 128000 },
    { id: "groq/llama-4-scout", name: "Llama 4 Scout", maxTokens: 131072 },
    { id: "groq/deepseek-r1-distill-llama-70b", name: "DeepSeek R1 70B", maxTokens: 131072 },
    { id: "groq/qwen-3-32b", name: "Qwen 3 32B", maxTokens: 131072 },
  ],
  together: [
    { id: "together/llama-4-maverick", name: "Llama 4 Maverick", maxTokens: 128000 },
    { id: "together/deepseek-r1", name: "DeepSeek R1", maxTokens: 131072 },
    { id: "together/qwen-3-235b-a22b", name: "Qwen 3 235B", maxTokens: 131072 },
  ],
  fireworks: [
    { id: "fireworks/llama-4-maverick", name: "Llama 4 Maverick", maxTokens: 128000 },
    { id: "fireworks/qwen-3-32b", name: "Qwen 3 32B", maxTokens: 131072 },
  ],
  deepinfra: [
    { id: "deepinfra/llama-4-maverick", name: "Llama 4 Maverick", maxTokens: 128000 },
    { id: "deepinfra/qwen-3-32b", name: "Qwen 3 32B", maxTokens: 131072 },
  ],
  xai: [
    { id: "xai/grok-3", name: "Grok 3", maxTokens: 131072 },
    { id: "xai/grok-3-mini", name: "Grok 3 Mini", maxTokens: 131072 },
  ],
  // openai_compatible has no predefined models — user must type custom IDs
};
```

### Step 6: Add new state variables

```typescript
const [newBaseUrl, setNewBaseUrl] = useState("");
const [newModels, setNewModels] = useState<string[]>([]);
const [customModelId, setCustomModelId] = useState("");
```

### Step 7: Update handleCreate to pass ALL fields

```typescript
await Byok.createApiKeyApiByokPost({
  provider: newProvider,
  api_key: newKey.trim(),
  label: newLabel.trim() || null,
  base_url: newBaseUrl.trim() || null,
  models: newModels.length > 0 ? newModels : null,
});
```

### Step 8: Show base_url and models in the key list

Update `ApiKey` interface:
```typescript
interface ApiKey {
  id: number;
  provider: string;
  key_label: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  base_url?: string | null;   // NEW
  models?: string[] | null;   // NEW
}
```

Show base_url below the date:
```tsx
{k.base_url && (
  <p className="text-xs text-charcoal/40 font-mono truncate max-w-xs mt-0.5">{k.base_url}</p>
)}
```

Show models as before.

## Constraints
- **Never remove the existing 5 providers** (deepseek, openai, anthropic, openrouter, google) — add the new ones alongside them
- `base_url` IS optional — if empty/null, the backend uses the default for that provider
- `models` IS optional — empty/null means "all models from this provider"
- When user picks "OpenAI Compatible", auto-fill base_url = "" so they enter their own
- Predefined model checkboxes are provider-specific — changing provider resets the list
- Custom model IDs are additive — they coexist with checked predefined models
- Model ID format: `provider/model-name` (e.g. `openai/gpt-4o`, `openrouter/anthropic/claude-sonnet-4`)
- For `openai_compatible`: user MUST type custom model IDs (no predefined list)
- Reset ALL new fields when closing form: `setNewKey(""); setNewLabel(""); setNewModels([]); setNewBaseUrl(""); setCustomModelId("");`

## Verification
1. `cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -20` — must build clean
2. Add key with provider="Groq" → base_url auto-fills to `https://api.groq.com/openai/v1`
3. Add key with provider="OpenAI Compatible" → base_url stays empty, models list shows text input
4. Select "Llama 4 Maverick" checkbox + type "my-corp/custom-v1" in custom field → both saved
5. Check key list: shows base_url under date, model tags for configured models
6. Switch provider → model checkboxes update, custom tags remain
7. `grep -rn "newBaseUrl\|newModels\|customModelId\|base_url\|PROVIDER_MODELS" src/app/` — verify all new code
