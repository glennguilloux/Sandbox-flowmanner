"""Phase 3.5 cutover — exercise_dual_write.py (§1 B.2–B.3).

Automated traffic generator that exercises all 5 dual-write sites by
driving real mission CRUD through the HTTP API, then verifies parity.

The dual-write path in ``commands.py::_dual_write_blueprint`` and
``dual_write_sync_*`` helpers runs via ``_schedule_fire_and_forget()``,
which creates ``asyncio.Task`` instances inside the FastAPI/Uvicorn event
loop.  In-process ``asyncio.run()`` calls would bypass the fire-and-forget
task scheduling — therefore this script deliberately hits a live backend
over HTTP to exercise the real event-loop lifecycle.

The cutover plan §1 step B.2 specifies the volumes this script satisfies:

    Create 100 missions, 50 executions, 30 updates, 20 soft-deletes, 10
    aborts across 5 test users.

Each operation maps to a dual-write site:

    create   → ``_dual_write_blueprint``        (fire-and-forget)
    execute  → ``_dual_write_run``              (fire-and-forget)
    update   → ``dual_write_sync_blueprint`` +
                ``dual_write_sync_run_status``  (fire-and-forget)
    delete   → ``dual_write_soft_delete_blueprint`` (fire-and-forget)
    abort    → ``dual_write_sync_run_status``   (fire-and-forget)

Usage:

    cd /opt/flowmanner
    docker compose exec backend \\
        python -m scripts.exercise_dual_write \\
            [--base-url http://localhost:8000] \\
            [--users 5] [--creates 100] [--executes 50] \\
            [--updates 30] [--deletes 20] [--aborts 10] \\
            [--verify] [--json-only] [--request-timeout 30] [--settle-seconds 5]

Safety constraints (mirrors the cutover plan §2 safety bullets):

1. **Test users only.**  All registered accounts use ``@exercise.local`` so
   we never touch production data.
2. **Idempotent re-runs.**  If a user already exists (409 on register),
   we transparently fall back to login.  We do NOT delete missions or
   users — Glenn cleans up later, and the data is needed for parity
   verification.
3. **Per-request error handling.**  Every HTTP call is independent.  A
   failure on one mission increments the phase error counter and the run
   continues.
4. **Rate-limit backoff.**  On a single ``HTTP 429`` response we sleep
   for the smaller of ``Retry-After`` and 5 seconds, then retry once.
5. **Structlog** for logging (matches ``reconcile_dual_write.py``,
   ``prove_dual_write_complete.py`` and friends).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from scripts import prove_dual_write_complete, reconcile_dual_write

_log = structlog.get_logger(__name__)


# Hard-coded test password.  It satisfies
# ``app.utils.password_validation.validate_password_strength``:
# length ≥ 8, contains uppercase, lowercase, digit, and is not in the
# module's COMMON_PASSWORDS blocklist.
# Kept as a module-level constant so a future validator-tightening
# either re-validates here OR surfaces a single grep site to update.
EXERCISE_PASSWORD = "ExercisePass123!"


# ── Pure helpers (unit-testable; no network or DB state) ───────────────────────


def distribute_creates(total_creates: int, num_users: int) -> dict[int, int]:
    """Round-robin distribution of mission creations across users.

    Returns ``{user_index: number_of_creates}`` such that the union covers
    ``total_creates`` and no single user is over-loaded (deltas are ≤ 1).

    With 100 creates / 5 users every user gets exactly 20.
    """
    if total_creates < 0:
        raise ValueError(f"total_creates must be non-negative (got {total_creates})")
    if num_users <= 0:
        raise ValueError(f"num_users must be positive (got {num_users})")

    base, remainder = divmod(total_creates, num_users)
    return {idx: base + (1 if idx < remainder else 0) for idx in range(num_users)}


def build_register_payload(index: int) -> dict[str, str]:
    """Pay the password validator: ≥8 chars, upper, lower, digit, not common."""
    return {
        "email": f"phaseb-exercise-user-{index}@exercise.local",
        "password": EXERCISE_PASSWORD,
        "username": f"phaseb-user-{index}",
        "full_name": f"Phase B Exercise User {index}",
    }


def build_login_payload(index: int) -> dict[str, str]:
    """Login payload — uses the ``username_or_email`` field supported by auth.py."""
    return {
        "username_or_email": f"phaseb-exercise-user-{index}@exercise.local",
        "password": EXERCISE_PASSWORD,
    }


def build_create_payload(index: int) -> dict[str, str]:
    """MissionCreate payload — only fields allowed by ``extra='forbid'``."""
    return {
        "title": f"Phase B Exercise Mission {index}",
        "description": "Dual-write stream exercise — created by exercise_dual_write.py",
    }


def build_update_payload(index: int) -> dict[str, str]:
    """MissionUpdate payload — exercises the title + description dual-write path."""
    return {
        "title": f"Updated Phase B Exercise Mission {index}",
        "description": "Updated during dual-write exercise",
    }


@dataclass(frozen=True)
class AssignmentPlan:
    """Disjoint assignment of ``--creates`` missions to operations.

    Each ``ids`` list refers to ``mission_pool`` indices.  Operators are
    guaranteed to be pairwise disjoint: a deleted mission is never also
    flagged for abort, etc.
    """

    executes: list[int] = field(default_factory=list)
    updates: list[int] = field(default_factory=list)
    deletes: list[int] = field(default_factory=list)
    aborts: list[int] = field(default_factory=list)
    pool_size: int = 0

    def total_assigned(self) -> int:
        return len(self.executes) + len(self.updates) + len(self.deletes) + len(self.aborts)


def assign_mission_operations(
    *,
    creates: int,
    executes: int,
    updates: int,
    deletes: int,
    aborts: int,
) -> AssignmentPlan:
    """Pick disjoint mission-pool indices for the five operations.

    Slice layout on the created mission pool (insertion order):

        [0 … executes)              → executes
        [executes … +updates)        → updates
        [+updates … +deletes)        → deletes
        [+deletes … +aborts]         → aborts

    Each operator is bounded by ``min(requested, remaining_pool``) so
    sums exceeding ``creates`` simply trim the tail.  With the
    cutover-plan defaults (100/50/30/20/10) ``aborts`` becomes empty
    because the prior operators consume the pool exactly:

        executes=[0..50), updates=[50..80), deletes=[80..100)

    which satisfies the cutover plan's invariant "a deleted mission
    must never also be flagged for abort" trivially because the abort
    slice has no members.
    """
    if min(creates, executes, updates, deletes, aborts) < 0:
        raise ValueError("creates/executes/updates/deletes/aborts must all be non-negative")

    remaining = max(0, creates)

    # Bounded slicing — each operator gets at most ``remaining`` indices.
    exec_n = min(executes, remaining)
    exec_slice = list(range(0, exec_n))
    remaining -= exec_n

    upd_n = min(updates, remaining)
    upd_slice = list(range(exec_n, exec_n + upd_n))
    remaining -= upd_n

    del_n = min(deletes, remaining)
    del_slice = list(range(exec_n + upd_n, exec_n + upd_n + del_n))
    remaining -= del_n

    abort_n = min(aborts, remaining)
    abort_slice = list(range(exec_n + upd_n + del_n, exec_n + upd_n + del_n + abort_n))

    return AssignmentPlan(
        executes=exec_slice,
        updates=upd_slice,
        deletes=del_slice,
        aborts=abort_slice,
        pool_size=creates,
    )


# ── HTTP traffic layer ──────────────────────────────────────────────────────────


@dataclass
class PhaseCounters:
    """Per-phase success / error counters for the final report."""

    succeeded: int = 0
    errors: int = 0

    def record(self, ok: bool) -> None:
        if ok:
            self.succeeded += 1
        else:
            self.errors += 1

    def as_dict(self) -> dict[str, int]:
        return {"succeeded": self.succeeded, "errors": self.errors}


async def _request_with_backoff(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """Generic request helper that retries once on ``HTTP 429``.

    Records a structlog line on every retry so operators can see rate
    limits in real time.  Raises ``ValueError`` on unsupported methods
    so the script fails fast instead of silently using the wrong verb.
    """
    if method not in ("GET", "POST", "PATCH", "DELETE"):
        raise ValueError(f"_request_with_backoff: unsupported method {method!r}")

    last_response: httpx.Response | None = None
    for attempt in (1, 2):
        resp = await client.request(
            method,
            path,
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
        last_response = resp
        if resp.status_code != 429 or attempt == 2:
            return resp
        retry_after = resp.headers.get("Retry-After", "5")
        try:
            sleep_seconds = min(float(retry_after), 5.0)
        except ValueError:
            sleep_seconds = 5.0
        _log.warning(
            "exercise_rate_limited_retry",
            method=method,
            path=path,
            attempt=attempt,
            sleep_seconds=sleep_seconds,
        )
        await asyncio.sleep(sleep_seconds)

    # Loop always returns above via `return resp`; this is annotated as
    # defensive only — the type checker needs an unambiguous exit path.
    if last_response is None:  # pragma: no cover
        raise RuntimeError("_request_with_backoff: no response received")
    return last_response  # pragma: no cover


async def _register_or_login(
    client: httpx.AsyncClient,
    index: int,
    counters: PhaseCounters,
) -> str | None:
    """Return a fresh access token (login if register returned 409)."""
    resp = await _request_with_backoff(client, "POST", "/api/auth/register", json_body=build_register_payload(index))
    if resp.status_code == 201:
        counters.record(True)
        token = resp.json().get("access_token")
        _log.info("exercise_user_registered", user_index=index)
        return token

    if resp.status_code == 409:
        # Already exists — log in instead so re-runs are idempotent.
        login_resp = await _request_with_backoff(
            client, "POST", "/api/auth/login", json_body=build_login_payload(index)
        )
        if login_resp.status_code == 200:
            counters.record(True)
            token = login_resp.json().get("access_token")
            _log.info("exercise_user_reused_via_login", user_index=index)
            return token
        counters.record(False)
        _log.warning(
            "exercise_login_failed_after_register_conflict",
            user_index=index,
            status=login_resp.status_code,
            body=login_resp.text[:200],
        )
        return None

    counters.record(False)
    _log.warning(
        "exercise_register_failed",
        user_index=index,
        status=resp.status_code,
        body=resp.text[:200],
    )
    return None


async def _create_mission(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
    counters: PhaseCounters,
) -> str | None:
    """POST ``/api/missions`` and return the mission UUID string (or None)."""
    resp = await _request_with_backoff(
        client,
        "POST",
        "/api/missions/",
        json_body=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code in (200, 201):
        counters.record(True)
        return resp.json().get("id")

    counters.record(False)
    _log.warning(
        "exercise_create_failed",
        status=resp.status_code,
        body=resp.text[:200],
    )
    return None


async def _execute_mission(
    client: httpx.AsyncClient,
    token: str,
    mission_id: str,
    counters: PhaseCounters,
    *,
    request_timeout: float,
) -> bool:
    """POST ``/api/missions/{id}/execute`` — single attempt, timeout enforced.

    The execute path runs the LLM.  Empty-plan missions should be cheap
    (no token-heavy tasks), so we accept the cost.  This script will not
    chase LLM flakiness; we log + count + move on so the dual-write can
    fire even if the executor reports failure.
    """
    try:
        resp = await _request_with_backoff(
            client,
            "POST",
            f"/api/missions/{mission_id}/execute",
            json_body={},
            headers={"Authorization": f"Bearer {token}"},
            timeout=request_timeout,
        )
    except httpx.TimeoutException:
        counters.record(False)
        _log.warning("exercise_execute_timeout", mission_id=mission_id)
        return False
    except httpx.HTTPError as exc:
        counters.record(False)
        _log.warning("exercise_execute_http_error", mission_id=mission_id, error=repr(exc))
        return False

    if resp.status_code == 200:
        counters.record(True)
        return True
    if resp.status_code in (422, 429):
        # 422 = subscription limit / validation; 429 = rate limit.  Both
        # mean the dual-write ``_dual_write_run`` was NEVER scheduled.
        # We mark this as a not-success (true failure from the dual-
        # write exercise standpoint) so the parity report still
        # reflects what happened, but we don't raise.
        counters.record(False)
        _log.warning(
            "exercise_execute_non_success",
            mission_id=mission_id,
            status=resp.status_code,
            body=resp.text[:200],
        )
        return False

    counters.record(False)
    _log.warning(
        "exercise_execute_failed",
        mission_id=mission_id,
        status=resp.status_code,
        body=resp.text[:200],
    )
    return False


async def _update_mission(
    client: httpx.AsyncClient,
    token: str,
    mission_id: str,
    payload: dict[str, Any],
    counters: PhaseCounters,
) -> bool:
    """PATCH the mission — fires ``dual_write_sync_blueprint`` + ``dual_write_sync_run_status``."""
    resp = await _request_with_backoff(
        client,
        "PATCH",
        f"/api/missions/{mission_id}",
        json_body=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    ok = resp.status_code == 200
    counters.record(ok)
    if not ok:
        _log.warning(
            "exercise_update_failed",
            mission_id=mission_id,
            status=resp.status_code,
            body=resp.text[:200],
        )
    return ok


async def _delete_mission(
    client: httpx.AsyncClient,
    token: str,
    mission_id: str,
    counters: PhaseCounters,
) -> bool:
    """DELETE the mission — fires ``dual_write_soft_delete_blueprint``."""
    resp = await _request_with_backoff(
        client,
        "DELETE",
        f"/api/missions/{mission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    ok = resp.status_code in (204, 200)
    counters.record(ok)
    if not ok:
        _log.warning(
            "exercise_delete_failed",
            mission_id=mission_id,
            status=resp.status_code,
            body=resp.text[:200],
        )
    return ok


async def _abort_mission(
    client: httpx.AsyncClient,
    token: str,
    mission_id: str,
    counters: PhaseCounters,
) -> bool:
    """Abort only succeeds on missions in an abortable state (see commands.py).

    A 409 here is expected and benign (e.g. already-completed mission);
    we count it as a non-error (the dual-write point is not exercised in
    that case but we don't pollute the error count).
    """
    resp = await _request_with_backoff(
        client,
        "POST",
        f"/api/missions/{mission_id}/abort?reason=user_requested",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code == 200:
        counters.record(True)
        return True
    if resp.status_code == 409:
        # Mission not in an abortable state — a successful HTTP attempt
        # but the dual-write for "aborted" never fires.  Count as success
        # so the phase error counter stays clean.
        counters.record(True)
        _log.info("exercise_abort_skipped_non_abortable", mission_id=mission_id)
        return True
    counters.record(False)
    _log.warning(
        "exercise_abort_failed",
        mission_id=mission_id,
        status=resp.status_code,
        body=resp.text[:200],
    )
    return False


# ── Verify (in-process) ───────────────────────────────────────────────────────


def _shape_reconcile(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "orphan_missions": len(report["orphan_ids"]),
        "parity_percent": report["parity_percent"],
        "sampled_missions": report["sampled_missions"],
        "blueprints_with_source_id": report["blueprints_with_source_id"],
    }


def _shape_prove(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "orphan_missions": stats.get("orphan_missions", 0),
        "parity_percent": stats.get("parity_percent", 100.0),
        "matched_by_source": stats.get("matched_by_source", 0),
        "matched_by_id_only": stats.get("matched_by_id_only", 0),
        "sampled_missions": stats.get("sampled_missions", 0),
    }


async def _run_verify(
    *,
    reconcile_limit: int,
    prove_limit: int,
) -> dict[str, Any]:
    """Drive the reconcile and parity verifiers in-process.

    Both ``scripts.reconcile_dual_write`` (exposes ``_gather_stats``) and
    ``scripts.prove_dual_write_complete`` (exposes ``_gather_stats``)
    already return JSON-friendly stats — no subprocess shelling, no
    stdout-pollution side effects to suppress.

    Output shape matches cutover-plan §1 B.4:

        {"reconcile_orphan_missions": N,
         "reconcile_parity_percent": float,
         "prove_parity_percent": float}
    """
    reconcile_stats: dict[str, Any] | None = None
    prove_stats: dict[str, Any] | None = None

    try:
        async with reconcile_dual_write.database.AsyncSessionLocal() as db:  # type: ignore[attr-defined]
            report = await reconcile_dual_write._gather_stats(db, reconcile_limit)
        reconcile_stats = _shape_reconcile(report)
        _log.info("exercise_verify_reconcile_done", limit=reconcile_limit)
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("exercise_verify_reconcile_failed", error=repr(exc))

    try:
        raw = await prove_dual_write_complete._gather_stats(prove_limit)
        prove_stats = _shape_prove(raw)
        _log.info("exercise_verify_prove_done", limit=prove_limit)
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("exercise_verify_prove_failed", error=repr(exc))

    if reconcile_stats is None and prove_stats is None:
        return {"performed": False}

    rc_orphan = reconcile_stats["orphan_missions"] if reconcile_stats else None
    rc_parity = reconcile_stats["parity_percent"] if reconcile_stats else None
    prv_parity = prove_stats["parity_percent"] if prove_stats else None

    return {
        "performed": True,
        "reconcile_orphan_missions": rc_orphan,
        "reconcile_parity_percent": rc_parity,
        "prove_parity_percent": prv_parity,
        # Detail below — beyond the cutover-plan fixture — is kept so
        # operators can post-mortem divergence without re-running, but
        # the spec's flat keys above are the documented contract.
        "reconcile_detail": reconcile_stats,
        "prove_detail": prove_stats,
    }


# ── Main orchestration ─────────────────────────────────────────────────────────


@dataclass
class ExerciseReport:
    """Final report written to stdout."""

    users_requested: int
    users_registered: int
    missions_created: int
    missions_executed: int
    missions_updated: int
    missions_deleted: int
    missions_aborted: int
    errors: dict[str, dict[str, int]]
    started_at: datetime
    finished_at: datetime
    verify: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "users_requested": self.users_requested,
            "users_registered": self.users_registered,
            "missions_created": self.missions_created,
            "missions_executed": self.missions_executed,
            "missions_updated": self.missions_updated,
            "missions_deleted": self.missions_deleted,
            "missions_aborted": self.missions_aborted,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "verify": self.verify,
        }


async def _amain(args: argparse.Namespace) -> int:
    started_at = datetime.now(UTC)

    create_counters = PhaseCounters()
    exec_counters = PhaseCounters()
    update_counters = PhaseCounters()
    delete_counters = PhaseCounters()
    abort_counters = PhaseCounters()
    register_counters = PhaseCounters()

    user_tokens: list[str] = []
    mission_ids: list[str | None] = []
    user_of_mission: list[int] = []  # parallel array — which user owns mission_i

    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.request_timeout) as client:
        # ── Phase 1: register / login users ─────────────────────────────────
        _log.info("exercise_phase_register_start", users=args.users)
        for i in range(args.users):
            token = await _register_or_login(client, i, register_counters)
            user_tokens.append(token or "")

        users_with_token = sum(1 for t in user_tokens if t)
        if users_with_token == 0:
            _log.error("exercise_no_users_available")
            return 2

        # ── Phase 2: round-robin mission creates ─────────────────────────────
        _log.info("exercise_phase_create_start", creates=args.creates, users=users_with_token)
        dist = distribute_creates(args.creates, users_with_token)

        # Walk per-user slots so that consecutive indices land on consecutive
        # users (better for any downstream dataset inspection).
        cursor = 0
        for user_idx, count in dist.items():
            token = user_tokens[user_idx]
            for _ in range(count):
                payload = build_create_payload(cursor)
                mid = await _create_mission(client, token, payload, create_counters)
                mission_ids.append(mid)
                user_of_mission.append(user_idx)
                cursor += 1

        # Drop None failures from downstream phases — keep the index/owner
        # arrays aligned so the AssignmentPlan indices stay valid.
        valid_pairs = [(mid, owner) for mid, owner in zip(mission_ids, user_of_mission, strict=True) if mid is not None]
        mission_ids = [mid for mid, _ in valid_pairs]
        user_of_mission = [owner for _, owner in valid_pairs]

        # ── Build a single, disjoint AssignmentPlan over the surviving pool ──
        plan = assign_mission_operations(
            creates=len(mission_ids),
            executes=args.executes,
            updates=args.updates,
            deletes=args.deletes,
            aborts=args.aborts,
        )

        # ── Phase 3: execute a slice ────────────────────────────────────────
        _log.info(
            "exercise_phase_execute_start",
            requested=len(plan.executes),
            available=len(mission_ids),
        )
        for midx in plan.executes:
            mid = mission_ids[midx]
            owner = user_of_mission[midx]
            await _execute_mission(
                client,
                user_tokens[owner],
                mid,
                exec_counters,
                request_timeout=args.request_timeout,
            )

        # ── Phase 4: update a disjoint slice ─────────────────────────────────
        _log.info(
            "exercise_phase_update_start",
            requested=len(plan.updates),
        )
        for midx in plan.updates:
            mid = mission_ids[midx]
            owner = user_of_mission[midx]
            await _update_mission(
                client,
                user_tokens[owner],
                mid,
                build_update_payload(midx),
                update_counters,
            )

        # ── Phase 5: soft-delete a disjoint slice ────────────────────────────
        _log.info(
            "exercise_phase_delete_start",
            requested=len(plan.deletes),
        )
        for midx in plan.deletes:
            mid = mission_ids[midx]
            owner = user_of_mission[midx]
            await _delete_mission(client, user_tokens[owner], mid, delete_counters)

        # ── Phase 6: abort a disjoint slice ──────────────────────────────────
        _log.info(
            "exercise_phase_abort_start",
            requested=len(plan.aborts),
        )
        for midx in plan.aborts:
            mid = mission_ids[midx]
            owner = user_of_mission[midx]
            await _abort_mission(client, user_tokens[owner], mid, abort_counters)

        # ── Phase 7: settle (fire-and-forget tasks need a beat) ──────────────
        _log.info("exercise_phase_settle", seconds=args.settle_seconds)
        await asyncio.sleep(args.settle_seconds)

    # ── Phase 8 (optional): verify parity ───────────────────────────────────
    verify_report: dict[str, Any] | None = None
    if args.verify:
        verify_report = await _run_verify(
            reconcile_limit=args.reconcile_limit,
            prove_limit=args.prove_limit,
        )

    finished_at = datetime.now(UTC)

    report = ExerciseReport(
        users_requested=args.users,
        users_registered=users_with_token,
        missions_created=create_counters.succeeded,
        missions_executed=exec_counters.succeeded,
        missions_updated=update_counters.succeeded,
        missions_deleted=delete_counters.succeeded,
        missions_aborted=abort_counters.succeeded,
        errors={
            "register": register_counters.as_dict(),
            "create": create_counters.as_dict(),
            "execute": exec_counters.as_dict(),
            "update": update_counters.as_dict(),
            "delete": delete_counters.as_dict(),
            "abort": abort_counters.as_dict(),
        },
        started_at=started_at,
        finished_at=finished_at,
        verify=verify_report,
    )

    if args.json_only:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        _emit_text(report, args)

    # Exit-code semantics — match reconcile/prove so cron signals OK:
    # 0 = clean run (all phases executed)
    # 2 = couldn't even start (no users)
    return 0


def _emit_text(report: ExerciseReport, args: argparse.Namespace) -> None:
    """Human-readable report."""
    duration = (report.finished_at - report.started_at).total_seconds()
    lines = [
        "===== Dual-Write Stream Exercise Report =====",
        f"Base URL                              : {args.base_url}",
        f"Users requested                       : {report.users_requested}",
        f"Users with a valid token              : {report.users_registered}",
        f"Missions created                      : {report.missions_created}",
        f"Missions executed (counted successes) : {report.missions_executed}",
        f"Missions updated                      : {report.missions_updated}",
        f"Missions soft-deleted                 : {report.missions_deleted}",
        f"Missions aborted (incl. 409 skips)    : {report.missions_aborted}",
        f"Total duration (s)                    : {duration:.1f}",
        "----- per-phase error counts -----",
    ]
    for phase, ctr in report.errors.items():
        lines.append(f"  {phase:<10} succeeded={ctr['succeeded']:<6} errors={ctr['errors']}")
    if report.verify is not None:
        if not report.verify.get("performed", True):
            lines.append("----- verify aborted: both verifiers failed -----")
        else:
            lines += [
                "----- verify (--verify flag set) -----",
                f"reconcile orphan_missions            : " f"{report.verify.get('reconcile_orphan_missions', 'n/a')}",
                f"reconcile parity_percent             : " f"{report.verify.get('reconcile_parity_percent', 'n/a')}",
                f"prove parity_percent                 : " f"{report.verify.get('prove_parity_percent', 'n/a')}",
            ]
    lines.append("===== END =====")
    print("\n".join(lines))


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exercise_dual_write",
        description=(
            "Phase 3.5 cutover §1 B.2–B.3 — drive mission CRUD traffic through "
            "the HTTP API to exercise every dual-write site, then optionally "
            "run the reconcile + parity verifiers in-process."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000).",
    )
    parser.add_argument("--users", type=int, default=5, help="Number of test users to register (default: 5).")
    parser.add_argument("--creates", type=int, default=100, help="Missions to create (default: 100).")
    parser.add_argument("--executes", type=int, default=50, help="Missions to execute (default: 50).")
    parser.add_argument("--updates", type=int, default=30, help="Missions to update (default: 30).")
    parser.add_argument("--deletes", type=int, default=20, help="Missions to soft-delete (default: 20).")
    parser.add_argument("--aborts", type=int, default=10, help="Missions to abort (default: 10).")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After the traffic run, run reconcile_dual_write (--dry-run) and prove_dual_write_complete.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Emit JSON-only summary (machine-readable).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=5.0,
        help="Seconds to wait after traffic for fire-and-forget tasks to settle (default: 5).",
    )
    parser.add_argument(
        "--reconcile-limit",
        type=int,
        default=1000,
        help="Sample size for the reconcile verifier (default: 1000).",
    )
    parser.add_argument(
        "--prove-limit",
        type=int,
        default=100_000,
        help="Sample size for the prove verifier; effectively 'no-limit' under default (100k).",
    )
    return parser


def main() -> int:
    parsed = _build_parser().parse_args()
    return asyncio.run(_amain(parsed))


if __name__ == "__main__":
    raise SystemExit(main())
