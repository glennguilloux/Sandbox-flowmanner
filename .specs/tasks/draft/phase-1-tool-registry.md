# Phase 1 — Tool Registry + Inline Tool-Call Cards — Known Limitations

## Status: Implementation complete, pending frontend build verification

## Deliberate Phase 1 Constraints (to be resolved in later phases)

### `_execute_tool_call` denies all tools with `required_scopes` in chat context
- **Why:** Phase 1 avoid the per-call DB lookup cost for scope resolution.
- **Impact:** Any tool with non-empty `required_scopes` will be denied in chat.
  Phase 1 allowlisted tools all have empty scopes, so this is defense-in-depth.
- **Phase 5 fix:** Add cached user-scope resolution before the tool-calling loop.

### Two parallel sources of truth for tool events
- **Current:** `steps[]` on message AND `ToolEventContext` sidebar feed are independent.
- **Spec wanted:** `steps[]` as source of truth, sidebar derived from it.
- **Phase 2 fix:** Make sidebar feed a read-only projection of `steps[]`.

### Frontend build not verified
- **Reason:** Frontend source at `/home/glenn/FlowmannerV2-frontend/` is outside the
  project root accessible to the coding agent.
- **Action required:** Run `pnpm lint && pnpm build && pnpm test` in the frontend
  directory before deploying.

### `ToolCallCard` animation uses CSS transitions, not framer-motion
- **Why:** The spec mentioned `motion` (framer-motion) for expand/collapse.
- **Current:** Uses CSS `rotate-180` transition on the chevron. Works correctly.
- **Optional:** Add framer-motion for smoother expand/collapse in a polish pass.

### `_user_has_scopes` hardcodes `admin`/`owner` role strings
- **Why:** No shared constants for role names in the codebase.
- **Phase 2 fix:** Extract to a constants module or verify against the actual user model.
