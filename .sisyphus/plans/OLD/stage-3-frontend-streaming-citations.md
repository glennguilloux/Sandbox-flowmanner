# Stage 3 — Frontend Memory Citation Chips

## TL;DR

> **Quick Summary**: Render backend-emitted `memory_citation` SSE events as inline chips under assistant chat messages in the Flowmanner frontend. Extends the existing streaming hook, adds a new chip component, and wires i18n copy. TDD-first with Vitest + Playwright, and ships behind `bash /opt/flowmanner/deploy-frontend.sh`.

> **Deliverables**:
> - Typed `MemoryCitation` interface + `memory_citation` SSE event variant in `src/lib/chat-types.ts`
> - `useStreaming` handler that collects citations per assistant message via a new `addMemoryCitation` callback
> - New `MemoryCitationChip` component (label + WhyDrawer-style tooltip)
> - `MessageList` renders chips under each assistant bubble
> - `en.json` copy for chip label / tooltip
> - Vitest + Playwright tests, all green
> - Deployed to production via `deploy-frontend.sh`

> **Estimated Effort**: Short (3-5 implementation tasks + verification)
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: types → useStreaming handler → chip component → MessageList render → deploy

---

## Context

### Original Request

Plan Stage 3 of the T33 inline-citation work after Stage 2 backend (commit `2eff1b2`) is on `origin/main`. Stage 3 is frontend integration of `memory_citation` SSE events emitted by `app/services/memory_citation_service.build_citation_event`.

### Interview Summary

**Key Decisions**:
- **Tests**: TDD-first (Vitest unit + Playwright e2e).
- **Deploy**: Included in plan; final step is `bash /opt/flowmanner/deploy-frontend.sh` + live SSE behavior check.
- **No backend changes**: Stage 2 contract is final; frontend must consume existing payload.
- **No delegation** for exploration/QA (out of credits); direct local inspection only.

**Research Findings**:
- SSE event payload (`build_citation_event`, `app/services/memory_citation_service.py:219-266`):
  - `type: "memory_citation"`, `message_id`, `citation_id`, `claim_id`, `label`, `short_id`, `subject`, `predicate`, `object`, `scope`, `confidence`, `source`, optional `mission_id`, `mission_number`, `expires_at`.
  - Backend also emits a pre-stage `memory_recall_used` event (`build_recall_used_event`, line 269) with a subset of the same fields.
- Frontend chat surface: `src/lib/chat-types.ts` (SSEEvent, ChatMessage), `src/hooks/useStreaming.ts` (SSE parser + tool-call handler pattern), `src/components/chat/MessageList.tsx` (memoized message renderer), `src/components/chat/SSEChat.tsx` (composes `useStreaming` + passes `addToolEvent` etc.).
- i18n: next-intl; keys live in `src/i18n/locales/en.json`; tests mock with `useTranslations: (k) => k`.
- Test infra: Vitest 4.1.6 + jsdom + `@testing-library/react` 16.3.2 + `@testing-library/jest-dom`; `vitest.config.ts` aliases `@/`, `include: src/**/*.test.{ts,tsx}`. Playwright 1.60.0 with `e2e/` suite, single chromium project, `webServer: npm run dev` on :3000. `package.json` has no `test` script — add one.
- No existing chip/badge component for memory citations; pattern: `MilestoneBadge.tsx` (variant + size props, `cn()` from `@/lib/utils`) is the closest sibling.
- `MessageList.tsx` passes `msg` props to `MessageItem`; chip should be rendered between the assistant bubble and the `MessageActions` row.

### Metis Review

**Identified Gaps** (addressed):
- **Gap**: SSE parser currently only handles `tool_call_start` / `tool_call_result` between token events; `memory_citation` events are emitted AFTER the `complete` event — verify ordering and avoid being swallowed by `parsed.type === "complete" continue;` early-return (line 178). → Mitigation: branch must check `parsed.type === "memory_citation"` BEFORE the `complete` short-circuit, or rely on the loop continuing past `complete` and handle the new branch.
- **Gap**: No `addMemoryCitation` callback exists; citations must be persisted onto the message, not into a sibling side-panel store (chips are per-message). → Mitigation: extend `ChatMessage` with `citations?: MemoryCitation[]`; update with `setMessages` in callback.
- **Gap**: `MessageList`'s memo comparator (line 491-501) only checks `content` and `isStreaming`; adding citations will not trigger re-render. → Mitigation: include `prevProps.msg.citations === nextProps.msg.citations` in comparator; for streaming updates use a stable `id` reference.
- **Gap**: i18n for "Why" / "View memory" copy must be added; chip needs a tooltip with the recall metadata (subject/predicate/object/confidence) for parity with the existing `WhyDrawer` on Memory Inspector.
- **Gap**: Defensive handling — backend may emit citation events for an assistant message that hasn't been persisted yet (race with `message_id`). Frontend should match by `message_id` against the last assistant message in flight.

---

## Work Objectives

### Core Objective

Make T33 memory citations visible in the chat UI by adding a typed event path, a chip component, and per-message rendering, without regressing the existing streaming tool-call behavior or the live SSE protocol.

### Concrete Deliverables

- Updated `src/lib/chat-types.ts` with `MemoryCitation` type and `SSEEvent` extension.
- Updated `src/hooks/useStreaming.ts` with `addMemoryCitation` param and a `memory_citation` SSE branch.
- New `src/components/chat/MemoryCitationChip.tsx` with tooltip.
- Updated `src/components/chat/MessageList.tsx` to render chips.
- New `src/hooks/__tests__/useStreaming.memory-citations.test.ts`.
- New `src/components/chat/__tests__/MemoryCitationChip.test.tsx`.
- New `e2e/memory-citation-chip.spec.ts` (Playwright).
- Updated `src/i18n/locales/en.json` with `chat.citation.*` keys.
- New `src/i18n/locales/__tests__/en-citation-keys.test.ts` (parity check).
- `package.json` `test` and `test:run` scripts.
- All changes committed + pushed; `deploy-frontend.sh` ran; live SSE behavior verified.

### Definition of Done

- `npx vitest run` (or `npm test`) → all unit tests pass, including new ones.
- `npx tsc --noEmit` → 0 errors.
- `npm run lint` → 0 errors.
- `npx playwright test e2e/memory-citation-chip.spec.ts` → 0 failures (local only; CI out of scope unless CI flag set).
- `bash /opt/flowmanner/deploy-frontend.sh` from homelab → success, container healthy.
- Live `https://flowmanner.com/en/chat/...` shows a chip after a chat reply that triggers memory recall (manual via Playwright probe or browser screenshot saved to `.sisyphus/evidence/stage-3/`).

### Must Have

- TDD-first: tests written and confirmed failing (red) before each implementation step.
- Component, hook, and i18n changes only — no backend edits.
- Stable, accessible chip (keyboard focusable, `aria-label`, role="status" or similar) without breaking the existing `MessageActions` hover pattern.
- Citations deduplicated by `citation_id` per assistant message.
- Event ordering: `memory_citation` events are processed after token accumulation; do not regress existing 60fps batched rendering.
- Verification evidence committed to `.sisyphus/evidence/stage-3/`.

### Must NOT Have (Guardrails)

- No backend file changes. No alembic migration. No docker rebuild of `workflows-backend`.
- No edits to `/opt/flowmanner/frontend/` on the VPS — source must be edited in `/home/glenn/FlowmannerV2-frontend/` and deployed via `deploy-frontend.sh`.
- No new top-level dependencies — only use what's already in `package.json` (`lucide-react`, `clsx`, `tailwind-merge` for `cn`).
- No over-abstraction: do not extract a generic "CitationEvent" interface; T33 ships one citation source.
- No premature optimization (YAGNI): no IndexedDB persistence of citations, no virtualization of chips, no animation library.
- No f-string in `logger.*` (mirrors backend G003/G004 — frontend has no logger, but no console.log spam in prod either).

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — all verification is agent-executed. No exceptions. No "user manually tests" criteria.

### Test Decision

- **Infrastructure exists**: YES (Vitest + Playwright).
- **Automated tests**: TDD-first (RED → GREEN → REFACTOR per task).
- **Framework**: Vitest 4.1.6 (unit) + Playwright 1.60.0 (e2e).
- **If TDD**: each task's "What to do" lists the failing test first; "Acceptance criteria" requires that the test exists and passes after impl.

### QA Policy

Every task MUST include agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/stage-3/task-{N}-{slug}.{ext}`.

- **Frontend/UI**: Use Playwright (playwright skill) — navigate, assert DOM, screenshot.
- **Hooks/Logic**: Use Bash (`npx vitest run src/hooks/__tests__/...`) — assert exit 0 and green output.
- **Type Safety**: Use Bash (`npx tsc --noEmit`) — assert exit 0 and "0 errors".

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundations + RED tests, max parallel):
├── Task 1: chat-types.ts — add MemoryCitation + SSEEvent.memory_citation field (types only)
├── Task 2: en.json — add chat.citation.* keys + i18n parity test
├── Task 3: MemoryCitationChip component scaffold + RED test
└── Task 4: useStreaming — add addMemoryCitation param + RED test for memory_citation branch

Wave 2 (After Wave 1 — integration + GREEN):
├── Task 5: MemoryCitationChip implementation (turn RED → GREEN)
├── Task 6: useStreaming implementation (turn RED → GREEN)
├── Task 7: MessageList — render chips + comparator fix + GREEN test
└── Task 8: SSEChat — wire addMemoryCitation into per-message state

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan Compliance Audit
├── Task F2: Code Quality Review
├── Task F3: Real Manual QA (Playwright live SSE check)
└── Task F4: Scope Fidelity Check
→ Present results → Get explicit user okay

Critical Path: Task 1 → Task 4 → Task 6 → Task 7 → Task 8 → deploy → F1-F4 → user okay
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix (abbreviated — see full list below)

- **1**: - → 4, 5, 6, 7
- **2**: - → 5
- **3**: - → 5
- **4**: 1 → 6
- **5**: 2, 3 → 7
- **6**: 1, 4 → 7
- **7**: 1, 5, 6 → 8
- **8**: 7 → deploy

### Agent Dispatch Summary

- **Wave 1**: `quick` (4 tasks — small file edits + RED tests)
- **Wave 2**: `quick` × 3 (turn tests green), `unspecified-high` × 1 (SSEChat wiring)
- **Wave FINAL**: `oracle` × 1, `unspecified-high` × 3

---

## TODOs

- [ ] 1. Extend `chat-types.ts` with `MemoryCitation` + SSE variant (RED test)

  **What to do**:
  - In `src/lib/chat-types.ts`:
    - Add `export interface MemoryCitation { citation_id: string; claim_id: string; short_id: string; label: string; subject: string; predicate: string; object: string; scope: string; confidence: number; mission_id?: string; mission_number?: number; expires_at?: string; }` near the other Phase 3 types (after `ToolEvent`, ~line 156).
    - Add `citations?: MemoryCitation[]` to `ChatMessage` (line 52-66).
    - Add to `SSEEvent` (line 76-100) the fields needed for `memory_citation`: `type?: string` (already present), and the typed payload via a discriminated union OR by adding optional fields `message_id?: string; citation_id?: string; claim_id?: string; short_id?: string; label?: string; subject?: string; predicate?: string; object?: string; confidence?: number; mission_id?: string; mission_number?: number`. Pre-stage `memory_recall_used` shares `message_id`, `claim_id`, `label` (as short_id), `subject`, `predicate`, `scope`, `confidence`.
  - Create `src/lib/__tests__/chat-types.memory-citation.test.ts` (or extend an existing type test) that:
    1. Imports the new types.
    2. Builds a sample `MemoryCitation` and asserts it round-trips through `SSEEvent` shape.
    3. Asserts `ChatMessage` accepts `citations` field.
    - Run `npx vitest run` → confirm RED (compile error or assertion failure).

  **Must NOT do**:
  - Do not change existing `SSEEvent` fields' types.
  - Do not add runtime code (this task is types only).

  **Recommended Agent Profile**:
  > Category: `quick` (single type file + tiny test). Skills: `[]`.
  - Reason: minimal edit, deterministic.

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1 (with Tasks 2, 3, 4)
  - Blocks: 4, 5, 6, 7
  - Blocked By: None

  **References**:
  - `src/lib/chat-types.ts:52-100` — existing `ChatMessage` and `SSEEvent` definitions to extend.
  - `backend/app/services/memory_citation_service.py:219-266` — `build_citation_event` payload, the source of truth for the type shape.
  - `src/hooks/__tests__/useStreaming.tool-calls.test.ts:1-44` — pattern for vitest unit test (mock fetch, build SSE stream, assert state).

  **Acceptance Criteria**:
  - [ ] `npx vitest run src/lib/__tests__/chat-types.memory-citation.test.ts` → PASS
  - [ ] `npx tsc --noEmit` → 0 errors

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: New types compile and round-trip a memory_citation payload
    Tool: Bash (npx vitest run)
    Preconditions: Task 1 files written.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run src/lib/__tests__/chat-types.memory-citation.test.ts
    Expected Result: exit 0, "1 passed" (or similar)
    Failure Indicators: compile error, "is not assignable", missing field
    Evidence: .sisyphus/evidence/stage-3/task-1-types-test.txt
  ```

  **Commit**: YES
  - Message: `test(chat-types): RED add MemoryCitation + SSE memory_citation field`
  - Files: `src/lib/chat-types.ts`, `src/lib/__tests__/chat-types.memory-citation.test.ts`
  - Pre-commit: `npx vitest run src/lib/__tests__/chat-types.memory-citation.test.ts` (must show RED before commit; CI/agent re-runs after)

- [ ] 2. Add i18n keys for citation chip in `en.json` (RED test)

  **What to do**:
  - In `src/i18n/locales/en.json`, add a new top-level `citation` namespace (next to `chat`, `memory`, `memoryInspector`). Suggested keys:
    - `citation.shortTitle`: `"Memory"` (used as the chip's accessible short label; matches the existing `memory` key at line 44 but keep the namespace local to chat for clarity).
    - `citation.whyLabel`: `"Why this memory?"`
    - `citation.tooltipSubject`: `"Subject: {subject}"` (use ICU placeholder, same pattern as `accessibility.currentLanguage` at line 23).
    - `citation.tooltipPredicate`: `"Predicate: {predicate}"`
    - `citation.tooltipConfidence`: `"Confidence: {confidence, number, percent}"` (use ICU number formatting).
    - `citation.missionRef`: `"Mission #{number}"` (placeholder `{number}`).
  - Add `src/i18n/locales/__tests__/en-citation-keys.test.ts` (Vitest, no React) that:
    1. Reads `en.json` via `import en from "../en.json"`.
    2. Asserts every key above exists (use bracket-notation traversal).
    3. Asserts ICU placeholders resolve to a string (no nested objects).
    - Run `npx vitest run` → confirm RED (keys missing → assertion failure).

  **Must NOT do**:
  - Do not change the existing `memory` or `chat` namespaces.
  - Do not add a new locale file; English is the only required translation for Stage 3.

  **Recommended Agent Profile**:
  > Category: `quick`. Skills: `[]`.

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1 (with Tasks 1, 3, 4)
  - Blocks: 5
  - Blocked By: None

  **References**:
  - `src/i18n/locales/en.json:1-50` — top-level namespace pattern (`about`, `accessibility`, `admin`).
  - `src/i18n/locales/en.json:44` — existing `"memory": "Memory"` key (do not reuse; add new `citation` namespace).
  - `src/i18n/locales/en.json:23` — `{language}` placeholder example.
  - `src/components/memory-inspector/__tests__/MemoryInspector.test.tsx:22-25` — `next-intl` mock pattern (not needed for this test, which is locale-only).

  **Acceptance Criteria**:
  - [ ] `npx vitest run src/i18n/locales/__tests__/en-citation-keys.test.ts` → PASS
  - [ ] `npx tsc --noEmit` → 0 errors
  - [ ] `node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en.json'))"` → exit 0 (valid JSON)

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: All required citation i18n keys exist and are strings
    Tool: Bash (npx vitest run)
    Preconditions: en.json updated, test file written.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run src/i18n/locales/__tests__/en-citation-keys.test.ts
    Expected Result: exit 0, "1 passed"
    Failure Indicators: "expected key 'citation.shortTitle' to exist" or similar
    Evidence: .sisyphus/evidence/stage-3/task-2-i18n-test.txt

  Scenario: en.json is valid JSON
    Tool: Bash
    Preconditions: en.json updated.
    Steps:
      1. node -e "JSON.parse(require('fs').readFileSync('/home/glenn/FlowmannerV2-frontend/src/i18n/locales/en.json'))"
    Expected Result: exit 0, no output
    Failure Indicators: "SyntaxError" in JSON
    Evidence: .sisyphus/evidence/stage-3/task-2-en-json-valid.txt
  ```

  **Commit**: YES
  - Message: `feat(i18n): RED add citation chip copy + en.json parity test`
  - Files: `src/i18n/locales/en.json`, `src/i18n/locales/__tests__/en-citation-keys.test.ts`
  - Pre-commit: vitest run + node -e JSON.parse

- [ ] 3. Scaffold `MemoryCitationChip` component + RED test

  **What to do**:
  - Create `src/components/chat/MemoryCitationChip.tsx` exporting a `React.memo` component:
    - Props: `{ citation: MemoryCitation; t: (key: string, values?: Record<string, unknown>) => string }` (t is the `useTranslations("citation")` result, passed in so tests can drive it).
    - Initial scaffold renders `<div data-testid="memory-citation-chip" aria-label={t("citation.whyLabel")}>{citation.label}</div>` only (no tooltip, no styling) — enough to satisfy the test but not yet polished.
  - Create `src/components/chat/__tests__/MemoryCitationChip.test.tsx` (Vitest + `@testing-library/react`) that:
    1. Renders with a fake `t` that returns the key and a sample `MemoryCitation` (label `[memory: c-14, conf 0.85]`, subject `Flowmanner uses`, predicate `framework`, confidence `0.85`).
    2. Asserts `getByTestId("memory-citation-chip")` is in the document.
    3. Asserts the chip's textContent includes the label.
    4. Asserts the chip has `aria-label` set to the translated `citation.whyLabel` string.
    5. Asserts a `role="status"` (or similar) attribute is present (this is the design intent — fail RED if you haven't decided yet, then the test sets the contract for GREEN).
    - Run `npx vitest run` → confirm RED (test fails because the scaffolded component does not yet set `role="status"` or the test expects a tooltip stub that doesn't exist).

  **Must NOT do**:
  - Do not import any backend or chat-store here — chip is a pure component.
  - Do not add a CSS file; use Tailwind classes only.

  **Recommended Agent Profile**:
  > Category: `quick`. Skills: `[]`.

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1 (with Tasks 1, 2, 4)
  - Blocks: 5
  - Blocked By: None

  **References**:
  - `src/components/chat/MilestoneBadge.tsx:1-60` — sibling component pattern (props, `cn`, variant classes, `React.memo`).
  - `src/lib/utils.ts:5` — `cn()` helper from `tailwind-merge`/`clsx`.
  - `src/components/memory-inspector/__tests__/MemoryInspector.test.tsx:48-90` — `@testing-library/react` `render` + `getByTestId` pattern.
  - `src/i18n/locales/__tests__/en-citation-keys.test.ts` (added in Task 2) — keys the component will use.

  **Acceptance Criteria**:
  - [ ] `npx vitest run src/components/chat/__tests__/MemoryCitationChip.test.tsx` → PASS
  - [ ] `npx tsc --noEmit` → 0 errors

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Chip renders label, accessible name, and role
    Tool: Bash (npx vitest run)
    Preconditions: Component scaffold + test written.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run src/components/chat/__tests__/MemoryCitationChip.test.tsx
    Expected Result: exit 0, "1 passed"
    Failure Indicators: "Unable to find element with testid", role mismatch
    Evidence: .sisyphus/evidence/stage-3/task-3-chip-test.txt
  ```

  **Commit**: YES
  - Message: `test(chat): RED scaffold MemoryCitationChip + test`
  - Files: `src/components/chat/MemoryCitationChip.tsx`, `src/components/chat/__tests__/MemoryCitationChip.test.tsx`
  - Pre-commit: vitest run

- [ ] 4. Add `memory_citation` SSE branch in `useStreaming` + RED test

  **What to do**:
  - In `src/hooks/useStreaming.ts`:
    - Extend `UseStreamingParams` (line 9-23) with `addMemoryCitation: (messageId: string, citation: MemoryCitation) => void;`.
    - Add the new field to the destructure list (line 33-41) and to the `useCallback` dependency array (line 333).
    - In the SSE parsing loop (line 155-177), BEFORE the `parsed.type === "complete"` short-circuit, add a branch:
      - If `parsed.type === "memory_citation"` and the parsed event has the required fields (`citation_id`, `claim_id`, `label`, `short_id`, `subject`, `predicate`, `object`, `scope`, `confidence`), call `addMemoryCitation(parsed.message_id, { ... })`. If a field is missing, log a warning via `console.warn` (not `toast`) and skip.
    - Do not add the `memory_recall_used` handler in this task — T33.1 will add it. Only `memory_citation`.
  - Create `src/hooks/__tests__/useStreaming.memory-citations.test.ts` mirroring the `tool-calls.test.ts` pattern:
    1. Mock `@/lib/get-auth-token`, `sonner`, `@/lib/tool-event-parser` (same as existing test).
    2. Build an SSE stream with: one `token` event, one `memory_citation` event (`message_id: "42"`, `citation_id: "c-1"`, `label: "[memory: c-1, conf 0.85]"`, full payload), then `[DONE]`.
    3. Render the hook with `addMemoryCitation: vi.fn()`.
    4. Assert `addMemoryCitation` was called exactly once with `("42", expect.objectContaining({ citation_id: "c-1", label: "[memory: c-1, conf 0.85]" }))`.
    5. Second test: malformed event (missing `citation_id`) → `addMemoryCitation` NOT called, no unhandled rejection.
    6. Third test: `memory_citation` after `complete` is still processed (don't regress ordering).
    - Run `npx vitest run` → confirm RED.

  **Must NOT do**:
  - Do not touch the existing `tool_call_start` / `tool_call_result` branches.
  - Do not introduce a new state shape in `useStreaming` — citation storage lives in the consumer (SSEChat) via the `addMemoryCitation` callback.

  **Recommended Agent Profile**:
  > Category: `quick`. Skills: `[]`.

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1 (with Tasks 1, 2, 3)
  - Blocks: 6
  - Blocked By: 1 (needs the `MemoryCitation` type)

  **References**:
  - `src/hooks/useStreaming.ts:155-222` — exact insertion point for the new branch.
  - `src/hooks/__tests__/useStreaming.tool-calls.test.ts:1-44` — vitest mock + SSE stream pattern (copy and adapt).
  - `backend/app/services/memory_citation_service.py:219-266` — `build_citation_event` payload, field-by-field contract.
  - `src/lib/chat-types.ts:52-66` — `ChatMessage.citations` field added in Task 1.

  **Acceptance Criteria**:
  - [ ] `npx vitest run src/hooks/__tests__/useStreaming.memory-citations.test.ts` → PASS
  - [ ] `npx vitest run` (full suite) → all existing tool-call tests still pass
  - [ ] `npx tsc --noEmit` → 0 errors

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: memory_citation event is forwarded to addMemoryCitation
    Tool: Bash (npx vitest run)
    Preconditions: useStreaming updated, test written.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run src/hooks/__tests__/useStreaming.memory-citations.test.ts
    Expected Result: exit 0, "3 passed" (or per-test count)
    Failure Indicators: "expected addMemoryCitation to have been called with..."
    Evidence: .sisyphus/evidence/stage-3/task-4-usestreaming-test.txt
  ```

  **Commit**: YES
  - Message: `feat(chat): RED useStreaming handles memory_citation SSE events`
  - Files: `src/hooks/useStreaming.ts`, `src/hooks/__tests__/useStreaming.memory-citations.test.ts`
  - Pre-commit: vitest run (full)

- [ ] 5. Implement `MemoryCitationChip` (turn RED → GREEN)

  **What to do**:
  - Replace the scaffold in `src/components/chat/MemoryCitationChip.tsx` with the full implementation:
    - Wrap chip body in a `button` (or `<span role="status">` if non-interactive — pick `role="status"` + `tabIndex={0}` + keyboard handlers so it can be focused but isn't a button trap).
    - Visual: small pill (`inline-flex items-center gap-1 rounded-full bg-clay/10 px-2 py-0.5 text-[11px] text-charcoal/80` — match the chip aesthetic from `MessageList.tsx` action bar).
    - Show an icon (use `BookOpen` from `lucide-react`, size `h-3 w-3`).
    - Visible text: `citation.label` (e.g. `[memory: c-14, conf 0.85]`).
    - On hover/focus, show a tooltip with subject/predicate/confidence using the `title` attribute as a quick win, OR a `react-markdown`-free popover. Keep it simple: use `title` (native HTML tooltip) plus `aria-describedby` for screen readers.
    - Use `cn()` from `@/lib/utils` for class composition.
  - Update the test from Task 3 to assert:
    1. `title` attribute includes the subject/predicate text.
    2. `aria-describedby` is present (or, if you choose not to use `aria-describedby`, drop that assertion — the test is allowed to evolve with the impl).
  - Run `npx vitest run src/components/chat/__tests__/MemoryCitationChip.test.tsx` → confirm GREEN.

  **Must NOT do**:
  - Do not add a popover library.
  - Do not change the chip's external props (still `{ citation, t }`).

  **Recommended Agent Profile**:
  > Category: `quick`. Skills: `[]`.

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 2 (with Task 6)
  - Blocks: 7
  - Blocked By: 1, 2, 3 (types, i18n keys, scaffold)

  **References**:
  - `src/components/chat/MilestoneBadge.tsx:1-60` — styling reference.
  - `src/components/chat/MessageList.tsx:208-272` — action-bar `text-[11px]` size + `hover:text-charcoal/60 hover:bg-white/[0.04]` chip aesthetic.
  - `src/lib/utils.ts:5` — `cn()` helper.
  - `src/i18n/locales/en.json` (after Task 2) — the `citation.*` keys.

  **Acceptance Criteria**:
  - [ ] `npx vitest run src/components/chat/__tests__/MemoryCitationChip.test.tsx` → PASS
  - [ ] `npx tsc --noEmit` → 0 errors
  - [ ] `npm run lint` → 0 errors (chip file must pass eslint)

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Chip renders label, tooltip, accessible name, and role
    Tool: Bash (npx vitest run)
    Preconditions: Component fully implemented.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run src/components/chat/__tests__/MemoryCitationChip.test.tsx
    Expected Result: exit 0, all assertions pass
    Failure Indicators: missing aria-label, missing title, role mismatch
    Evidence: .sisyphus/evidence/stage-3/task-5-chip-green.txt
  ```

  **Commit**: YES
  - Message: `feat(chat): render MemoryCitationChip with tooltip + a11y`
  - Files: `src/components/chat/MemoryCitationChip.tsx`, `src/components/chat/__tests__/MemoryCitationChip.test.tsx`
  - Pre-commit: vitest + tsc + lint

- [ ] 6. Implement `useStreaming` `memory_citation` branch (turn RED → GREEN)

  **What to do**:
  - In `src/hooks/useStreaming.ts`, finalize the `memory_citation` branch added in Task 4:
    - Field-by-field copy from `parsed` into the `MemoryCitation` object: `citation_id`, `claim_id`, `label`, `short_id`, `subject`, `predicate`, `object`, `scope`, `confidence`; conditionally include `mission_id`, `mission_number`, `expires_at` only if present.
    - Call `addMemoryCitation(String(parsed.message_id), citation)`.
    - If the message_id refers to an assistant message that is still streaming (which it will be — `memory_citation` is emitted after persistence in the backend, but the frontend's `assistantId` may be different), fall back to attaching to the last assistant message by leaving it to the consumer (SSEChat) to resolve the id mismatch. Frontend convention: `addMemoryCitation` receives the raw `message_id` from the SSE; the consumer stores a map from `message_id` → local message id.
  - Ensure the branch runs BEFORE the `parsed.type === "complete"` early-`continue` (line 178), because citations are emitted between token events and the `complete` event in the backend stream.
  - Run `npx vitest run` (full) → all tool-call + memory-citation tests pass.

  **Must NOT do**:
  - Do not regress the existing `tool_call_*` tests.
  - Do not add a new top-level state to `useStreaming` (citations are passed up via the callback).

  **Recommended Agent Profile**:
  > Category: `quick`. Skills: `[]`.

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 2 (with Task 5)
  - Blocks: 7
  - Blocked By: 1, 4

  **References**:
  - `src/hooks/useStreaming.ts:178-220` — insertion point + dependency array.
  - `src/hooks/__tests__/useStreaming.tool-calls.test.ts:1-44` — pattern for new test cases.
  - `backend/app/services/chat_service.py:1464-1470` — backend emission site confirms `message_id` is the persisted assistant message id (which equals the frontend's `assistantId`).

  **Acceptance Criteria**:
  - [ ] `npx vitest run` → all tests pass (tool-call + memory-citation)
  - [ ] `npx tsc --noEmit` → 0 errors
  - [ ] `npm run lint` → 0 errors

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: useStreaming full suite still green after memory_citation branch
    Tool: Bash (npx vitest run)
    Preconditions: useStreaming finalized.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run
    Expected Result: exit 0, all test files pass (including tool-calls and memory-citations)
    Failure Indicators: any failed test
    Evidence: .sisyphus/evidence/stage-3/task-6-usestreaming-green.txt
  ```

  **Commit**: YES
  - Message: `feat(chat): wire memory_citation events through useStreaming`
  - Files: `src/hooks/useStreaming.ts`
  - Pre-commit: vitest run (full) + tsc + lint

- [ ] 7. Render citations in `MessageList` + comparator fix + RED→GREEN test

  **What to do**:
  - In `src/components/chat/MessageList.tsx`:
    - Import `MemoryCitationChip` and `useTranslations` from `next-intl` (must be added to MessageList's imports).
    - Inside `MessageItem` (line 406-501), after the assistant bubble div (line 477) and BEFORE the `MessageActions` row (line 479-487), render:
      ```tsx
      {msg.citations && msg.citations.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="memory-citation-list">
          {msg.citations.map((c) => (
            <MemoryCitationChip key={c.citation_id} citation={c} t={t} />
          ))}
        </div>
      )}
      ```
    - Update the `React.memo` comparator (line 491-501) to include `prevProps.msg.citations === nextProps.msg.citations` so chips re-render when added.
  - Create `src/components/chat/__tests__/MessageList.memory-citations.test.tsx` (Vitest + RTL):
    1. Mock `next-intl` like the existing tests (`useTranslations: () => (k) => k`).
    2. Render `<MessageList messages={[{ id: 'm1', role: 'assistant', content: 'Hello', timestamp: 1, citations: [{ citation_id: 'c-1', claim_id: 'c-1', short_id: 'c-1', label: '[memory: c-1, conf 0.85]', subject: 's', predicate: 'p', object: '{}', scope: 'personal', confidence: 0.85 }] }]} isStreaming={false} messagesEndRef={{ current: null }} onBranchFromMessage={() => {}} />`.
    3. Assert `getByTestId('memory-citation-list')` exists and contains one `MemoryCitationChip` with the label `[memory: c-1, conf 0.85]`.
    4. Second test: message with no `citations` → `queryByTestId('memory-citation-list')` is `null`.
    5. Third test: message with `citations: []` (empty array) → same as above.
    - Run `npx vitest run` → confirm RED first, then GREEN after impl.

  **Must NOT do**:
  - Do not break the existing message memoization.
  - Do not change `MessageList` props.

  **Recommended Agent Profile**:
  > Category: `quick`. Skills: `[]`.

  **Parallelization**:
  - Can Run In Parallel: NO (depends on Tasks 5 and 6)
  - Parallel Group: Wave 2 (sequential after 5 and 6)
  - Blocks: 8
  - Blocked By: 1, 5, 6

  **References**:
  - `src/components/chat/MessageList.tsx:406-501` — `MessageItem` and memo comparator.
  - `src/components/chat/MessageList.tsx:12-17` — existing imports (add `MemoryCitationChip` and `useTranslations`).
  - `src/components/chat/MessageList.tsx:479-487` — `MessageActions` placement (chips go before this).
  - `src/components/memory-inspector/__tests__/MemoryInspector.test.tsx:48-90` — `next-intl` mock pattern.

  **Acceptance Criteria**:
  - [ ] `npx vitest run src/components/chat/__tests__/MessageList.memory-citations.test.tsx` → PASS
  - [ ] `npx vitest run` (full) → all pass
  - [ ] `npx tsc --noEmit` → 0 errors

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Citations render below assistant bubble; no citations → no list
    Tool: Bash (npx vitest run)
    Preconditions: MessageList updated, test written.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx vitest run src/components/chat/__tests__/MessageList.memory-citations.test.tsx
    Expected Result: exit 0, "3 passed"
    Failure Indicators: "Unable to find element with testid 'memory-citation-list'"
    Evidence: .sisyphus/evidence/stage-3/task-7-messagelist-test.txt
  ```

  **Commit**: YES
  - Message: `feat(chat): render memory citation chips in MessageList`
  - Files: `src/components/chat/MessageList.tsx`, `src/components/chat/__tests__/MessageList.memory-citations.test.tsx`
  - Pre-commit: vitest + tsc + lint

- [ ] 8. Wire `addMemoryCitation` in `SSEChat` and add `package.json` test scripts

  **What to do**:
  - In `src/components/chat/SSEChat.tsx`:
    - Maintain a `Map<string /* backend message_id */, string /* local message_id */>` for the currently-streaming assistant message (use `useRef`). When `streamResponse` is called with a local `assistantId`, also store the mapping `assistantId → assistantId` (frontend uses the same id backend emits; verify by checking `chat_service.py:1470`).
    - Implement `addMemoryCitation` callback (memoized) that:
      1. Calls `setMessages((prev) => prev.map((m) => m.id === localId ? { ...m, citations: dedupeById([...(m.citations ?? []), citation], (c) => c.citation_id) } : m))`.
      2. Dedupe helper: keep first occurrence of each `citation_id`.
    - Pass `addMemoryCitation` into `useStreaming` (line 123-131).
  - In `package.json` `scripts` (line 5-10), add:
    - `"test": "vitest run"`
    - `"test:watch": "vitest"`
    - `"test:e2e": "playwright test"`
  - Create `e2e/memory-citation-chip.spec.ts` (Playwright):
    1. Reuse `AUTH_FILE` and `TEST_EMAIL`/`TEST_PASSWORD` from `e2e/auth-regression.spec.ts:1-30` (extract into a fixture if they exist, otherwise re-define with `process.env.TEST_EMAIL`).
    2. Sign in, navigate to `/en/chat/...` (or a deterministic thread that has a memory recall fixture). Since live chat requires a real LLM, this e2e test mocks the SSE endpoint via `page.route`:
       - Intercept `**/api/chat/threads/*/chat/stream` and respond with a `text/event-stream` containing a `memory_citation` event.
       - Send a message, wait for the chip to appear.
       - Assert `getByTestId('memory-citation-chip')` is visible.
    3. Skip the test gracefully if the env vars are missing (CI-only flag).
  - Run `npx vitest run` + `npm run lint` + `npx tsc --noEmit` → all green.

  **Must NOT do**:
  - Do not mutate `messages` outside the React state setter.
  - Do not add a new dependency.

  **Recommended Agent Profile**:
  > Category: `unspecified-high`. Skills: `[]`.
  - Reason: SSEChat integration touches state plumbing; slightly higher risk than other tasks.

  **Parallelization**:
  - Can Run In Parallel: NO (depends on Task 7)
  - Parallel Group: Wave 2 (last task)
  - Blocks: deploy
  - Blocked By: 7

  **References**:
  - `src/components/chat/SSEChat.tsx:88-131` — `useChatMessages`, `useStreaming` wiring.
  - `src/components/chat/SSEChat.tsx:112` — `useToolEvents` pattern (mirror for memory citations).
  - `src/components/chat/SSEChat.tsx:174-202` — ref + effect patterns.
  - `e2e/auth-regression.spec.ts:14-60` — sign-in fixture + `page.route` pattern.
  - `package.json:5-10` — scripts section to extend.

  **Acceptance Criteria**:
  - [ ] `npx vitest run` → all pass
  - [ ] `npx tsc --noEmit` → 0 errors
  - [ ] `npm run lint` → 0 errors
  - [ ] `npx playwright test e2e/memory-citation-chip.spec.ts` → PASS (with mocked SSE)
  - [ ] `npm test` → runs the full vitest suite (sanity)

  **QA Scenarios (MANDATORY)**:
  ```
  Scenario: Full frontend suite green after SSEChat wiring
    Tool: Bash (npx vitest run + lint)
    Preconditions: SSEChat wired, package.json updated, e2e written.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npm test
      3. npm run lint
    Expected Result: vitest exit 0 (all files pass), eslint exit 0
    Failure Indicators: any failed test, eslint errors
    Evidence: .sisyphus/evidence/stage-3/task-8-ssechat-test.txt

  Scenario: E2E chip-render test passes with mocked SSE
    Tool: Bash (npx playwright test)
    Preconditions: e2e spec written, dev server starts.
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend
      2. npx playwright test e2e/memory-citation-chip.spec.ts --reporter=line
    Expected Result: "1 passed" (or skip if env not set)
    Failure Indicators: "Unable to find element with testid 'memory-citation-chip'"
    Evidence: .sisyphus/evidence/stage-3/task-8-e2e.txt
  ```

  **Commit**: YES
  - Message: `feat(chat): wire addMemoryCitation in SSEChat + e2e + test scripts`
  - Files: `src/components/chat/SSEChat.tsx`, `package.json`, `e2e/memory-citation-chip.spec.ts`
  - Pre-commit: vitest + lint + tsc + playwright

---

## Final Verification Wave (MANDATORY)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback → fix → re-run → present again → wait for okay.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  For each "Must Have" verify implementation exists (read file, run command). For each "Must NOT Have" search codebase for forbidden patterns — reject with file:line if found. Check evidence files in `.sisyphus/evidence/stage-3/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `npx tsc --noEmit` + `npm run lint` + `npx vitest run`. Review changed files for `any` casts, `console.log`, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture screenshots to `.sisyphus/evidence/stage-3/final-qa/`. Test cross-task integration (streaming + chip render together). Test edge cases: no citations, duplicate citation_id, malformed event. Verify live `flowmanner.com` shows chip after deploy.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (`git log -p main..HEAD`). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1 RED**: one commit per task (4 commits), no functional change beyond test scaffold.
- **Wave 2 GREEN**: one commit per task (4 commits), each turns a failing test green.
- **Wave FINAL**: one final commit per review pass, no-op for changes unless issues found.

Format: `type(scope): desc` (e.g., `feat(chat): render memory citation chips`).

Pre-commit gate: `npx vitest run src/<touched-path>__tests__ && npx tsc --noEmit && npm run lint` (run from `/home/glenn/FlowmannerV2-frontend`).

Deploy: `bash /opt/flowmanner/deploy-frontend.sh` (homelab, ~4 min, `timeout=300`).

---

## Success Criteria

### Verification Commands

```bash
cd /home/glenn/FlowmannerV2-frontend

# Type safety
npx tsc --noEmit                                 # Expected: exit 0, "0 errors"

# Unit tests
npx vitest run                                   # Expected: all pass

# Lint
npm run lint                                     # Expected: 0 errors

# E2E (local only)
npx playwright test e2e/memory-citation-chip.spec.ts  # Expected: 0 failures

# Deploy
ssh 172.16.1.1 'bash /opt/flowmanner/deploy-frontend.sh'  # Expected: success, health green
```

### Final Checklist

- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (`vitest`, `tsc`, `lint`, `playwright`)
- [ ] Live `flowmanner.com` chat shows memory citation chip after a reply that triggers recall
- [ ] Evidence files saved to `.sisyphus/evidence/stage-3/`
- [ ] All commits pushed to `origin/main`
- [ ] User gave explicit "okay" after F1-F4 review
