# Task: Phase 1 — Zero-Risk Cleanup (No Logic Changes)

**Status:** DRAFT
**Priority:** P1 — reduces build noise, fixes i18n gaps
**Estimated effort:** 30 minutes
**Created:** 2026-07-06
**Source:** `docs/STUB-COMPLETION-PLAN-2026-07-06.md` §Phase 1
**Depends on:** Phase 0 (save state) ✅ complete
**Blocks:** Nothing (safe to do anytime)

---

## Problem

Two categories of low-risk cleanup:

1. **Orphan ghost routes** — 6 dashboard route directories under `src/app/[locale]/dashboard/` (FLAT directory, not the `(dashboard)` route group) render only "Coming soon." The real pages live in `src/app/[locale]/(dashboard)/` (route group with layout). The nav points to the real pages. The flat `/dashboard/build/`, `/dashboard/run/`, `/dashboard/market/`, and `/dashboard/tools/` clones are orphan ghosts that confuse the route map and can cause Next.js route conflicts.

   **Verified:** The nav-config.ts does NOT reference any of these ghost paths. The real `(dashboard)` route group has `marketplace/` and `runs/` (not `market/` or `run/`).

   **Key architecture note:** Two dashboard layouts exist:
   - `src/app/[locale]/dashboard/` — flat directory with `page.tsx` (MissionsWidget, UsageStats, etc.), `layout.tsx`, and the ghost subdirs
   - `src/app/[locale]/(dashboard)/` — route group (URL-invisible) with 28 real pages including `marketplace/`, `runs/`, `missions/`, `settings/`, `chat/`, etc.

   The flat `/dashboard/page.tsx` IS real (not a ghost). Only the 4 subdirectories are ghosts.

2. **Missing i18n keys** — `settings.toolPermissions` and `settings.toolPermissionsDesc` exist in EN but are missing from FR, DE, ES, JA locales.

---

## Acceptance Criteria

- [ ] Ghost route directories deleted: `build/`, `run/`, `market/`, `tools/` (under `[locale]/dashboard/`)
- [ ] `pnpm build` succeeds with no broken links
- [ ] `npx tsx scripts/validate-nav-routes.ts` confirms nav still valid (script exists ✅)
- [ ] 2 i18n keys added to all 4 non-EN locales
- [ ] i18n verification script shows 0 missing keys for all locales
- [ ] Two clean commits (one per task)

---

## Sub-tasks

### 1.1 — Delete 6 orphan ghost routes

These render only "Coming soon." The real pages exist in the `(dashboard)` route group and the nav points there.

**Directories to delete:**
```bash
cd /home/glenn/FlowmannerV2-frontend
git rm -r src/app/\[locale\]/dashboard/build
git rm -r src/app/\[locale\]/dashboard/run
git rm -r src/app/\[locale\]/dashboard/market
git rm -r src/app/\[locale\]/dashboard/tools
```

**Files affected (9 total):**
```
src/app/[locale]/dashboard/build/page.tsx         → "Coming soon."
src/app/[locale]/dashboard/run/page.tsx            → "Coming soon."
src/app/[locale]/dashboard/market/page.tsx         → "Coming soon."
src/app/[locale]/dashboard/market/create-listing/page.tsx
src/app/[locale]/dashboard/market/my-installed/page.tsx
src/app/[locale]/dashboard/market/my-listings/page.tsx
src/app/[locale]/dashboard/tools/page.tsx          → "Coming soon."
src/app/[locale]/dashboard/tools/hub/page.tsx
src/app/[locale]/dashboard/tools/memory-inspector/page.tsx
```

**Keep:** All other directories under `[locale]/dashboard/` AND the entire `[locale]/(dashboard)/` route group.

**Steps:**
1. `cd /home/glenn/FlowmannerV2-frontend`
2. Run the `git rm -r` commands above
3. `npx next build` → confirm no broken links
4. `npx tsx scripts/validate-nav-routes.ts` → confirm nav still valid (script exists ✅)
5. Commit: `refactor: delete 6 orphan dashboard ghost routes (build, run, market, tools)`

**Note:** The `[locale]/(dashboard)/` route group already has `marketplace/`, `runs/`, `blueprints/`, `missions/`, `chat/`, `settings/` etc. — those are the real pages. The ghosts under `[locale]/dashboard/` are flat-route duplicates from an earlier iteration.

### 1.2 — Add 2 missing i18n keys to all locales

**Keys to add to `settings` section:**
- `toolPermissions` — "Tool Permissions"
- `toolPermissionsDesc` — "Control which tools the AI assistant can use in this workspace"

**Exact EN values (from `en.json`):**
```json
"toolPermissions": "Tool Permissions",
"toolPermissionsDesc": "Control which tools the AI assistant can use in this workspace"
```

**Translations (FR is primary per project convention):**

| Locale | `toolPermissions` | `toolPermissionsDesc` |
|--------|-------------------|----------------------|
| FR | "Permissions des outils" | "Contrôlez quels outils l'assistant IA peut utiliser dans cet espace de travail" |
| DE | "Berechtigungen für Werkzeuge" | "Steuern Sie, welche Tools der KI-Assistent in diesem Arbeitsbereich verwenden darf" |
| ES | "Permisos de herramientas" | "Controla qué herramientas puede usar el asistente de IA en este espacio de trabajo" |
| JA | "ツールの権限" | "このワークスペースでAIアシスタントが使用できるツールを制御します" |

**Steps:**
1. For each locale file (`fr.json`, `de.json`, `es.json`, `ja.json`), add the two keys to the `settings` section
2. Run the i18n verification script (see below)
3. Commit: `i18n: add settings.toolPermissions keys to all 5 locales`

---

## Verification

```bash
cd /home/glenn/FlowmannerV2-frontend

# Build
npx next build

# i18n check
python3 -c "
import json
en = json.load(open('src/i18n/locales/en.json'))
def keys(x,p=''):
    r=set()
    for k,v in x.items():
        f=f'{p}.{k}' if p else k
        r.update(keys(v,f) if isinstance(v,dict) else {f})
    return r
en_keys = keys(en)
for lang in ['fr','de','es','ja']:
    d = json.load(open(f'src/i18n/locales/{lang}.json'))
    miss = en_keys - keys(d)
    print(f'{lang}: {len(miss)} missing')
"
# All should show 0 missing

# Nav validation (script exists ✅)
npx tsx scripts/validate-nav-routes.ts
```

---

## File Map

| File | Action |
|------|--------|
| `src/app/[locale]/dashboard/build/` | DELETE |
| `src/app/[locale]/dashboard/run/` | DELETE |
| `src/app/[locale]/dashboard/market/` | DELETE |
| `src/app/[locale]/dashboard/tools/` | DELETE |
| `src/i18n/locales/fr.json` | Add 2 keys to `settings` |
| `src/i18n/locales/de.json` | Add 2 keys to `settings` |
| `src/i18n/locales/es.json` | Add 2 keys to `settings` |
| `src/i18n/locales/ja.json` | Add 2 keys to `settings` |

---

## Risks

| Risk | Mitigation |
|------|------------|
| An import references a deleted ghost route | Run `npx tsc --noEmit` after `git rm` to catch broken imports |
| The flat `/dashboard/page.tsx` uses subroutes from deleted dirs | Inspect `page.tsx` imports before deleting |
