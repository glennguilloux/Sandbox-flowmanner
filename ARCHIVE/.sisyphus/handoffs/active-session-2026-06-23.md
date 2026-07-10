# Handoff Document — 2026-06-23 (Session 2)

## Session Summary
Guides Rebuild completed AND **DYNAMIC_SERVER_USAGE 500 error FIXED**. All 7 guide detail pages now return 200 on production.

---

## What Was Fixed This Session ✅

### Root Cause
`generateStaticParams` in `src/app/[locale]/guides/[slug]/page.tsx` returned only `{ slug }` but the route lives under `[locale]`, so Next.js needs `{ locale, slug }`. This resulted in **zero pre-rendered pages** (confirmed via `prerender-manifest.json`: `fallback: null`, 0 guide routes). At runtime, Next.js attempted on-demand static generation, which hit `DYNAMIC_SERVER_USAGE` when the layout's `getMessages()` read from the request scope.

### Fix
```ts
// Before (broken):
export async function generateStaticParams() {
  return getAllGuideSlugs().map((slug) => ({ slug }));
}

// After (fixed):
import { routing } from "@/i18n/routing";
export async function generateStaticParams() {
  return routing.locales.flatMap((locale) =>
    getAllGuideSlugs().map((slug) => ({ locale, slug }))
  );
}
```

The page is now `ƒ` (Dynamic, server-rendered on demand) instead of `●` (SSG with zero pre-rendered pages). Dynamic rendering is fine — the page uses `getTranslations` which works correctly on-demand.

### Verification
- ✅ Local build: all 7 guides × 5 locales return 200
- ✅ Local content: h1 renders correctly, FR locale shows French content
- ✅ Production (flowmanner.com): all 7 guides return 200
- ✅ Production FR locale: 200 with French content
- ✅ Unit tests: 8/8 pass
- ✅ Deployed via `deploy-frontend.sh` (build succeeded, container restarted)

---

## Repo State

### `/home/glenn/FlowmannerV2-frontend` (frontend source)
- **Branch**: `master` (ahead 2 commits, not pushed — CI budget)
- **Commits this session**:
  - `d489064` fix(guides): add locale to generateStaticParams to fix DYNAMIC_SERVER_USAGE 500
  - `f5ebdca` feat(guides): rebuild Guides section — 7 guides, 5 locales, SEO, sitemap

### `/opt/flowmanner` (backend/ops repo)
- **Branch**: `feat/cli-v0.1-audit-fixes` (ahead 4 commits, clean)
- Unchanged this session.

---

## What Works ✅
- `/guides` index page (200 OK)
- All 7 guide detail pages (200 OK on production)
- Full i18n across 5 locales (en, fr, es, de, ja)
- Sitemap auto-generates from registry
- TDD tests pass (8/8)

## Known Minor Issues
- **Double "FlowManner" in title tag**: `<title>Setting Up BYOK — FlowManner — FlowManner</title>` — the metadata title gets the site name suffix twice. Cosmetic, not blocking.

---

## CI Budget Status ⚠️
**BLOCKED** — GitHub Actions exhausted. **Do NOT `git push`** until 2026-07-01.
- Frontend commits are local only on `master` (2 ahead of origin)
- Backend commits are local only on `feat/cli-v0.1-audit-fixes` (4 ahead of origin)
- `gh issue create` is FREE — use for discussion/triage

---

## Next Steps (for next agent)
1. **After 2026-07-01**: Push both repos to origin
2. **Optional**: Fix the double "FlowManner" title suffix in `createGuideMetadata` / `createMetadata`
3. **Optional**: Consider making guide pages truly SSG (would require passing explicit locale to `getMessages()` in the layout)
