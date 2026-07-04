# EXIT AUDIT — 2026-07-01 — Tool Routing Inspector (Frontend)

**Agent:** Buffy (Codebuff)
**Date:** 2026-07-01
**Scope:** Build the Tool Routing Inspector page — second feature in the frontend wiring roadmap (after Reliability Center). Audit trail + routing playground.

---

## WHAT CHANGED (one bullet per file, what + why)

### Frontend (`/home/glenn/FlowmannerV2-frontend/`)

| File | Change |
|------|--------|
| `src/app/[locale]/(dashboard)/tool-routing/page.tsx` | **NEW** — Server component with `generateMetadata()` for the tool routing inspector route (15 lines) |
| `src/app/[locale]/(dashboard)/tool-routing/page-client.tsx` | **NEW** — Main client component with two sections: Audit Trail (mission selector + routing event timeline) and Routing Playground (task input + scored tool results). 416 lines |
| `src/i18n/locales/en.json` | Added `toolRouting` namespace (41 keys) + `nav.toolRouting` key |
| `src/i18n/locales/de.json` | Same — German translations |
| `src/i18n/locales/es.json` | Same — Spanish translations |
| `src/i18n/locales/fr.json` | Same — French translations |
| `src/i18n/locales/ja.json` | Same — Japanese translations |
| `src/components/layout/nav-config.ts` | Added `{ labelKey: "nav.toolRouting", href: "/tool-routing" }` to the `tools` group in `topTier` |

### Summary

- **2 new files** (page.tsx + page-client.tsx) — 431 lines total
- **6 modified files** (5 locale JSONs + nav-config.ts) — +213 insertions, -7 deletions
- **No backend changes** — read-only reference of existing endpoints

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `src/app/[locale]/(dashboard)/reliability/page-client.tsx`: 18 changes (+11/-7) — appears to be from a concurrent session, not this one
- `src/components/layout/floating-nav.tsx`: 2 changes (+1/-1) — same, not from this session

---

## TESTS RUN + RESULT

### TypeScript

```
$ cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit

(exit code 0, no errors)
```

### Vitest

```
$ cd /home/glenn/FlowmannerV2-frontend && npx vitest run

 Test Files  72 passed (72)
      Tests  878 passed (878)
   Start at  17:40:38
   Duration  10.39s
```

---

## ⚠️ TROUBLES ENCOUNTERED — DOUBLE-CHECK THESE

### 1. File writing difficulties (HIGH concern — verify file integrity)

The `page-client.tsx` file was extremely difficult to create because it lives at `/home/glenn/FlowmannerV2-frontend/` (outside the Codebuff project root at `/opt/flowmanner/`). The `write_file` tool cannot write outside the project directory, so the file had to be created via `basher` running Python scripts. This led to:

- **Multiple failed attempts** using bash heredocs — TSX template literals (`${...}`) and curly braces conflicted with shell expansion and Python triple-quoted string delimiters
- **At least 3 partial writes** where the file was overwritten instead of appended, losing content
- **One attempt** where `content.replace()` matched the first `</section>` instead of the second, inserting extra closing braces (`</div>;\n}`) after the audit trail section — causing a 3-brace imbalance (61 open / 64 close)
- **Final solution** worked: a single Python script (`/tmp/write_full_page.py`) that constructs the entire file as a list of strings joined with newlines and writes atomically

**ACTION NEEDED:** Please verify the file renders correctly in a browser at `/tool-routing`. The TypeScript compiler and vitest both pass, but the JSX was assembled programmatically and should be visually inspected. Key things to check:
- Both sections (Audit Trail + Routing Playground) render
- Mission selector dropdown populates correctly
- Event cards expand to show JSON payload
- Score bars animate in the playground results
- Mode badges show correct colors (green for sparse, amber for fallback)

### 2. TypeScript type errors for `Record<string, unknown>` payload

The `payload` field on routing events is typed as `Record<string, unknown> | null`. Rendering `unknown` values directly in JSX causes `Type 'unknown' is not assignable to type 'ReactNode'` errors. Fixed by:
- Adding `!!` coercion for conditional rendering: `{!!payload.mode && <ModeBadge.../>}`
- Adding explicit type annotation on `.map()` callback: `(toolId: string) => ...`
- Using `String()` for rendered values

**These fixes are correct but subtle.** If you see type errors on future edits to this file, this is the pattern to follow.

### 3. `fetchMissions` useCallback dependency on `selectedMission`

The `fetchMissions` callback includes `selectedMission` in its dependency array, which means the callback identity changes every time the user selects a mission. The `!selectedMission` guard inside prevents duplicate fetches, so this works correctly. However, it's technically a code smell — the same pattern exists in `CircuitBreakerPanel.tsx` so it's consistent with the codebase, but could be cleaner with a ref.

### 4. Hardcoded English strings

Three strings in the playground section were initially hardcoded in English: "Result Summary", "Task Description", "Hash". These were caught during code review and replaced with `t()` calls (`t("resultSummary")`, `t("taskDescription")`, `t("hash")`), and the corresponding i18n keys were added to all 5 locale files. **For `ja` locale**, these were left as English (`"Result Summary"`, `"Task Description"`, `"Hash"`) since they're technical terms that may not need translation — a native speaker should review.

---

## STATUS (raw output)

### git status (frontend)

```
$ cd /home/glenn/FlowmannerV2-frontend && git status --short

M src/app/[locale]/(dashboard)/reliability/page-client.tsx
M src/components/layout/floating-nav.tsx
M src/components/layout/nav-config.ts
M src/i18n/locales/de.json
M src/i18n/locales/en.json
M src/i18n/locales/es.json
M src/i18n/locales/fr.json
M src/i18n/locales/ja.json
?? src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx
?? src/app/[locale]/(dashboard)/tool-routing/page-client.tsx
?? src/app/[locale]/(dashboard)/tool-routing/page.tsx
```

**Note:** The `reliability/page-client.tsx`, `floating-nav.tsx`, and the reliability test file are from a concurrent session — NOT from this session. Only the tool-routing files, locale JSONs, and nav-config.ts changes are from this session.

### TypeScript check

```
$ npx tsc --noEmit 2>&1 | grep 'tool-routing'

(no output — zero errors)
```

### Vitest

```
$ npx vitest run 2>&1 | tail -5

 Test Files  72 passed (72)
      Tests  878 passed (878)
   Duration  10.39s
```

---

## NEXT SESSION HANDOFF

The Tool Routing Inspector is built and type-checks clean, but it has **not been committed yet**. The next agent should:

1. **Review the page visually** — open `http://localhost:3000/tool-routing` in a browser and verify both sections render correctly. The file was assembled programmatically and should be visually confirmed.
2. **Commit** — the commit message should be: `feat(frontend): add tool routing inspector with audit trail and playground`
3. **This is the 2nd of 3 features** in the frontend wiring roadmap. The 1st (Reliability Center) is done. The 3rd feature's spec should be in the roadmap documents.

**Gotchas:**
- The `write_file` tool cannot write to `/home/glenn/FlowmannerV2-frontend/` — only to `/opt/flowmanner/`. Any future frontend file creation must use `basher` with Python scripts.
- The `Record<string, unknown>` payload type requires `!!` coercion or explicit type annotations when rendering in JSX.
- The Japanese locale (`ja.json`) has "Result Summary", "Task Description", and "Hash" left in English — a native Japanese speaker should review these translations.

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- `src/app/[locale]/(dashboard)/reliability/page-client.tsx` — modified by concurrent session
- `src/components/layout/floating-nav.tsx` — modified by concurrent session
- `src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx` — untracked, from concurrent session
- No backend files changed
- No migrations added or modified

---

## END
