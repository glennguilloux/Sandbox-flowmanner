# Discord Integration Card — Implementation Plan

**Goal:** Add a Discord integration card to the FlowManner integrations page, following the same pattern as Slack, Google, Notion, and GitHub.

**Architecture:** The integrations page is data-driven — both `/integrations` and `/dashboard/settings/integrations` render whatever the backend `GET /api/v1/integrations` returns. The backend has two layers: a static `AVAILABLE_INTEGRATIONS` registry (defines name/description/category for the card) and a `OAUTH_PROVIDERS` dict (defines OAuth2 endpoints + credentials).

**Current state:** Discord already has a `_NON_OAUTH_CONFIGS` entry in `integration_bridge.py` with `DISCORD_BOT_TOKEN` (bot token, not OAuth). The frontend also already references Discord via `SiDiscord` usage — need to verify. The card needs OAuth2 for user-level authentication like the other providers.

**Tech Stack:** FastAPI backend + Next.js frontend + Discord OAuth2 API

---

## Task 1: Add Discord OAuth Provider (Backend)

> **Why first:** The card won't render as a clickable integration without the backend provider registered.

**Files:**
- Modify: `backend/app/core/oauth.py` — add Discord OAuthProviderConfig
- Modify: `backend/app/api/v1/integrations.py` — add Discord to AVAILABLE_INTEGRATIONS

### Step 1.1: Register Discord OAuth Provider

In `backend/app/core/oauth.py`, add Discord to `OAUTH_PROVIDERS`:

```python
"discord": OAuthProviderConfig(
    slug="discord",
    name="Discord",
    authorize_url="https://discord.com/api/oauth2/authorize",
    token_url="https://discord.com/api/oauth2/token",
    client_id_env="DISCORD_OAUTH_CLIENT_ID",
    client_secret_env="DISCORD_OAUTH_CLIENT_SECRET",
    scopes=["identify", "guilds", "messages.read", "webhook.incoming"],
),
```

**Env vars needed (not in code):**
- `DISCORD_OAUTH_CLIENT_ID` — Discord app client ID
- `DISCORD_OAUTH_CLIENT_SECRET` — Discord app client secret

**Note:** `identify` and `guilds` are always-available Discord OAuth2 scopes. The additional scopes depend on what FlowManner's Discord integration does — adjust based on the existing bot token integration's capabilities.

### Step 1.2: Add Discord to Available Integrations

In `backend/app/api/v1/integrations.py`, add Discord to `AVAILABLE_INTEGRATIONS`:

```python
Integration(
    slug="discord",
    name="Discord",
    description="Send messages, manage servers, and automate workflows with Discord.",
    category="communication",
    icon_url="",
    auth_type="oauth2",
),
```

**Category:** `communication` — same as Slack (they're both chat platforms). This means no new `CATEGORY_COLORS` entry needed in the frontend.

### Step 1.3: Update the Dashboard Connected Integrations page

In `backend/app/api/v1/integrations.py` `_NON_OAUTH_SETTINGS`, keep the existing `discord: "DISCORD_BOT_TOKEN"` for the non-OAuth path, but also check if the user has an OAuth connection from the DB. The `GET /connected` endpoint already handles both paths correctly (OAuth connections from DB + non-OAuth from config), so no changes needed here — the OAuth connection will automatically show up once a user connects via the new OAuth flow.

### Verification

```bash
# Restart backend
docker compose -f /opt/flowmanner/docker-compose.yml up -d --no-deps --force-recreate backend

# Check the endpoint
curl -s http://127.0.0.1:8000/api/v1/integrations | python3 -m json.tool | grep -A5 discord
```

Expected: Discord appears in the integrations list.

---

## Task 2: Add Discord Icon to Frontend Integration Pages

> **Why now:** Without the icon, the card shows a generic plug icon.

### Step 2.1: Public Integrations Page (`/integrations`)

**Files:**
- Modify: `frontend/src/app/[locale]/integrations/page.tsx`

Add `SiDiscord` to the import from `@icons-pack/react-simple-icons`:

```tsx
import {
  SiGithub, SiGoogledrive, SiNotion, SiZapier, SiDiscord,
} from "@icons-pack/react-simple-icons";
```

Add `discord` to the `ICON_MAP`:

```tsx
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  github: SiGithub,
  google_drive: SiGoogledrive,
  notion: SiNotion,
  zapier: SiZapier,
  discord: SiDiscord,
};
```

No `SlackSvg`-style custom SVG needed — `SiDiscord` from simple-icons has the Discord logo.

### Step 2.2: Dashboard Settings Integrations Page (`/dashboard/settings/integrations`)

**Files:**
- Modify: `frontend/src/app/[locale]/dashboard/settings/integrations/page.tsx`

Add Discord icon to `INTEGRATION_ICONS`:

```tsx
const INTEGRATION_ICONS: Record<string, React.ReactNode> = {
  slack: <MessageSquare className="h-8 w-8" />,
  github: <Code className="h-8 w-8" />,
  google_drive: <Cloud className="h-8 w-8" />,
  notion: <FileText className="h-8 w-8" />,
  zapier: <Zap className="h-8 w-8" />,
  discord: <MessageSquare className="h-8 w-8" />,  # or a custom SVG
};
```

**Note:** For the dashboard settings page, there's no simple-icons dependency — it uses Lucide icons. Use `MessageSquare` which matches Discord's theme. A custom Discord SVG could be added later for polish.

### Verification

```bash
# Frontend test
npm test -- --run  # Vitest
# Or simply run dev mode
npm run dev
# Navigate to /integrations — Discord card should appear with icon
```

---

## Task 3: Register Discord OAuth App

> **Prerequisite:** The app needs to exist on the Discord Developer Portal — this is a manual step.

### What the user needs to do (in Discord Developer Portal):

1. Go to https://discord.com/developers/applications
2. Create a new application (e.g. "FlowManner")
3. Go to **OAuth2** → **General**
4. Add redirect URL: `https://flowmanner.com/api/integrations/discord/oauth/callback`
   - For local dev: `http://localhost:8000/api/integrations/discord/oauth/callback`
5. Copy **Client ID** and **Client Secret**
6. Set them in the VPS `.env`:
   ```
   DISCORD_OAUTH_CLIENT_ID=your_client_id
   DISCORD_OAUTH_CLIENT_SECRET=your_client_secret
   ```

### Why this matches the existing pattern:

| Integration | Redirect URI Pattern | Provider |
|------------|-------------------|----------|
| GitHub | `/api/integrations/github/oauth/callback` | GitHub App "flowmannergithub" (from memory) |
| Slack | `/api/integrations/slack/oauth/callback` | Slack App |
| Google | `/api/integrations/google/oauth/callback` | Google Cloud project |
| Notion | `/api/integrations/notion/oauth/callback` | Notion Integration |
| **Discord** | `/api/integrations/discord/oauth/callback` | **New Discord App** |

The redirect URI format `https://flowmanner.com/api/integrations/{slug}/oauth/callback` is auto-constructed by the backend at line 228-232 of `integrations.py`.

---

## Dependency Graph

```
Task 1 (Backend OAuth provider)
  ├── 1.1 Add OAuthProviderConfig in oauth.py
  └── 1.2 Add AVAILABLE_INTEGRATIONS entry
  
Task 2 (Frontend icons) ─── independent of Task 1 (can be done in parallel)
  ├── 2.1 Public integrations page icon
  └── 2.2 Dashboard settings integrations icon

Task 3 (OAuth app setup) ─── manual, needed for production
  └── Register Discord app + set env vars
```

Tasks 1 and 2 are independent and can be done in parallel. Task 3 is manual and needed for the OAuth flow to work in production.

---

## Effort Estimate

| Task | Time | Complexity |
|------|------|------------|
| 1.1 Add Discord to OAUTH_PROVIDERS | 5 min | Low — 1 dataclass entry |
| 1.2 Add Discord to AVAILABLE_INTEGRATIONS | 2 min | Low — 1 Integration entry |
| 2.1 Public page icon | 3 min | Low — 2 lines |
| 2.2 Dashboard page icon | 2 min | Low — 1 line |
| 3 Discord app setup (manual) | 10 min | Low — Developer Portal |
| **Total** | **~20 min** | |

---

## Quick Win

If the `@icons-pack/react-simple-icons` package already includes `SiDiscord` (likely — it has 1,700+ icons), Task 2.1 is a 1-line import addition. Verify with:

```bash
grep -r "discord" /home/glenn/FlowmannerV2-frontend/node_modules/@icons-pack/react-simple-icons/ 2>/dev/null | head -3
```