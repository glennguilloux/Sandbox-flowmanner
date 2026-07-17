# Backend Architect Ledger — Compose / "how do the pieces assemble"

**Lens:** COMPOSE — trace how Flowmanner's subsystems assemble into a coherent whole, and where the seams leak.
**Question I own:** How do the subsystems compose, and where do the seams leak?
**Method:** READ-ONLY. All claims cite `path:line` against the worktree at `/opt/flowmanner/.worktrees/t_b4d8c5b7`.
**Repo reality check:** The brief's "12.7M lines / 42,083 `.py` files" is stale/garbage. Real backend is **979 `.py` files / 255,584 lines** under `backend/app/` (measured via `find app -name '*.py'`). There is already a **v3** surface — the brief's "v1→v2 split" angle is partly obsolete.

---

## Top 5 Findings

### F1 — WebSocket DMs are broadcast to the entire workspace room; the server trusts the client to filter private messages (tenant-isolation leak)
**Severity: HIGH (security/privacy)**
**Type: fact**

`backend/app/websocket/mission_ws.py:362-373` — `workspace_dm` emits the direct message to the **whole workspace room**:
```python
await sio.emit("workspace:dm", {...}, room=f"workspace_{workspace_id}")
```
Every member of `workspace_{id}` receives every DM; the comment at line 361 says *"the frontend filters by recipient_id"*. So private 1:1 DMs are server-broadcast to all workspace members; confidentiality depends entirely on the client not rendering them. `workspace_typing` (line 393-401) has the same pattern — it broadcasts `recipient_id` to the whole room.

Additionally the membership gate on `workspace_dm` is explicitly **fail-open**: line 326 comment *"Light membership check (fail-open: allow message if DB is down)"* — if the `WorkspaceMember` lookup throws, the message is still persisted and broadcast (the `except` at 358 only `logger.debug`s and falls through to the emit). Compare `subscribe_mission` (line 183-199) and `workspace_subscribe` (line 272-296) which correctly **fail closed**.

**Anchor:** `backend/app/websocket/mission_ws.py:307-373`.

### F2 — The "unified execution substrate" (H5.1) exists, but the old 7-executor paths are STILL live and wired into v1 routers — two parallel execution engines
**Severity: HIGH (architecture/consistency)**
**Type: fact**

`app/api/v1/mission.py` is correctly CQRS-delegated (25 references to `get_mission_commands`/`get_mission_queries`). But other v1 routers still reach directly into models/old executors:
- `backend/app/api/v1/graph.py:323-345` executes `db.execute(select(GraphExecution)...)` and `select(WorkflowState)...` directly inside the router — i.e. the router reaches into the ORM, not a service.
- `backend/app/api/v1/substrate.py:235,282,331` repeatedly does `mission.plan.get("substrate_run_id")` and returns *"Mission has no substrate run (may not have been executed with substrate)"* — proving **not all missions run through the substrate**.

`app/services/substrate/AGENTS.md` (line ~"Current state") confirms: *"The old executors are still in the tree ... and are still wired up by their legacy routes, but new code MUST target the substrate,"* and lists `mission_executor.py` (1,387 LOC) as still present. The feature-flag cleanup (Phase C) was never completed: `FLOWMANNER_UNIFIED_EXECUTOR=all` was never flipped, so two execution engines serve traffic simultaneously. This is the central composition seam that leaks: a mission's state can be mutated by either path, with the substrate event-log guarantee (AGENTS.md guarantee #1: *"every state transition emits a substrate event"*) NOT satisfied for missions executed by the legacy path.

**Anchor:** `backend/app/api/v1/substrate.py:235`; `backend/app/api/v1/graph.py:323`; `app/services/substrate/AGENTS.md` ("Current state").

### F3 — A DEPRECATED, 0%-success strategy is still registered and dispatchable in the substrate registry
**Severity: MEDIUM (dead-code risk / silent failure)**
**Type: fact**

`backend/app/services/substrate/strategies/meta.py:35-36`:
```python
DEPRECATED = True  # 0% success with 27B model per strategy profiling 2026-07-04
EXPERIMENTAL = True
```
Yet `backend/app/services/substrate/strategies/__init__.py:36` still registers it in the `StrategyRegistry._ensure_imported` module list (`("meta", ".meta", "MetaStrategy")`), and `UnifiedExecutor` dispatches by `WorkflowType` — so a `WorkflowType.META` workflow will still be routed to a strategy the authors themselves marked 0%-success. No kill-switch guard rejects `META` at dispatch. The class comment (line 3) says it "Replaces: nexus/meta_loop_orchestrator.py" — but the nexus orchestrator still exists too (see F5).

**Anchor:** `app/services/substrate/strategies/meta.py:35`; `app/services/substrate/strategies/__init__.py:36`.

### F4 — The "self-healing / predictive auto-scaling" runtime cluster is SIMULATED, not real (phantom reliability subsystem)
**Severity: HIGH (blind-spot — see also "Biggest miss")**
**Type: fact**

`backend/app/services/runtime/predictive_scaler.py:27-43` — `get_predictions()` comment *"Simulate ML predictions"* and returns `random.uniform(40,80)` CPU/memory values with `random.uniform(0.7,0.95)` "confidence". Nothing reads real metrics.
`backend/app/services/runtime/self_healing.py:44-45` — `trigger_recovery()` comment *"Simulate recovery"*, does `await asyncio.sleep(0.5)`, and appends to an **in-memory** `self._recovery_history` list (line 19) that is lost on process restart. No real restart, no real action.
`backend/app/services/runtime/anomaly_detector.py:7` imports `random`; `health_monitor.py` exists but the cluster is only reachable via `RuntimeSDK` (`runtime_sdk.py:18` default `base_url="http://localhost:8000"`) — an out-of-process HTTP client, not wired into the app lifecycle. Grep shows `runtime/` is **never imported by any router or service** except its own singletons (the 17 matches are all internal `from ...runtime...` within the cluster itself). So the entire "self-healing / auto-scaling" reliability subsystem is decorative: it produces fake numbers and no operator is paged, no service is restarted.

**Anchor:** `app/services/runtime/predictive_scaler.py:27`; `app/services/runtime/self_healing.py:44`; `app/services/runtime/__init__` singletons only.

### F5 — Three overlapping "autonomous" orchestration concepts coexist with unclear ownership: nexus orchestrator, substrate, and the gutted improvement loop
**Severity: MEDIUM (cohesion / dead-weight)**
**Type: fact**

- `app/services/nexus/orchestrator.py:53` `NexusOrchestrator` — *"Central coordination service ... any subsystem to request capabilities from any other"* (506 LOC). Still live (imported by `distributed_executor.py:46-52`, `integration_bridge.py`, `mission_planner.py`, etc.).
- `app/services/substrate/` — the actual unified executor (H5.1, GA).
- `app/services/improvement/improvement_loop_v2.py:5-8` — the autonomous self-improvement loop was **gutted**: *"Phases 3–6 ... were never wired into production — 107 missions ran with zero improvement data recorded."* What remains (line 40-60) is a single `on_mission_complete` hook that fires a Celery `review_mission` task (an LLM memory writer). The "strategy evolution / hypothesis testing / knob tuning" the persona brief prizes is gone.

So Flowmanner has **nexus** (cross-system capability routing), **substrate** (execution), and a **hollow improvement loop** — three names for "the smart coordination layer," with the actual autonomy removed and the meta-orchestrator superseded by substrate's `MetaStrategy` (which is itself deprecated). The seams between these three are undefined; new code must guess which to call.

**Anchor:** `app/services/nexus/orchestrator.py:53`; `app/services/improvement/improvement_loop_v2.py:5-8`.

---

## Biggest single architectural blind spot (this lens)

**The reliability/observability story is largely theatrical, not operational.** The persona's core success metric is *"uptime exceeds 99.9% with proper monitoring"* and *"monitoring strategies that provide early warning."* But the one cluster built to deliver that — `app/services/runtime/` (self-healing, predictive scaler, anomaly detector, health monitor) — is **simulated** (`random`-based fake telemetry, `asyncio.sleep(0.5)` "recovery", in-memory-only history) and **not wired into the app at all** (no router/service imports it; only an `http://localhost:8000` `RuntimeSDK` client). Meanwhile the genuine execution substrate has strong guarantees (append-only event log, replay, circuit breakers) but they apply only to the substrate path, not the still-live legacy executors (F2). The net effect: Flowmanner advertises self-healing/auto-scaling architecture that, under real failure, does nothing — and the subsystem most likely to catch a degradation (the runtime cluster) is the one that is pretend. A 99.9% SLA claim is unsupported by the code as it stands.

---

## 3 Ranked Brainstorm Recommendations (Flowmanner-specific)

### R1 — Make the v1→substrate migration a completed cutover, not a permanent fork (kill the dual-executor path)
**Why now:** F2 shows two execution engines serve traffic; the substrate's durability guarantee is void for legacy-path missions, and incident forensics/replay cannot reconstruct those runs. Every day the fork lives, consistency drift compounds.
**Effort:** L (requires parity-test gate + flag flip + deletion of `mission_executor.py` + migration of the still-inline v1 routers: graph.py, substrate.py's "no substrate run" branches).
**Anchor:** `app/services/substrate/AGENTS.md` "Current state" + `app/api/v1/graph.py:323` + `app/api/v1/substrate.py:235`.

### R2 — Replace the simulated `runtime/` cluster with a real, thin health/recovery layer bound to actual signals (or delete it)
**Why now:** F4 — the subsystem is decorative and creates a false sense of reliability coverage that could lead an operator to skip real monitoring. Either wire it to Prometheus metrics + a real restart hook (Celery/K8s), or remove it so the OpenAPI/observability surface stops implying capabilities that don't exist.
**Effort:** M (delete-and-replace with a real `health_monitor` reading Prometheus + a `recovery_strategies` that actually calls the deploy/restart path; OR a clean deletion + doc note).
**Anchor:** `app/services/runtime/predictive_scaler.py:27` + `app/services/runtime/self_healing.py:44`.

### R3 — De-register the deprecated `MetaStrategy` and retire the `nexus` orchestrator in favor of substrate + capability registry
**Why now:** F3 + F5 — a 0%-success strategy is still dispatchable (silent failure risk), and three overlapping "coordination" concepts confuse every new feature. Collapsing to substrate (execution) + capability_registry (routing) + the surviving `review_mission` Celery hook (learning) removes dead weight and clarifies the composition contract.
**Effort:** M (guard `WorkflowType.META` at dispatch + delete `meta.py`; migrate `nexus/orchestrator.py` callers to `capability_registry`; keep `distributed_executor` if still needed).
**Anchor:** `app/services/substrate/strategies/__init__.py:36` + `app/services/nexus/orchestrator.py:53`.

---

## Confidence & cross-check request

**Confidence: HIGH** on F1 (read the emit + fail-open path verbatim), F2 (router reaches into ORM; substrate AGENTS.md states legacy paths are live), F4 (read the `random`/`sleep`/in-memory proof and confirmed zero external imports). **MEDIUM** on F3/F5 scope (deprecation intent is documented; I did not enumerate every `nexus` caller, but grep shows it is still imported by live services).

**Most important claim for the synthesizer to cross-check:** F4 — that `app/services/runtime/` (self-healing / predictive scaler / anomaly detector) is **simulated and unwired**, because if true it directly contradicts the platform's stated reliability posture and should reshape any "strength" claims in the final report. Verify by grepping for `from app.services.runtime` outside the cluster, and reading `predictive_scaler.py:27` / `self_healing.py:44`.

---

*Persona: engineering-backend-architect (COMPOSE lens). Read-only; no edits, no commits, no build.*
