# Handoff — Phase 1: Zero-Risk Cleanup

**Completed:** 2026-07-06
**Commit:** `49dd8218` (frontend)
**Deployed:** ✅ Frontend deployed to VPS

---

## Summary

Phase 1 was a zero-risk cleanup with no logic changes:

1. **Deleted 9 orphan ghost route files** across 4 directories (`build/`, `run/`, `market/`, `tools/`) under `src/app/[locale]/dashboard/`. These rendered only "Coming soon." The real pages live in `(dashboard)` route group. Nav config had no references to these paths.

2. **Added 2 missing i18n keys** (`settings.toolPermissions`, `settings.toolPermissionsDesc`) to fr.json, de.json, es.json, ja.json. All locales now have 0 missing keys for the settings section.

## Verification

- `pnpm build` passes clean
- `npx tsx scripts/validate-nav-routes.ts` confirms 49/49 core routes intact
- No broken imports from deleted ghost routes
- i18n verification: 0 missing keys across all locales

## Gotchas for Next Agent

- The flat `/dashboard/page.tsx` IS real (not a ghost) — it renders MissionsWidget, UsageStats, etc. Only the subdirectories were ghosts.
- The `(dashboard)` route group (parenthesized, URL-invisible) contains all real pages including `marketplace/`, `runs/`, `missions/`, `settings/`, `chat/`, etc.
- DE/ES/JA had 63 additional missing keys in the `services` section — addressed in Phase 4.
