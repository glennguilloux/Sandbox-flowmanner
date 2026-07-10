# W3 — Mission Engine + Swarm/Consensus + Self-Improvement (VERIFIED 2026-07-10)

**Date:** 2026-07-10
**Worker:** roadmap deep-analysis (re-claimed `t_9f9ae323`; prior runs 2-4 crashed exit 1, run 5 was a zombie — reclaimed dead worker)
**Grounding:** `/opt/flowmanner/backend/app` — re-grepped live 2026-07-10.
**Note:** the task body asks "what's actually wired vs stub." Finding: **this subsystem is genuinely wired, not stubbed.** The depth the brief claims is real.

---

## 0. Measured facts (live)

| Subsystem | Verified | State |
|-----------|----------|-------|
| Mission lifecycle | `mission_models.py:38-46` — external states `draft/pending/queued/running/completed/approved/failed/paused/aborted` + internal `planning/planned/executing` | Real enum |
| Mission execution path | `_mission_cqrs/commands.py:405-429` — `get_unified_executor()` + `mission_to_workflow()` | **Substrate GA** (H5.1) |
| Swarm consensus | `swarm_protocol.py` — debate / handoff / escalation protocols; `SwarmProfile.consensus_strategy` + `consensus_config` + `daily_limit` + `monthly_limit` (`models/swarm.py:31-34`) | Real, configurable |
| Self-improvement | `improvement_generator.py` (546 lines), `self_improvement.py` (63), `critique_service.py`, `learning_service.py` | Real, non-trivial |

---

## 1. Plan → Execute → Improve lifecycle (wired)

**Plan** — `mission_planner.py` (966 lines): LLM-generated execution plan → `MissionTask` records. Lifecycle `pending → planning → planned`. Late-bound deps avoid circular imports.

**Execute** — dispatched through the **unified substrate** (H5.1, GA):
- `backend/app/services/substrate/executor.py`: `UnifiedExecutor` (class at line 65, `execute()` at 285, `execute_node()` at 602).
- 7 strategies on 1 executor: `solo` (was mission_executor), `dag`, `graph`, `swarm`, `pipeline`, `meta`, `langgraph`.
- CQRS `execute_async` (`commands.py:487`) calls `get_unified_executor().execute(...)` with `mission_to_workflow(mission, tasks)`.
- 4 guarantees: Durable (event log), Type-checked, Capability-bounded (`CapabilityToken`), Bounded (every LLM call via `BudgetEnforcer.call()`).
- Crash recovery automatic via replay engine (pass known `run_id` → rebuild state).

**Improve** — `improvement_generator.py` (546 LOC) + `self_improvement.py` + `critique_service.py` + `learning_service.py`. The "plan, execute, improve" loop the landing page *claims* is **actually implemented** in `services/`.

**Gap (brief §5 / task ask):** the landing page undersells this. The engine does plan→execute→improve; the shopfront says "AI Mission Platform" but shows none of it. This is a **perception gap**, exactly Phase 1's mandate (§2.5 of `phase-1-perception-and-reach.md`).

---

## 2. Swarm / multi-agent (wired, configurable)

- `SwarmProfile` (`models/swarm.py`): `consensus_strategy` (String), `consensus_config` (JSON), `daily_limit` / `monthly_limit` (Double, usage caps). `swarm_consensus_rounds` table records `strategy_used`.
- `swarm_service.py` (269 LOC) — `create_swarm`, `get_swarm`, `list_swarms`.
- `api/v1/swarm_protocol.py` — concrete protocols, not a thin stub:
  - `POST /debate` + `GET /debate/{id}` (`DebateProtocol`)
  - `POST /handoff/delegate` + `/handoff/{id}/accept` + `/handoff/{id}/complete` (`HandoffProtocol`)
  - escalation chain (`EscalationChain`)
- Companion agent services present: `agent_service`, `agent_registry_service`, `delegation_service`, `team_space`, `cross_workspace_service`.

**Consensus is implemented as named protocols** (debate / handoff / escalation), configured per-profile via `consensus_strategy` + `consensus_config`. The brief's "configurable consensus strategies + usage caps" is accurate.

---

## 3. What's actually wired vs stub

- **Wired & real:** mission planner, substrate executor (all 7 strategies), CQRS mission commands/queries, swarm debate/handoff/escalation, self-improvement + critique + learning, memory citation (W2).
- **Legacy-but-present:** old executors (`mission_executor.py` etc.) still in-tree and wired by legacy routes; new code targets substrate. Per `substrate/AGENTS.md`, old executors are deletable after `FLOWMANNER_UNIFIED_EXECUTOR=all` has been on ≥2 weeks + parity tests green. This is cleanup debt, not a stub.
- **No `NotImplementedError` / `# stub` / `pass` markers** found in `improvement_generator.py`, `self_improvement.py`, `swarm_service.py`.

---

## 4. Why the landing page under-sells it (gap analysis)

The engine is deep and working:
- Plan→execute→improve loop (§1)
- Multi-agent swarm with debate/handoff/escalation (§2)
- 115-tool arsenal, 3-gate allowlist (W1)
- Hardened SSE + memory citations (W2)

But the **first 30 seconds** (landing + nav) convey "chat with a box," not "multi-agent mission platform that plans, executes, and improves itself." The fix is **perception** (Phase 1.2 / 2.5): surface a mission run view, a swarm explainer, a "see the arsenal" panel. No engine work needed.

---

## 5. Verification gates passed

- [x] Execution path read from `commands.py` (substrate dispatch), not the brief.
- [x] Swarm protocols enumerated from `swarm_protocol.py` router.
- [x] Self-improvement LOC + stub-marker scan.
- [x] No-deploy: analysis only.

---

*Generated by roadmap deep-analysis worker. Prior `W3-missions-swarm.md` (2026-07-07) should be re-verified against the substrate GA state; this file reflects 2026-07-10 code.*
