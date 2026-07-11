# Flowmanner — Intent Execution Architecture

> Source of truth: the Hermes skill `flowmanner-intent-execution-architecture`.
> This document is the repo-tracked copy so the constitution lives with the code.

Flowmanner is an **Intent Execution Platform**, not an automation platform.

## The 10 Principles

1. **Intent before implementation** — every feature starts from an explicit,
   validated intent schema (Pydantic `Workflow` via `substrate/adapters.py`),
   never ad-hoc kwargs.
2. **Execution must be observable** — every state change appends a
   `SubstrateEvent` (`EventLog.append`), reconstructable by `ReplayEngine`;
   structlog + OpenTelemetry + WebSocket progress.
3. **Execution must recover** — drive execution through
   `UnifiedExecutor.execute(run_id=…)`; crash recovery + "terminal → no
   re-execution" are free; idempotency keys dedup retries; lease + abort
   (`asyncio.Event`) for liveness.
4. **Failures are first-class** — `MissionError` hierarchy
   (`Retryable`/`Permanent`/`TransitionConflict`) + `classify_error` +
   `CircuitBreakerState` + `ReplayAssertionEngine` + governance/poison-scan.
5. **State is explicit** — `(str, Enum)` enums; `substrate_events` is the
   source of truth (append-only, trigger-protected); `ReplayEngine`
   reconstructs; illegal transitions raise HTTP 409.
6. **Measurable "Done"** — `ReplayAssertionEngine` asserts tool sequence,
   cost ceiling, latency, task completion, circuit-breaker-trip counts;
   `BaselineExtractor` derives expected behaviors from a known-good run.
7. **Human intervention without breaking automation** — `HITLPaused` +
   `hitl_service` + `InboxItemStatus` + `UnifiedExecutor.abort()` +
   pipeline pause/resume; intervention mutates explicit state + appends an
   event, never corrupts the run.
8. **Adapt instead of restarting** — resume to last durable state via replay
   (DAG resumes from the failed layer); never full re-execution from zero.
9. **Never hide failures** — structlog + OTEL (no swallowed exceptions);
   `_schedule_fire_and_forget` logs and never re-raises; audit is no-fail;
   assertion failures are surfaced.
10. **Deterministic over heuristic** — Pydantic type-checking, explicit
    `workflow_models`, deterministic Kahn topo-sort, `{{node_id.output.field}}`
    interpolation, deterministic `classify_error`; avoid LLM-judged branching in
    the execution path. All LLM calls via `UnifiedExecutor.call_llm()` →
    `BudgetEnforcer.call()`; all tools via `CapabilityEngine` + token.

## Architectural procedure (before coding)

1. Capture intent as an explicit Pydantic schema / `Workflow` model.
2. Define state explicitly as `(str, Enum)`; declare the source of truth.
3. Make execution observable: append `SubstrateEvent` per state change; emit WS
   progress.
4. Make execution recoverable: drive via `UnifiedExecutor.execute(run_id=…)`;
   use idempotency keys; pause/resume not restart.
5. Make failure first-class: subclass `MissionError`; wrap risky external calls
   in circuit breaker; never swallow.
6. Define "Done" measurably via `ReplayAssertionEngine` + a baseline.
7. Allow human intervention (pause/resume/abort/approve) without destroying the
   run.
8. Prefer deterministic execution; route LLM/tool calls through the substrate.
9. Write per `flowmanner-backend-patterns` (CQRS, DI, transaction ownership).
10. Verify: `cd /opt/flowmanner/backend && make lint && make test`.

## Design-review checklist (gate before coding)

A feature is architecturally complete only if all hold:

- [ ] Intent is an explicit Pydantic schema / `Workflow` model.
- [ ] State is a `(str, Enum)`; source of truth is `substrate_events` or a
      documented exception; illegal transitions raise 409.
- [ ] Every state change appends a `SubstrateEvent` and is `ReplayEngine`-
      reconstructable.
- [ ] Execution is driven by `UnifiedExecutor.execute(run_id=…)` (crash
      recovery + no re-run on terminal).
- [ ] Retry/restart uses replay-to-last-durable-state, not full re-run.
- [ ] All errors subclass `MissionError` and are `classify_error`-mapped.
- [ ] External calls circuit-breaker wrapped where shared/risky.
- [ ] "Done" is encoded as `ReplayAssertionEngine` assertions + a baseline.
- [ ] Human pause/resume/abort/approve paths exist without destroying the run.
- [ ] No swallowed failures; fire-and-forget logs; audit is no-fail.
- [ ] Execution path is deterministic; LLM/tool calls route through the
      substrate.
- [ ] Conventions verified: `make lint && make test` green.

## Substrate guarantees (always on for `UnifiedExecutor`)

1. **Durable** — every transition emits a `SubstrateEvent`.
2. **Type-checked** — Pydantic input/output.
3. **Capability-bounded** — `CapabilityToken` per tool call.
4. **Bounded** — `BudgetEnforcer` wraps every LLM call.

New code MUST target the substrate (`FLOWMANNER_UNIFIED_EXECUTOR=all` is GA).
The old 7 executors are deprecated; do not extend them.

## Grounded enforcement map

See the skill's `references/principle_enforcement_map.md` for file/line owners
(`substrate/executor.py`, `event_log.py`, `mission_errors.py`,
`circuit_breaker.py`, `assertion_engine.py`, `baseline_extractor.py`,
`hitl_pause.py`, `workflow_models.py`, `adapters.py`, `replay_engine.py`).
