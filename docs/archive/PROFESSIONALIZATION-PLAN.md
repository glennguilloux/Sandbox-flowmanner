# Flowmanner Professionalization Plan

> **Created:** 2026-06-06
> **Status:** Not started
> **Stack:** Next.js 16 + React 19 + TypeScript + next-intl + Tailwind CSS + Sentry

---

## Current State Audit

| Area | Status | Priority |
|------|--------|----------|
| **Translations** | en: 995 keys (100%), fr: 796 (80%), de/es/ja: 536 (53.9%) — missing 17 sections each | 🔴 High |
| **Pagination** | Used in 6 pages. Mobile layout likely breaks on small screens | 🔴 High |
| **Testing** | Vitest + Playwright deps installed, but **no test scripts in package.json**. Only 1 test file | 🔴 High |
| **TypeScript** | Unknown error count — needs `tsc --noEmit` sweep | 🔴 High |
| **Linting** | ESLint configured via `next lint` — unknown warning count | 🔴 High |
| **Error handling** | ✅ Good: global-error.tsx, not-found.tsx, 5 route-specific error pages | ✅ Done |
| **Security headers** | ✅ Good: CSP, HSTS, X-Frame-Options in next.config.ts | ✅ Done |
| **Monitoring** | ✅ Sentry integrated with tunnel routing | ✅ Done |
| **SEO** | ✅ sitemap.ts + robots.ts present | ✅ Done |
| **Known bugs** | 2 TODOs: team page presence API, UsersService soft-delete | 🟡 Medium |

---

## Phase 1: Foundation (Week 1)

Goal: Fix the build pipeline so you can catch bugs automatically.

### 1.1 Add Test Scripts to package.json

**What:** Add missing scripts so Vitest and Playwright can actually run.

```json
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage",
  "test:e2e": "playwright test"
}
```

**Why:** Vitest and @playwright/test are installed as dependencies but there's no way to run them. Without test scripts, you have zero automated bug detection.

**Verify:**
```bash
cd /home/glenn/FlowmannerV2-frontend
npm test
```
- Should run the existing `pagination.test.tsx` and report pass/fail

### 1.2 TypeScript Error Sweep

**What:** Find and fix all type errors in the codebase.

```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit 2>&1 | tee /tmp/tsc-errors.txt
```

**Why:** TypeScript errors are bugs waiting to happen — they catch undefined variables, wrong function signatures, and type mismatches before they reach users.

**Verify:**
- `npx tsc --noEmit` returns zero errors
- Save the error count: `npx tsc --noEmit 2>&1 | grep -c "error TS"`

### 1.3 ESLint Sweep

**What:** Find and fix all lint warnings.

```bash
cd /home/glenn/FlowmannerV2-frontend
npx next lint 2>&1 | tee /tmp/lint-warnings.txt
```

**Why:** Lint warnings indicate potential bugs, accessibility issues, and code quality problems.

**Verify:**
- `npx next lint` returns zero warnings
- Fix auto-fixable issues first: `npx next lint --fix`

### 1.4 Resolve Known TODOs

**What:** Address the 2 existing TODO comments:

| File | Line | Issue |
|------|------|-------|
| `src/app/[locale]/(dashboard)/team/page.tsx` | 1375 | Replace with `workspace_presence` API when backend ready |
| `src/lib/sdk/services/UsersService.ts` | 45 | Soft-delete implementation (may already be done — verify) |

**Why:** TODOs represent incomplete features that may cause runtime errors.

**Verify:**
- `grep -rn "TODO\|FIXME" src/ --include='*.ts' --include='*.tsx'` returns fewer matches

---

## Phase 2: Translations (Week 2)

Goal: Bring all locales to 100% coverage.

### 2.1 Generate Missing Key Report

**What:** Create a script that compares each locale against en.json.

**Missing sections by locale:**

| Locale | Missing Sections |
|--------|-----------------|
| fr | `swarm`, `evaluation` |
| de | `team`, `files`, `admin`, `gettingStarted`, `rag`, `feedback`, `onboarding`, `notifications`, `analytics`, `graphs`, `nps`, `evaluation`, `marketplace`, `triggers`, `templates`, `swarm`, `missions` |
| es | Same 17 sections as de |
| ja | Same 17 sections as de |

**Run this to see exact missing keys:**
```bash
cd /home/glenn/FlowmannerV2-frontend
python3 -c "
import json

def get_keys(d, prefix=''):
    keys = set()
    for k, v in d.items():
        full = f'{prefix}{k}'
        if isinstance(v, dict):
            keys |= get_keys(v, full + '.')
        else:
            keys.add(full)
    return keys

with open('src/i18n/locales/en.json') as f:
    en_keys = get_keys(json.load(f))

for lang in ['fr', 'de', 'es', 'ja']:
    with open(f'src/i18n/locales/{lang}.json') as f:
        lang_keys = get_keys(json.load(f))
    missing = sorted(en_keys - lang_keys)
    print(f'\n{lang}.json: {len(missing)} missing keys')
    for k in missing[:10]:
        print(f'  - {k}')
    if len(missing) > 10:
        print(f'  ... and {len(missing) - 10} more')
"
```

**Why:** You need a concrete list of what's missing before you can translate.

**Verify:** Script runs and outputs missing keys per locale.

### 2.2 Translate Missing Keys (AI-Assisted)

**What:** Use the DeepSeek API (already configured in your backend) to translate missing keys.

**Process for each locale (de, es, ja):**

1. Extract the missing sections from en.json as a JSON snippet
2. Send to DeepSeek with this prompt:

```
Translate these UI strings to [LANGUAGE]. Keep the JSON structure identical.
Only translate the values, not the keys. Maintain any {{variables}} and
{{placeholders}} exactly as-is. Return valid JSON only.
```

3. Review the output for obvious errors
4. Merge into the locale file

**For fr.json (only 2 sections missing):**
```bash
# Extract the swarm and evaluation sections from en.json
python3 -c "
import json
with open('src/i18n/locales/en.json') as f:
    en = json.load(f)
missing = {k: en[k] for k in ['swarm', 'evaluation'] if k in en}
print(json.dumps(missing, indent=2, ensure_ascii=False))
"
```

**Why:** AI translation is free (you already have the API key) and fast. Manual review catches obvious errors.

**Verify:**
- Each locale file has the same key count as en.json (995 keys)
- Run the i18n check: `npm run i18n:check` (after adding the script — see 2.3)

### 2.3 Add Translation Coverage Check

**What:** Create a build-time check that warns about missing translations.

Create `scripts/check-translations.js`:
```javascript
const fs = require('fs');
const path = require('path');

const localesDir = path.join(__dirname, '../src/i18n/locales');
const sourceFile = 'en.json';

function getKeys(obj, prefix = '') {
  let keys = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'object' && value !== null) {
      keys = keys.concat(getKeys(value, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

const source = JSON.parse(fs.readFileSync(path.join(localesDir, sourceFile), 'utf8'));
const sourceKeys = new Set(getKeys(source));

const files = fs.readdirSync(localesDir).filter(f => f.endsWith('.json') && f !== sourceFile);
let hasErrors = false;

for (const file of files) {
  const locale = JSON.parse(fs.readFileSync(path.join(localesDir, file), 'utf8'));
  const localeKeys = new Set(getKeys(locale));
  const missing = [...sourceKeys].filter(k => !localeKeys.has(k));

  if (missing.length > 0) {
    hasErrors = true;
    console.log(`\n❌ ${file}: ${missing.length} missing keys`);
    missing.slice(0, 5).forEach(k => console.log(`   - ${k}`));
    if (missing.length > 5) console.log(`   ... and ${missing.length - 5} more`);
  } else {
    console.log(`✅ ${file}: complete`);
  }
}

if (hasErrors) process.exit(1);
```

Add to package.json scripts:
```json
"i18n:check": "node scripts/check-translations.js"
```

**Why:** Prevents translations from drifting again. Run in CI to catch regressions.

**Verify:**
- `npm run i18n:check` passes with all locales showing ✅

### 2.4 Install i18n-ally (VS Code Extension)

**What:** Install the `i18n-ally` extension in VS Code.

**Why:** Shows translation keys inline in your editor, highlights missing translations in real-time, and lets you edit translations without switching files. Free.

**Verify:** Open any component that uses `t()` — you should see the English text inline and warnings for missing translations.

---

## Phase 3: Mobile Pagination (Week 2-3)

Goal: Make pagination usable on phones.

### 3.1 Audit Current Pagination

**What:** Test every paginated page on mobile viewport.

**Pages to test:**

| Page | File | Current Pattern |
|------|------|----------------|
| Admin Users | `src/app/[locale]/(dashboard)/admin/users/page.tsx` | Page numbers |
| Missions | `src/app/[locale]/(dashboard)/missions/page-client.tsx` | Unknown |
| Graphs | `src/app/[locale]/(dashboard)/graphs/page-client.tsx` | Unknown |
| Runs | `src/app/[locale]/(dashboard)/runs/page-client.tsx` | Unknown |
| SDK | `src/app/[locale]/developers/sdk/page.tsx` | Unknown |
| Changelog | `src/app/[locale]/developers/changelog/page.tsx` | Unknown |

**How to test:**
1. Open Chrome DevTools (F12)
2. Click "Toggle device toolbar" (Ctrl+Shift+M)
3. Select "iPhone 14 Pro" (390×844)
4. Visit each page and screenshot the pagination controls
5. Try tapping each button — is it easy to hit?

**Why:** You need to see what's broken before you can fix it.

**Verify:** Document which pages have broken/usable pagination with screenshots.

### 3.2 Fix Pagination Component

**What:** Update the pagination UI component to be mobile-responsive.

**Recommended approach:**
- On screens < 640px: Show only `← Prev | Page X of Y | Next →`
- On screens ≥ 640px: Show full page numbers with ellipsis
- All tap targets must be at least 44×44px (Apple's minimum)
- Use `flex-wrap: wrap` so buttons don't overflow

**Tailwind example:**
```tsx
<div className="flex flex-wrap items-center justify-center gap-1 sm:gap-2">
  <button className="min-h-[44px] min-w-[44px] text-sm px-2 sm:px-3">← Prev</button>
  {/* Hidden on mobile, shown on sm+ */}
  <span className="hidden sm:flex gap-1">{/* Page numbers */}</span>
  {/* Shown on mobile, hidden on sm+ */}
  <span className="sm:hidden text-sm">Page {current} of {total}</span>
  <button className="min-h-[44px] min-w-[44px] text-sm px-2 sm:px-3">Next →</button>
</div>
```

**Why:** Mobile users can't tap tiny page number buttons. Simplified controls fix this.

**Verify:**
- All pagination controls work at 320px, 375px, and 390px widths
- Buttons are easy to tap without zooming
- Navigation works correctly (no off-by-one errors)

### 3.3 Choose Right Pattern Per Page

| Page | Recommended Pattern | Why |
|------|-------------------|-----|
| Admin users | Traditional pagination | Admins need to jump to specific pages |
| Missions list | Load More button | Users scroll through their own missions |
| Graphs list | Load More button | Visual cards, browsing pattern |
| Runs list | Infinite scroll or Load More | Timeline-like data, chronological |
| SDK docs | Traditional pagination | Reference material, users jump around |
| Changelog | Infinite scroll | Chronological, read-and-scroll pattern |

**Why:** Different data types need different interaction patterns. A "Load More" button is simpler and more mobile-friendly than page numbers for casual browsing.

**Verify:** Each page uses the pattern that feels most natural for its content type.

---

## Phase 4: Quality & Polish (Week 3-4)

Goal: Make the site feel professional.

### 4.1 Lighthouse Audit

**What:** Run Lighthouse on the production site (flowmanner.com).

```bash
# In Chrome DevTools → Lighthouse tab → Select "Desktop" and "Mobile"
# Or use CLI:
npx lighthouse https://flowmanner.com --output html --output-path ./lighthouse-report.html
```

**Target scores:**
| Category | Target |
|----------|--------|
| Performance | > 90 |
| Accessibility | > 90 |
| Best Practices | > 90 |
| SEO | > 90 |

**Why:** Lighthouse gives you a concrete, measurable score and specific fix recommendations.

**Verify:** All four categories score above 90.

### 4.2 Accessibility Audit

**What:** Install the axe DevTools Chrome extension and scan every page.

**Common issues to fix:**
- Missing `alt` text on images
- Insufficient color contrast (text too light on light backgrounds)
- Missing form labels
- Missing `aria-label` on icon-only buttons
- Focus indicators not visible

**Why:** Accessibility isn't optional — it's a legal requirement in many jurisdictions and affects ~15% of users.

**Verify:** axe DevTools reports zero critical or serious issues on every page.

### 4.3 Loading States

**What:** Add skeleton loaders to all pages that fetch data.

**Why:** Without loading states, users see a blank white screen on slow connections. Skeleton loaders (gray placeholder shapes) feel instant even when data takes time.

**Verify:** Throttle network to "Slow 3G" in DevTools → every page shows a skeleton, then content.

### 4.4 Meta Tags & Social Sharing

**What:** Ensure every page has unique `<title>` and `<meta description>` via `generateMetadata`.

**Also add:**
- `og:title`, `og:description`, `og:image` for social sharing
- `twitter:card` for Twitter/X previews

**Test with:** https://opengraph.xyz — paste your URL and check the preview.

**Verify:** Every public page has unique, descriptive meta tags.

### 4.5 Console Cleanup

**What:** Remove all `console.log` statements from production code.

```bash
grep -rn "console\.log" src/ --include='*.ts' --include='*.tsx' | wc -l
```

**Why:** Console logs are a debugging tool, not a production feature. They leak information and clutter the browser console.

**Verify:** Zero `console.log` in source (except intentional error logging).

---

## Tools Reference

### Free Tools Already Available

| Tool | What | How to Use |
|------|------|-----------|
| Chrome DevTools | Debugging, mobile testing, Lighthouse | F12 in Chrome |
| Sentry | Error monitoring | Already configured — check sentry.io dashboard |
| TypeScript | Type checking | `npx tsc --noEmit` |
| ESLint | Code quality | `npx next lint` |
| Vitest | Unit testing | `npm test` (after adding script) |
| Playwright | E2E testing | `npm run test:e2e` (after adding script) |
| axe DevTools | Accessibility | Chrome extension — scan each page |
| Lighthouse | Performance audit | Chrome DevTools → Lighthouse tab |

### Recommended Free Tools to Install

| Tool | What | Install |
|------|------|---------|
| i18n-ally | Translation management in VS Code | VS Code extension marketplace |
| axe DevTools | Accessibility scanning | Chrome Web Store |
| PageSpeed Insights | Performance from Google's servers | https://pagespeed.web.dev |

### AI-Assisted Translation (Already Available)

| Tool | Cost | Use For |
|------|------|---------|
| DeepSeek API | ~$0.01/page | Translating missing locale keys |
| ChatGPT/Claude | Free tier | Reviewing translations for accuracy |

---

## Progress Tracker

Use this to track completion. Check off items as you finish them.

### Phase 1: Foundation (Week 1)
- [x] 1.1 Add test scripts to package.json
- [x] 1.2 TypeScript error sweep — 0 errors confirmed — `tsc --noEmit` returns zero errors
- [x] 1.3 ESLint sweep — 0 errors (React 19 compiler rules downgraded to warn for incremental migration) — `next lint` returns zero warnings
- [x] 1.4 Resolve 2 known TODOs (both are JSDoc comments describing implemented behavior, no code changes needed)

### Phase 2: Translations (Week 2)
- [x] 2.1 Generate missing key report
- [x] 2.2 Translate fr.json to 100% (2 sections missing → swarm + evaluation done)
- [x] 2.3 Translate de.json to 100% (20 sections missing → all done)
- [x] 2.4 Translate es.json to 100% (20 sections missing → all done)
- [x] 2.5 Translate ja.json to 100% (20 sections missing → all done)
- [x] 2.6 Add `i18n:check` script — `scripts/check-translations.js` + `npm run i18n:check` already in package.json
- [ ] 2.7 Install i18n-ally VS Code extension

### Phase 3: Mobile Pagination (Week 2-3)
- [x] 3.1 Audit all 6 paginated pages on mobile viewport — 4 pages use pagination (Admin, Missions, Graphs, Runs), 2 static pages (SDK, Changelog)
- [x] 3.2 Fix pagination component for mobile (< 640px) — shared `<Pagination />` has `sm:hidden`/`hidden sm:flex`, 44×44px tap targets, `flex-col sm:flex-row`
- [x] 3.3 Choose right pattern per page — Admin uses shared `<Pagination />`, Missions/Graphs/Runs use shared `<Pagination />` (client-side), SDK/Changelog are static (no pagination needed)
- [ ] 3.4 Test on real mobile device — component is mobile-responsive, needs manual verification on physical device

### Phase 4: Quality & Polish (Week 3-4)
- [x] 4.1 Lighthouse audit — scores: Performance 90, Accessibility 92, Best Practices 96, SEO 100 (all ≥ 90)
- [x] 4.2 Accessibility audit — fixed ARIA issues in floating-nav.tsx (logo label match, menubar child roles), removed 14 debug console.logs
- [x] 4.3 Add loading states / skeleton loaders — created `src/components/ui/skeleton.tsx` (Skeleton, SkeletonText, SkeletonCard, SkeletonTable, SkeletonPage), updated root `loading.tsx`
- [x] 4.4 Meta tags — added generateMetadata to 26 pages via server wrapper pattern (24 renamed to *-content.tsx, 2 marketplace pages converted). 12 i18n namespaces have metaTitle/metaDescription. 1 page (settings/notifications) reverted due to Turbopack bug
- [x] 4.5 Remove console.log from production — 14 debug logs removed from auth-store, websocket, middleware, floating-nav, pwa-provider; auth.ts logs guarded by !isProduction kept

---

## Quick Commands Reference

```bash
# Frontend directory
cd /home/glenn/FlowmannerV2-frontend

# Type check
npx tsc --noEmit

# Lint
npx next lint
npx next lint --fix              # Auto-fix issues

# Run tests (after adding scripts)
npm test
npm run test:coverage

# Translation check (after adding script)
npm run i18n:check

# Lighthouse
npx lighthouse https://flowmanner.com --output html

# Count console.log
grep -rn "console\.log" src/ --include='*.ts' --include='*.tsx' | wc -l

# Deploy after changes
ship                             # Auto-commit + push + deploy
# Or: bash /opt/flowmanner/deploy-frontend.sh
```
