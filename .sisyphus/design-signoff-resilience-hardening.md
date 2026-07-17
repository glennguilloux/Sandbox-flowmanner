# Design Sign-Off — Resilience Hardening Backlog

**Date:** 2026-07-17 · **Author:** Hermes (ops session)
**Companion to:** `.sisyphus/swarm-audit-2026-07-17/REPORT.md` (corrective, NOT an audit item)

## Why this doc exists

A post-deploy note claimed three "audit Medium-effort items" —
*Redis-backed breaker, event-bus off-request-path, resilience consolidation* —
need design sign-off. Investigation shows **none of these are items the 2026-07-17
swarm audit produced** (grep of the report + all six ledgers returns zero hits for
any of the three phrases). They are a real *infra-hardening backlog* that got
mentally merged with the audit. This doc re-grounds them in actual code and
poses the design decisions that genuinely need sign-off.

The audit's actual highest-value **unaddressed** items are **R1** (unlock 185
invisible personas, S-effort) and **R2** (fail-close v3 auth, S-effort) —
CRITICAL/HIGH, not Medium. Track those separately; do not let this backlog
crowd them out.

## Precondition already cleared (verification half of the goal)

Live `postgres` (service name `postgres`, container `workflow-postgres`):

```
SELECT state, count(*) FROM pg_stat_activity
  WHERE datname='flowmanner' GROUP BY state;
 idle  | 6
 active| 1
 → total 7 / max_connections=100

docker compose exec backend env | grep -iE 'DATABASE_(POOL_SIZE|MAX_OVERFLOW|URL)='
 DATABASE_URL=postgresql+asyncpg://flowmanner:****@workflow-postgres:5432/flowmanner
 (no POOL_SIZE / MAX_OVERFLOW override → config.py defaults)

backend container: uvicorn … --workers 1
```

- **Connection count is healthily under 100 (7/100).** ✅
- **The claimed "new 5/10 ceiling" does NOT exist in production.** The only
  `5`/`10` in the repo is `dev/.env.dev` (the *dev* stack). Production
  falls back to `backend/app/config.py:16-17` → `POOL_SIZE=10`,
  `MAX_OVERFLOW=20` → effective **ceiling 30** per container (and the
  backend runs `--workers 1`, so just one pool). Whatever deploy ran
  (backend container `Up 5 minutes (healthy)`) did **not** change the prod
  pool config. The "under 100 with 5/10 ceiling" framing is therefore
  moot — the check passes because the box is lightly loaded, not because a
  tightening landed.
- **Action:** no pool change warranted unless Glenn wants a deliberate 5/10
  prod cap (see Open Question 4). Leave config as-is for now.

## Item 1 — "Redis-backed breaker" → *breaker durability / cross-process coordination*

**Current code (verbatim):** `backend/app/core/circuit_breaker.py`
- State is in-process only: `self._failures: list[float]` (`:67`),
  `time.monotonic()` (`:68,85,96`), module-level `_breakers: dict` (`:195`),
  Prometheus gauges (`:29-38`). **No Redis, no persistence.**
- There IS a breaker *named* `"redis"` (`:221`) but it *protects the Redis
  dependency* — the inverse of "Redis-backed." Don't be misled by the name.

**Why it's a gap (latent, not breaking today):** Safe *only* because prod
runs `--workers 1`. If workers scale >1, each process has its own breaker
state → no coordination (one worker trips, others keep sending). And any
restart wipes all breaker state.

**Design decisions needing sign-off:**
1. **Durability target** — must breaker state survive a restart? For external-
   dependency protection (deepseek/llamacpp/qdrant/redis), restart-wipe is
   usually acceptable (fresh CLOSED on boot). If yes, Redis (or Postgres) is
   the backing store.
2. **Coordination model** — shared global state (Redis hash per
   dependency) for multi-worker correctness, vs. per-worker independent
   breakers (simpler, slight thundering-herd on recovery).
3. **New dependency risk** — backing with Redis means the breaker now depends
   on Redis being up to *read* state. Need a defined failure mode (fail-open
   vs fail-closed when the backing store is unreachable). Note
   `FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED=True` (config.py:340) already
   sets the guardrail's failure bias — must stay consistent with the new store.

## Item 2 — "event-bus off-request-path" → *sync bus blocks the HTTP response*

**Current code (verbatim):**
- `backend/app/services/event_bus.py:161-179` — `publish()` loops
  `await consumer(db, event)` **inline**, then sets status. Consumers
  (registered at `:305-307`): `trigger_matching_consumer` (→ substrate
  execution), `audit_log_consumer`, `failure_alert_consumer`.
- `backend/app/api/v1/integration_webhooks.py:519-527` calls
  `bus.publish(...)` **directly inside the webhook handler's transaction** and
  the caller commits (docstring `:483` "BEFORE acknowledging").

**Why it's a gap:** every webhook request holds its HTTP connection (and a
Postgres connection from the pool) while trigger-matching + substrate execution
+ audit + alerts run synchronously. A slow consumer → webhook delivery
timeouts, retries, and held DB connections. Concern scales with webhook
volume.

**Existing mitigation that makes offloading safe:** idempotency is already
enforced (`publish()` checks `delivery_id` at `:127-137` and returns the
existing event without re-processing). So moving dispatch to a background task
is at-least-once safe today.

**Design decisions needing sign-off:**
4. **Dispatch mechanism** — (a) `asyncio.create_task` within the request
   (cheap, but still bound to that uvicorn worker's event loop and dies on
   restart/worker death), or (b) enqueue to Redis/Celery and let
   `celery-worker` run consumers (durable, but adds latency + needs the
   caller to commit the `ExternalEvent` row *before* enqueue — currently the
   row is flushed but committed by the webhook route).
5. **Delivery semantics** — confirm at-least-once is acceptable for
   trigger-matching (idempotency already covers it) vs. a hard need for
   exactly-once.
6. **Failure surfacing** — `failure_alert_consumer` currently runs inline
   post-processing (`:196-206`); if moved to async, ensure Slack/PagerDuty
   alerts still fire on `status == "failed"`.

## Item 3 — "resilience consolidation" → *actually a deletion item (R11), not infra-building*

The audit's real item here is **R11**: *"De-register deprecated `MetaStrategy`
+ retire `nexus` orchestrator in favor of substrate + capability registry."*
That's removing dead weight (the audit flags "3 overlapping coordination
concepts" — nexus / substrate / hollow improvement loop), **not** building a
consolidated resilience layer. Don't scope-creep this into "build a unified
resilience service" — the value is *deletion*.

**Design decisions needing sign-off:**
7. **Confirm `nexus` is truly dead** — `swarm/orchestrator.py` import failed
   `find_spec` per the audit's own verification (REPORT.md §5.2). Agree the
   deletion PR scope (code + any lingering `app.services.swarm` refs).
8. **MetaStrategy** (`strategies/meta.py:35` + `__init__.py:36`) — same:
   de-register from the dispatchable set, confirm no live missions reference it.

## Open Question 4 (from Item 0) — do we even want a 5/10 prod pool cap?

The original fragment assumed a 5/10 prod ceiling. It isn't there. If the
intent was deliberate connection tightening (e.g. prod is over-provisioned at
30/container and you want headroom for more backend replicas under the 100
Postgres `max_connections`), that's a separate, simple change: set
`DATABASE_POOL_SIZE=5` / `DATABASE_MAX_OVERFLOW=10` in the prod `.env`
(loaded by the `backend` service via `env_file: .env`) and redeploy. **No
code change, no image rebuild** — `.env` is read at container start. Needs
Glenn's explicit call; not assumed.

## Sign-off checklist

- [ ] Q1 — breaker durability target (volatile-OK vs Redis-backed)
- [ ] Q2 — breaker coordination model (per-worker vs shared)
- [ ] Q3 — backing-store-unavailable failure mode (open vs closed)
- [ ] Q4 — bus offload mechanism (create_task vs Redis/Celery)
- [ ] Q5 — bus delivery semantics (at-least-once acceptable?)
- [ ] Q6 — async bus failure-alert path verified
- [ ] Q7 — `nexus` deletion scope confirmed dead
- [ ] Q8 — `MetaStrategy` de-registration confirmed safe
- [ ] Q4(Open) — prod 5/10 pool cap: yes/no
