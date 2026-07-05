# Task: Phase 0 — Stabilize Chat Surface

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P0 — blocks all hybrid platform work
**Estimated effort:** 1 session
**Created:** 2026-07-05
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`, `docs/SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md`, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

The original draft made two material errors that must be flagged before implementation:

1. **Marketplace v2 router does NOT exist.** The draft claimed "The v2 marketplace router **does** exist (`backend/app/api/v2/__init__.py` registers a marketplace router)". This is verifiably false: `v2/__init__.py` (90 lines, read in full on 2026-07-05) imports and registers `auth, missions, agents, chat, workspaces, search, programs, personal_memory, critiques, dashboard, integrations, integrations_actions, integrations_oauth, openapi, blueprints, runs, regression` — **no marketplace router anywhere**. There is also no `v1/marketplace.py` or `v1/marketplace/` directory (`ls` confirmed). The frontend hits `/api/marketplace/listings` (no `/v2/` prefix) and gets 404 because no router is mounted at any version. The `MarketplaceService` exists at `backend/app/services/marketplace_service.py` and is actively seeded on startup (`lifespan.py:65` calls `_seed_marketplace()` → `seed_marketplace_listings()`), but none of it is exposed via HTTP. **The task is therefore: create the v1 marketplace router (the frontend calls the un-versioned `/api/marketplace/` path), or update the frontend client to hit a new v2 endpoint.** The frontend `apiClient` strips the `/api` prefix and the versioning middleware negotiates v1/v2 — pick one before coding.

2. **The `_seed_marketplace()` call** in `lifespan.py:65` seeds data but does not expose it via HTTP. Do not be misled by the word "seed" — the listings need a route, not just a DB row.

---

## Problem

The chat surface (`/chat`) has three known issues that block all further hybrid platform work:

1. **🔴 P0 — React hydration error #419** — triggers when sending a message. Server/client DOM mismatch. Likely also causes the sandbox preview to appear blank despite the backend forward-auth fix being confirmed working (200 OK). The error only surfaces when a user sends a message, which suggests the mismatch is in conditional render paths exercised during/after `POST /threads/{id}/chat/stream`.

2. **🟡 P1 — Marketplace 404** — `GET /api/marketplace/listings?type=integration` and `GET /api/marketplace/listings/featured` return 404. The `MarketplaceService` is fully implemented and seeded on startup, but **no router exposes it** at any version (verified — see correction #1 above).

3. **🟢 P2 — Form field accessibility** — ~6 `<input>`/`<textarea>` elements across `/chat`, `/missions`, `/integrations/browse` missing `id`/`name` attributes. Console warning only.

---

## Acceptance Criteria

- [ ] `pnpm build` succeeds with zero errors on `/home/glenn/FlowmannerV2-frontend`
- [ ] `pnpm dev` → load `/chat` → send a message → **no React #419 error** in browser console
- [ ] Sandbox preview iframe mounts and renders (if sandbox is active)
- [ ] `GET /api/v2/marketplace/listings?type=integration` returns 200 with listing data
- [ ] `GET /api/v2/marketplace/listings/featured` returns 200 with featured listings
- [ ] Frontend `/integrations/browse` page loads without 404 network errors
- [ ] No "form field element should have an id or name attribute" warnings in console for `/chat`, `/missions`, `/integrations/browse`

---

## Sub-tasks

### 0.1 — Investigate React hydration error #419

**Owner:** Frontend
**Approach:** Do NOT guess. Run dev mode to get the full unminified error.

**🔴 Reference prototype pattern:** The prototype at `.sisyphus/src/lib/store.ts` has **zero `Date.now()` calls in its initial state**. Its `createInitialStreamingState()` (store.ts:21-35) returns pure static defaults — no timestamps, no `new Date()`, no `crypto.randomUUID()` at module init. All time-varying values are set inside action bodies (which only run after mount). This is the exact pattern the production `chat-store.ts` must adopt. Compare the prototype's store init (lines 109-131) against the production store init (`chat-store.ts:120-135`) — the production store has `sessionStartTime: Date.now()` at lines 127, 188, 203; the prototype has nothing equivalent.

```bash
cd /home/glenn/FlowmannerV2-frontend
NODE_ENV=development pnpm dev
# Load /chat, send a message, read the full error from browser console
```

The dev build will name the exact mismatching component and DOM node.

**Verified prime suspects (ordered by likelihood, with line numbers checked on 2026-07-05):**

| # | Suspect | File | Lines | Problem | Likely Fix |
|---|---------|------|-------|---------|------------|
| 1 | `sessionStartTime: Date.now()` at module init | `src/stores/chat-store.ts` | 127, 188, 203 | SSR renders one timestamp, client hydrates with a different one. Confirmed present at three separate initializer sites. | Move `sessionStartTime` into a `useEffect` or lazy getter; initialize to `0` in the state shape and set on mount |
| 2 | SandboxPreviewButton SSR | `src/components/chat/SandboxPreviewButton.tsx` | escaped unicode (`\u2026`, `\u2014`) in JSX string literals may render differently through React's SSR escape pipeline; auth token fetch in `useEffect` burns first paint with `Loader2` which differs | Replace escaped chars with literal UTF-8 chars; wrap conditional rendering in a `mounted` guard |
| 3 | MessageList timestamps | `src/components/chat/MessageList.tsx` | `new Date()` / `Date.now()` rendered during SSR | `suppressHydrationWarning` on cosmetic timestamps, or render timestamps only after mount |
| 4 | SSEChat client-only state | `src/components/chat/SSEChat.tsx` (725 lines) | `typeof window !== "undefined"` checks producing different JSX paths | Unify server/client render — return same JSX, defer state to `useEffect` |
| 5 | ChatLayout store destructuring | `src/components/chat/ChatLayout.tsx:42-48` | Zustand values with different initial states server vs client | Use `useEffect`-gated state for client-only values |

**Rules:**
- Identify the **exact** mismatching element from the dev error before patching
- Minimal change only — don't refactor surrounding code
- Use `suppressHydrationWarning` ONLY where the value is genuinely time-varying and cosmetic (like a timestamp label)

### 0.2 — Patch the hydration mismatch

**Owner:** Frontend
**Depends on:** 0.1 (need to know which component)

Apply the minimal fix identified in 0.1. Typical patterns:
- `Date.now()` in Zustand initial state → lazy init in `useEffect`
- Escaped unicode in JSX → replace with literal characters (`…` instead of `\u2026`)
- Conditional `typeof window` rendering → render same markup server/client, defer client-only logic to `useEffect`
- Cosmetic timestamps → add `suppressHydrationWarning`

### 0.3 — Create marketplace v2 router (backend) + update frontend client

**Owner:** Backend + Frontend

**⚠️ CORRECTION:** The v2 marketplace router does NOT exist. `backend/app/api/v2/__init__.py` registers 18 sub-routers; none of them is `marketplace`. There is no `v1/marketplace.*` either — `ls` and `grep` both confirm. The service layer is present in three files (`services/marketplace_service.py`, `services/nexus/marketplace.py`, `services/nexus/marketplace_db.py`) but it is never wired to HTTP. The frontend `MarketplaceService.ts` and `marketplace-api.ts` both call `/api/marketplace/listings` with no version prefix.

**Step 1 — pick the service entry point.** Read `services/marketplace_service.py` and `services/nexus/marketplace_db.py` to determine which one is the canonical `MarketplaceService` (likely `nexus/marketplace_db.py` based on the workspace doc's note that it has `search`, `get_all_categories`, CRUD). The `MarketplaceService` at `services/marketplace_service.py` is likely a thin facade — confirm by reading it.

**Step 2 — create the router.** Create `backend/app/api/v2/marketplace.py`:

```python
"""V2 Marketplace router — exposes the existing MarketplaceService over HTTP."""

from fastapi import APIRouter, Depends, Query
from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
# Adjust import to the canonical service class discovered in Step 1.

router = APIRouter(prefix="/marketplace", tags=["v2-marketplace"])

@router.get("/listings")
async def list_listings(
    type: str | None = Query(None),          # tool | capability | integration
    category: str | None = Query(None),
    q: str | None = Query(None),
    featured: bool | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    user = Depends(get_current_user),
):
    # Wire to the MarketplaceService.search(...) method discovered in Step 1.
    ...

@router.get("/listings/featured")
async def list_featured(
    user = Depends(get_current_user),
):
    # Shortcut for featured listings — equivalent to listings?featured=true
    ...
```

**Step 3 — register the router.** Add to `backend/app/api/v2/__init__.py`:

```python
from app.api.v2.marketplace import router as marketplace_router
api_v2_router.include_router(marketplace_router)
```

Place the import alphabetically with the other v2 imports (somewhere after `dashboard_router`).

**Step 4 — update the frontend client.** The frontend has two call sites:
- `src/lib/marketplace-api.ts` — references `/api/marketplace/listings`, `/api/marketplace/listings/featured`, `/api/marketplace/listings/{slug}`, plus reviews and install/uninstall.
- `src/lib/sdk/services/MarketplaceService.ts` — generated client (do NOT hand-edit; regenerate from the OpenAPI spec via the SDK pipeline or leave for a later task).

Update `marketplace-api.ts` to target `/api/v2/marketplace/...`. Do NOT edit `MarketplaceService.ts` by hand (it's generated — note in the commit message that the SDK regeneration is a follow-up).

### 0.4 — Fix form field accessibility

**Owner:** Frontend (batch, low effort)

**🔴 Reference prototype pattern:** The prototype's `ChatInput.tsx:165-166` already does this correctly:
```tsx
<textarea ... id="chat-input" name="chat-input" />
```
The production `ChatInputArea.tsx` is missing these attributes. Copy the prototype's pattern: kebab-case `id`, matching `name`, descriptive.

Add `id` and `name` to every `<input>`, `<select>`, `<textarea>` in:
- `src/components/chat/ChatInputArea.tsx` — 3 fields (per audit)
- The missions form — 1 field (run `grep -rn '<input\|<textarea\|<select' src/app/**/missions*/` to find the exact file — the workspace doc names it as "the missions form" without a path)
- Integrations browse page — 2 fields (`grep` `/integrations/browse` route to find the exact file)

Pattern: `id="chat-input-message" name="message"` (descriptive, kebab-case id, camelCase name).

### 0.5 — Verification gate

**All must pass before marking Phase 0 complete:**

```bash
# Frontend build
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build

# Backend health
curl http://127.0.0.1:8000/api/health

# Marketplace endpoint (new v2 router)
curl -H "Authorization: Bearer <test_token>" http://127.0.0.1:8000/api/v2/marketplace/listings?type=integration
curl -H "Authorization: Bearer <test_token>" http://127.0.0.1:8000/api/v2/marketplace/listings/featured

# Manual: open /chat in dev mode, send a message, confirm no #419
# Manual: open /integrations/browse, confirm no 404s in the network tab
# Manual: check console for form field warnings
```

Do NOT deploy yet. Phases accumulate and deploy once at the end of a coherent set.

---

## Dependencies

- None. This is the first phase.

## Blocks

- Phase 1 (Tool registry + inline cards) — needs clean chat baseline
- Phase 2 (Agent step streaming) — needs clean chat baseline
- All subsequent phases

## Notes

- The backend `ToolRegistry` in `app/tools/base.py` is **far more complete** than the research doc assumed — `register()`, `list_all()`, `search()`, `by_tag()`, `to_openai_tool()`, `to_anthropic_tool()` are all present. Phase 1.1 work is reduced to adding 3 fields to `ToolMetadata` and exposing a discovery endpoint.
- The frontend already has `@dnd-kit` (drag/resize), `motion` (animations), `zustand` (state), `@xyflow/react` (flow diagrams), and `socket.io-client` installed. No new dependencies needed for Phases 1-3.
- `socket.io-client: ^4.8.3` confirmed in `package.json` (for Phase 2 agent control messages).
- The frontend `pnpm dev` command may conflict with the `npm run dev` alias noted in the workspace doc — prefer `pnpm` since the repo uses `pnpm-lock.yaml` and `pnpm` workspace scripts.
