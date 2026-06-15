# Frontend Awesome-React Adoption — Consolidated Research

**Consolidated:** 2026-06-15
**Source:** Five per-phase RESEARCH.md files created 2026-06-15 by Claude Code
in `.planning/phases/`. Folded into a single research document per
option B in the session plan. The original `.planning/` directory has
been removed; this file is the single source of truth for research.
**Valid until:** 2026-07-15 (each phase carries its own validity)
**Companion plan:** `.sisyphus/plans/frontend-awesome-react-adoption.md`
(strategic 5-phase roadmap, 300 lines)

---

## Table of Contents

- [Phase 1 — Defensive polish (react-error-boundary, react-scan, auto-animate)](#phase-1--defensive-polish--research)
- [Phase 2 — Forms + validation (react-hook-form, zod, @hookform/resolvers)](#phase-2--forms--validation--research)
- [Phase 3 — Component primitives (Radix UI, shadcn/ui)](#phase-3--component-primitives--research)
- [Phase 4 — Data display (TanStack Table, Recharts, date-fns)](#phase-4--data-display--research)
- [Phase 5 — Power features (motion, kbar, @dnd-kit, Storybook)](#phase-5--power-features--research)

Each phase section is self-contained: research summary, standard stack with
version-pinned libraries, architecture patterns, don't-hand-roll table,
common pitfalls, code examples, state-of-the-art notes, open questions,
sources, and metadata.

---

# Phase 1 — Defensive polish — Research

**Researched:** 2026-06-15
**Domain:** React/Next.js defensive polish: error boundaries, render profiling, and list animation
**Confidence:** HIGH

<research_summary>
## Summary

Phase 1 adopts a small, dependency-ordered defensive layer for FlowManner's React/Next.js frontend: `react-error-boundary` for reusable client-side fallback UI, `react-scan` for development-only render profiling, and `@formkit/auto-animate` for low-risk list/card movement polish. The standard approach is not to replace Next.js route-level error handling, but to layer reusable boundaries around meaningful client component islands while preserving Sentry visibility.

The strongest implementation recommendation is to keep `app/error.tsx` and `app/global-error.tsx` as Next.js route/root error handlers, add a reusable `FlowErrorBoundary` wrapper around selected interactive regions, gate `react-scan` strictly behind `NODE_ENV !== "production"`, and apply `useAutoAnimate` only to parent list containers with stable keys. This phase should not change user-visible behavior except animation polish and improved fallback UX.

**Primary recommendation:** Use `react-error-boundary@6.1.2`, `react-scan@0.5.7`, and `@formkit/auto-animate@0.9.0` as dev/polish primitives; do not hand-roll boundary classes, render profilers, or list animation state machines.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `react-error-boundary` | `6.1.2` | Reusable client-side Error Boundary wrapper | Avoids hand-written class components; supports `FallbackComponent`, `onError`, `onReset`, and `resetKeys`. |
| `react-scan` | `0.5.7` | Development render profiling overlay | Current React profiling tool recommended for spotting unnecessary renders in React apps. |
| `@formkit/auto-animate` | `0.9.0` | Zero-config list/card add/remove/move animation | Handles immediate-child animation and respects `prefers-reduced-motion`. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@sentry/nextjs` | `10.53.1` | Error reporting | Capture boundary errors before rendering fallback. |
| `next` | `16.2.6` | App Router framework | Keep existing route-level `error.tsx`/`global-error.tsx` behavior. |
| `react` / `react-dom` | `19.2.4` | UI runtime | Existing FlowManner stack. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `react-error-boundary` | Custom class boundary | Custom works but duplicates a maintained pattern and risks missing reset/owner-stack ergonomics. |
| `react-scan` | React DevTools Profiler | DevTools is built-in but less drop-in for local overlay/quick render audits. |
| `@formkit/auto-animate` | Framer Motion / CSS transitions | More setup; overkill for simple list add/remove/move polish. |

**Installation:**

```bash
pnpm add react-error-boundary@6.1.2 @formkit/auto-animate@0.9.0
pnpm add -D react-scan@0.5.7
```

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Layered Error Handling

**What:** Combine Next.js route-level handlers with a reusable `FlowErrorBoundary` for client islands.
**When to use:** All client-interactive regions that can throw during render or effect setup.
**Example:**

```tsx
// app/error.tsx — keep, Next.js root error UI
"use client";
export default function RootError({ error, reset }: { error: Error; reset: () => void }) {
  return <ErrorScreen onRetry={reset} />;
}

// components/ui/flow-error-boundary.tsx — new
"use client";
import { ErrorBoundary } from "react-error-boundary";
import * as Sentry from "@sentry/nextjs";

function FlowFallback({ reset }: { reset: () => void }) {
  return <ErrorScreen onRetry={reset} />;
}

export function FlowErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary
      FallbackComponent={FlowFallback}
      onError={(error) => Sentry.captureException(error)}
      onReset={() => window.location.reload()}
    >
      {children}
    </ErrorBoundary>
  );
}
```

### Pattern 2: Dev-Only Profiling

**What:** Initialize `react-scan` only in development.
**When to use:** Every dev session.
**Example:**

```tsx
// providers/query-provider.tsx or a new dev-only client component
"use client";
import { scan } from "react-scan";

if (process.env.NODE_ENV !== "production") {
  scan({ enabled: true });
}
```

### Pattern 3: Auto-Animate Lists

**What:** Apply `useAutoAnimate` to a single list parent with stable child keys.
**When to use:** Featured carousel, notification bell, program run history.
**Example:**

```tsx
"use client";
import { useAutoAnimate } from "@formkit/auto-animate/react";

export function NotificationList({ items }: { items: Notification[] }) {
  const [parent] = useAutoAnimate();
  return (
    <ul ref={parent}>
      {items.map((n) => (
        <li key={n.id}>{n.body}</li>
      ))}
    </ul>
  );
}
```

### Anti-Patterns to Avoid
- **Do not replace `app/error.tsx` and `app/global-error.tsx`.** They are required by Next.js App Router.
- **Do not enable `react-scan` in production.** It is dev-only.
- **Do not animate every list.** Reserve auto-animate for high-visibility transitions.
- **Do not call `Sentry.captureException` after the fallback renders.** Capture first, render second.

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Class-based error boundary | Custom class component | `react-error-boundary` | Resets, owner stack, fallback composition, server/client compatibility. |
| Render profiler overlay | Custom hooks with Profiler | `react-scan` | Drop-in overlay, dev-only, identifies unnecessary renders quickly. |
| List add/remove/move animation | CSS keyframes + `useState` | `@formkit/auto-animate` | One hook call, respects `prefers-reduced-motion`, handles FLIP automatically. |
| Error reporting inside boundary | `try/catch` around children | Boundary's `onError` | Catches render and effect errors that try/catch misses. |

**Key insight:** Error boundaries, render profilers, and FLIP animations all have hidden edge cases. Reach for the maintained library unless the gap is real.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Production Bundle Bloat
**What goes wrong:** `react-scan` ships in production and slows the app.
**Why it happens:** No `NODE_ENV` guard.
**How to avoid:** Initialize inside a `useEffect` or guard with `process.env.NODE_ENV !== "production"`.
**Warning signs:** Bundle analyzer shows `react-scan` in `/_next/static`.

### Pitfall 2: Unstable Keys Break Animation
**What goes wrong:** Auto-animate cancels mid-transition.
**Why it happens:** Index-based or non-stable keys.
**How to avoid:** Use stable IDs from data.
**Warning signs:** Items appear to flash during re-render.

### Pitfall 3: Boundary Swallows Sentry
**What goes wrong:** Errors are caught but never reported.
**Why it happens:** `onError` callback not wired.
**How to avoid:** Always pass `onError={(err) => Sentry.captureException(err)}`.
**Warning signs:** Sentry dashboard shows zero boundary errors despite UI fallbacks.

</common_pitfalls>

<code_examples>
## Code Examples

### Error Boundary Provider

```tsx
"use client";

import { ErrorBoundary, type ErrorBoundaryProps } from "react-error-boundary";
import * as Sentry from "@sentry/nextjs";
import { ErrorScreen } from "@/components/ui/error-screen";

export function FlowErrorBoundary({ children }: { children: React.ReactNode }) {
  const handleError: ErrorBoundaryProps["onError"] = (error) => {
    Sentry.captureException(error);
  };
  return (
    <ErrorBoundary FallbackComponent={ErrorScreen} onError={handleError}>
      {children}
    </ErrorBoundary>
  );
}
```

### Dev-Only Scan Init

```tsx
// components/dev/InitReactScan.tsx
"use client";
import { useEffect } from "react";
import { scan } from "react-scan";

export function InitReactScan() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      scan({ enabled: true });
    }
  }, []);
  return null;
}
```

</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom class error boundary | `react-error-boundary` | Longstanding standard | Reset keys, owner stack, fallback composition. |
| React DevTools Profiler only | `react-scan` overlay | 2024+ | Faster in-dev render audit. |
| CSS keyframe lists | `@formkit/auto-animate` | Longstanding standard | Zero-config FLIP, reduced-motion aware. |

**New tools/patterns to consider:**
- Owner-stack trace under `react-error-boundary@6.x`.
- `react-scan` configuration via `scan({ enabled, log: false })`.

**Deprecated/outdated:**
- Class-based error boundaries written by hand.
- CSS-only list animation for non-trivial transitions.

</sota_updates>

<open_questions>
## Open Questions

1. **Should `react-scan` show up in storybook dev too?**
   - What we know: Phase 5 introduces Storybook as a dev surface.
   - What's unclear: Whether profiling is useful in isolated component work.
   - Recommendation: Enable by default; turn off per story if noise is high.

2. **Where do we put the Sentry capture call?**
   - What we know: Boundary's `onError` is the natural hook.
   - What's unclear: Whether to also capture effect errors via a wrapper hook.
   - Recommendation: Start with boundary `onError`; revisit after Phase 5.

</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- React error boundaries docs — https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary
- `react-error-boundary` docs — https://github.com/bvaughn/react-error-boundary
- `react-scan` README — https://github.com/aidenybai/react-scan
- `@formkit/auto-animate` docs — https://auto-animate.formkit.com/
- Next.js error handling — https://nextjs.org/docs/app/building-your-application/routing/error-handling

### Secondary (MEDIUM confidence)
- Sentry React error boundary guidance — https://docs.sentry.io/platforms/javascript/guides/react/features/error-boundary/
- React 19 changes for boundaries — https://react.dev/blog/2024/12/05/react-19

### Tertiary (LOW confidence - needs validation)
- None.

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: react-error-boundary, react-scan, @formkit/auto-animate
- Ecosystem: @sentry/nextjs, Next.js App Router error handling
- Patterns: Layered error handling, dev-only profiling, auto-animate lists
- Pitfalls: Production bundle, unstable keys, Sentry capture gap

**Confidence breakdown:**
- Standard stack: HIGH — official docs and project package.json checked.
- Architecture: HIGH — aligns with React/Next.js conventions.
- Pitfalls: HIGH — documented library behavior.
- Code examples: HIGH — official patterns.

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
</metadata>

---

# Phase 2 — Forms + validation — Research

**Researched:** 2026-06-15
**Domain:** React form state and schema validation with React Hook Form, Zod, and `@hookform/resolvers`
**Confidence:** HIGH

<research_summary>
## Summary

Phase 2 introduces the standard FlowManner form stack: `react-hook-form`, `zod`, and `@hookform/resolvers`. The recommended pattern is to put schema definitions in `src/lib/schemas/*.ts`, bridge them into React Hook Form through `zodResolver`, and keep async persistence in TanStack Query mutations. This separates validation, server state, and component concerns while reducing the current scattered `useState`-based form state.

The implementation should migrate high-traffic forms incrementally, starting with auth, 2FA/billing, memory inspector, marketplace review, RAG search/upload, and evaluation dashboard. For controlled third-party components such as `react-dropzone`, use `Controller` or a tested wrapper helper.

**Primary recommendation:** Create `src/lib/schemas/*` and `src/lib/forms/use-zod-form.ts`; migrate forms one at a time with `useZodForm({ schema })`, `mode: "onBlur"`, `reValidateMode: "onChange"`, and TanStack Query mutations for submission.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `react-hook-form` | `7.79.0` | Form state, registration, validation, submission | Standard uncontrolled React form API with low re-render overhead. |
| `zod` | `4.4.3` | TypeScript-first schema validation | Provides parse, inference, and reusable schemas for frontend/backend contract tests. |
| `@hookform/resolvers` | `5.4.0` | Resolver bridge between RHF and schema libraries | Officially recommended way to use Zod with React Hook Form. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `react-dropzone` | `15.0.0` | File upload interactions | Existing dependency; wrap with RHF `Controller` for file fields. |
| `@tanstack/react-query` | `5.100.11+` | Async mutation and server-state cache | Keep submission/loading/error state in mutations. |
| `next-intl` | `4.12.0` | Locale-aware UI | Use locale from current context for error copy/date display where needed. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| React Hook Form + Zod | Formik + Yup/Zod | Formik is mature but more boilerplate and less aligned with current React patterns. |
| Zod | Yup / Valibot | Zod is already implied by FastAPI/Pydantic contract parity and TypeScript inference. |
| Manual `useState` validation | Custom validation map | High maintenance; duplicates resolver behavior and error accessibility patterns. |

**Installation:**

```bash
pnpm add react-hook-form@7.79.0 zod@4.4.3 @hookform/resolvers@5.4.0
```

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure

```text
frontend/src/
├── lib/
│   ├── schemas/
│   │   ├── auth.ts
│   │   ├── settings.ts
│   │   ├── marketplace.ts
│   │   ├── memory.ts
│   │   ├── rag.ts
│   │   └── mission-builder.ts
│   └── forms/
│       ├── use-zod-form.ts
│       └── use-dropzone-field.ts
└── components/
    ├── auth/
    │   └── signin-password-input.tsx
    ├── settings/
    │   └── two-factor-modal.tsx
    └── ...
```

### Pattern 1: Centralized Zod Schemas

**What:** Define each form's schema once in `lib/schemas/*` and re-use for `useZodForm` and any backend contract tests.
**When to use:** All forms that produce structured payloads.
**Example:**

```ts
// lib/schemas/auth.ts
import { z } from "zod";

export const signInSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});
export type SignInInput = z.infer<typeof signInSchema>;
```

### Pattern 2: `useZodForm` Wrapper

**What:** A thin wrapper around `useForm({ resolver: zodResolver(schema) })` that sets standard mode/reset options.
**When to use:** Every form that uses a Zod schema.
**Example:**

```ts
// lib/forms/use-zod-form.ts
import { useForm, type UseFormProps } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

export function useZodForm<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  options?: Omit<UseFormProps<z.infer<TSchema>>, "resolver">,
) {
  return useForm<z.infer<TSchema>>({
    resolver: zodResolver(schema),
    mode: "onBlur",
    reValidateMode: "onChange",
    ...options,
  });
}
```

### Pattern 3: `react-dropzone` via RHF `Controller`

**What:** Wrap `useDropzone` in a `Controller` so the file list lives inside RHF state.
**When to use:** RAG document upload and any file field in a larger form.
**Example:**

```tsx
<Controller
  control={control}
  name="files"
  render={({ field }) => (
    <Dropzone
      onDrop={(accepted) => field.onChange(accepted)}
    >
      {({ getRootProps, getInputProps }) => (
        <div {...getRootProps()}>
          <input {...getInputProps()} />
          <p>Drop files here</p>
        </div>
      )}
    </Dropzone>
  )}
/>
```

### Anti-Patterns to Avoid
- **Do not scatter `z.object` definitions in components.** Centralize in `lib/schemas/`.
- **Do not bypass `useZodForm`** for one-off forms — keep the contract consistent.
- **Do not call mutations directly inside `onSubmit`** without using a `useMutation` hook. Keep submission error/loading state in the mutation.
- **Do not use Yup or Valibot in parallel** with Zod; pick one schema lib for the project.

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Form state with `useState` | Per-field `useState` | React Hook Form | Uncontrolled refs, fewer re-renders, schema-bound validation. |
| Field validation | Per-field `if (!value) ...` checks | Zod schema + `zodResolver` | Single source for client validation, contract tests, and TS inference. |
| Error accessibility | Manual `aria-invalid` strings | RHF's `formState.errors` + `aria-invalid` binding | Standard, screen-reader-correct error semantics. |
| Submit handling | `useEffect` for success state | TanStack Query `useMutation` | Loading/error/success state, retries, and cache invalidation. |
| Dropzone wiring | Manual `useState<File[]>` | RHF `Controller` + `useDropzone` | Stable field value and reset semantics. |

**Key insight:** Forms have many small edge cases (reset, dirty tracking, async validation, field arrays). Using the standard stack keeps these in one maintained place.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Schema vs API Drift
**What goes wrong:** Zod schema and FastAPI Pydantic schema diverge.
**Why it happens:** No contract test, or backend changes ship first.
**How to avoid:** Add a Vitest contract test that imports both schemas and asserts the Zod `z.infer` matches the OpenAPI/Pydantic shape.
**Warning signs:** Frontend types `string`, backend returns `string | null`.

### Pitfall 2: Default-Value Inference Failures
**What goes wrong:** Zod `optional()` or `default()` fields produce wrong form state.
**Why it happens:** RHF's `defaultValues` don't match the schema's `default()`.
**How to avoid:** Derive `defaultValues` from `schema.parse({})` or build a `getDefaults` helper.
**Warning signs:** Required errors fire on initial render.

### Pitfall 3: Async Submit + Double-Submit
**What goes wrong:** User submits twice; server processes twice.
**Why it happens:** No `isSubmitting` guard or button disable.
**How to avoid:** Use `useMutation`'s `isPending` to disable submit; pass it to the button's `disabled`.
**Warning signs:** Duplicate rows in DB or repeated emails.

### Pitfall 4: Field Array Reset
**What goes wrong:** `useFieldArray` items don't reset on cancel.
**Why it happens:** `reset()` not called after cancel.
**How to avoid:** Call `reset(defaultValues)` on cancel, or refetch from server state.
**Warning signs:** Stale items reappear after navigating away and back.

</common_pitfalls>

<code_examples>
## Code Examples

### Sign-In Form with `useZodForm`

```tsx
"use client";
import { signInSchema, type SignInInput } from "@/lib/schemas/auth";
import { useZodForm } from "@/lib/forms/use-zod-form";
import { useMutation } from "@tanstack/react-query";

export function SignInForm() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useZodForm(signInSchema, { defaultValues: { email: "", password: "" } });
  const mutation = useMutation({ mutationFn: signIn });

  return (
    <form onSubmit={handleSubmit((data) => mutation.mutate(data))}>
      <input {...register("email")} aria-invalid={!!errors.email} />
      {errors.email && <span role="alert">{errors.email.message}</span>}
      <input type="password" {...register("password")} aria-invalid={!!errors.password} />
      {errors.password && <span role="alert">{errors.password.message}</span>}
      <button type="submit" disabled={isSubmitting}>Sign in</button>
    </form>
  );
}
```

### File Upload with RHF `Controller` + `react-dropzone`

```tsx
import { Controller } from "react-hook-form";
import { useDropzone } from "react-dropzone";

export function FileField({ control, name }: { control: Control<any>; name: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => {
        const { getRootProps, getInputProps } = useDropzone({
          onDrop: (accepted) => field.onChange(accepted),
        });
        return (
          <div {...getRootProps()}>
            <input {...getInputProps()} />
            <p>Drop files here</p>
          </div>
        );
      }}
    />
  );
}
```

</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `useState` per field | React Hook Form uncontrolled | Longstanding standard | Fewer re-renders, schema-bound validation. |
| Per-component Yup schemas | Zod + `@hookform/resolvers` | Current standard | TS inference and backend parity. |
| Formik | React Hook Form | 2020+ | Smaller bundle, fewer concepts, no render props. |
| `useEffect` submit | `useMutation` | Longstanding standard | Loading/error/success state in one hook. |

**New tools/patterns to consider:**
- `zod-to-openapi` for backend parity documentation.
- Server Actions (Next.js) as an alternative to `useMutation` for trivial cases.

**Deprecated/outdated:**
- Formik for new projects.
- Manual validation maps in component files.

</sota_updates>

<open_questions>
## Open Questions

1. **Should we adopt Server Actions instead of `useMutation` for simple forms?**
   - What we know: Next.js 16 supports Server Actions.
   - What's unclear: Whether the team is ready to commit to the Server Components model.
   - Recommendation: Start with `useMutation`; revisit after Phase 3 component primitives stabilize.

2. **Where do we put cross-field validation?**
   - What we know: Zod supports `.refine` on the full object.
   - What's unclear: Where to centralize (per-schema file or a `validators/` directory).
   - Recommendation: Keep `.refine` calls inside each schema file; export the schema, not the refine.

</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- React Hook Form docs — https://react-hook-form.com/
- Zod docs — https://zod.dev/
- `@hookform/resolvers` — https://github.com/react-hook-form/resolvers
- Zod + FastAPI parity notes — https://zod.dev/?id=json-schema

### Secondary (MEDIUM confidence)
- TanStack Query mutations — https://tanstack.com/query/latest/docs/framework/react/guides/mutations
- React Hook Form + Server Actions — https://react-hook-form.com/advanced-usage#ReactHookFormwithServerActions

### Tertiary (LOW confidence - needs validation)
- None.

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: react-hook-form, zod, @hookform/resolvers
- Ecosystem: react-dropzone, @tanstack/react-query, next-intl
- Patterns: Centralized schemas, useZodForm wrapper, dropzone Controller, mutation-driven submit
- Pitfalls: Schema/API drift, defaults, double-submit, field array reset

**Confidence breakdown:**
- Standard stack: HIGH — official docs and project package.json checked.
- Architecture: HIGH — matches React Hook Form / Zod / TanStack patterns.
- Pitfalls: HIGH — documented library behavior and known issues.
- Code examples: HIGH — official patterns.

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
</metadata>

---

# Phase 3 — Component primitives — Research

**Researched:** 2026-06-15
**Domain:** Accessible component primitives with Radix UI and shadcn/ui
**Confidence:** HIGH

<research_summary>
## Summary

Phase 3 adopts Radix UI primitives and shadcn/ui as FlowManner's owned component-primitive layer. Radix provides accessible, unstyled, composition-first primitives for Dialog, DropdownMenu, Popover, Tooltip, Select, Tabs, Switch, RadioGroup, Accordion, Slider, ScrollArea, and related widgets. shadcn/ui provides the CLI-driven, copy/paste component model that matches FlowManner's existing Tailwind + `cva` + `clsx` + `tailwind-merge` recipe.

The recommended architecture is to keep feature folders focused on product behavior and move reusable interactive primitives into `src/components/ui/*`. Do not import Radix directly into feature folders except for unusual composition needs. Mark interactive components as client components where needed.

**Primary recommendation:** Initialize shadcn/ui with `components.json`, add only needed primitives via the CLI, rebase `components/ui/button.tsx` on `@radix-ui/react-slot`, and replace `confirm-dialog.tsx` with shadcn AlertDialog.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `radix-ui` / individual `@radix-ui/react-*` | current Radix primitives | Accessible unstyled primitives | WAI-ARIA behavior, focus management, keyboard interaction, composition. |
| `shadcn/ui` | latest CLI/components | Owned component library generator | Matches FlowManner's Tailwind/CVA/cvx recipe and keeps component code editable. |
| `@radix-ui/react-slot` | current | `asChild` composable slot | Enables polymorphic button/link primitives. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tailwindcss` | `3.4.19` | Styling | Existing FlowManner stack. |
| `class-variance-authority` | `0.7.1` | Variant definitions | Existing pattern for buttons and UI variants. |
| `clsx` | `2.1.1` | Conditional classes | Existing pattern. |
| `tailwind-merge` | verify compatibility | Class conflict resolution | Existing pattern; verify Tailwind v3 compatibility before upgrading. |
| `sonner` | `2.0.7` | Toasts | Existing notification stack. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| shadcn/ui | Mantine/Chakra | Faster prebuilt UI, but less ownership and more styling overrides. |
| Radix direct imports | Custom primitives | Custom primitives risk accessibility regressions. |
| Headless UI | Radix | Radix has broader primitive coverage for menus/dialogs/comboboxes. |

**Installation:**

```bash
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button dialog dropdown-menu popover tooltip select tabs switch radio-group accordion slider scroll-area separator label checkbox
```

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure

```text
frontend/src/
├── components/
│   └── ui/
│       ├── button.tsx
│       ├── dialog.tsx
│       ├── dropdown-menu.tsx
│       ├── popover.tsx
│       ├── tooltip.tsx
│       ├── select.tsx
│       ├── tabs.tsx
│       ├── switch.tsx
│       ├── radio-group.tsx
│       ├── accordion.tsx
│       ├── slider.tsx
│       ├── scroll-area.tsx
│       ├── separator.tsx
│       ├── label.tsx
│       └── checkbox.tsx
└── lib/
    └── utils.ts
```

### Pattern 1: UI Boundary
**What:** Keep reusable primitives in `components/ui/*`; feature folders import from there.
**When to use:** All accessible interactive widgets.
**Example:**

```tsx
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
```

### Pattern 2: `cn()` Utility
**What:** Centralize class merging.
**When to use:** Every component that accepts `className`.
**Example:**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

### Pattern 3: CVA Variants
**What:** Use `cva` for controlled component variants.
**When to use:** Buttons, badges, inputs, cards, and other reusable UI.
**Example:**

```tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);
```

### Pattern 4: Radix `asChild`
**What:** Use `Slot`/`asChild` when a primitive should render a custom child component.
**When to use:** Polymorphic buttons, links, and styled wrappers.
**Anti-Patterns to Avoid**
- **Do not scatter Radix imports in feature folders.** It creates drift and inconsistent styling.
- **Do not hand-roll focus/keyboard behavior for dialogs/menus/tooltips.**
- **Do not use interactive primitives in Server Components without `"use client"` where required.**
- **Do not assume Tailwind v3 is compatible with every `tailwind-merge` major.** Verify before upgrading.

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dialog focus trap/Escape handling | Custom modal logic | Radix Dialog / shadcn Dialog | Focus management, aria, portal behavior. |
| Dropdown menus | Custom absolute menus | Radix DropdownMenu | Keyboard navigation, dismissal, aria semantics. |
| Tooltip positioning | Custom hover overlay | Radix Tooltip | Delay, collision, accessibility. |
| Select/Radio/Switch/Tabs | Custom state machines | Radix primitives | Complex keyboard and aria behavior. |
| Button polymorphism | Manual prop branching | `@radix-ui/react-slot` | Safer composable rendering. |

**Key insight:** Accessibility-critical widgets are not just styling problems. Radix/shadcn encode focus, keyboard, and ARIA behavior that is easy to get wrong by hand.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Accessibility Regression
**What goes wrong:** Menus/dialogs/tooltips work with a mouse but fail keyboard/screen-reader flows.
**Why it happens:** Custom components omit ARIA/focus/dismissal behavior.
**How to avoid:** Use Radix/shadcn primitives.
**Warning signs:** Keyboard-only smoke tests fail.

### Pitfall 2: shadcn Drift
**What goes wrong:** Copied components diverge from upstream and become hard to update.
**Why it happens:** Manual edits without pinning/CLI discipline.
**How to avoid:** Use `components.json`, pin the upstream commit, and update intentionally.
**Warning signs:** Components no longer match shadcn conventions.

### Pitfall 3: Tailwind Merge Version Mismatch
**What goes wrong:** Class conflicts resolve unexpectedly.
**Why it happens:** Tailwind v3 project with a `tailwind-merge` major aimed at newer Tailwind.
**How to avoid:** Verify compatibility before upgrading or keep a known-good major.
**Warning signs:** Variant classes do not override as expected.

### Pitfall 4: Bundle Growth
**What goes wrong:** App bundle grows with unused primitives.
**Why it happens:** Importing broad UI packages or unused primitives.
**How to avoid:** Add only needed components and import directly.
**Warning signs:** Bundle analyzer shows unused UI code.

</common_pitfalls>

<code_examples>
## Code Examples

### shadcn-style Button

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, asChild, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, className }))} {...props} />;
}

export { buttonVariants };
```

### Dialog Usage

```tsx
<Dialog>
  <Button variant="outline">Open</Button>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Confirm action</DialogTitle>
    </DialogHeader>
  </DialogContent>
</Dialog>
```

</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom modal primitives | Radix/shadcn Dialog | Longstanding standard | Better accessibility and focus behavior. |
| Prebuilt monolithic UI libraries | shadcn copy/paste primitives | Current dominant pattern | Owned code, Tailwind-native styling, less bundle bloat. |
| Manual class merging | `twMerge` + `clsx` | Current standard | Predictable class override behavior. |

**New tools/patterns to consider:**
- shadcn CLI for repeatable component addition.
- Radix `asChild` for polymorphic UI.
- CSS variable theming for dark/light mode.

**Deprecated/outdated:**
- Hand-rolled focus traps.
- Custom dropdown menus with ad-hoc keyboard behavior.

</sota_updates>

<open_questions>
## Open Questions

1. **Which `tailwind-merge` major should FlowManner keep?**
   - What we know: Project currently uses Tailwind 3.4.19 and `tailwind-merge` 3.6.0.
   - What's unclear: Compatibility with Tailwind v3.
   - Recommendation: Verify before adopting more shadcn components; downgrade if needed.

2. **Should shadcn components be added via CLI or manually?**
   - What we know: CLI is official and repeatable.
   - What's unclear: Existing `components/ui` conventions.
   - Recommendation: Use CLI, then adapt to FlowManner style.

</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- Radix UI Primitives intro — https://www.radix-ui.com/primitives/docs/overview/introduction
- Radix UI styling guide — https://www.radix-ui.com/primitives/docs/guides/styling
- Radix UI accessibility — https://www.radix-ui.com/primitives/docs/overview/accessibility
- shadcn/ui docs — https://ui.shadcn.com/docs
- shadcn/ui Next.js install — https://ui.shadcn.com/docs/installation/next
- shadcn/ui theming — https://ui.shadcn.com/docs/theming

### Secondary (MEDIUM confidence)
- `tailwind-merge` docs — https://github.com/dcastil/tailwind-merge
- CVA docs — https://cva.style/docs/getting-started/installation
- Sonner docs — https://sonner.emilkowal.ski/getting-started

### Tertiary (LOW confidence - needs validation)
- None.

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Radix UI + shadcn/ui
- Ecosystem: Tailwind, CVA, clsx, tailwind-merge, Sonner
- Patterns: UI boundary, `cn()`, CVA variants, `asChild`
- Pitfalls: Accessibility, shadcn drift, Tailwind merge compatibility, bundle growth

**Confidence breakdown:**
- Standard stack: HIGH — official docs and project package.json checked.
- Architecture: HIGH — matches shadcn/Radix conventions.
- Pitfalls: HIGH — documented library behavior and roadmap risks.
- Code examples: HIGH — official patterns.

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
</metadata>

---

# Phase 4 — Data display — Research

**Researched:** 2026-06-15
**Domain:** Data tables, charts, virtualization, and date formatting for React/Next.js dashboards
**Confidence:** HIGH

<research_summary>
## Summary

Phase 4 adopts `@tanstack/react-table`, `recharts`, and `date-fns` to replace hand-rolled table, chart, and date formatting logic in FlowManner dashboards. TanStack Table is headless: it owns data processing, sorting, filtering, pagination, column visibility, and row model state, while FlowManner owns markup, styling, accessibility, and domain-specific cells. Recharts provides chart primitives for analytics/cost/mission dashboards, and `date-fns` centralizes locale-aware formatting and relative time.

The recommended architecture is a shared `useTableState` hook, a new `components/charts/` wrapper layer lazy-loaded on dashboard routes, and a `src/lib/date.ts` module that pulls locale from `next-intl`. For large datasets, keep server-side sorting/filtering/pagination in TanStack Query and pass manual table state to TanStack Table.

**Primary recommendation:** Use TanStack Table as the table state/processing layer, pair it with existing `@tanstack/react-virtual` for large lists, lazy-load Recharts wrappers, and centralize date formatting in `src/lib/date.ts`.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@tanstack/react-table` | `8.21.3` | Headless table state and row processing | Standard for sortable/filterable/paginated tables without imposing markup. |
| `recharts` | `3.8.1` | React chart primitives | Widely used for dashboard charts; composes with React state. |
| `date-fns` | `4.4.0` | Date formatting and locale helpers | Small, modular, ESM-first date utilities. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tanstack/react-virtual` | `3.13.26+` | Row/window virtualization | Existing dependency; pair with TanStack Table for large lists. |
| `@tanstack/react-query` | `5.100.11+` | Server state and query keys | Keep table filters/sort/pagination in query state. |
| `next-intl` | `4.12.0` | Locale context | Feed `date-fns` locale selection. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| TanStack Table | AG Grid | Faster turnkey grids, but heavier and less customizable. |
| Recharts | Victory/Nivo | Different rendering/model tradeoffs; Recharts is simpler for existing dashboard charts. |
| date-fns | Day.js/luxon | Day.js is mutable-ish; date-fns is functional and modular. |

**Installation:**

```bash
pnpm add @tanstack/react-table@8.21.3 recharts@3.8.1 date-fns@4.4.0
```

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure

```text
frontend/src/
├── components/
│   ├── charts/
│   │   ├── chart-wrapper.tsx
│   │   ├── token-cost-chart.tsx
│   │   └── cost-breakdown-chart.tsx
│   └── evaluation/
│       └── evaluation-dashboard.tsx
├── hooks/
│   ├── useTableState.ts
│   └── use-cost-tracker.ts
└── lib/
    ├── date.ts
    └── schemas/
        └── table-filters.ts
```

### Pattern 1: Headless Table State
**What:** Use TanStack Table for state and row processing, not styling.
**When to use:** Any sortable/filterable/paginated list.
**Example:**

```tsx
const table = useReactTable({
  data: rows,
  columns,
  state: { sorting, columnFilters, pagination },
  onSortingChange: setSorting,
  onColumnFiltersChange: setColumnFilters,
  onPaginationChange: setPagination,
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
});
```

### Pattern 2: Server-Side Table State
**What:** For large FlowManner datasets, keep sorting/filtering/pagination in the server query and pass manual mode flags.
**When to use:** Tables backed by API pagination.
**Example:**

```tsx
const table = useReactTable({
  data: response.items,
  columns,
  manualSorting: true,
  manualFiltering: true,
  manualPagination: true,
  rowCount: response.total,
  state: { sorting, columnFilters, pagination },
  onSortingChange: setSorting,
  onColumnFiltersChange: setColumnFilters,
  onPaginationChange: setPagination,
  getCoreRowModel: getCoreRowModel(),
});
```

### Pattern 3: Virtualized Rows
**What:** Pair TanStack Table with `@tanstack/react-virtual`.
**When to use:** Large row lists such as program run history or evaluation dashboards.
**Example:**

```tsx
const rowVirtualizer = useVirtualizer({
  count: table.getRowModel().rows.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 44,
  overscan: 10,
});
```

### Pattern 4: Chart Wrappers
**What:** Wrap Recharts in FlowManner-specific chart components with theme/tooltip styling.
**When to use:** Evaluation, cost, and mission analytics dashboards.
**Example:**

```tsx
<ResponsiveContainer width="100%" height={240}>
  <BarChart data={data}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="timestamp" />
    <YAxis />
    <Tooltip />
    <Bar dataKey="tokens" fill="#3b82f6" />
  </BarChart>
</ResponsiveContainer>
```

### Anti-Patterns to Avoid
- **Do not hand-roll sort/filter/pagination state.** Use TanStack Table.
- **Do not mix client-side and server-side table modes accidentally.** Be explicit.
- **Do not render Recharts in Server Components.** Mark chart wrappers client-only and lazy-load.
- **Do not scatter date formatting helpers.** Centralize in `src/lib/date.ts`.
- **Do not import every `date-fns/locale`.** Use a small locale map.

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sorting/filtering/pagination state | Custom `useState<SortKey>` maps | TanStack Table | Handles column models, row models, visibility, selection, and state updates. |
| Virtualized rows | Manual scroll math | `@tanstack/react-virtual` | Existing FlowManner dependency; handles measurements and overscan. |
| Chart axes/tooltips/responsive sizing | Custom SVG charts | Recharts | Avoids SVG scale/tooltip/legend bugs. |
| Date formatting/relative time | Scattered `toLocaleString` helpers | `date-fns` | Modular, locale-aware, predictable formatting. |

**Key insight:** Data display libraries are headless for a reason: FlowManner should own domain-specific cells and styling, not the low-level mechanics of table state, chart scales, or date formatting.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Headless Accessibility Gaps
**What goes wrong:** Table UI lacks keyboard/focus behavior for filters, menus, and column visibility.
**Why it happens:** TanStack Table does not provide markup/accessibility.
**How to avoid:** Pair with Radix/shadcn primitives from Phase 3.
**Warning signs:** Column menus work with mouse but not keyboard.

### Pitfall 2: Server/Client Mode Confusion
**What goes wrong:** UI sorts locally while API expects server-side sorting, or pagination state diverges.
**Why it happens:** Manual flags are omitted or mixed.
**How to avoid:** Use `manualSorting/manualFiltering/manualPagination` for server-backed tables.
**Warning signs:** Page size changes but API query does not.

### Pitfall 3: Recharts Hydration Warnings
**What goes wrong:** Charts render differently on server and client.
**Why it happens:** SVG/chart dimensions or random state differ during SSR.
**How to avoid:** Use client wrappers and `next/dynamic` with `ssr: false` for dashboard charts.
**Warning signs:** Hydration mismatch warnings on `/evaluation` or `/analytics`.

### Pitfall 4: Date Locale Drift
**What goes wrong:** EN/FR dates format inconsistently.
**Why it happens:** Date helpers are scattered.
**How to avoid:** Centralize `date-fns` locale selection from `next-intl`.
**Warning signs:** Same timestamp formats differently across pages.

</common_pitfalls>

<code_examples>
## Code Examples

### Shared Date Module

```ts
import { format, formatDistanceToNow, isValid } from "date-fns";
import { enUS, fr } from "date-fns/locale";

const DATE_FNS_LOCALES = {
  en: enUS,
  "en-US": enUS,
  fr,
  "fr-FR": fr,
} as const;

export function getLocale(locale: string | undefined) {
  return DATE_FNS_LOCALES[(locale as keyof typeof DATE_FNS_LOCALES) ?? "en"];
}

export function formatDateTime(value: string | Date | null | undefined, locale?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (!isValid(date)) return "";
  return format(date, "PP p", { locale: getLocale(locale) });
}

export function formatDistanceToNowString(
  value: string | Date | null | undefined,
  locale?: string,
) {
  if (!value) return "";
  const date = new Date(value);
  if (!isValid(date)) return "";
  return formatDistanceToNow(date, {
    addSuffix: true,
    locale: getLocale(locale),
  });
}
```

### TanStack Table + Virtualizer

```tsx
const parentRef = useRef<HTMLDivElement | null>(null);

const rowVirtualizer = useVirtualizer({
  count: table.getRowModel().rows.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 44,
  overscan: 10,
});
```

</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-rolled table state | TanStack Table | Longstanding standard | Predictable table state and row models. |
| Custom SVG charts | Recharts wrappers | Current dashboard standard | Faster chart iteration with maintained primitives. |
| Scattered `Intl` helpers | Central `date-fns` module | Current modular date pattern | Locale consistency and smaller imports. |

**New tools/patterns to consider:**
- `@date-fns/tz` if explicit timezone arithmetic becomes necessary.
- Dynamic imports for chart-heavy dashboard routes.

**Deprecated/outdated:**
- Hand-rolled sort/filter/pagination state for dashboards.
- Scattered date formatting helpers.

</sota_updates>

<open_questions>
## Open Questions

1. **Which tables are server-backed vs client-backed?**
   - What we know: Evaluation dashboard and program run history are likely API-backed.
   - What's unclear: Exact API pagination/sort/filter support.
   - Recommendation: Inspect API response shape before choosing manual mode.

2. **How much chart SSR should be disabled?**
   - What we know: Recharts can trigger hydration warnings.
   - What's unclear: Which charts are safe under Next.js SSR.
   - Recommendation: Start with `ssr: false` for dashboard charts and revisit after perf audit.

</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- TanStack Table introduction — https://tanstack.com/table/latest/docs/introduction
- TanStack Table sorting — https://tanstack.com/table/latest/docs/guide/sorting
- TanStack Table filtering — https://tanstack.com/table/latest/docs/guide/column-filtering
- TanStack Table pagination — https://tanstack.com/table/latest/docs/guide/pagination
- TanStack Table virtualization — https://tanstack.com/table/latest/docs/guide/virtualization
- TanStack Virtual docs — https://tanstack.com/virtual/latest/docs/introduction
- Recharts docs — https://recharts.org/en-US/
- Recharts SSR guide — https://recharts.org/en-US/guide/ssr
- date-fns docs — https://date-fns.org/docs/Getting-Started

### Secondary (MEDIUM confidence)
- npm metadata for `@tanstack/react-table`, `recharts`, and `date-fns`.
- TanStack Query React docs — https://tanstack.com/query/latest/docs/framework/react/overview

### Tertiary (LOW confidence - needs validation)
- None.

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: TanStack Table, Recharts, date-fns
- Ecosystem: TanStack Virtual, TanStack Query, next-intl
- Patterns: Headless table state, server-side table mode, chart wrappers, central date module
- Pitfalls: Accessibility gaps, hydration, server/client mode confusion, locale drift

**Confidence breakdown:**
- Standard stack: HIGH — official docs and package metadata checked.
- Architecture: HIGH — aligns with TanStack/Recharts/date-fns patterns.
- Pitfalls: HIGH — roadmap risks and library docs align.
- Code examples: HIGH — official patterns.

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
</metadata>

---

# Phase 5 — Power features — Research

**Researched:** 2026-06-15
**Domain:** Motion, command palette, drag-and-drop, and Storybook for React/Next.js polish
**Confidence:** HIGH

<research_summary>
## Summary

Phase 5 adds power-user polish on top of the earlier form/primitive/data foundations: `motion` for transitions, `kbar` for the command palette, `@dnd-kit` for drag-and-drop, and Storybook for component documentation. The recommended approach is to introduce these libraries as focused wrappers and providers rather than scattering behavior across the app.

FlowManner already has a hand-rolled command palette and some raw drag/drop patterns. The research recommends replacing the command palette with `kbar` only after shortcut conflicts are resolved, replacing raw HTML5 drag/drop with `@dnd-kit` for sortable lists, and using Storybook as a static dev/docs surface for `components/ui/*`.

**Primary recommendation:** Add `motion`, `kbar`, `@dnd-kit/core`, `@dnd-kit/sortable`, and Storybook 10; centralize motion wrappers, command actions, sortable list logic, and stories so these libraries do not become scattered production-bundle debt.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `motion` | `12.40.0` | React animation primitives | Current official React package for Framer Motion-style animation. |
| `kbar` | `0.1.0-beta.48` | Command palette/action center | Complete command palette with actions, shortcuts, search, and keyboard behavior. |
| `@dnd-kit/core` | `6.3.1` | Drag-and-drop context/sensors | Standard DnD primitive layer. |
| `@dnd-kit/sortable` | `10.0.0` | Sortable lists | Reorderable lists with keyboard support. |
| `storybook` | `10.4.4` | Component documentation/testing surface | Static dev/docs surface for UI primitives. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `cmdk` | `1.1.1` | Command primitive | Use only if building a custom command dialog instead of kbar. |
| `@dnd-kit/utilities` | `3.2.2` | DnD helpers | `arrayMove`, transforms, constraints. |
| `@storybook/nextjs` | `10.4.4` | Storybook Next.js preset | Supports Next.js 14+ including 16 per npm peers. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `motion` | CSS transitions | CSS is lighter but harder to coordinate across mount/unmount/layout transitions. |
| `kbar` | `cmdk` only | `cmdk` is a primitive; kbar is the more complete command center. |
| `@dnd-kit` | HTML5 drag/drop | HTML5 is simpler but weaker for keyboard/accessibility and complex gestures. |
| Storybook | Ad-hoc docs | Storybook provides standardized stories and CI build checks. |

**Installation:**

```bash
pnpm add motion kbar @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
pnpm add -D storybook @storybook/nextjs
```

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure

```text
frontend/src/
├── components/
│   ├── chat/
│   │   └── CommandPalette.tsx          # Replace/wrap with kbar
│   ├── layout/
│   │   └── floating-nav.tsx            # dnd-kit sortable
│   ├── mission-builder/
│   │   └── NodePalette.tsx             # dnd-kit sortable
│   └── ui/
│       └── motion/
│           ├── FadeIn.tsx
│           ├── SlideUp.tsx
│           └── Stagger.tsx
├── providers/
│   └── command-palette-provider.tsx
└── lib/
    └── command-palette/
        └── actions.ts
```

### Pattern 1: Motion Wrapper Layer
**What:** Create small `components/ui/motion/*` wrappers for common transitions.
**When to use:** Chat messages, overlays, cards, and layout transitions.
**Example:**

```tsx
"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

export function FadeIn({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
    >
      {children}
    </motion.div>
  );
}
```

### Pattern 2: kbar Provider + Actions
**What:** Centralize command actions by role/route.
**When to use:** Global command palette.
**Example:**

```tsx
<KBarProvider actions={actions}>
  <KBarPortal>
    <KBarPositioner>
      <KBarAnimator>
        <KBarSearch />
        <KBarResults />
      </KBarAnimator>
    </KBarPositioner>
  </KBarPortal>
</KBarProvider>
```

### Pattern 3: dnd-kit Sortable List
**What:** Use `DndContext`, `SortableContext`, `KeyboardSensor`, and `PointerSensor`.
**When to use:** Reorderable lists in mission builder and floating nav.
**Example:**

```tsx
const sensors = useSensors(
  useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  useSensor(KeyboardSensor),
);
```

### Pattern 4: Static Storybook
**What:** Use Storybook as a dev/docs surface, not production bundle.
**When to use:** `components/ui/*` and reusable primitives.
**Example:**

```json
{
  "scripts": {
    "storybook": "storybook dev -p 6006",
    "build-storybook": "storybook build"
  }
}
```

### Anti-Patterns to Avoid
- **Do not keep raw HTML5 drag/drop for sortable UI.**
- **Do not leave command palette shortcuts conflicting across chat/settings.**
- **Do not animate every component inline with ad-hoc CSS.**
- **Do not bundle Storybook into production.**
- **Do not add Storybook stories for RSC-only components without adapters.**

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Command filtering/keyboard/virtualization | Custom command center | `kbar` | Handles actions, shortcuts, search, and keyboard behavior. |
| Sortable list drag/drop | Raw HTML5 `draggable` | `@dnd-kit/core` + `@dnd-kit/sortable` | Better accessibility, sensors, collision, and keyboard support. |
| Mount/unmount transitions | Ad-hoc CSS classes | `motion` / `AnimatePresence` | Centralized animation semantics. |
| Component documentation | Ad-hoc markdown/screenshots | Storybook | Standard stories and CI validation. |

**Key insight:** Power features are where custom code becomes expensive quickly. Use primitives and wrappers so polish remains maintainable.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Shortcut Conflicts
**What goes wrong:** Cmd/Ctrl+K opens different surfaces depending on focus.
**Why it happens:** Existing chat/settings keyboard handlers overlap.
**How to avoid:** Define a canonical shortcut model before adopting kbar.
**Warning signs:** `use-chat-keyboard.ts` and `CommandPalette.tsx` both listen for Cmd/Ctrl+K.

### Pitfall 2: DnD Accessibility Gaps
**What goes wrong:** Drag works with pointer but not keyboard.
**Why it happens:** Raw HTML5 drag/drop lacks robust keyboard semantics.
**How to avoid:** Use `KeyboardSensor`, focusable activators, and dnd-kit sortable patterns.
**Warning signs:** Tab+arrow reordering fails.

### Pitfall 3: Motion Bundle Bloat
**What goes wrong:** Animation library grows production bundle.
**Why it happens:** Motion is imported broadly or used on every route.
**How to avoid:** Central wrappers and dynamic imports for heavy routes.
**Warning signs:** Bundle analyzer shows motion on routes without animation.

### Pitfall 4: Storybook Provider Gaps
**What goes wrong:** Stories fail because auth/i18n/query providers are missing.
**Why it happens:** Components depend on app providers.
**How to avoid:** Add Storybook decorators for theme, i18n, query, and auth mocks.
**Warning signs:** `pnpm storybook` boots but stories error on missing context.

</common_pitfalls>

<code_examples>
## Code Examples

### Motion Wrapper

```tsx
"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

export function SlideUp({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
    >
      {children}
    </motion.div>
  );
}
```

### dnd-kit Sortable List

```tsx
const sensors = useSensors(
  useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  useSensor(KeyboardSensor),
);

<DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
  <SortableContext items={items} strategy={verticalListSortingStrategy}>
    {items.map((item) => (
      <SortableItem key={item.id} id={item.id} />
    ))}
  </SortableContext>
</DndContext>
```

### Storybook Story

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "./button";

const meta = {
  title: "UI/Button",
  component: Button,
} satisfies Meta<typeof Button>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    children: "Continue",
    variant: "default",
  },
};
```

</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `framer-motion` import path | `motion` package | Current docs point to `motion` | Newer package/docs alignment. |
| Custom command palette | `kbar` | Current command-center pattern | Actions, shortcuts, search, keyboard behavior. |
| HTML5 drag/drop | `@dnd-kit` | Current DnD standard | Better accessibility and sensor model. |
| Ad-hoc component docs | Storybook 10 | Current component story surface | Repeatable stories and CI checks. |

**New tools/patterns to consider:**
- `motion/react` wrappers for shared transitions.
- kbar action registry by role/route.
- dnd-kit `KeyboardSensor` for sortable lists.
- Static Storybook build in CI.

**Deprecated/outdated:**
- Raw HTML5 drag/drop for sortable UI.
- Custom command filtering without a central action model.

</sota_updates>

<open_questions>
## Open Questions

1. **Should FlowManner use kbar or cmdk for the command palette?**
   - What we know: Existing command palette is hand-rolled.
   - What's unclear: Whether the team wants a full command center or a primitive dialog.
   - Recommendation: Use kbar unless the custom dialog shell is a hard requirement.

2. **Which drag/drop surfaces are safe to migrate first?**
   - What we know: Mission builder and floating nav are named targets.
   - What's unclear: Existing XYFlow/node drag interactions.
   - Recommendation: Migrate one low-risk sortable list before touching canvas/node drag.

</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- Motion React docs — https://motion.dev/docs/react
- Motion installation — https://motion.dev/docs/react-installation
- Motion AnimatePresence — https://motion.dev/docs/react-animate-presence
- Motion reduced motion — https://motion.dev/docs/react-use-reduced-motion
- dnd-kit docs — https://dndkit.com/
- dnd-kit sensors — https://dndkit.com/guides/sensors
- dnd-kit accessibility — https://dndkit.com/guides/accessibility
- dnd-kit sortable API — https://dndkit.com/api-documentation/sortable
- kbar docs — https://kbar.vercel.app/docs
- cmdk GitHub — https://github.com/dip/cmdk
- Storybook install docs — https://storybook.js.org/docs/get-started/install

### Secondary (MEDIUM confidence)
- npm metadata for `motion`, `kbar`, `cmdk`, `@dnd-kit/core`, `@dnd-kit/sortable`, `storybook`, and `@storybook/nextjs`.

### Tertiary (LOW confidence - needs validation)
- None.

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Motion, kbar, dnd-kit, Storybook
- Ecosystem: cmdk, @dnd-kit/utilities, @storybook/nextjs
- Patterns: Motion wrappers, command action registry, sortable list sensors, static Storybook
- Pitfalls: Shortcut conflicts, accessibility gaps, bundle bloat, provider gaps

**Confidence breakdown:**
- Standard stack: HIGH — official docs and package metadata checked.
- Architecture: HIGH — aligns with current library docs and FlowManner roadmap.
- Pitfalls: HIGH — roadmap risks and existing code evidence align.
- Code examples: HIGH — official patterns.

**Research date:** 2026-06-15
**Valid until:** 2026-07-15
</metadata>

---

## Provenance

Five per-phase research documents created 2026-06-15 by Claude Code in
`.planning/phases/{1-defensive-polish,2-forms-validation,3-component-primitives,4-data-display,5-power-features}/{N}-RESEARCH.md`.
Each carried the GSD `<research_summary>`, `<standard_stack>`,
`<architecture_patterns>`, `<dont_hand_roll>`, `<common_pitfalls>`,
`<code_examples>`, `<sota_updates>`, `<open_questions>`, `<sources>`, and
`<metadata>` blocks, ending with `Ready for planning: yes`.

Folded into this single file 2026-06-15 per session decision B. The
`.planning/` directory has been removed; this file is the canonical
research document. The companion strategic plan at
`.sisyphus/plans/frontend-awesome-react-adoption.md` references this
file for the per-phase deep-dives.

Each phase's research was conducted against the awesome-react catalog
(https://github.com/enaqx/awesome-react, 262 lines, fetched 2026-06-15)
and cross-referenced with the existing FlowManner frontend stack
(`/home/glenn/FlowmannerV2-frontend/package.json`, 30+ hand-rolled UI
patterns, 215 form-related useState sites).
