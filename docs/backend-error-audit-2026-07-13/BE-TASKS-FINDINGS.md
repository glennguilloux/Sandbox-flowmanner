# Backend Audit — Celery Tasks / Workers / Orchestration

Branch under audit: `agent/2026-07-11-intent-execution-architecture` (worktree `t_7afaeeda`, HEAD = `f6fc3637`).
Scope audited: `backend/app/tasks/*`, `backend/app/workers/*`, `backend/app/orchestration/*`.

Persona: Code Reviewer. Hunting for real defects (crashes, silent work drops, deadlocks, retry
forever, state corruption), not style.

Legend: 🔴 blocker · 🟡 suggestion · 💬 nit.

---

## 🔴 1. swarm_tasks.py imports non-existent models — ALL swarm tasks crash on import/despatch
`backend/app/tasks/swarm_tasks.py:41,122,337,400,464`

```python
from app.models.swarm_models import SwarmAgent, SwarmTask
...
from app.models.swarm_models import SwarmConsensusRound
...
from app.models.swarm_models import SwarmAgent
...
from app.models.swarm_models import SwarmProfile
```

`app/models/swarm_models.py` exists but only defines `OrchestratorExecution` and
`OrchestratorTask` (confirmed by grep). The actual `SwarmAgent`, `SwarmTask`,
`SwarmConsensusRound`, `SwarmProfile` classes live in `app/models/swarm.py`.
`app/models/__init__.py:269` only re-exports `OrchestratorExecution, OrchestratorTask` from
`swarm_models`.

WHY: Every one of the five swarm Celery tasks (`swarm.execute_task`,
`swarm.consensus_timeout`, `swarm.agent_heartbeat_check`, `swarm.cost_budget_check`) does
`from app.models.swarm_models import Swarm…` inside its body the first time it runs. Because the
name is undefined in that module, the import raises `ImportError` → the task fails (and, since four
of the five swallow exceptions, they report `{"success": False}` / a generic error instead of the
real cause). `swarm.execute_task` is `max_retries=3` and will retry 3× then give up. Net effect:
the entire swarm subsystem is non-functional; any queued swarm work is silently dropped or
permanently failed.

FIX: point the imports at the real module:
```python
from app.models.swarm import SwarmAgent, SwarmTask, SwarmConsensusRound, SwarmProfile
```
(apply at each of the 5 call sites, or hoist to module top.)

---

## 🔴 2. swarm_tasks.py opened an ASYNC session factory and runs SYNC ORM — AttributeError
`backend/app/tasks/swarm_tasks.py:40,45,49,58,124,126,339,402,467`

```python
from app.database import SessionLocal
...
db = SessionLocal()          # SessionLocal == AsyncSessionLocal (app/database.py:61)
task = db.query(SwarmTask)…  # .query() is the SYNC SQLAlchemy 1.x API
```

`app/database.py:61` defines `SessionLocal = AsyncSessionLocal`, and `AsyncSessionLocal` is an
`async_sessionmaker` yielding `AsyncSession`. An `AsyncSession` has no `.query()` method
(`AttributeError: 'AsyncSession' object has no attribute 'query'`), and `db.commit()` /
`db.close()` are coroutine methods that must be awaited. So even after fixing finding #1, every
swarm task dies at `db.query(...)` with `AttributeError`.

WHY: the swarm tasks were written for the synchronous `SessionLocal` that no longer exists; the
alias was repointed to the async factory. All swarm DB access is wrong for the async session.
Severity stays 🔴 (combined with #1 it makes swarm fully broken; on its own it is an
AttributeError on every swarm task).

FIX: either (a) add a real sync engine + `SyncSessionLocal` to `app/database.py` and import that,
or (b) rewrite every swarm task to `async def` + `AsyncSessionLocal()` + `await db.execute(...)`
+ `await db.commit()` + `await db.close()`. Option (a) mirrors what the disabled
`webhook_tasks.py` revival note (celery_app.py:151) already calls for.

---

## 🔴 3. execute_swarm_task returns failure dict after exhausting retries (false "handled")
`backend/app/tasks/swarm_tasks.py:142-147`

```python
if self.request.retries < 3:
    ...
    raise self.retry(exc=e, countdown=retry_in)
return {"success": False, "task_id": task_id, "error": str(e)}
```

WHY: once `self.request.retries` reaches 3, the task returns a dict instead of re-raising. Celery
then treats the task as SUCCESSFULLY completed (return value is the result). The job has failed 3
times but the broker acks it as done — the swarm task is permanently dropped with no alarm. This
is a "false green": the failure path looks like a normal completion. Combined with #1/#2 the task
will hit this on the first dispatch.

FIX: after retries are exhausted, raise the exception (or a custom `self.retry` with
`throw=True`) so Celery marks the task FAILED:
```python
raise  # or: raise self.retry(exc=e, countdown=retry_in)  # will raise MaxRetriesExceeded
```
(Note: `max_retries=3` on the decorator + `if self.request.retries < 3` is also off-by-one —
the 4th attempt is the one that should exhaust; with this guard the 3rd retry returns success.
Reconcile the boundary against `max_retries`.)

---

## 🔴 4. mission_execution.py: double-work / duplicate execution on retry
`backend/app/tasks/mission_execution.py:55,74-112,134,169-198`

```python
def run(self, mission_id, user_id, run_id=None, selected_plan_id=None):
    loop = asyncio.get_running_loop()
except RuntimeError:
    return asyncio.run(self._execute_async(...))
else:
    new_loop = asyncio.new_event_loop()
    ...
    return new_loop.run_until_complete(...)
...
mission.status = MissionStatus.RUNNING
await session.commit()
...
strategy_result = await get_unified_executor().execute(session, workflow, run_id=run_id)
...
except Exception as exc:
    await session.rollback()
    ... mark FAILED ...
    raise self.retry(exc=exc, countdown=...)
```

WHY: the idempotency guard only checks `mission.status != MissionStatus.QUEUED` and skips if not
queued. But on a RETRY (after the executor has already done real, possibly non-idempotent, work),
the status is `RUNNING`, not `QUEUED`, so the guard does NOT skip — `_execute_async` runs the
whole mission again. The `with_for_update()` lock is released at the end of the first attempt's
`async with` block (the session is closed), so a concurrent retry is not blocked. If the
`UnifiedExecutor.execute` raises partway through (after partial writes/tool calls), the task
retries and re-runs the entire mission from scratch — duplicating side effects (emails sent,
records created, external API calls made). Retries here re-execute destructive work, the exact
anti-pattern the task description warns about.

Additionally: `run()` calls `asyncio.run()` only when there is no running loop, but a Celery
prefork worker has no running loop, so `asyncio.run` is used — fine. However the `else` branch
creates a new loop; if `run()` is ever invoked from a context that already has a loop (e.g. the
API `dispatch_mission_execution` runs in uvicorn's loop and calls `current_app.send_task`, which
is fine — it does NOT call `.run()`), this is moot, but worth noting the `_execute_async` body is
not re-entrant-safe across retries.

FIX: make execution idempotent on resume. Persist a durable "execution start" marker (e.g. set
status to RUNNING only if a claim token/`run_id` matches, or record `executed_run_ids` on the
mission) and have the retry path resume/crash-recover rather than re-run the whole workflow. At
minimum, gate re-execution on a unique execution lock keyed by `run_id` and skip if that `run_id`
already started.

---

## 🔴 5. mission_execution.py: Engine never disposed; cross-loop asyncpg crash on every retry
`backend/app/tasks/mission_execution.py:74-72` (contrast hitl_expiry.py:52, hitl_resume.py:65, integration_health_tasks.py:62, expire_paused_missions.py:141)

```python
async def _execute_async(self, mission_id, user_id, run_id=None, selected_plan_id=None):
    async with AsyncSessionLocal() as session:
        ...
        strategy_result = await get_unified_executor().execute(session, workflow, run_id=run_id)
```

WHY: every other async task in this codebase that opens a DB session inside a Celery worker calls
`await engine.dispose()` at the start of its coroutine to drop fork-inherited asyncpg connections
bound to the parent event loop (documented extensively in hitl_expiry.py, hitl_resume.py,
integration_health_tasks.py, expire_paused_missions.py). `ExecuteMissionTask._execute_async`
does NOT dispose the engine. On Celery prefork workers the async engine's pooled connections are
bound to the parent's event loop; when this task creates a fresh loop via
`asyncio.run`/`new_event_loop` and then awaits a DB call, asyncpg raises
`RuntimeError: Task <Task> got Future attached to a different loop` on the first
`await session.execute(...)` or inside `UnifiedExecutor.execute`. Because this happens inside the
`try`, the mission is rolled back and marked FAILED — so EVERY mission execution fails on prefork
workers, and the task retries 3× (each retrying the same crash, per finding #4 partially),
wasting the mission and consuming retries.

FIX: mirror the established pattern — at the top of `_execute_async`:
```python
from app.database import engine
await engine.dispose()
```
before `async with AsyncSessionLocal() as session:`.

---

## 🔴 6. decay_memory.py: `run_decay_job` reads `settings.MEMORY_DECAY_*` with no fallback — crash on missing setting
`backend/app/tasks/decay_memory.py:293-300`

```python
ttl_days = ttl_days if ttl_days is not None else settings.MEMORY_DECAY_TTL_DAYS
decay_rate = decay_rate if decay_rate is not None else settings.MEMORY_DECAY_RATE_PER_DAY
min_importance = min_importance if min_importance is not None else settings.MEMORY_DECAY_MIN_IMPORTANCE
immortal_sensitivity = immortal_sensitivity if immortal_sensitivity is not None else settings.MEMORY_DECAY_IMMORTAL_SENSITIVITY
sensitive_claim_type = sensitive_claim_type if sensitive_claim_type is not None else settings.MEMORY_DECAY_SENSITIVE_CLAIM_TYPE
```

The docstring/comment claims "Defaults mirror app.config so a unit test can call the pure helpers
without needing the full Settings object." But `run_decay_job` always reads `settings.MEMORY_DECAY_*`
when the arg is `None`. (The settings DO currently exist in `app/config.py:329-333`, so today it
works — but) it is 🟡-latent: if any one of those five settings is ever removed/renamed, the
daily beat task `memory.decay_entries` raises `AttributeError`, which is caught and
`self.retry`s (max_retries=1) then fails permanently — meaning the daily decay job silently stops
archiving/decaying memory with no alert (only a log line). The module advertises testability
without Settings but the production path depends on Settings.

FIX: provide module-level defaults (the `DEFAULT_*` constants already defined at lines 65-69) as
the fallback instead of hard-reading `settings.*`:
```python
ttl_days = ttl_days if ttl_days is not None else getattr(settings, "MEMORY_DECAY_TTL_DAYS", DEFAULT_TTL_DAYS)
```
(or read once with `getattr` + constant fallback for all five).

---

## 🟡 7. swarm_tasks.py: naive-UTC `created_at` mixed with timezone-aware `datetime.now(UTC)` → TypeError
`backend/app/tasks/swarm_tasks.py:349,415`

```python
created_at = consensus.created_at          # mapped_column(default=datetime.utcnow)  -> naive UTC
...
if created_at and (datetime.now(UTC) - created_at) > timedelta(seconds=60):
```
and
```python
last_active = agent.last_active_at         # mapped_column(nullable=True), no default
...
if last_active and (datetime.now(UTC) - last_active) > heartbeat_threshold:
```

WHY: `swarm.py:106` defines `created_at` with `default=datetime.utcnow` (naive datetime).
`datetime.now(UTC)` is timezone-aware. Subtracting an aware from a naive datetime raises
`TypeError: can't subtract offset-naive and offset-aware datetimes`. So `swarm.consensus_timeout`
and `swarm.agent_heartbeat_check` will crash the first time they hit a row whose `created_at`
(any consensus round) or `last_active_at` (any active agent) is set by the naive default. Both
tasks swallow the exception and return `{"success": False}` — the timeouts/heartbeats never fire,
so stalled consensus rounds and dead agents are never resolved and never alarm. (If the app sets
these columns via a timezone-aware value elsewhere, only those rows are safe; the naive default
still applies to rows created without an explicit value.)

FIX: normalize to aware before subtraction:
```python
from datetime import timezone
def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt
if created_at and (datetime.now(UTC) - _aware(created_at)) > timedelta(seconds=60):
```
Better: fix the column defaults in `swarm.py` to `datetime.now(UTC)` / `lambda: datetime.now(UTC)`.

---

## 🟡 8. swarm_tasks.py: `agent` may be None → `agent.assigned_model` AttributeError
`backend/app/tasks/swarm_tasks.py:58-66`

```python
agent = db.query(SwarmAgent).filter(SwarmAgent.agent_instance_id == agent_id).first()
...
model_name = agent.assigned_model if agent else "default"
```

WHY: this is the one place that correctly guards `agent is None`. But it is the ONLY guard — and it
is inside a try/except that, on failure, re-enters a second `db.query` block (line 126) which does
NOT re-fetch `agent` and would `mark_failed` with `task_id`. The asymmetry is fragile but not a
crash on this line. The real latent issue: if the first `db.query` succeeds but `agent` is None,
`model_name = "default"` is used, then `coordinator.track_swarm_cost(..., model_name="default", ...)`
and `model_router.track_model_performance(agent_id=agent_id, model_name="default", ...)` are
called — but `get_agent_model_router_service()` may raise or record under the wrong model.
Minor data-quality bug, not a crash. 🟡.

FIX: if `agent is None`, fail the task explicitly rather than silently using `"default"`:
```python
if agent is None:
    raise ValueError(f"Agent {agent_id} not found for task {task_id}")
```

---

## 🟡 9. n8n_callback.py: `wait_for_n8n_callback` busy-polls Redis with `time.sleep` for up to 5 min inside a Celery worker
`backend/app/tasks/n8n_callback.py:56-104`

```python
while True:
    elapsed = (datetime.now(UTC) - start_time).total_seconds()
    if elapsed >= timeout:
        return {"status": "timeout", ...}
    callback_data = redis_client.get(callback_key)
    if callback_data:
        ...
    time.sleep(poll_interval)   # 2s, up to timeout (default 300s)
```

WHY: this task blocks a Celery worker process for up to `CALLBACK_TIMEOUT` (300s default, but
callers may pass larger) doing a synchronous `time.sleep` poll loop. With
`worker_prefetch_multiplier=1` (workers/celery_app.py:19) a single worker slot is occupied for the
whole wait, so a burst of n8n callbacks serializes and starves other tasks. Worse, it holds the
worker's process but not a DB transaction, so it is just wasted capacity; and if the worker is
restarted mid-wait (deploy, OOM), the wait is lost — the callback arrives, is stored in Redis with
TTL, but no task consumes it; a later `get_n8n_execution_status` can still find it, but the
original `wait_for_n8n_callback` task silently vanished (its result is "timeout"-style lost).
This is a fragile long-blocking task, not a crash. 🟡.

FIX: use a proper result backend / Redis pub-sub or a `sleep`-based approach with a hard
`time_limit` < `timeout`, or implement the wait as a chained task that retries after a short
`countdown` instead of one long-blocking task.

---

## 🟡 10. n8n_callback.py: `get_redis_client()` creates a NEW connection per call; `cleanup_stale_callbacks` uses `keys()`
`backend/app/tasks/n8n_callback.py:27-29, 217`

```python
def get_redis_client():
    return redis.from_url(REDIS_URL, decode_responses=True)
...
keys = redis_client.keys(f"{CALLBACK_PREFIX}*")   # scans whole keyspace
```

WHY: every task invocation builds a brand-new Redis client (no connection pooling reuse), which
leaks sockets over time under load. `cleanup_stale_callbacks` calls `redis.keys("*")` which, on a
production Redis with many keys, blocks the server (O(N) full scan) and is explicitly warned
against in Redis docs. If this periodic task is scheduled/run it can stall Redis. 🟡 (latent
production issue, not a crash in normal small deployments).

FIX: create one module-level pooled client; replace `keys()` with `scan_iter()`.

---

## 🟡 11. hitl_expiry.py: `acks_late=False` + `self.retry` inside try — possible double-processing / non-idempotent ack
`backend/app/tasks/hitl_expiry.py:69-92`

```python
@celery_app.task(name="hitl.expire_items", bind=True, max_retries=2, acks_late=False, ...)
def expire_hitl_items(self):
    try:
        result = _run_async(_expire_async())
        ...
        return result
    except Exception as exc:
        ...
        raise self.retry(exc=exc, countdown=countdown)
```

WHY: `acks_late=False` means the task is acked as soon as the worker receives it, BEFORE
`_expire_async()` runs. If the worker dies (kill -9, deploy, OOM) between ack and completion, the
task is GONE — the stale HITL items are never expired for that 5-min beat interval (silent drop,
self-heals next beat, so minor). More importantly, `self.retry` re-queues a NEW task message;
with `acks_late=False` the original was already acked, so a crash during processing loses work and
the retry also re-runs `expire_and_act()`. The docstring claims idempotency via
`SELECT FOR UPDATE SKIP LOCKED`, but `acks_late=False` means a crash never re-runs the task at
all (lost), whereas under `acks_late=True` it would. The surrounding tasks (hitl_resume,
mission.execute_async, decay_memory_entries) all use `acks_late=True`; this one is the outlier.
🟡 — inconsistent and a real (if rare) silent-drop vector on worker loss.

FIX: set `acks_late=True` to match the sibling tasks and the documented idempotency guarantee.

---

## 🟡 12. expire_paused_missions.py: same `acks_late=False` inconsistency
`backend/app/tasks/expire_paused_missions.py:179-209`

Identical concern to #11: `acks_late=False` while the docstring (lines 1-23) explicitly claims
"FOR UPDATE SKIP LOCKED for race safety" and "idempotent". With `acks_late=False`, a worker loss
between receive and commit silently drops the auto-fail for that beat tick. 🟡.

FIX: `acks_late=True`.

---

## 🟡 13. eval_run.py: retry guard `if self.request.retries < self.max_retries` skips the final retry
`backend/app/tasks/eval_run.py:60-61, 132-133`

```python
@celery_app.task(name="evaluation.run_suite", bind=True, max_retries=2, ...)
...
if self.request.retries < self.max_retries:   # 0<2,1<2 retry; 2<2 false -> no 3rd retry
    raise self.retry(exc=exc)
return {"status": "failed", "error": str(exc), ...}
```

WHY: with `max_retries=2`, `self.request.retries` goes 0,1,2. At retries==2 the guard is false, so
the task returns a failure dict instead of retrying a 3rd time — effectively only 2 attempts
(total) instead of the intended 3, AND the final failure returns a dict (Celery marks it
SUCCESS). Same pattern in `run_candidate_comparison` (max_retries=1): at retries==1 the guard is
false, so it never retries at all — `max_retries=1` is a no-op. This is a "false green" + weaker
retry than intended. 🟡 (the simpler correct idiom is `raise self.retry(...)` with no guard and
let Celery honor `max_retries`).

FIX: drop the guard and rely on Celery:
```python
except Exception as exc:
    logger.exception(...)
    raise self.retry(exc=exc)
```

---

## 🟡 14. training_tasks.py: `train_adapter_task` may run a 4-hour blocking subprocess inside the worker
`backend/app/tasks/training_tasks.py:223-274`

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=4*60*60)
if result.returncode != 0:
    raise Exception(f"Training failed: {result.stderr}")
metrics = json.loads(result.stdout)
```

WHY: when `/app/train_lora.py` exists, this task blocks the Celery worker for up to 4 hours with a
synchronous `subprocess.run`. With `worker_prefetch_multiplier=1` that is one worker slot fully
occupied for 4h, plus no `time_limit` is set on the task, so a hung training script holds the
worker indefinitely past the 4h subprocess timeout only if subprocess itself hangs on I/O (the
`timeout=` kills it). Also `metrics = json.loads(result.stdout)` will raise `json.JSONDecodeError`
if the script prints anything extra — that exception propagates and is caught by the outer
`except` which `raise`s, so the task fails (acceptable) but the JSON error is unhelpful. The
bigger issue: a 4-hour synchronous subprocess in a web-facing Celery worker is a capacity/deadlock
risk. 🟡.

FIX: route training to a dedicated worker/queue with a matching `time_limit`, or run it as a
sub-task with progress; validate stdout is JSON before `json.loads`.

---

## 🟡 15. training_tasks.py / n8n_callback.py: module-level Redis client built at import from env default
`backend/app/tasks/training_tasks.py:20-21`

```python
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_client = redis.from_url(REDIS_URL)
```

WHY: `redis_client` is created at module import time using `os.getenv` with a hardcoded
`redis://redis:6379` fallback. If the real `REDIS_URL` is set via env at runtime it is fine, but
the fallback points at the Docker service name `redis` — if this module is imported in a context
where that host is unreachable, the connection is lazy so it won't crash at import, but first use
will fail. Minor, but the hardcoded fallback is a footgun distinct from `settings`. 🟡.

FIX: read from `settings.CELERY_RESULT_BACKEND` / `settings.REDIS_URL` rather than a re-declared
env default.

---

## 💬 16. batch_processing.py: in-memory `_batch_jobs` dict — state lost on worker restart; tasks not durable
`backend/app/tasks/batch_processing.py:83,107`

```python
_batch_jobs: dict[str, BatchJob] = {}
...
batch_job = get_batch_job(batch_id)   # looks up the in-process dict
if not batch_job:
    logger.error("Batch job not found: %s", batch_id)
    return {"error": "Batch job not found"}
```

WHY: batch jobs are created via `create_batch_job` which stores them in a module-level dict on the
process that called it (the API/web worker). The Celery task `process_batch_task` runs in a
DIFFERENT process (the worker). When the worker picks up `process_batch_task(batch_id)`, the
in-process `_batch_jobs` dict in the worker does not contain the job → it logs "Batch job not
found" and returns an error every time. Even within one process, any worker restart loses all
batch jobs. This task is effectively non-functional across processes. 💬 (it is an architecture
gap rather than a crash, and may be intentional scaffolding, but it will silently fail in
production Celery).

FIX: persist batch jobs in the DB (or Redis) instead of a process-local dict; have the task load
from the shared store by `batch_id`.

---

## 💬 17. circuit_breaker.py / human_interrupt.py: orchestration primitives are in-memory singletons — no cross-worker coordination
`backend/app/orchestration/human_interrupt.py:246-253`, `backend/app/orchestration/circuit_breaker.py:74-92`

```python
_manager: HITLManager | None = None
def get_hitl_manager() -> HITLManager:
    global _manager
    if _manager is None:
        _manager = HITLManager()
    return _manager
```
and `MissionCircuitBreaker` holds mutable counts in instance attributes
(`llm_calls`, `cost_usd`, `tool_calls_by_agent`) with no locking.

WHY: `HITLManager._listeners` and `MissionCircuitBreaker` counters are process-local. A mission
executed by a Celery worker cannot share its `MissionCircuitBreaker` instance (or listener
callbacks) with the web worker or another Celery worker — each process has its own instance, so
the per-mission budget is NOT actually enforced across the distributed execution (a mission whose
LLM calls span retries/workers resets the counter). `HITLManager`'s listener callbacks registered
in one process are invisible in another, so `raise_interrupt`'s "fire listeners" only notifies
in-process listeners — cross-process WebSocket/event-bus signalling is not wired. 💬 (the module
docstrings acknowledge this is an adapter boundary / not yet production, but it means the
circuit-breaker safety net is not real in a multi-worker deployment).

FIX: back the circuit breaker with shared state (Redis) keyed by `mission_id`, and make
`HITLManager` listeners a cross-process bus (Redis pub/sub / the WS layer) rather than an
in-process list.

---

## 💬 18. workers/celery_app.py: separate Celery app instance + `autodiscover_tasks` — never actually used by the running worker
`backend/app/workers/celery_app.py:1-22`

```python
celery_app = Celery("workflows", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(task_serializer="json", ..., worker_prefetch_multiplier=1)
celery_app.autodiscover_tasks(["app.workers"])
```

WHY: the actual worker boots from `app/tasks/celery_app.py` (per docker-compose: `celery -A
app.tasks.celery_app worker`). This `app/workers/celery_app.py` defines a SECOND, separate
`celery_app` with `task_acks_late=True` / `worker_prefetch_multiplier=1` that is never imported by
the worker command (it is not in the `include`/registration list of `app/tasks/celery_app.py`, and
`app/workers/__init__.py` is empty). So:
1. The `tasks` celery_app (the one that runs) sets `task_acks_late`? — it does NOT (see #11/#12,
   `hitl_expiry`/`expire_paused_missions` set `acks_late=False` explicitly). The `workers`
   celery_app's `task_acks_late=True` is dead config.
2. `autodiscover_tasks(["app.workers"])` discovers nothing useful (there are no `@shared_task`s in
   `app/workers/`).
This is configuration drift / dead code. 💬.

FIX: either delete `app/workers/celery_app.py` (it is unused) or consolidate the two `celery_app`
instances into one source of truth so the worker's ack/retry policy is actually applied.

---

## 💬 19. task_optimizer.py: `optimize_celery_app` overwrites `task_acks_late` indirectly / sets global `max_retries=3` annotation
`backend/app/tasks/task_optimizer.py:190-218`

```python
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_annotations = {"**": {"max_retries": 3, "default_retry_delay": 60}}
```

WHY: `task_optimizer()` / `optimize_celery_app()` is never called anywhere in the audited scope (no
import of it from celery_app.py or the worker). If it WERE wired in, the `"**"` annotation would
force `max_retries=3` on EVERY task, overriding the carefully-tuned `max_retries` on
`hitl_expiry` (2), `expire_paused_missions` (2), `eval.run_suite` (2),
`memory.extract_claims` (1), etc. This is a latent footgun — the module is currently dead but
would silently change retry behavior if imported. 💬.

FIX: do not apply a global `"**"` annotation; if a router is needed, apply per-task routes without
overriding `max_retries`.

---

## 🔴 20. celery_app.py beat `decay-memory-entries` schedule uses `crontab` but the task name registered is `memory.decay_entries` — registration drift is benign, BUT the beat tasks list omits `swarm.*` and `training.*` (not a bug). However `integration-health-check-all` and `expire-paused-missions` rely on `redis`/DB — OK.
(No defect; noted for completeness — the beat schedule matches registered task names. Skipped as non-finding.)

---

## VERDICT

Total 🔴 blockers: 6 (findings #1, #2, #3, #4, #5, plus the engine-dispose omission #5 which on
prefork workers makes every mission execution crash). Total 🟡 suggestions: 9 (#6–#15). Total 💬
nits: 5 (#16–#19, #20 non-finding).

HIGHEST-RISK ERROR: **#1 + #2 (swarm_tasks.py)** — every swarm Celery task imports
`Swarm*` classes from the wrong module (`app.models.swarm_models`, which contains only
`OrchestratorExecution`/`OrchestratorTask`) AND opens the async `SessionLocal` then calls the
sync `.query()` API. The combined effect is that the entire swarm subsystem (`swarm.execute_task`,
`swarm.consensus_timeout`, `swarm.agent_heartbeat_check`, `swarm.cost_budget_check`) crashes on
first use — `ImportError`/`AttributeError` — and three of the four tasks swallow the exception and
return `{"success": False}`, so swarm work is silently dropped with no operator-visible failure
(only a log line). This is the single most damaging issue because it affects a whole task family
and presents as "handled" rather than "broken".

Close second: **#4 + #5 (mission_execution.py)** — `ExecuteMissionTask` never disposes the fork-
inherited async engine (so on prefork workers it crashes with the "different loop" asyncpg
RuntimeError on every mission execution) AND its retry path re-runs the entire mission workflow
instead of resuming, duplicating side effects on transient failures. Together these make durable
mission execution unreliable in the default (prefork) Celery deployment.

All findings are READ-ONLY observations; no source files were modified.
