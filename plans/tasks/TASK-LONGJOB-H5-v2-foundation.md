# DEEPSEEK LONG JOB — H5: V2 Foundation (Memory + HITL + Cost Attribution + Mission Circuit Breakers)

TASK: H5-V2-FOUNDATION
HORIZON: Phase 6 stop-gate readiness (backend-first, minimal vertical slice)
PROJECT: FlowManner Backend (+ minimal frontend inbox surface only if required)
ROOTS:
- Backend: /opt/flowmanner/backend
- Frontend: /home/glenn/FlowmannerV2-frontend

## Objective
Ship a real, test-backed vertical slice for Phase 6 foundations:
1) episodic memory consolidation worker
2) human-in-the-loop interrupt primitives (backend-first)
3) mission cost attribution engine
4) mission circuit breaker enforcement (cost/tool-call/time constraints)

This is not full V2 completion. It is a hard, verifiable foundation slice that proves architecture and execution path.

## Verified current state (must be treated as facts)
- Existing memory stack already present:
  - /opt/flowmanner/backend/app/models/memory_models.py
  - /opt/flowmanner/backend/app/services/memory_service.py
  - /opt/flowmanner/backend/app/api/v1/memory.py
- Mission executor exists and currently does not expose HITL primitives:
  - /opt/flowmanner/backend/app/services/mission_executor.py
- General dependency circuit breaker exists (external deps), mission-level breaker not implemented:
  - /opt/flowmanner/backend/app/core/circuit_breaker.py
- Cost tracker exists for LLM calls, but no query-focused attribution engine:
  - /opt/flowmanner/backend/app/services/cost_tracker.py
- No `human_interrupt.py` file exists in backend
- No `observability/cost_engine.py` file exists in backend
- Frontend currently has no dedicated Inbox route implementation for interrupts

## Hard constraints
- English only.
- Backend-first priority. Frontend changes only if required for minimal proof path.
- No VPS deploy steps.
- No broad architecture rewrites.
- No new external dependencies unless absolutely required; if required, stop and justify.
- If new .py files are created, chmod 644.

## Required deliverables

### 1) Episodic memory consolidation worker (minimal real path)
Create:
- /opt/flowmanner/backend/app/memory/consolidation_worker.py

Requirements:
- Provide callable worker entrypoint that can ingest completed mission-like payloads
- Extract episode tuple: context, action, outcome, success/failure metadata
- Store summary + metadata using existing memory infrastructure (reuse current services/models)
- Include configurable retention/archival policy hooks (90-day policy stub acceptable if test-backed)
- Do NOT fake RabbitMQ subscription if infra wiring is too large; instead provide explicit adapter boundary + testable ingest API

Add tests:
- /opt/flowmanner/backend/tests/test_memory_consolidation_worker.py

Must verify:
- ingestion produces stored episode artifact
- metadata fields include mission_id, agent_id, success flag
- retrieval path can surface stored episodes by mission/agent filter
- retention policy logic is deterministic and test-covered

### 2) HITL backend primitives
Create:
- /opt/flowmanner/backend/app/orchestration/human_interrupt.py

Requirements:
- Define `HumanInterrupt` exception/dataclass with at least:
  - interrupt_type: approval | clarification | escalation
  - context
  - proposed_action
  - confidence
  - deadline (optional)
- Add persistence model/table path for interrupt inbox (can be new model + migration OR reuse existing generic mechanism with explicit schema)
- Add emitter function for websocket/event-bus signal name `HUMAN_INTERRUPT_RAISED` (adapter boundary acceptable)
- Integrate minimal hook into mission execution path for `approval_required_for` tool/action list
- Mission must pause/await human decision path rather than continuing blindly

Add tests:
- /opt/flowmanner/backend/tests/test_human_interrupt_primitives.py

Must verify:
- interrupt object validation/serialization
- mission execution path raises/handles interrupt when gated action encountered
- interrupt record persisted for later approval

### 3) Cost attribution engine
Create:
- /opt/flowmanner/backend/app/observability/cost_engine.py

Requirements:
- Implement `compute(event)` or equivalent for normalized cost payload:
  provider, model, input_tokens, output_tokens, cost_usd, agent_id, mission_id, user_id, workspace_id
- Reuse existing pricing logic from cost_tracker where possible
- Add aggregation queries/functions for:
  - by agent
  - by mission
  - by user
  - by workspace
  - by period
- Must support answering: "How much did agent X cost this month?"

Add tests:
- /opt/flowmanner/backend/tests/test_cost_engine.py

Must verify:
- deterministic cost computation
- aggregation accuracy across mixed events
- monthly query correctness for specific agent_id

### 4) Mission circuit breaker enforcement
Create or extend:
- /opt/flowmanner/backend/app/orchestration/circuit_breaker.py (preferred mission-scoped)
  OR extend existing with clear mission-level namespace

Requirements:
- Enforce per-mission limits:
  - max_llm_calls
  - max_cost_usd
  - max_duration_seconds
- Enforce per-agent max_tool_calls
- Add destructive-action policy gate:
  - destructive actions require approval (wired to HumanInterrupt path)
- Integrate checks into mission executor before each risky action/tool call
- Transition mission/task to explicit failure/aborted/circuit-broken-compatible state path with clear reason in logs

Add tests:
- /opt/flowmanner/backend/tests/test_mission_circuit_breaker.py

Must verify:
- exceeding max_cost_usd stops execution deterministically
- exceeding call limits stops execution deterministically
- destructive action triggers approval interrupt path

### 5) Minimal API surface for validation (backend)
If needed, add lightweight endpoints under existing API versioning for:
- listing pending interrupts
- approving/rejecting one interrupt
- querying aggregated cost for agent/month

Tests required for any new API endpoint.

### 6) H5 evidence report
Create:
- /opt/flowmanner/backend/H5-V2-FOUNDATION-REPORT.md

Must include:
1. exact files changed
2. exact commands run
3. test result table
4. proof snippets for:
   - memory episode ingest + retrieval
   - interrupt raise + persistence
   - cost query for agent/month
   - circuit breaker stop condition
5. remaining gaps to full P6 (clearly listed)
6. verdict: `H5_READY: YES/NO`

## Allowed file scope
You may edit/create only:
- /opt/flowmanner/backend/app/memory/consolidation_worker.py (new)
- /opt/flowmanner/backend/app/orchestration/human_interrupt.py (new)
- /opt/flowmanner/backend/app/observability/cost_engine.py (new)
- /opt/flowmanner/backend/app/orchestration/circuit_breaker.py (new or extend existing mission path)
- /opt/flowmanner/backend/app/services/mission_executor.py
- /opt/flowmanner/backend/app/api/v1/* (only if minimal endpoint needed)
- /opt/flowmanner/backend/app/models/* (only if interrupt persistence model needed)
- /opt/flowmanner/backend/alembic/versions/* (only if new table migration needed)
- /opt/flowmanner/backend/tests/test_memory_consolidation_worker.py (new)
- /opt/flowmanner/backend/tests/test_human_interrupt_primitives.py (new)
- /opt/flowmanner/backend/tests/test_cost_engine.py (new)
- /opt/flowmanner/backend/tests/test_mission_circuit_breaker.py (new)
- /opt/flowmanner/backend/H5-V2-FOUNDATION-REPORT.md (new)

If additional files are required, stop and explain first.

## Execution order (strict)
Step 1 — Read current mission/memory/cost/circuit code and choose smallest cohesive architecture
Step 2 — Apply all code + tests in one patch wave
Step 3 — chmod 644 all newly created .py files
Step 4 — Run targeted tests:
- cd /opt/flowmanner/backend
- PYTHONPATH=/opt/flowmanner/backend pytest -q \
  tests/test_memory_consolidation_worker.py \
  tests/test_human_interrupt_primitives.py \
  tests/test_cost_engine.py \
  tests/test_mission_circuit_breaker.py
Step 5 — Run one integration-flavored mission execution test path if available
Step 6 — Write final report with evidence

## Required final chat output format
Return exactly:
- STATUS: SUCCESS | PARTIAL | BLOCKED
- FILES:
- TESTS:
- EVIDENCE:
- RISKS:
- H5_READY: YES | NO
- NEXT:

No vague claims. Every success statement must be backed by command output evidence.