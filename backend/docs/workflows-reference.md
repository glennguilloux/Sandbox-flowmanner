# Flowmanner Workflow Engine — Lifecycle & Resilience Reference

> Authoritative study of how workflows (Blueprint + Run) and missions (Mission/MissionTask)
> behave across the backend. Extracted from source, not docs. Source of truth is the
> **event-sourced substrate** (`substrate_events`, append-only, PostgreSQL UPDATE/DELETE blocked by trigger).
>
> Paths (homelab backend root = `/opt/flowmanner/backend`):
> - `app/models/substrate_models.py` — event types + in-memory `SubstrateRunState`
> - `app/models/mission_models.py` — `MissionStatus` / `MissionTaskStatus` enums + validated `_TRANSITIONS`
> - `app/models/blueprint_models.py` — `BlueprintStatus` / `RunStatus`
> - `app/models/mission_program_models.py` — `ProgramStatus` / `ProgramRunStatus`
> - `app/services/substrate/workflow_models.py` — unified `WorkflowNode`/`Workflow` (carries `max_retries`, `fallback_strategy`, `status`)
> - `app/services/substrate/executor.py` — `UnifiedExecutor` (run lifecycle, lease, abort, HITL pause, circuit breaker hookup)
> - `app/services/substrate/node_executor.py` — per-node retry loop, dispatch, sandbox snapshots
> - `app/services/swarm/escalation_chain.py` — multi-level agent escalation + dead-letter
> - `app/services/substrate/circuit_breaker.py` — per-workspace+provider circuit breaker (CLOSED/OPEN/HALF_OPEN)
> - `app/services/substrate/lease_reclaimer.py` — stale-lease crash recovery
> - `app/services/substrate/replay_engine.py` + `resume_validation.py` — deterministic replay / resume
> - `app/services/webhook_handler/retry.py` — exponential-jitter webhook retry
> - `app/tasks/mission_execution.py` — Celery task retry config
> - `app/models/capability_models.py` — `Budget.is_exhausted()` (timeout/wall-clock/iteration enforcement)

---

## 1. Lifecycle States

### 1a. Mission (legacy/high-level orchestration) — `MissionStatus`
`draft → pending → planning → planned → queued → executing → running → completed → approved`
Terminal: **completed→approved** (approved is terminal), **failed**, **aborted** (= deprecated `cancelled`).
`paused` is a non-terminal hold that can return to `running` or `aborted`.
Abort reachable from: `draft, pending, planning, planned, executing, queued, running, paused` (i.e. almost everywhere).

### 1b. MissionTask — `MissionTaskStatus`
`pending → running → completed | failed`; `failed → pending` is allowed (retry re-entry).
`completed` is terminal.

### 1c. Blueprint (reusable definition) — `BlueprintStatus`
`draft → published → deprecated` (linear, deprecated terminal).

### 1d. Run (one execution instance) — `RunStatus`
`pending → queued → executing → paused | completed | failed | aborted`.

### 1e. Program / ProgramRun — `ProgramStatus` / `ProgramRunStatus`
Program: `active → paused | archived`. Run: `running → completed | failed | aborted` (all terminal).

### 1f. Substrate event-stream states (the real runtime truth)
Run: `mission.started → executing → completed | failed | aborted | paused → resumed`.
Node: `task.started → task.completed | task.failed | task.retrying | task.skipped`.
Plus rich events: `circuit_breaker.*`, `run.lease.*`, `abort_requested`, `human_interrupt.*`, `substrate.budget_exhausted`, `substrate.error`, `self_correction.*`, `handoff.*`, `sandbox.*`.
`SubstrateRunState` is rebuilt from the event log, never persisted.

### 1g. Circuit breaker — `CircuitBreakerState`
`closed → open → half_open → closed | open`.

### 1h. Swarm escalation — `EscalationRecord.status`
`retrying → escalated → dead_letter`; also `active`. `dead_letter` is terminal+resolved.

---

## 2. Transitions (validated)

Mission/MissionTask/Program/ProgramRun enforce a `_TRANSITIONS` dict and expose `can_transition_to()`.
Key gaps / observations:
- `completed → approved` is the ONLY post-completion transition; there is **no `completed → failed` rollback** (immutability by design).
- `failed` and `aborted` are hard terminals — **no automatic re-run from failure**; re-run requires a new Run.
- `MissionTask.failed → pending` is the only retry re-entry; individual nodes can re-enter, the whole mission cannot.
- HITL pause: `running → paused` (emits `mission.paused`, releases worker lease), `paused → executing` on `mission.resumed`. **`pause()` currently delegates to `abort()`** — per-source comments, per-strategy pause-point handling is a future enhancement, so a true mid-run "freeze but keep lease" pause is NOT implemented.

---

## 3. Retries

### 3a. Per-node retry (`node_executor.py`)
`max_retries` (default **3**) → loop `range(max_retries + 1)`. On failure before exhaustion: emit `task.retrying`, increment `retry_count`, `continue`. Checks `is_aborted(run_id)` **between attempts** and bails out returning `{success:False, error:"Aborted"}` without a `task.failed` event. On exhaustion: emit `task.failed` with `retries_exhausted:true`.
Retry is **immediate / synchronous** within the loop — no backoff between node retries.

### 3b. Swarm escalation retries (`escalation_chain.py`)
4 levels: L0 retry same agent, L1 escalate specialist, L2 escalate human, L3 dead-letter.
Policy-driven (`total_max_retries`: default 5, aggressive 3, conservative 8, never_escalate 3).
`max_retries_same/specialist/human` consumed per level, then escalate.

### 3c. Webhook retries (`webhook_handler/retry.py`)
`RetryConfig(max_retries=3, initial_delay=60s, max_delay=3600s, strategy=exponential_jitter, backoff_factor=2.0, jitter=0.1)`.
`should_retry()` only retries on a **whitelist of retryable error substrings** (timeout, connection_error, rate_limit, service_unavailable, internal_error) — non-matching errors are NOT retried.

### 3d. Celery mission task (`tasks/mission_execution.py`)
`max_retries=3`, `default_retry_delay=30s` (exponential: `countdown = 30 * 2**retries`), `acks_late=True`.

---

## 4. Failure Recovery

- **Event sourcing = the recovery primitive.** Every transition is an append-only event. `ReplayEngine.replay()` rebuilds `SubstrateRunState` from the log after a crash; `validate_resume_state()` gate runs BEFORE rebuild and only resumes into `completed/failed/aborted` states if already terminal, else finds the resume point.
- **Worker-lease / crash recovery.** Each run holds a lease with heartbeat + TTL. `lease_reclaimer.py` scans expired leases (worker OOM/segfault/`kill -9`), claims+releases them and emits `run.lease.released reason="reclaimed"`. On restart the executor re-arms any durable `abort_requested` event and replays.
- **Idempotent skip.** If `node.completed` event exists, the node is skipped and cached result returned (`node_skipped_idempotent`).
- **Budget exhaustion** (`Budget.is_exhausted()`): wall-clock (`max_wall_time_seconds`, default 300), iteration count (`max_iterations`, default 100), cost. Raises `BudgetExhausted` which propagates to finalize the run as `failed`/`aborted` (reason `budget_exceeded`).
- **Provider fallback** (`provider_fallback.py`): when a provider's circuit breaker is OPEN, walk the fallback chain (workspace-specific > global; by priority). Emits `provider.fallback_invoked`; `degraded=True` when served != requested.
- **Self-correction** events (`self_correction.attempted/completed/aborted`) for adaptive recovery; **handoff** (`handoff.initiated/accepted/completed/failed/lease_lost`) for multi-agent recovery.

---

## 5. Timeout Behavior

- **Wall-clock budget:** `max_wall_time_seconds` enforced by `Budget` (checked at node pre-execution; `BudgetExhausted` raised). Default 300s for solo, 86400s (24h) for the "unlimited" budget profile.
- **Per-call timeouts:** code-execution node uses `asyncio.wait_for(..., timeout=60)` (60s sandbox python). Lease heartbeat uses `asyncio.wait_for(..., timeout=5.0)`.
- **HITL expiry:** inbox items have `expires_at`; `hitl_expiry` Celery task calls `expire_and_act()` — expired items resolve as `status="expired"` (treated as resolved so the node does not hang forever).
- **Circuit breaker cooldown:** `cooldown_seconds` per provider; while OPEN, requests denied with `retry_after`.
- **Webhook retry** capped at `max_delay_seconds=3600`.

---

## 6. Compensation

- **There is NO saga/compensation framework.** No `compensat*` symbol exists anywhere in the backend.
- The closest thing:
  - **Sandbox `snapshot_before`** (node config, default `False`): before a sandbox task runs, a container snapshot is created (`sandbox.snapshot_created`). This is a **rollback *point*** (for re-execution / manual restore), not an automatic compensating action. No code path auto-restores it on failure.
  - **`UnifiedChainExecutor`** docstring claims "Error handling with rollback" but the implementation only sets `status="failed"` and re-raises — **no actual rollback logic** is present.
  - **Mission `abort`** is the de-facto "stop and leave partially-done" mechanism; it does not undo completed nodes.
- External side-effects of completed nodes are **not compensated** on abort/failure.

---

## 7. Dead-Letter Handling

- **Location:** swarm escalation only (`app/services/swarm/escalation_chain.py`). A task that exhausts `total_max_retries` across L0–L2 is moved to `status="dead_letter"`, `resolved=True`, and an `AgentMessage` with `recipient_id="dead-letter"` / `recipient_name="Dead Letter Queue"` is written.
- **API:** `GET /api/v1/swarm/dead-letters` (`list_dead_letters(limit)`) lists records for manual review.
- **Scope limitation:** dead-lettering is specific to the swarm escalation chain. The substrate node executor does **NOT** dead-letter — it just records `task.failed` and returns; the parent run becomes `failed`. Webhook exhaustion drops the retry silently (no DLQ table).
- Dead-letter records are **resolved=true** (terminal, for humans to process out-of-band).

---

## 8. Rollback Strategies

- **Event-sourced replay is the rollback model for *state***: replaying the append-only log to any sequence rebuilds a prior consistent state. `replay_engine.verify()` checks determinism (replay yields identical state); `resume_validation` identifies safe resume points.
- **No transactional rollback of external actions.** DB writes for completed nodes are committed; there is no undo.
- **Sandbox snapshot** = the only explicit rollback *artifact*, opt-in via `snapshot_before`.
- **`abort`** finalizes the run (`mission.aborted`) but completed nodes stay completed.
- **Idempotency keys** (`SubstrateEvent.idempotency_key`, indexed) prevent duplicate event emission on redelivery.

---

## 9. Cross-Cutting Observations / Gaps (for future-workflow review)

1. **No compensation/saga layer** — external effects of completed nodes are never undone. Largest resilience gap.
2. **`pause()` is really `abort()`** — no true lease-preserving freeze.
3. **`failed`/`aborted` are terminal with no re-run transition** — must spawn a new Run to retry a whole mission.
4. **Node retries are synchronous with no backoff** (unlike webhooks which DO have exponential-jitter). Inconsistent retry semantics across subsystems.
5. **Dead-letter is swarm-only** — substrate node failures, webhook exhaustion, and budget-exhausted runs have no DLQ.
6. **`workspace_id` propagation is fail-open** — if an adapter leaves it `None`, circuit-breaker/constraint enforcement is silently skipped for that run (see `workflow_models.py` warning comment).
7. **Two parallel circuit breakers** — per-mission budget guard (`circuit_breaker_service`) AND per-workspace+provider (`substrate/circuit_breaker`), different tables. Easy to mis-reason about.
8. **`UnifiedChainExecutor` "rollback" is aspirational** — only marks failed.
9. **No explicit transition-versioning of RunStatus vs MissionStatus** — legacy `Mission` states and new `Run` states coexist; adapters must keep them in sync.
10. **HITL expiry is a background Celery task** — if the worker is down, pending HITL nodes can stall until it recovers.
