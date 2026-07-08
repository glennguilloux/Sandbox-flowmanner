# ADR-002: Ordered `prepareStep` Injection Hook for Chat (Spike)

**Status**: Proposed (spike, feature-flagged — no behavior change while off)
**Date**: 2026-07-08
**Deciders**: Hermes (agent), Glenn (owner)
**Supersedes / Related**: `docs/analyse/AGENTIC-CHAT-REENTRANT-TURN-MODEL.md`,
`docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` (Phase 2 — Agent step streaming)

## Context

trigger.dev's `chat.agent` runtime (`packages/trigger-sdk/src/v3/ai.ts`,
commit `a6bd370`) wires all context injection through a single `prepareStep`
primitive called at each AI-SDK step boundary, in a fixed order: compaction →
steering → background. The ordering is enforced by **code structure**, not
convention, and injection writes a confirmation chunk so the UI can reconcile
injected-vs-queued context.

Flowmanner's chat layer (`backend/app/services/chat_service.py`) injects
context inline and **pre-LLM only**: memory recall
(`_inject_memory_context`, `:447`) and web search (`_inject_web_search`,
`:471`) are appended before the LLM call, with no ordered closure, no
step-boundary hook, and no injection receipt. The substrate already models the
re-entrant/durable/interruptible turn (via `UnifiedExecutor` + `HITLPaused`),
but chat does not.

Agentic / multi-step chat **is on the roadmap** (Phase 2 "Agent step
streaming", `spawn-mission` design). When it lands, chat must inject context
*between* tool steps — which requires a step-boundary hook and a `shouldInject`
gate. This ADR introduces that hook **now, behind a flag**, so the loop is ready
and no single-shot behavior changes until agentic chat ships.

## Decision

Add a single ordered injection closure `_prepare_step_inject(messages, *,
memory_claims, web_search, content, steps=None, should_inject=None)` in
`chat_service.py`, called from `_stream_message_to_llm_body` gated by a new
settings flag `CHAT_PREPARE_STEP_HOOK_ENABLED` (default **False**).

- When the flag is **off** (default): the legacy inline memory/web_search
  injection runs unchanged. Single-shot chat is byte-for-byte identical.
- When the flag is **on**: context injection routes through
  `_prepare_step_inject`, which returns `(messages_with_context,
  injected_events)`. Each injected source emits an `{"type": "injected", ...}`
  SSE receipt event, yielded to the frontend before the LLM call.
- The closure's order is **memory → web search** today; the future step-boundary
  path adds a `should_inject` gate and additional per-step sources at the
  `(Future step-boundary hook point)` comment.

This deliberately mirrors the trigger.dev model: one ordered closure, a receipt
per injection, and a gate point reserved for step boundaries.

## Alternatives Considered

1. **Add injection calls inline at each step of the existing tool loop.** —
   Rejected: scatters injection across the loop, repeats the ordering logic,
   and provides no receipt. Duplicates the very anti-pattern trigger.dev's
   single `prepareStep` exists to prevent.
2. **Adopt the AI SDK `prepareStep` directly (JS).** — Not applicable: the
   Flowmanner backend is Python/FastAPI with an openai-style tool loop, not the
   Vercel AI SDK. We adopt the *pattern*, implemented in Python, not the library.
3. **Build the full re-entrant turn model now (run_id + replay + HITL).** —
   Rejected for the spike: out of scope for a no-behavior-change hook. Tracked
   as the follow-on in `AGENTIC-CHAT-REENTRANT-TURN-MODEL.md` (lifts #1, #4).

## Design Patterns Used

- **Feature-flag gate** (`settings.CHAT_PREPARE_STEP_HOOK_ENABLED`) — matches the
  existing `CHAT_MEMORY_CITATIONS_ENABLED` (T33) precedent: a `settings` bool,
  default False, no DB row required for a spike.
- **Single ordered closure** — code-structure-enforced injection order.
- **Receipt event** — SSE `injected` events let the frontend reconcile
  injected-vs-queued, killing the "did my steer land?" ambiguity class.
- **Reserved hook point** — `steps` / `should_inject` params + a `(Future)`
  comment mark where the step-boundary gate plugs in.

## Consequences

### Positive
- Chat is ready for multi-step agentic injection without a rewrite when Phase 2
  lands.
- Frontend gains an `injected` event to distinguish recalled/auto-injected
  context from user-sent messages.
- Zero behavior change for existing users while the flag is off (proven by the
  equivalence test).

### Negative
- A new code path (the closure) that is dormant until the flag flips. Mitigated
  by the equivalence test asserting flag-off == legacy.
- Flag debt: must be removed or promoted to default-on when Phase 2 ships.

### Mitigations
- Test `tests/test_chat_prepare_step_hook.py` asserts: (a) flag off → identical
  message list and no `injected` events; (b) flag on → same context injected +
  receipt events emitted; (c) ordering memory-before-web_search.
- The closure reuses the existing `_inject_memory_context` /
  `_inject_web_search` functions, so there is no duplicated injection logic.

## Follow-on (out of scope for this spike)

- Lift #1: give chat turns a `run_id` bound to the substrate event log.
- Lift #4: reuse `HITLPaused` for chat tool-call approvals.
- Promote the hook to run at each step boundary with the `shouldInject` gate
  once the re-entrant turn loop exists.

See `docs/analyse/AGENTIC-CHAT-REENTRANT-TURN-MODEL.md` §5 for the full lift list.
