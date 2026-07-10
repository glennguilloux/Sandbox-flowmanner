# Agentic Chat & the Re-entrant Turn Model — Roadmap Fit Analysis

**Date:** 2026-07-08
**Author:** Hermes (agent)
**Status:** Analysis — supports planning, does not implement
**Trigger:** Investigation of `trigger.dev`'s `chat.agent` runtime (`prepareStep` / durable
Session / re-entrant turn loop) and whether Flowmanner's chat layer should adopt the same
shape. Conclusion: **agentic + multi-step chat IS on the roadmap**, so the re-entrant model
is the correct target — but chat is not yet structured for it. This doc maps the gap and the
lifts, grounded in the actual codebase.

---

## 1. Is agentic / multi-step chat on the roadmap? — Yes.

Concrete evidence (not assumptions):

- `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` §4 / §5, **Phase 2 — Agent step
  streaming**: "One event stream for chat-with-tools and missions", `POST
  /api/v2/chat/threads/{id}/spawn-mission`. Renders substrate `UnifiedExecutor` events inline
  as `AgentStep[]`.
- `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §2.1: full `spawn-mission` design — returns
  `mission_id` + SSE `mission-stream` endpoint that re-emits `agent_step`,
  `permission_request` frames into chat. Test plan at line 135 asserts inline agent step tree +
  Approve-on-permission-card flow.
- `docs/HYBRID-PLATFORM-WORKSPACE.md` line 91 / 246 / 327: spawn-mission endpoint scoped to
  `backend/app/api/v2/chat.py`, permission request cards as a first-class surface.
- **Backend already has the building blocks**: `chat_service.stream_message_to_llm`
  (`app/services/chat_service.py:284`) carries an openai-style tool-calls loop
  (`tool_calls_by_index`, `tool_call_start`/`tool_call_result` SSE events) — partially
  implemented per the roadmap's own §1.2. Substrate `UnifiedExecutor` already does
  autonomous multi-step execution with `HITLPaused` resume (`app/services/substrate/
  node_executor.py:1341`, `:1509`).

So the question "should we build the re-entrant turn model?" is already answered by the
roadmap: **multi-step agentic chat is planned, therefore the durable/re-entrant shape is the
right end state.** The remaining work is restructuring chat to match what workflows already
have.

---

## 2. The trigger.dev model, restated (source-grounded)

From `packages/trigger-sdk/src/v3/ai.ts` (commit `a6bd370`, trigger.dev main):

- **Turn = a re-entrant task run bound to a durable Session** (`chat.agent` is a thin
  `createTask` wrapper; `ai.ts:5391`). Each turn is one run invocation; the session row
  (`sessions.open(payload.chatId)`, `ai.ts:5475`) is the durable identity.
- **One injection point: `prepareStep`** (`toStreamTextOptions`, `ai.ts:3822` →
  `ai.ts:3883`). A single closure runs, in fixed order: (1) compaction, (2) pending-message
  steering injection, (3) background context injection. The ordering is enforced by code
  structure, not convention.
- **`prepareStep` fires at the AI-SDK step boundary** — between every tool-call step. For
  single-step (pure text) turns it never fires; the outer loop (`ai.ts:7405`) handles
  compaction between turns instead.
- **`shouldInject` is called once per batch** at the boundary (`drainSteeringQueue`,
  `ai.ts:3363` → `:3387`). A rejected injection stays queued for the next boundary.
- **Injection writes a confirmation chunk** (`PENDING_MESSAGE_INJECTED_TYPE`, `ai.ts:3421`)
  carrying message IDs + text, so the UI can reconcile injected-vs-queued.
- **HITL = raising `HITLPaused`** (the agent run ends; resolution re-enters the same run by
  `run_id`). Durability comes from the Session, not in-process memory.

---

## 3. Where Flowmanner already matches the model

| trigger.dev primitive | Flowmanner equivalent | Location |
|---|---|---|
| Durable Session / `run_id` | `WorkflowRun` + append-only `substrate_events` | `substrate/event_log.py`, `substrate/AGENTS.md` guarantee #2 |
| Re-entrant run resume | `ReplayEngine` rebuilds state from event log by `run_id` | `substrate/replay_engine.py`, AGENTS.md #10 |
| `HITLPaused` resume | `node_executor._check_hitl_resume` + `raise HITLPaused` | `substrate/node_executor.py:1341`, `:1509` |
| Durable interrupt inbox | `HumanInterruptRecord` + `HITLManager.resolve_interrupt` | `orchestration/human_interrupt.py` |
| Ordered injection | pieces exist (`_inject_memory_context`, `_inject_web_search`,
  `personal_memory_service`) but called inline, pre-LLM | `chat_service.py:448`, `:471`;
  `chat_context.py:86` |

**Key finding:** the re-entrant / durable / pause-resume model is **already built for
workflows** (`substrate/`). It is simply **not applied to chat turns**. Chat is single-shot
streaming with no `run_id`, no step boundary, no resume.

---

## 4. Where chat assumes a single in-process loop (the flags)

1. **No turn/run identity in chat.** `stream_message_to_llm` (`chat_service.py:284`) is
   invoked per HTTP request and streams to completion. There is no `run_id`, no
   `prepareStep`, no resumable state. A human steering mid-turn has nowhere to inject — the
   LLM call has already begun. This is exactly the hole `prepareStep` fills.

2. **Injection is pre-LLM, not at step boundaries.** `_stream_message_to_llm_body` calls
   `_inject_memory_context` (`:448`) and `_inject_web_search` (`:471`) *before* streaming.
   Fine for single-shot chat; but the moment chat gains **multi-step tool loops** (roadmap
   Phase 2), injection must happen *between steps* — and there is no hook for it. The
   substrate's `NodeExecutor` already iterates nodes step-by-step; chat does not.

3. **No `shouldInject` gate.** Memory / web-search injection always fires when data is
   present. trigger.dev gates per batch at the boundary so steering is *decided*, not
   *blindly appended*. Without the gate you cannot distinguish "human steered this turn"
   from "RAG auto-recalled".

4. **HITL lives in workflows, not chat turns.** `human_interrupt.py` + `node_executor.py`
   pausing targets `Mission`/`WorkflowRun`. An agentic chat turn that hits an
   approval-worthy tool call has no path to `raise HITLPaused` and resume — it would block
   the HTTP response. The roadmap's `permission_request` card needs this plumbing.

5. **No injection-receipt event.** The SSE layer (`_sse_keepalive_merge`, `chat_service.py
   :240`) merges keepalive pings but emits no "injected" receipt. The UI cannot reconcile
   injected-vs-queued — the root of "did my steer land?" bugs.

---

## 5. The four lifts (priority order)

1. **Give chat turns a `run_id`, bind to the event log.** Cheapest win — reuse
   `UnifiedExecutor`'s durability. Wrap each turn as a substrate run instead of a fire-and-
   forget stream. This is what makes crash-resume + HITL free, exactly like workflows.

2. **Add one ordered `prepareStep`-style hook.** Collocate memory / web-search / personal-
   memory injection into a single async closure `(messages, steps) => messages`, called at
   the step boundary, with a `shouldInject` gate. Mirror `drainSteeringQueue`'s "clear only
   after gate passes" so a rejected steer survives to the next boundary. Reuse for
   `mission_planner.py` where multi-step already exists.

3. **Emit an injection-receipt SSE chunk.** Extend `_sse_keepalive_merge`'s event stream with
   a `data-injected` chunk carrying message ids (like `PENDING_MESSAGE_INJECTED_TYPE`) so the
   frontend can reconcile. Kills the injected-vs-queued ambiguity class.

4. **Reuse `HITLPaused` for chat.** When an agentic chat turn hits an approval-worthy tool
   call, `raise HITLPaused` + write a `human_interrupts` row, return. Resolution re-enters the
   same `run_id` and continues from the step boundary. The machinery already exists for
   workflows — point chat at it.

---

## 6. Honest caveat (do not over-build)

The `chat.agent` re-entrant trick pays off **only** when turns are long-lived, resumable, and
interruptible (agentic tool loops, HITL). Today's `chat_service.py` is single-shot streaming —
for that, the in-process loop is the *correct* shape; do not force it into runs. Build lift #1
+ #2 **now, behind a feature flag**, so the loop is ready when Phase 2 lands — but do not
change single-shot behavior until then. The ordered injection closure (#2) is the one lift
worth doing unconditionally: it improves `mission_planner.py` today and is reusable for chat
later.

---

## 7. Recommendation

- Treat this as a **Phase-2 prerequisite**, not a parallel effort. The spawn-mission design in
  `REIMAGINE-CHAT-PROMPT-2026-07-05.md` already needs "one event stream for chat-with-tools
  and missions" — which is structurally the `prepareStep`/re-entrant model. Align the spawn-
  mission implementation with the substrate's existing durable run + `HITLPaused` path rather
  than inventing a second pause/resume mechanism for chat.
- Next concrete step: an ADR + spike that wraps a chat turn in a substrate `run_id` and adds
  the ordered injection closure behind `feature_flags.py` (which already exists), with tests
  that assert behavior is unchanged for single-shot chat and that a steered/injected event is
  emitted for multi-step.

---

## 8. Source references

**trigger.dev (analyzed 2026-07-08, commit `a6bd370e42de91311fe0291ae87704c640018164`):**
- `packages/trigger-sdk/src/v3/ai.ts` — `chatAgent` (`:5391`), `toStreamTextOptions`
  (`:3822`), combined `prepareStep` (`:3883`), `drainSteeringQueue` (`:3363`),
  outer-loop compaction (`:7405`).
- `packages/trigger-sdk/src/v3/chat-server.ts` — head-start / handover wiring.
- `packages/trigger-sdk/src/v3/sessions.ts` — durable Session row.

**Flowmanner (local):**
- `backend/app/services/chat_service.py` — `_sse_keepalive_merge` (`:240`),
  `stream_message_to_llm` (`:284`), `_stream_message_to_llm_body` (`:343`, injection `:448`
  `:471`).
- `backend/app/services/chat_context.py` — `_inject_memory_context` (`:86`).
- `backend/app/services/substrate/node_executor.py` — `_check_hitl_resume` (`:1341`),
  `raise HITLPaused` (`:1509`).
- `backend/app/orchestration/human_interrupt.py` — `HumanInterruptRecord`,
  `HITLManager.resolve_interrupt`.
- `backend/app/services/substrate/AGENTS.md` — 4 guarantees, event-log source of truth.
- `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md`,
  `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md`, `docs/HYBRID-PLATFORM-WORKSPACE.md` —
  roadmap Phase 2 (agent step streaming / spawn-mission).
