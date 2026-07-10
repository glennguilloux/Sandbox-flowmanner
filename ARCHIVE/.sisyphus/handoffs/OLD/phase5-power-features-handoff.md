# Phase 5 handoff — Power features

**Status:** READY TO RUN, not started in the current frontend tree.
**Phase:** 5 — Power features: motion, command palette, drag-and-drop, Storybook.
**Source plan:** `.sisyphus/plans/q2-q3-agentic-workflow.md:201-237`.
**Research handoff:** `.sisyphus/plans/frontend-awesome-react-research.md:1313-1515`.
**Frontend repo:** `/home/glenn/FlowmannerV2-frontend`
**Backend source:** `/opt/flowmanner/backend`
**VPS rule:** never edit files on the VPS directly. Frontend deploy only via `bash /opt/flowmanner/deploy-frontend.sh` after approval.

## Current baseline

Verified in `/home/glenn/FlowmannerV2-frontend`:

```text
c250181 (HEAD -> master, origin/master, origin/HEAD) feat(frontend): add phase 4 data display charts and tables
```

Current dirty tree is unrelated Phase 2/4 cleanup and evidence files. Do not stage or commit that noise with Phase 5:

```text
 M e2e/.auth/user.json
 M e2e/mission-builder.spec.ts
 M src/components/mission-builder/PropertiesPanel.tsx
 D .sisyphus/evidence/frontend-phase2-slice10/check-i18n.py
?? .sisyphus/evidence/...
?? .sisyphus/plans/
?? plans/memory-citations-t33-handoff.md
```

Current Phase 5 baseline facts:

- `package.json` has no `motion`, `kbar`, `cmdk`, `@dnd-kit/*`, `storybook`, or `@storybook/*` dependencies.
- `src/app/layout.tsx` is a server component root layout.
- `src/app/providers.tsx` is the client provider shell; put global client-only providers there or in a new client provider imported by it.
- `src/app/[locale]/(dashboard)/layout.tsx` currently only wraps dashboard routes in `FlowErrorBoundary`.
- `src/components/chat/CommandPalette.tsx` already has a hand-rolled command palette and slash-command behavior.
- `src/components/chat/ChatInputArea.tsx` also has slash-command filtering/rendering.
- `src/components/layout/floating-nav.tsx` is client-side and already has dropdown polish from Phase 3.
- `src/components/mission-builder/NodePalette.tsx` uses raw HTML5 drag/drop for dragging node types into the canvas.
- `src/components/chat/MessageList.tsx` renders chat messages in a plain `messages.map(...)` list.
- `src/app/[locale]/page-client.tsx` only has a CSS `prefers-reduced-motion` override for the hero; there is no app-wide motion wrapper layer yet.
- No Storybook config or `.stories.tsx` files exist.

## Goal

Make the app feel designed without bloating production routes:

1. Add centralized motion wrappers that respect `prefers-reduced-motion`.
2. Add a global command palette reachable with `Cmd/Ctrl+K` that searches routes and actions and navigates without a hard refresh.
3. Replace raw drag/drop with `@dnd-kit` in mission builder and floating nav, with keyboard support.
4. Add Storybook as a static dev/docs surface for `components/ui/*`.
5. Keep bundle size, Lighthouse, CLS, and INP stable on `/missions/:id`, `/marketplace`, and `/chat`.

## Recommended stack

Use the versions from the Phase 5 research as the starting pins, then verify registry/package compatibility before committing:

- `motion` — React animation primitives, import from `motion/react`.
- `kbar` — command palette/action center.
- `@dnd-kit/core`
- `@dnd-kit/sortable`
- `@dnd-kit/utilities`
- `storybook`
- `@storybook/nextjs`

Install command shape:

```bash
pnpm add motion kbar @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
pnpm add -D storybook @storybook/nextjs
```

If `kbar` conflicts with React 19/Next 16, use `cmdk` for the UI primitive but keep the same action registry/provider shape. Do not hand-roll filtering, virtualization, shortcuts, and keyboard behavior.

## Proposed file structure

```text
frontend/src/
├── components/
│   ├── chat/
│   │   ├── CommandPalette.tsx          # replace or wrap with kbar
│   │   ├── MessageList.tsx             # wrap messages with AnimatePresence
│   │   └── ChatInputArea.tsx           # resolve shortcut conflicts
│   ├── layout/
│   │   └── floating-nav.tsx            # dnd-kit sortable
│   ├── mission-builder/
│   │   └── NodePalette.tsx             # dnd-kit sortable
│   └── ui/
│       └── motion/
│           ├── FadeIn.tsx
│           ├── SlideUp.tsx
│           ├── Stagger.tsx
│           └── ChatMessagePresence.tsx
├── providers/
│   └── command-palette-provider.tsx    # kbar provider + portal
└── lib/
    └── command-palette/
        └── actions.ts                  # registered actions by role/route
frontend/.storybook/
├── main.ts
├── preview.ts
└── manager.ts
frontend/src/components/ui/**/*.stories.tsx
```

## Slice 1 — Dependency and Storybook skeleton

**Do first.** This makes the rest of the phase easier to verify.

- Add dependencies.
- Add scripts to `package.json`:
  - `storybook`: `storybook dev -p 6006`
  - `build-storybook`: `storybook build`
- Create `.storybook/main.ts`, `.storybook/preview.ts`, and `.storybook/manager.ts`.
- Keep Storybook out of the production bundle. It is a dev/docs surface only.
- Add stories for every reusable `components/ui/*.tsx` component.
- If `next build` type-checks Storybook files and fails on Storybook types, isolate story types behind Storybook-only config or move stories under a Storybook-controlled include path. Do not break production build to satisfy Storybook.

**Acceptance checks:**

```bash
pnpm install
pnpm build
pnpm storybook -- --ci
pnpm build-storybook
```

If the Storybook script syntax differs, adjust the script names but keep both dev and build commands.

## Slice 2 — Motion wrapper layer

Create small wrappers under `src/components/ui/motion/`:

- `FadeIn`
- `SlideUp`
- `Stagger`
- `ChatMessagePresence`

Requirements:

- Import from `motion/react`.
- Use `useReducedMotion` or an equivalent reduced-motion check.
- When reduced motion is enabled, render children without animation.
- Keep transitions short and conservative.
- Do not animate every component inline.
- Wrap common motion in one place so bundle impact is controlled.

Candidate surfaces:

- `src/components/chat/MessageList.tsx`
  - Wrap message mount/unmount with `AnimatePresence` and `ChatMessagePresence`.
  - Avoid animating streaming text character-by-character.
- `src/components/marketplace/featured-carousel.tsx`
  - Add subtle slide/fade transitions.
- `src/components/notifications/notification-bell.tsx`
  - Add dropdown/badge transitions.
- `src/components/layout/floating-nav.tsx`
  - Add dropdown/menu open transitions only if they do not hurt INP.

**Acceptance checks:**

- `pnpm test`
- `pnpm build`
- Manual check in browser:
  - OS reduced-motion setting on: no visible motion.
  - OS reduced-motion setting off: short, smooth transitions.
- Lighthouse on `/chat`, `/marketplace`, and `/missions/:id` has no material CLS/INP regression.

## Slice 3 — Command palette

There is already a hand-rolled command palette:

- `src/components/chat/CommandPalette.tsx`
- `src/components/chat/ChatInputArea.tsx`
- `src/lib/slash-commands.ts`

The Phase 5 goal is to centralize global actions, not just chat slash commands.

Recommended shape:

- `src/lib/command-palette/actions.ts`
  - Route actions: missions, marketplace, chat, dashboard, settings, profile, tools, browser, evaluation, etc.
  - App actions: theme toggle if already available, open command palette, help/keyboard shortcuts.
  - Mission actions only when inside a mission context.
  - Chat actions only when a chat thread is active.
- `src/providers/command-palette-provider.tsx`
  - `KBarProvider`
  - `KBarPortal`
  - `KBarPositioner`
  - `KBarAnimator`
  - `KBarSearch`
  - `KBarResults`
- `src/app/providers.tsx`
  - Wrap the existing client providers with the command palette provider.
- `src/app/[locale]/(dashboard)/layout.tsx`
  - Ensure `Cmd/Ctrl+K` opens the global palette on dashboard routes.
- Public marketing pages can also include the provider if desired, but dashboard routes are the minimum.

Important:

- Resolve shortcut conflicts before wiring `Cmd/Ctrl+K`.
- `src/components/chat/SSEChat.tsx` has keyboard behavior for chat; make sure it does not fight the global palette.
- `src/components/chat/ChatInputArea.tsx` uses `/` for slash commands; do not break that path.
- Palette actions should navigate client-side where possible. Avoid hard refreshes.
- Role-aware actions should degrade safely if the user is not authenticated or lacks a context.

**Acceptance checks:**

- Press `Cmd/Ctrl+K` on dashboard routes.
- Search for route names and mission/chat actions.
- Select an action with Enter.
- Confirm client-side navigation and no full page reload.
- Confirm `/` slash-command behavior still works inside chat.
- Confirm keyboard focus returns sensibly after closing the palette.

## Slice 4 — Drag-and-drop with dnd-kit

Replace raw drag/drop where reorderability or sortable behavior matters.

### Mission builder

Current target:

- `src/components/mission-builder/NodePalette.tsx`

Current behavior:

- Uses raw `onDragStart` to drag node types into the canvas.

Phase 5 behavior:

- Use `@dnd-kit/core` and `@dnd-kit/sortable` for sortable surfaces.
- Keep canvas drag/drop behavior correct; do not regress the mission builder.
- If only the palette list needs reordering, scope dnd-kit to the palette.
- If canvas nodes need reordering, coordinate with the existing React Flow node state and export/import logic.

Required:

- `PointerSensor` with an activation distance.
- `KeyboardSensor`.
- Focusable drag handles.
- `aria` labels for drag handles and reordered items.
- Tests or at least Playwright coverage for tab + arrow reordering.

### Floating nav

Current target:

- `src/components/layout/floating-nav.tsx`

Current behavior:

- Client-side dropdown navigation.

Phase 5 behavior:

- Reorder nav items via drag and persist the order.
- Persisting can start as `localStorage` if there is no suitable user-settings endpoint, but prefer a user preference if backend support exists.
- Current auth settings type only has `email_notifications`, `theme`, and `language` in `src/types/auth.ts`. Do not silently overload those fields without backend agreement.

Required:

- `KeyboardSensor`.
- Pointer drag with activation distance.
- Stable item IDs.
- Reset/reorder control.
- Hydration-safe initialization: do not read `localStorage` during server render.
- If persisted in `localStorage`, include a reset-to-default action.

**Acceptance checks:**

- Pointer drag reorders mission-builder palette/nav items.
- Keyboard drag reorders mission-builder palette/nav items.
- Reordered state persists after refresh for the chosen persistence mechanism.
- `pnpm test`
- `pnpm build`
- Playwright geometry check at `1280x800` for `/missions/:id` and dashboard nav.

## Slice 5 — Tests, accessibility, and performance gate

Minimum test additions:

- Vitest or RTL tests for motion wrappers with reduced motion.
- Vitest or RTL tests for command palette action registry.
- Vitest or RTL tests for dnd-kit reorder helpers if extracted.
- Playwright tests for:
  - `Cmd/Ctrl+K` opens the palette.
  - Enter selects an action and navigates client-side.
  - Mission-builder reorder works with keyboard.
  - Floating nav reorder persists or resets.

Accessibility requirements:

- `Cmd/Ctrl+K` has a visible shortcut hint.
- Command palette has focus trap and Escape closes it.
- DnD handles are keyboard accessible.
- Reduced-motion users get no motion.
- No contrast regressions from new overlays.

Performance requirements:

- No production bundle regression on routes that do not use motion/dnd.
- Lazy-load heavy motion use on heavy routes if bundle analysis flags it.
- Storybook remains dev-only.
- Lighthouse on `/chat`, `/marketplace`, and `/missions/:id` does not regress materially.

## Rollout plan

Use small PRs, not one giant Phase 5 PR.

1. PR 1: dependencies + Storybook skeleton + `build-storybook` CI gate.
2. PR 2: motion wrappers + reduced-motion support + chat message animation.
3. PR 3: kbar provider + route/action registry + `Cmd/Ctrl+K`.
4. PR 4: dnd-kit for mission-builder sortable surfaces.
5. PR 5: dnd-kit floating nav reorder + persistence/reset.
6. PR 6: tests, a11y fixes, performance pass.

Do not deploy after every micro-PR unless the user explicitly asks. Batch Phase 5 PRs for one frontend deploy after the whole slice is green, unless a PR fixes a production incident.

## Verification checklist before marking Phase 5 done

Run from `/home/glenn/FlowmannerV2-frontend`:

```bash
git status --short
git fetch origin
git log -1 --oneline --decorate

pnpm install
pnpm test
pnpm build
pnpm lint
pnpm build-storybook
pnpm test:e2e
```

If `pnpm test:e2e` is too broad for the Phase 5 PR, run the targeted Playwright specs for chat, mission builder, and dashboard nav instead, but do not claim full e2e coverage unless the full command passed.

Manual browser checks:

- `/chat`: `Cmd/Ctrl+K`, `/` slash commands, chat message animation, reduced-motion off/on.
- `/missions/:id`: mission-builder drag/drop and keyboard reorder.
- `/marketplace`: carousel/notification animation and no layout shift.
- Dashboard: floating nav drag reorder, persistence/reset, no content overlap.

Lighthouse:

- `/chat`
- `/marketplace`
- `/missions/:id`

Expected result:

- No material CLS/INP/LCP regression.
- No visible motion when reduced motion is enabled.
- No hard reload on command-palette navigation.

## Stop rules

- If `kbar` or Storybook does not work cleanly with Next 16/React 19, pause and choose the documented fallback (`cmdk` or static Storybook isolation). Do not spend days fighting provider incompatibility.
- If dnd-kit keyboard support is incomplete, do not mark Phase 5 done. Keyboard DnD is part of the success criteria.
- If motion increases bundle size materially on routes that should stay lean, gate it behind wrappers/dynamic imports before shipping.
- If floating-nav persistence requires backend schema changes, stop after the frontend-only MVP with reset-to-default and document the backend follow-up.

## Handoff note for the next agent

Phase 5 is a polish phase on top of Phases 1-4. The current tree is a good starting point because Phase 3 already added Radix/shadcn primitives and Phase 4 added data-display components. Do not rewrite those foundations. Add focused wrappers/providers and migrate the specific surfaces named above.
