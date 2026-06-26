# Handoff: Marketplace Public Visibility + Integrations Anchor Linking

**Date:** 2026-06-26
**Commit:** `348bcec` on `master` (frontend repo)
**Status:** ✅ Deployed to production

---

## Summary

Two related nav/UX gaps were investigated, implemented, tested, and shipped:

1. **Marketplace made publicly browseable** — anonymous users can now discover listings at `flowmanner.com/marketplace` without signing in. Install action redirects to signin.
2. **Integrations dropdown items now deep-link via `#anchor`** — each nav item (Slack, Notion, Discord, etc.) links to its card with scroll + highlight animation.

---

## What Changed

### Files Modified (frontend: `/home/glenn/FlowmannerV2-frontend/`)

| File | Change |
|------|--------|
| `src/middleware.ts` | Removed `/marketplace` from `protectedPaths`. Added specific sub-paths: `/marketplace/my-installed`, `/marketplace/my-listings`, `/marketplace/create-listing` |
| `src/components/layout/nav-config.ts` | Added `{ labelKey: "nav.marketplace", href: "/marketplace" }` to `publicNav` → Products group. Updated all 6 integrations items from `/integrations` → `/integrations#slack`, `#notion`, `#discord`, `#apiflow`, `#github`, `#google` |
| `src/app/[locale]/(dashboard)/marketplace/marketplace-page-content.tsx` | Added `useAuth` import + `isAuthenticated` guard in `handleInstall` — redirects to `/signin?from=...` when not authenticated |
| `src/app/[locale]/integrations/integrations-page-content.tsx` | Added `id={integration.slug}` to each integration card div. Added `useEffect` for scroll-to-anchor with 2-second cyan ring highlight (with timeout cleanup) |

### Lines Changed
+33 lines added, -7 lines removed across 4 files.

---

## Architecture Decisions

### Marketplace: Auth-only → Public

**Decision:** Make `/marketplace` publicly browseable, keep sub-pages auth-protected.

**Rationale:**
- SEO: listings get indexed by Google
- User acquisition: users discover tools before signing up
- Social sharing: direct links work without signin redirect
- Install action already gated by backend JWT auth

**Trade-off:** The `/marketplace/listing-detail` route is also public (confirmed it has no user-specific data). If that changes, add it to `protectedPaths`.

### Integrations: Anchor Linking (Option A)

**Decision:** Use `#anchor` hash linking instead of per-integration detail pages (Option B).

**Rationale:**
- Option A: ~20 min, works with existing architecture, each link is meaningful
- Option B: ~2-3 hours, needs backend `GET /integrations/{slug}` endpoint, new route + component
- Option A doesn't preclude Option B later

---

## Validation Results

### TypeScript
✅ Clean — `npx tsc --noEmit` passes with no errors.

### ESLint
✅ No new warnings/errors in modified files. Pre-existing warnings (unused vars in middleware, `window.location.href` in integrations) are unrelated.

### Tests
✅ 813 tests pass. 3 pre-existing failures in `SSEChat.test.tsx` (next-intl context issue in `WhyDrawer.tsx` — unrelated).

### Code Review
Addressed 2 findings from code-reviewer-mimo-pro:
1. **Missing `/marketplace/listing-detail`** in protectedPaths → Verified it's a public browseable page, correctly left unprotected.
2. **No timeout cleanup** in scroll-to-anchor useEffect → Added proper cleanup with `clearTimeout` for both scroll and highlight timers.

### Live Smoke Tests (curl + Playwright)

| Test | Result |
|------|--------|
| `GET /marketplace` (signed out) | ✅ HTTP 200, title: "Marketplace — FlowManner — FlowManner" |
| `GET /marketplace/my-installed` (signed out) | ✅ 307 → signin |
| `GET /marketplace/my-listings` (signed out) | ✅ 307 → signin |
| `GET /marketplace/create-listing` (signed out) | ✅ 307 → signin |
| `GET /integrations` (signed out) | ✅ 307 → signin (renders signin form) |
| Sign-in with Playwright | ✅ Redirects to `/dashboard` |
| `/marketplace` (signed in) | ✅ Loads correctly |
| `/integrations#slack` (signed in) | ⚠️ No cards render — backend `GET /api/v1/integrations` returns 404 |

---

## Known Issues / Follow-ups

### 🔴 Backend: `GET /api/v1/integrations` returns 404

The integrations page renders no cards because the backend endpoint doesn't exist. The frontend `fetchIntegrations()` calls `GET /api/v1/integrations` which returns `{"detail": "Not Found"}`.

**Impact:** The anchor linking code is correct (`id={integration.slug}` + scroll-to-anchor `useEffect`) but has no data to work with. Once the backend endpoint returns integration objects with `slug` fields, the anchors will work automatically.

**Next step:** Implement `GET /api/v1/integrations` endpoint in the backend. The frontend expects an array of objects with: `slug`, `name`, `description`, `category`, `icon_url`, `auth_type`.

### 🟡 Per-Integration Detail Pages (Option B — deferred)

Future enhancement: create `/integrations/[slug]` dynamic route with dedicated detail pages, setup instructions, and connect flow. Not needed now — anchor linking is sufficient.

### 🟡 Footer Links

The marketplace could be added to the public footer (Products section) for additional discoverability.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/components/layout/nav-config.ts` | Nav structure — `publicNav` and `authenticatedNav` configs |
| `src/components/layout/floating-nav.tsx` | Renders nav — uses `publicNav` for anon, `authenticatedNav` for signed-in |
| `src/middleware.ts` | Auth middleware — `protectedPaths` array controls which routes require auth |
| `src/app/[locale]/(dashboard)/marketplace/marketplace-page-content.tsx` | Marketplace page — fetches listings, handles install |
| `src/app/[locale]/integrations/integrations-page-content.tsx` | Integrations page — fetches integrations + connections, renders cards |
| `src/lib/marketplace-api.ts` | Marketplace API client — `fetchListings`, `installListing`, etc. |
| `src/lib/integrations-api.ts` | Integrations API client — `fetchIntegrations`, `connectIntegration`, etc. |
| `src/types/marketplace.ts` | Marketplace type definitions |

---

## Deployment

- **Commit:** `348bcec` on `master`
- **Deployed:** 2026-06-26 via `bash /opt/flowmanner/deploy-frontend.sh`
- **VPS containers:** `flowmanner-frontend` (up), `flowmanner-nginx` (up)
- **Backend:** No changes — backend was not modified in this session
