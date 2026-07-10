# DeepSeek Prompt — Guides Page Content & UX Improvement

## ⚠️ REPO PATH WARNING

The frontend source lives at `/home/glenn/FlowmannerV2-frontend/`.
Do NOT edit `/opt/flowmanner/frontend/` — that is the VPS rsync target and will be overwritten on next deploy.
Run `pwd` first. It MUST print `/home/glenn/FlowmannerV2-frontend`. If it doesn't, STOP.

---

## 1. Header

You are DeepSeek. You are improving the Guides section of the FlowManner marketing site (https://flowmanner.com/guides). This is a content depth + UX improvement pass — the guides work today but the content is thin (2-3 short paragraphs per guide, no code examples, no callouts, no prerequisites) and the UX lacks standard documentation affordances (table of contents, reading progress, "what you'll learn", tips/warnings).

## 2. Goal

Enrich all 7 guides with deeper, more practical content and add standard documentation UX patterns (callouts, code blocks, TOC, prerequisites, learning outcomes). Make guides feel like real tutorials a user can follow, not marketing teasers. Maintain i18n parity across all 5 locales (en, de, es, fr, ja).

## 3. What Changed (Current State)

The guides section was built in commit `f5ebdca` (2026-06-23) and has not been touched since. Current HEAD is `c5825eb`. The tree is clean.

**Files that exist (do NOT recreate):**

| File | Purpose |
|------|---------|
| `src/lib/guides-content.ts` | Guide registry — 7 entries with slug, difficulty, timeMinutes, stepCount, featured, relatedSlugs |
| `src/lib/guides-shared.tsx` | Shared helpers: `renderWithEm()`, `slugToCamel()`, `difficultyStyles`, `difficultyDot` |
| `src/lib/__tests__/guides-content.test.ts` | 7 unit tests for the registry |
| `src/app/[locale]/guides/page.tsx` | Listing page — hero + featured guide + numbered guide list |
| `src/app/[locale]/guides/[slug]/page.tsx` | Detail page — header, summary, sections, steps, related guides, CTA |
| `src/app/[locale]/sitemap.ts` | Sitemap includes `/guides` + all guide slugs |
| `src/i18n/locales/{en,de,es,fr,ja}.json` | Each has `guidesPage` namespace with 7 guides + shared UI strings |

**Each guide in en.json currently has:**
- `title`, `description`, `summary` — short strings
- `heroTitle` (with `<em>...</em>` emphasis), `heroBody`
- `sections` — array of `{title, body}` (2-3 per guide, each body is 1 paragraph)
- `steps` — array of `{title, body}` (4-8 per guide, each body is 1-2 sentences)

**What's already installed but NOT used in guides:**
- `react-markdown` (v10.1.0) — markdown rendering
- `rehype-highlight` (v7.0.2) — syntax highlighting for code blocks
- `remark-gfm` (v4.0.1) — GitHub-flavored markdown (tables, task lists, etc.)
- `rehype-raw` (v7.0.0) — allows raw HTML in markdown

These are used in the chat component (`src/components/chat/MessageList.tsx`) but not in guides. You can use them.

**Test baseline:**
```bash
cd /home/glenn/FlowmannerV2-frontend
npx vitest run src/lib/__tests__/guides-content.test.ts  # 7 tests, all pass
```

## 4. Project Context

FlowManner is a Next.js 16.2.6 + React 19.2.4 + Tailwind 3 marketing site with next-intl i18n (5 locales). The guides section is a static, content-driven feature — no API calls, no auth, no dynamic data. All content lives in locale JSON files. The design system uses a cream background (`bg-cream`), dark cards (`bg-[#1A1A1A]`), serif headings (`font-serif`), mono labels (`font-mono`), and clay/moss accent colors. Do not change the design system — extend it.

## 5. Read These Files (Then Stop)

Read these 6 files in order, then stop reading:

1. **`src/lib/guides-content.ts`** (133 lines) — the guide registry. Understand the `GuideEntry` interface and the 7 guide entries. This is where you'll add new fields (prerequisites, learningOutcomes, etc.).
2. **`src/lib/guides-shared.tsx`** (31 lines) — shared helpers. You'll add new helpers here (callout renderer, code block wrapper).
3. **`src/app/[locale]/guides/page.tsx`** (214 lines) — listing page. Understand the layout before modifying.
4. **`src/app/[locale]/guides/[slug]/page.tsx`** (268 lines) — detail page. This is the main file you'll enhance (TOC, callouts, prerequisites, learning outcomes, code blocks).
5. **`src/i18n/locales/en.json`** — read the `guidesPage` namespace (lines ~1-500). This is the content you'll enrich. Understand the shape: `guidesPage.guides.<camelSlug>.{title,description,summary,heroTitle,heroBody,sections[],steps[]}`.
6. **`src/lib/__tests__/guides-content.test.ts`** (66 lines) — existing tests. You must keep these passing and add new ones.

**DO NOT read** unless you have a specific question:
- `src/components/chat/MessageList.tsx` — reference only if you need to see how react-markdown is configured
- `src/lib/seo-metadata.ts` — already integrated, no changes needed
- `src/lib/json-ld.ts` — already integrated, no changes needed
- Any file under `src/app/[locale]/(dashboard)/` — different app section
- Any file under `src/app/[locale]/blog/` — different feature

## 6. Scope

### IN SCOPE

**A. Enrich the `GuideEntry` type** (`src/lib/guides-content.ts`):
- Add `prerequisites?: string[]` — what the user should have/know before starting
- Add `learningOutcomes?: string[]` — 3-5 bullet points of "by the end of this guide, you will..."
- Add `category?: "getting-started" | "building" | "advanced" | "automation"` — for future grouping/filtering
- Add a `lastUpdated?: string` (ISO date) field for display

**B. Enrich guide content in en.json** (all 7 guides in `guidesPage.guides`):
- Expand `sections` from 2-3 to 3-5 per guide with longer, more practical bodies
- Add `prerequisites` array (2-4 items per guide) to each guide
- Add `learningOutcomes` array (3-5 items per guide) to each guide
- Add `tips` array to each guide — 2-4 practical tips/callouts, each `{type: "tip"|"warning"|"info", title: string, body: string}`
- Add `codeExample` to relevant guides — a code block string (markdown format) for config snippets, agent prompts, or API calls. Not every guide needs one; use judgment. Example: BYOK guide should show the settings panel config, the workflow guide should show a sample agent system prompt.

**C. Add a `Callout` component** (`src/components/guides/Callout.tsx`):
- Renders tip/warning/info callout boxes with appropriate icons (use `lucide-react` icons already in the project: `Lightbulb`, `AlertTriangle`, `Info`)
- Styled to match the existing design system (dark card, clay/moss accents)

**D. Add a `CodeBlock` component** (`src/components/guides/CodeBlock.tsx`):
- Uses `react-markdown` + `rehype-highlight` (already installed) to render syntax-highlighted code
- Styled to match the dark card aesthetic (`bg-[#1A1A1A]`, mono font, subtle border)
- Must be a client component if needed (check if react-markdown requires it)

**E. Enhance the guide detail page** (`src/app/[locale]/guides/[slug]/page.tsx`):
- Add a **"What You'll Learn"** section after the summary — renders `learningOutcomes` as a checklist (use `ListChecks` icon already imported)
- Add a **"Prerequisites"** section before the first section — renders `prerequisites` as a list (use `CheckCircle2` or similar from lucide-react)
- Add a **table of contents** sidebar (sticky, desktop only — `hidden lg:block`) that lists all sections + steps with anchor links. Use `id` attributes on section/step headings for anchor navigation.
- Render `tips` as `Callout` components inline between sections
- Render `codeExample` as a `CodeBlock` component in the appropriate section
- Add a **"Last Updated"** date display in the header area

**F. Enhance the guide listing page** (`src/app/[locale]/guides/page.tsx`):
- Add `category` badge to each guide card (small label above the title)
- No other listing page changes needed — the current design is good

**G. Update i18n for all 5 locales** (`src/i18n/locales/{en,de,es,fr,ja}.json`):
- Add the new UI strings (`prerequisitesHeading`, `learningOutcomesHeading`, `lastUpdatedLabel`, `tipLabel`, `warningLabel`, `infoLabel`, `tableOfContents`, `category.gettingStarted`, `category.building`, `category.advanced`, `category.automation`) to all 5 locale files
- Translate the new UI strings to each locale (de, es, fr, ja)
- For the guide CONTENT (sections, prerequisites, learningOutcomes, tips, codeExample): write full English content in en.json. For the other 4 locales, add the same structure with translated content. If you are not confident in translation quality for a locale, add the English content as a placeholder and mark it with a `"// TODO: translate"` comment in the JSON (but JSON doesn't support comments — instead use `"_translated": false` as a field on the guide object for that locale).

**H. Update tests** (`src/lib/__tests__/guides-content.test.ts`):
- Add tests for the new `GuideEntry` fields (prerequisites, learningOutcomes, category, tips)
- Add a test that every guide has a valid category
- Add a test that every guide has at least 2 learningOutcomes
- Add a test that every guide has at least 1 prerequisite
- Update the `getAllGuideSlugs` count test if you add guides (you should NOT add new guides — only improve existing ones, so the count stays at 7)

### OUT OF SCOPE

- **Do NOT add new guides.** Improve the 7 existing ones only.
- **Do NOT change the design system** (colors, fonts, backgrounds, card styles). Extend it with new components that match.
- **Do NOT touch the blog, docs, or dashboard sections.**
- **Do NOT change the SEO/sitemap/JSON-LD setup.** It already works.
- **Do NOT change the `Footer`, `ScrollReveal`, or `FloatingNav` components.**
- **Do NOT add new npm dependencies.** Everything you need is already installed (`react-markdown`, `rehype-highlight`, `remark-gfm`, `rehype-raw`, `lucide-react`).
- **Do NOT change the routing structure.** `/guides` and `/guides/[slug]` stay as-is.
- **Do NOT deploy.** Do NOT run `deploy-frontend.sh` or `ship`. Produce work and stop.

## 7. Critical Design Details

1. **i18n shape is the contract.** Every guide in every locale MUST have the same key structure. If en.json has `guidesPage.guides.settingUpByok.prerequisites`, then de/es/fr/ja MUST have the same path. The `guides-content.ts` registry references keys by computed path (`guidesPage.guides.${camelSlug}.title` etc.) — new fields must follow the same pattern.

2. **`t.raw()` for arrays.** The detail page already uses `t.raw()` to read arrays from the i18n store (see `src/app/[locale]/guides/[slug]/page.tsx:95-100`). Use the same pattern for `prerequisites`, `learningOutcomes`, and `tips`. Do NOT try to use `t()` for array values — next-intl's `t()` returns strings, not arrays.

3. **`<em>` tag parsing.** The `renderWithEm()` helper in `guides-shared.tsx` parses `<em>...</em>` tags in i18n strings into styled JSX. This is used for hero titles. Do NOT change this behavior. If you add `<em>` tags in new content, use `renderWithEm()` to parse them.

4. **CodeBlock must handle markdown.** Use `react-markdown` with `rehype-highlight` to render code blocks. The `codeExample` field in the i18n JSON should be a markdown string with fenced code blocks (```lang ... ```). The CodeBlock component wraps react-markdown configured with `rehype-highlight` and `remark-gfm`. Import `highlight.js/styles/github-dark.min.css` in the CodeBlock component (this is the same CSS the chat component uses — see `src/components/chat/MessageList.tsx:3`).

5. **TOC anchor links.** Section headings already exist in the detail page. Add `id` attributes derived from the section title (slugified). The TOC sidebar links to these anchors. Use `scroll-mt-20` on the heading targets so the sticky header doesn't overlap.

6. **Category is optional on GuideEntry but required in practice.** Add `category?` to the TypeScript interface (optional) but set it on all 7 guides in the registry. Suggested mapping:
   - `setting-up-byok` → `getting-started`
   - `creating-your-first-agent` → `getting-started`
   - `your-first-workflow-client-deliverable` → `getting-started`
   - `building-a-multi-step-workflow` → `building`
   - `using-the-visual-builder` → `building`
   - `advanced-multi-agent-orchestration` → `advanced`
   - `setting-up-webhooks-and-triggers` → `automation`

7. **Tips array shape.** Each tip is `{type: "tip"|"warning"|"info", title: string, body: string}`. In the i18n JSON this is an array of objects. In next-intl, `t.raw()` returns the raw JSON value, so `t.raw("guides.${key}.tips")` will return the array. Type it as `{type: string; title: string; body: string}[]` in the component.

8. **Callout icons.** Use `lucide-react` icons: `Lightbulb` for tip, `AlertTriangle` for warning, `Info` for info. These are already in the project (check `lucide-react` is in package.json — it is). Import them in the Callout component.

9. **Sticky TOC.** Use `position: sticky; top: <header-height>` on the TOC sidebar. The site header is ~80px, so use `top-24` (6rem = 96px) to clear it with margin. Only show on `lg:` breakpoint and up. On mobile, the TOC is hidden — the sections are short enough to scroll.

10. **Do NOT break existing tests.** The 7 tests in `guides-content.test.ts` must all pass after your changes. The test `getAllGuideSlugs returns exactly 7 slugs` will still pass since you're not adding guides. If you add new fields to `GuideEntry`, the test `every guide has non-empty i18n key strings` checks `titleKey`, `descriptionKey`, `summaryKey` — these don't change.

## 8. Output Expectations

### Files Created
- `src/components/guides/Callout.tsx` — callout component (tip/warning/info)
- `src/components/guides/CodeBlock.tsx` — markdown code block with syntax highlighting

### Files Modified
- `src/lib/guides-content.ts` — add fields to `GuideEntry`, set `category` + `lastUpdated` on all 7 guides
- `src/lib/guides-shared.tsx` — add any new shared helpers if needed (e.g., `slugify` for TOC anchors)
- `src/app/[locale]/guides/[slug]/page.tsx` — add TOC, prerequisites, learning outcomes, callouts, code blocks, last-updated date
- `src/app/[locale]/guides/page.tsx` — add category badge to guide cards
- `src/i18n/locales/en.json` — enrich all 7 guides with deeper content + new fields
- `src/i18n/locales/de.json` — add new UI strings + translated content (or English placeholders with `_translated: false`)
- `src/i18n/locales/es.json` — same
- `src/i18n/locales/fr.json` — same
- `src/i18n/locales/ja.json` — same
- `src/lib/__tests__/guides-content.test.ts` — add 3-4 new tests

### Verification Commands

Run these from `/home/glenn/FlowmannerV2-frontend/`:

```bash
# 1. Type check — must be 0 errors
npx tsc --noEmit

# 2. Lint — must be 0 errors
npm run lint

# 3. Unit tests — all must pass (7 existing + new ones)
npx vitest run src/lib/__tests__/guides-content.test.ts

# 4. i18n parity check — every guide must have the same keys in every locale
node -e "
const fs = require('fs');
const locales = ['en','de','es','fr','ja'];
const en = JSON.parse(fs.readFileSync('src/i18n/locales/en.json','utf8'));
const enGuides = Object.keys(en.guidesPage.guides);
let issues = [];
for (const loc of locales) {
  const d = JSON.parse(fs.readFileSync('src/i18n/locales/'+loc+'.json','utf8'));
  const locGuides = Object.keys(d.guidesPage.guides);
  // Check guide keys match
  const missing = enGuides.filter(k => !locGuides.includes(k));
  if (missing.length) issues.push(loc + ' missing guides: ' + missing.join(', '));
  // Check each guide has the same fields
  for (const g of enGuides) {
    const enKeys = Object.keys(en.guidesPage.guides[g]).sort();
    const locKeys = Object.keys(d.guidesPage.guides[g]).sort();
    const missingFields = enKeys.filter(k => !locKeys.includes(k));
    if (missingFields.length) issues.push(loc + '.' + g + ' missing fields: ' + missingFields.join(', '));
  }
  // Check UI strings
  const enUi = Object.keys(en.guidesPage).filter(k => k !== 'guides');
  for (const k of enUi) {
    if (d.guidesPage[k] === undefined) issues.push(loc + ' missing UI key: guidesPage.' + k);
  }
}
if (issues.length) { console.log('I18N PARITY ISSUES:'); issues.forEach(i => console.log('  - ' + i)); process.exit(1); }
else console.log('I18N parity OK — all locales match en.json structure');
"

# 5. Build — must succeed (catches SSR/SSG issues)
npm run build
```

### Expected Test Counts
- Existing: 7 tests (all pass, unchanged)
- New: 3-4 tests (category validation, learningOutcomes presence, prerequisites presence)
- Total: 10-11 tests, all passing

## 9. Hard Rules

- **Do NOT commit.** Do NOT push. Produce your work and stop. Glenn reviews and commits.
- **Do NOT deploy.** Do NOT run `deploy-frontend.sh`, `ship`, or any deploy command.
- **Do NOT use `--no-verify`** for git commits. (Not relevant since you shouldn't commit, but stated for clarity.)
- **Do NOT add new npm dependencies.** Everything needed is already installed.
- **Do NOT edit files on the VPS.** All work is in `/home/glenn/FlowmannerV2-frontend/`.
- **Do NOT change the design system** (Tailwind colors, fonts, background classes). Match existing styles.
- **Do NOT add new guides.** Only improve the existing 7.
- **Do NOT touch** `src/app/[locale]/sitemap.ts`, `src/lib/seo-metadata.ts`, `src/lib/json-ld.ts`, `src/components/seo/`, `src/components/layout/footer.tsx`, `src/components/layout/scroll-reveal.tsx`, `src/components/layout/floating-nav.tsx`.
- **Do NOT break existing tests.** All 7 existing tests must pass.

## 10. Failure Modes (Avoid These)

1. **Breaking i18n parity.** If you add `prerequisites` to en.json but forget de.json, the German page will crash or show missing keys. The verification script in section 8 catches this — run it.
2. **Using `t()` instead of `t.raw()` for arrays.** `t("guides.foo.prerequisites")` will return a string like "[object Object]" for arrays. Use `t.raw("guides.foo.prerequisites")` — this is already the pattern in the detail page for `sections` and `steps`.
3. **Making CodeBlock a server component when it needs to be client.** `react-markdown` may require client-side rendering. Check if the existing usage in `MessageList.tsx` is a client component (it is — it has `"use client"`). Add `"use client"` to CodeBlock.tsx.
4. **Forgetting highlight.js CSS.** Without the CSS import, syntax highlighting classes have no colors. Import `highlight.js/styles/github-dark.min.css` in CodeBlock.tsx — this is the exact import used by `src/components/chat/MessageList.tsx:3`.
5. **TOC links that don't work.** The `id` on the heading must match the `href` in the TOC. Use a `slugify()` helper — don't hand-write IDs. Remember that `id` values must be URL-safe (no spaces, no special chars).
6. **Adding `<em>` tags in non-hero content.** The `renderWithEm()` parser is only used for hero titles. Section bodies and steps are rendered as plain text. Do NOT add `<em>` tags in section/step bodies — they'll render as literal text.
7. **Changing the `featured` guide.** The test asserts `getFeaturedGuide()` returns exactly 1 guide with `slug: "your-first-workflow-client-deliverable"`. Do NOT move the `featured: true` flag.
8. **Adding guides without updating the test count.** The test `getAllGuideSlugs returns exactly 7 slugs` asserts `.length === 7`. If you add a guide, update this number. But you should NOT add guides — out of scope.
9. **Hand-writing translations you're not confident about.** If your German/French/Spanish/Japanese is not fluent, add the English content and mark `_translated: false`. Glenn would rather see honest English placeholders than bad translations.
10. **Touching the `guidesPage.difficulty` keys.** The difficulty labels (`beginner`, `intermediate`, `advanced`) are used in both the listing and detail pages. Do NOT rename them.
11. **Breaking the `generateStaticParams` function.** It returns all locale + slug combinations for SSG. If you change the guide registry shape, this must still work. Don't touch it unless necessary.
12. **Making the page a client component.** The guide pages are server components (they use `getTranslations` from `next-intl/server`). Only the new `CodeBlock` and `Callout` components should be client components (if needed). Keep the page itself as a server component.

## 11. Output Format (When Done)

Produce a report with:

1. **Files created** — list each new file with its path and a 1-line description
2. **Files modified** — list each modified file with a summary of what changed
3. **Content summary** — for each of the 7 guides, note: how many sections (before → after), how many steps (unchanged), number of prerequisites, number of learning outcomes, number of tips, whether a code example was added
4. **i18n status** — table showing which locales are fully translated vs English-placeholder
5. **Verification results** — paste the output of:
   - `npx tsc --noEmit` (0 errors)
   - `npm run lint` (0 errors)
   - `npx vitest run src/lib/__tests__/guides-content.test.ts` (all pass)
   - The i18n parity check script (section 8)
   - `npm run build` (succeeds)
6. **What you did NOT do** — explicit list of out-of-scope items you were tempted to do but didn't

Do NOT commit. Do NOT push. Produce the report and stop. Glenn will review the diff and commit.
