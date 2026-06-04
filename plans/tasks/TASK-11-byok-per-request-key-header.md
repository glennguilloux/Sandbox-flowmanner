# DEEPSEEK TASK 11: Per-Request BYOK Key in Chat (X-User-API-Key Header)

## Files
- `/home/glenn/FlowmannerV2-frontend/src/components/chat/SSEChat.tsx` (258 lines)
- `/home/glenn/FlowmannerV2-frontend/src/components/chat/ChatSettings.tsx` (181 lines)
- `/home/glenn/FlowmannerV2-frontend/src/lib/chat-types.ts` (77 lines)
- `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/settings/api-keys/page.tsx` (228 lines — for reference only)

## Current State

The backend's chat endpoints (`/api/chat/threads/{id}/chat` and `/api/chat/threads/{id}/chat/stream`) read two headers from the request:

```python
# chat.py line 294 & 339
user_api_key = request.headers.get("X-User-API-Key")
user_base_url = request.headers.get("X-User-Base-URL")
```

These are passed to `send_message_to_llm()` → `chat_service.py` which creates a per-request `AsyncOpenAI` client using the user's key instead of the platform key:

```python
# chat_service.py line 359-361
if effective_user_key:
    effective_base = user_base_url or base_url
    client = AsyncOpenAI(api_key=effective_user_key, base_url=effective_base)
```

**The frontend never sends these headers.** SSEChat.tsx only sends `Authorization: Bearer <token>` and a JSON body with `content`, `model`, etc.

This means the "paste a key and chat instantly" flow is broken — users MUST save keys through Settings first, and even then the stored-key lookup in `llm_router.py` takes the first key regardless of provider.

## What to Do

### Step 1: Add a "Use my own key" toggle to ChatSettings

In `ChatSettings.tsx`, add a new section below the model selector:

```tsx
{/* BYOK Key Input */}
<div>
  <label className="flex items-center justify-between text-sm font-medium text-cream/80 mb-2">
    <span className="flex items-center gap-2">
      <Key className="h-4 w-4 text-clay" />
      Use My Own API Key
    </span>
    <button
      onClick={() => {
        if (settings.byokKey) {
          onSettingsChange({ ...settings, byokKey: "", byokBaseUrl: "" });
        }
      }}
      className="text-xs text-clay hover:text-clay/80"
      type="button"
    >
      {settings.byokKey ? "Clear" : "Enable"}
    </button>
  </label>
  {settings.byokKey !== undefined ? (
    <div className="space-y-2">
      <input
        type="password"
        value={settings.byokKey}
        onChange={(e) => onSettingsChange({ ...settings, byokKey: e.target.value })}
        placeholder="sk-..."
        className="w-full px-3 py-2 rounded-lg bg-white/[0.06] border border-white/[0.08] text-cream text-sm font-mono placeholder:text-cream/30 focus:outline-none focus:ring-1 focus:ring-clay/50"
      />
      <input
        type="text"
        value={settings.byokBaseUrl || ""}
        onChange={(e) => onSettingsChange({ ...settings, byokBaseUrl: e.target.value || undefined })}
        placeholder="Custom base URL (optional)"
        className="w-full px-3 py-2 rounded-lg bg-white/[0.06] border border-white/[0.08] text-cream text-sm placeholder:text-cream/30 focus:outline-none focus:ring-1 focus:ring-clay/50"
      />
      <p className="text-xs text-cream/40">
        Your key is sent per-request and never stored. Overrides any saved keys.
      </p>
    </div>
  ) : (
    <button
      onClick={() => onSettingsChange({ ...settings, byokKey: "" })}
      className="w-full px-3 py-2 rounded-lg bg-white/[0.06] border border-dashed border-white/[0.08] text-cream/40 text-sm hover:text-cream/60 hover:border-white/[0.15] transition-colors"
    >
      + Add API key for this chat
    </button>
  )}
</div>
```

### Step 2: Update ChatSettings type

In `chat-types.ts`, add two new optional fields:

```typescript
export interface ChatSettings {
  model: string;
  systemPrompt: string;
  temperature: number;
  maxTokens: number;
  byokKey?: string;       // NEW — per-request API key
  byokBaseUrl?: string;   // NEW — custom base URL for BYOK
}
```

### Step 3: Send headers in SSEChat

In `SSEChat.tsx`, update the fetch headers (around line 107-110) to include BYOK headers:

```typescript
const headers: Record<string, string> = {
  "Content-Type": "application/json",
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
};

// ADD: Send BYOK key as header if user provided one
if (settings.byokKey) {
  headers["X-User-API-Key"] = settings.byokKey;
}
if (settings.byokBaseUrl) {
  headers["X-User-Base-URL"] = settings.byokBaseUrl;
}
```

### Step 4: Update default settings

Find where default `ChatSettings` are initialized (likely in the parent component that renders `SSEChat` and `ChatSettings`). Add default values:

```typescript
const defaultSettings: ChatSettings = {
  model: "deepseek/deepseek-v4-flash",
  systemPrompt: "",
  temperature: 0.7,
  maxTokens: 4096,
  // NEW
  byokKey: undefined,
  byokBaseUrl: undefined,
};
```

Search for `useState<ChatSettings>` in components under `/chat/` to find the initialization point.

## Constraints
- The key must NEVER be persisted to localStorage or any storage — it's per-session, per-chat
- Use `type="password"` for the key input — never show it in plain text
- BYOK key takes priority over stored keys (the backend already handles this — `chat_service.py` checks `user_api_key` first)
- Don't change the existing auth flow — `Authorization: Bearer` header must still be sent alongside
- If `byokKey` is empty string or undefined, don't send the header
- Import `Key` from lucide-react (already available in the project)

## Verification
1. `cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -20` — must build clean
2. Open chat settings → click "Enable" → paste a test key → send a message
3. Check browser DevTools Network tab → verify `X-User-API-Key` header is sent
4. Check backend logs → verify `user_api_key` is not None
5. Clear the key → verify header is NOT sent on next request
6. `grep -rn "byokKey\|X-User-API-Key\|byokBaseUrl" src/components/chat/ src/lib/chat-types.ts` — verify integration
