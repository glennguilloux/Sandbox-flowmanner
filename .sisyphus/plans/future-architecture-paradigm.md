# Future Architecture Paradigm Documentation Plan

## TL;DR

> **Quick Summary**: Create an implementation-ready documentation plan that turns FlowManner's future-architecture pack into an evidence-backed, roadmap-aligned, QA-validated architecture record. The plan keeps the active rebuild roadmap intact while defining the 5–10 year V3 target: modular monolith, event-driven durable substrate, distributed worker plane, provider abstraction, and self-hosted-first deployment.
>
> **Deliverables**:
> - Future-architecture docs QA harness and validation contract.
> - Updated `01-paradigm-evaluation.md` with explicit decisions, non-goals, and stop gates.
> - Roadmap-aligned updates to docs `02-09`.
> - TDD contract checklist for risky architecture invariants.
> - Final docs-pack validation and drift report.
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Task 1 → Task 2 → Tasks 3-8 → Task 9 → Task 10 → F1-F4

---

## Context

### Original Request
Plan `/opt/flowmanner/docs/future-architecture/01-paradigm-evaluation.md`.

### Interview Summary
**Key Discussions**:
- User selected a **documentation plan**, not direct implementation.
- Scope is **docs plus roadmap alignment**, not backend code changes.
- Time horizon is the **full V3 / 5–10 year target**.
- Test strategy is **TDD for risky architecture contracts**, with characterization tests before refactoring existing behavior.

**Research Findings**:
- The architecture pack already defines the future shape: modular monolith + event-driven durable substrate + distributed worker plane.
- `REBUILD-ROADMAP.md` remains the active near-term roadmap and must not be replaced by the future-architecture pack.
- The future-architecture docs already cover diagrams, domain boundaries, execution/agent runtime, knowledge/events/data, observability/deployment, roadmap/risks/not-build, final recommendation, and current-state gaps.
- Test infrastructure exists: backend `pytest` with substrate-critical gates, and frontend Vitest/Playwright at `/home/glenn/FlowmannerV2-frontend`.
- Provider routing research failed during planning, so provider-specific claims must be source-backed or explicitly flagged as unresolved.

### Metis Review
**Identified Gaps** (addressed):
- Add explicit docs QA automation.
- Add TDD contract criteria for architecture invariants.
- Preserve active rebuild roadmap semantics.
- Flag provider routing as unresolved until source-backed research is retried.
- Add stop gates for microservices, service mesh, full event sourcing, actor-framework lock-in, NATS before outbox/schema, and Kubernetes-only self-hosting.

### Plan Self-Review
**Gap Classification**:
- **Auto-resolved minor gap**: Final verification code-quality command was generic (`bun test`); replaced with this project's exact backend pytest, frontend TypeScript, Vitest, and Playwright verification commands.
- **Disclosed unresolved research gap**: Provider routing remains flagged as unresolved because the background routing research failed with `{"code":400,"message":"Provider returned error","metadata":{"error_type":"invalid_request"}}`.

---

## Work Objectives

### Core Objective
Update and align FlowManner's future-architecture documentation so it is implementation-ready, evidence-backed, roadmap-aligned, and validated by executable checks.

### Concrete Deliverables
- `.sisyphus/plans/future-architecture-paradigm.md` plan file.
- Docs QA harness and validation contract.
- Updated future-architecture docs `01-09`.
- Roadmap alignment matrix against `REBUILD-ROADMAP.md`.
- TDD contract checklist for risky architecture invariants.
- Final validation report.

### Definition of Done
- [ ] `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md` exits 0.
- [ ] `cd /opt/flowmanner/backend && python -m pytest tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/test_nexus_orchestrator_singleton.py tests/chaos/test_kill_worker_mid_mission.py tests/chaos/test_kill_worker_mid_mission_process.py -v --tb=short` passes.
- [ ] `cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit && npx vitest run && npx playwright test` passes.
- [ ] Final docs-pack validation report shows zero unresolved critical gaps.

### Must Have
- Evidence-backed claims with code/test/doc references.
- Explicit non-goals and stop gates.
- Roadmap alignment with `REBUILD-ROADMAP.md`.
- TDD contract checklist for risky architecture invariants.
- No implementation work in the planning phase.

### Must NOT Have
- Premature microservices.
- Service mesh for homelab.
- Full event sourcing everywhere.
- Actor-framework lock-in.
- Kubernetes-only self-hosting.
- NATS before outbox/event-schema stability.
- Unsupported provider-specific claims.
- One-shot repository restructure.
- Docs that contradict the active rebuild roadmap.

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (TDD for risky architecture contracts; characterization tests before refactoring existing behavior)
- **Framework**:
  - Backend: `pytest`
  - Frontend: Vitest + Playwright
  - Docs: custom validation harness
- **If TDD**: Each risky architecture contract gets a failing pre-implementation assertion, a pass condition, and an exact command.

### QA Policy
Every task MUST include agent-executed QA scenarios.

- **Docs**: validation script + link checker + cross-reference checks.
- **Backend**: substrate-critical pytest gate.
- **Frontend**: TypeScript, Vitest, Playwright.
- **Provider routing**: unresolved research gap must be flagged, not hand-waved.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation):
├── Task 1: Docs QA harness and validation contract
├── Task 2: Paradigm decision record and stop gates
└── Task 3: Architecture diagrams alignment

Wave 2 (Docs Alignment):
├── Task 4: Domain boundaries
├── Task 5: Execution-agent runtime
├── Task 6: Knowledge/events/data/provider layer
├── Task 7: Observability/deployment
└── Task 8: Roadmap/risks/not-build

Wave 3 (Final Pack):
├── Task 9: Final recommendation + current-state gaps
└── Task 10: Docs-pack QA and drift report

Wave FINAL (After ALL tasks):
├── F1: Plan compliance audit
├── F2: Code quality review
├── F3: Real manual QA
└── F4: Scope fidelity check
```

### Dependency Matrix

- **1**: - - 2, 3, 4, 5, 6, 7, 8, 9, 10
- **2**: 1 - 3, 4, 5, 6, 7, 8, 9, 10
- **3**: 1, 2 - 4, 5, 6, 7, 8, 9, 10
- **4**: 1, 2, 3 - 5, 6, 7, 8, 9, 10
- **5**: 1, 2, 3, 4 - 6, 7, 8, 9, 10
- **6**: 1, 2, 3, 4, 5 - 7, 8, 9, 10
- **7**: 1, 2, 3, 4, 5, 6 - 8, 9, 10
- **8**: 1, 2, 3, 4, 5, 6, 7 - 9, 10
- **9**: 1-8 - 10
- **10**: 1-9 - F1-F4

### Agent Dispatch Summary
- **Wave 1**: 3 tasks
  - Task 1: `writing`
  - Task 2: `writing`
  - Task 3: `writing`
- **Wave 2**: 5 tasks
  - Task 4: `writing`
  - Task 5: `writing`
  - Task 6: `writing`
  - Task 7: `writing`
  - Task 8: `writing`
- **Wave 3**: 2 tasks
  - Task 9: `writing`
  - Task 10: `writing`
- **FINAL**: 4 tasks
  - F1: `oracle`
  - F2: `unspecified-high`
  - F3: `unspecified-high`
  - F4: `deep`

---

## Tasks

- [x] 1. Add future-architecture docs QA harness and validation contract.
- [x] 2. Update 01 into explicit decision record with ADR sections.

  **What to do**:
  - Create a docs validation harness that checks docs `01-09`, the README, and `REBUILD-ROADMAP.md` references.
  - Validate required headings, cross-links, non-goal consistency, roadmap alignment, and explicit stop gates.
  - Add a TDD contract checklist for risky architecture invariants:
    - modular monolith boundary enforcement
    - event schema v1 before event backbone work
    - outbox-before-NATS stop gate
    - worker lease/checkpoint/idempotency contracts
    - provider abstraction and local/cloud routing contracts
    - self-hosted Docker Compose baseline
  - Define exact validation commands that later implementation tasks must run.
  - Add evidence capture rules under `.sisyphus/evidence/`.

  **Must NOT do**:
  - Modify backend/frontend source beyond the validation harness.
  - Add live provider or live LLM tests.
  - Claim provider routing details that are not source-backed.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is documentation infrastructure and architecture-contract writing.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep validation docs and acceptance criteria readable.
    - `software-architecture`: Ensure the harness enforces architectural boundaries and stop gates.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because the task defines TDD contracts but does not implement production behavior.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 foundation
  - **Blocks**: Tasks 2-10
  - **Blocked By**: None

  **References**:
  - `docs/future-architecture/01-paradigm-evaluation.md` - Canonical paradigm decision and non-goals.
  - `docs/future-architecture/02-architecture-diagrams.md` - Diagram consistency target.
  - `docs/future-architecture/03-domain-boundaries.md` - Domain ownership and anti-corruption rules.
  - `docs/future-architecture/04-execution-agent-runtime.md` - Durable execution and agent runtime contracts.
  - `docs/future-architecture/05-knowledge-events-data.md` - Event schema, provider abstraction, and memory contracts.
  - `docs/future-architecture/06-observability-deployment.md` - Observability and deployment stop gates.
  - `docs/future-architecture/07-roadmap-risks-not-build.md` - Roadmap, risks, and what not to build.
  - `docs/future-architecture/08-final-recommendation.md` - Final recommendation and non-negotiable principles.
  - `docs/future-architecture/09-current-state-gaps.md` - Current-state gap mapping.
  - `docs/REBUILD-ROADMAP.md` - Active rebuild roadmap that must remain aligned.

  **Acceptance Criteria**:
  - [ ] Validation harness exists and runs from the repo root.
  - [ ] Harness exits non-zero when a required future-architecture doc is missing.
  - [ ] Harness exits non-zero when a required non-goal is missing from `01`.
  - [ ] Harness exits non-zero when `REBUILD-ROADMAP.md` active items are not represented in the alignment matrix.
  - [ ] TDD contract checklist is present and lists exact commands for docs, backend substrate, and frontend checks.

  **QA Scenarios**:

  ```
  Scenario: Docs validation succeeds on the current pack
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert output includes `docs_validated=9`.
    Expected Result: Command exits 0 and reports all nine future-architecture docs validated.
    Failure Indicators: Missing doc, broken cross-link, missing stop gate, or missing roadmap alignment.
    Evidence: `.sisyphus/evidence/task-1-docs-validation-pass.txt`

  Scenario: Docs validation fails on missing non-goal
    Tool: Bash
    Preconditions: Use a temporary copy of `01-paradigm-evaluation.md` with the non-goal section removed.
    Steps:
      1. Remove the non-goal section from the temporary copy.
      2. Run the validation harness against the temporary copy.
      3. Assert exit code is non-zero and the error names the missing non-goal.
    Expected Result: Command exits non-zero and reports the missing non-goal.
    Evidence: `.sisyphus/evidence/task-1-docs-validation-fail-missing-nongoal.txt`

  Scenario: Substrate-critical test command is documented
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner/backend`.
    Steps:
      1. Run the exact substrate-critical pytest command listed in the plan.
      2. Assert all substrate-critical tests pass or are skipped for documented environment reasons.
    Expected Result: Substrate-critical gate is executable and passes.
    Evidence: `.sisyphus/evidence/task-1-substrate-critical-gate.txt`
  ```

  **Evidence to Capture**:
  - [ ] Validation harness output
  - [ ] Missing-non-goal failure output
  - [ ] Substrate-critical pytest output

  **Commit**: YES - group 1
  - Message: `docs(future-architecture): add QA harness`
  - Files: `scripts/validate_future_arch_docs.py`, `.sisyphus/plans/future-architecture-paradigm.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [x] 2. Update `01-paradigm-evaluation.md` into an explicit decision record

  **What to do**:
  - Rewrite `01` as an ADR-style decision record with:
    - context
    - decision
    - rationale
    - alternatives rejected
    - consequences
    - non-goals
    - stop gates
    - roadmap relationship
  - Preserve the existing hybrid architecture decision exactly.
  - Add explicit stop gates for:
    - no microservices default
    - no service mesh for homelab
    - no full event sourcing everywhere
    - no actor-framework lock-in
    - no NATS before outbox/event-schema stability
    - no Kubernetes-only self-hosting
  - Add a roadmap alignment note linking to `REBUILD-ROADMAP.md`.

  **Must NOT do**:
  - Change the paradigm decision.
  - Add implementation promises.
  - Claim provider routing is solved.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is architecture documentation refinement.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep the decision record direct and scannable.
    - `software-architecture`: Preserve architectural boundaries and stop gates.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this is documentation, not implementation.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 foundation
  - **Blocks**: Tasks 3-10
  - **Blocked By**: Task 1

  **References**:
  - `docs/future-architecture/01-paradigm-evaluation.md` - Source document to rewrite.
  - `docs/future-architecture/07-roadmap-risks-not-build.md` - Roadmap and risk framing.
  - `docs/future-architecture/08-final-recommendation.md` - Final recommendation and non-negotiables.
  - `docs/future-architecture/09-current-state-gaps.md` - Current-state gap context.
  - `docs/REBUILD-ROADMAP.md` - Active rebuild roadmap alignment.

  **Acceptance Criteria**:
  - [ ] `01` contains all ADR-style sections listed above.
  - [ ] `01` explicitly lists all six stop gates.
  - [ ] `01` references `REBUILD-ROADMAP.md`.
  - [ ] `01` does not contradict `07`, `08`, or `09`.
  - [ ] Validation harness reports `01` as valid.

  **QA Scenarios**:

  ```
  Scenario: Decision record validates cleanly
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert the output contains `01-paradigm-evaluation.md: valid`.
    Expected Result: `01` validates successfully.
    Failure Indicators: Missing section, missing stop gate, or roadmap mismatch.
    Evidence: `.sisyphus/evidence/task-2-decision-record-valid.txt`

  Scenario: Stop-gate grep check passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run a grep-style check for the six stop gates in `01`.
      2. Assert each gate appears at least once.
    Expected Result: All six stop gates are present.
    Failure Indicators: Any stop gate is absent.
    Evidence: `.sisyphus/evidence/task-2-stop-gates.txt`
  ```

  **Evidence to Capture**:
  - [ ] Validation output
  - [ ] Stop-gate presence output

  **Commit**: YES - group 2
  - Message: `docs(future-architecture): clarify paradigm decision record`
  - Files: `docs/future-architecture/01-paradigm-evaluation.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [x] 3. Align `02-architecture-diagrams.md` with the chosen paradigm

  **What to do**:
  - Update diagrams so they show:
    - modular monolith backend
    - event outbox
    - RabbitMQ as current compatibility layer
    - NATS JetStream only as a future Phase 4 dependency
    - stateless workers
    - provider abstraction
    - self-hosted Docker Compose baseline
    - Kubernetes-ready SaaS packaging later
  - Add labels for "current" vs "future" components.
  - Add a short note explaining why the diagram is not a microservice diagram.

  **Must NOT do**:
  - Depict microservices as the default backend shape.
  - Depict service mesh as a homelab requirement.
  - Depict NATS as already implemented.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is diagram/documentation alignment.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep diagram captions precise.
    - `software-architecture`: Ensure diagram topology matches the paradigm.
  - **Skills Evaluated but Omitted**:
    - `frontend-design`: Omitted because this is not UI design work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 with Tasks 1-2
  - **Blocks**: Tasks 4-10
  - **Blocked By**: Tasks 1-2

  **References**:
  - `docs/future-architecture/02-architecture-diagrams.md` - Diagram source.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Paradigm decision.
  - `docs/future-architecture/05-knowledge-events-data.md` - Event backbone and provider layer.
  - `docs/future-architecture/06-observability-deployment.md` - Deployment topology.
  - `docs/future-architecture/09-current-state-gaps.md` - Infrastructure reality check.

  **Acceptance Criteria**:
  - [ ] Diagram text contains all current/future labels.
  - [ ] Diagram text does not show microservices as default.
  - [ ] Diagram text does not show service mesh as homelab requirement.
  - [ ] Diagram text does not show NATS as already implemented.
  - [ ] Validation harness reports `02` as valid.

  **QA Scenarios**:

  ```
  Scenario: Diagram validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `02-architecture-diagrams.md: valid` appears.
    Expected Result: Diagram document validates successfully.
    Failure Indicators: Missing current/future labels or forbidden topology.
    Evidence: `.sisyphus/evidence/task-3-diagram-validation.txt`

  Scenario: Forbidden topology grep check passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Grep `02` for forbidden topology terms.
      2. Assert `microservices`, `service mesh`, and `NATS` appear only in future/non-goal context.
    Expected Result: Forbidden terms are either absent or explicitly non-goal/future.
    Failure Indicators: Forbidden terms appear as current defaults.
    Evidence: `.sisyphus/evidence/task-3-forbidden-topology.txt`
  ```

  **Evidence to Capture**:
  - [ ] Diagram validation output
  - [ ] Forbidden topology grep output

  **Commit**: YES - group 3
  - Message: `docs(future-architecture): align diagrams`
  - Files: `docs/future-architecture/02-architecture-diagrams.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [x] 4. Align `03-domain-boundaries.md` with modular monolith boundaries

  **What to do**:
  - Update `03` to define domain ownership, public APIs, events, invariants, and tests for each bounded domain.
  - Add explicit anti-corruption layers for legacy v1 mission APIs, Celery/RabbitMQ compatibility, external AI provider SDKs, and sandbox/tool boundaries.
  - Add module dependency rules and boundary-test expectations.
  - Add a roadmap note explaining that package layout changes must be incremental and test-backed.

  **Must NOT do**:
  - Perform or prescribe a one-shot repository restructure.
  - Allow domain services to import infrastructure adapters directly.
  - Allow other domains to mutate execution tables directly.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is architecture documentation for domain boundaries.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep boundary rules crisp.
    - `software-architecture`: Preserve DDD/clean-architecture boundaries.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task defines boundary contracts, not implementing them.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 5-8
  - **Blocks**: Tasks 9-10
  - **Blocked By**: Tasks 1-3

  **References**:
  - `docs/future-architecture/03-domain-boundaries.md` - Domain boundary source.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Modular monolith decision.
  - `docs/future-architecture/02-architecture-diagrams.md` - Domain map.
  - `docs/future-architecture/04-execution-agent-runtime.md` - Execution ownership.
  - `docs/future-architecture/09-current-state-gaps.md` - Package layout migration target.
  - `backend/tests/test_substrate_event_log.py` - Substrate event ownership pattern.
  - `backend/tests/test_substrate_replay.py` - Replay ownership pattern.

  **Acceptance Criteria**:
  - [ ] `03` lists domain ownership for User, Workspace, Agent, Workflow, Execution, Tool, Knowledge, Billing, and Observability.
  - [ ] `03` includes anti-corruption layers for legacy APIs, Celery/RabbitMQ, AI provider SDKs, and sandbox/tool boundaries.
  - [ ] `03` states that package layout changes must be incremental and test-backed.
  - [ ] Validation harness reports `03` as valid.

  **QA Scenarios**:

  ```
  Scenario: Domain boundary validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `03-domain-boundaries.md: valid` appears.
    Expected Result: Domain boundary document validates successfully.
    Failure Indicators: Missing ownership, missing anti-corruption layer, or invalid cross-link.
    Evidence: `.sisyphus/evidence/task-4-domain-boundaries-valid.txt`

  Scenario: Boundary-test expectation is documented
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Grep `03` for `boundary tests`.
      2. Assert the phrase appears in the migration notes.
    Expected Result: Boundary tests are explicitly required for package layout changes.
    Failure Indicators: Boundary tests are absent.
    Evidence: `.sisyphus/evidence/task-4-boundary-tests.txt`
  ```

  **Evidence to Capture**:
  - [ ] Domain boundary validation output
  - [ ] Boundary-test grep output

  **Commit**: YES - group 4
  - Message: `docs(future-architecture): align domain boundaries`
  - Files: `docs/future-architecture/03-domain-boundaries.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [x] 5. Align `04-execution-agent-runtime.md` with durable execution and worker plane

  **What to do**:
  - Update `04` to document durable execution state machine, worker leases, checkpoint strategy, retry/failure taxonomy, HITL pause/resume, idempotency keys, crash recovery, replay, agent lifecycle, tool capability checks, and context builder rules.
  - Add a TDD contract checklist for worker crash before checkpoint, lease expiry and stale-lease reclaim, idempotent task execution, replay determinism, and HITL pause/resume.
  - Add references to existing substrate tests and chaos tests.

  **Must NOT do**:
  - Introduce a custom actor framework.
  - Allow in-process-only agent state.
  - Claim execution is production-complete.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is architecture documentation for execution and agent runtime.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep runtime rules readable.
    - `software-architecture`: Preserve durable execution and runtime boundaries.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task documents contracts, not implementing them.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 4, 6, 7, 8
  - **Blocks**: Tasks 9-10
  - **Blocked By**: Tasks 1-3

  **References**:
  - `docs/future-architecture/04-execution-agent-runtime.md` - Runtime source.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Durable substrate decision.
  - `docs/future-architecture/09-current-state-gaps.md` - Worker leases, checkpointing, replay gaps.
  - `backend/tests/test_substrate_event_log.py` - Event log behavior.
  - `backend/tests/test_substrate_replay.py` - Replay behavior.
  - `backend/tests/chaos/test_kill_worker_mid_mission.py` - Crash recovery behavior.
  - `backend/tests/chaos/test_kill_worker_mid_mission_process.py` - Process-level crash recovery.
  - `backend/tests/test_unified_executor.py` - Executor behavior.
  - `backend/tests/test_node_executor.py` - Node execution behavior.

  **Acceptance Criteria**:
  - [ ] `04` includes worker lease semantics and stale-lease recovery.
  - [ ] `04` includes checkpoint strategy and crash recovery.
  - [ ] `04` includes HITL pause/resume and idempotency keys.
  - [ ] `04` includes agent lifecycle and tool capability checks.
  - [ ] `04` does not mention actor-framework lock-in as a requirement.

  **QA Scenarios**:

  ```
  Scenario: Runtime document validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `04-execution-agent-runtime.md: valid` appears.
    Expected Result: Runtime document validates successfully.
    Failure Indicators: Missing lease, checkpoint, HITL, or idempotency sections.
    Evidence: `.sisyphus/evidence/task-5-runtime-valid.txt`

  Scenario: Substrate-critical pytest gate passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner/backend`.
    Steps:
      1. Run the exact substrate-critical pytest command listed in the plan.
      2. Assert exit code is 0.
    Expected Result: Substrate-critical tests pass.
    Failure Indicators: Any substrate-critical test fails.
    Evidence: `.sisyphus/evidence/task-5-substrate-critical.txt`
  ```

  **Evidence to Capture**:
  - [ ] Runtime validation output
  - [ ] Substrate-critical pytest output

  **Commit**: YES - group 5
  - Message: `docs(future-architecture): align execution runtime`
  - Files: `docs/future-architecture/04-execution-agent-runtime.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [x] 6. Align `05-knowledge-events-data.md` with event schema, outbox, and provider abstraction

  **What to do**:
  - Update `05` to define event schema v1, Postgres outbox, RabbitMQ compatibility, NATS JetStream as future Phase 4, provider abstraction, provider registry, local/cloud routing rules, knowledge events, and memory retention/deletion.
  - Add a TDD contract checklist for event schema fields, outbox transaction boundary, provider adapter interface, provider health checks, local/cloud fallback, and knowledge event consumers.
  - Explicitly flag provider routing research as unresolved until source-backed.

  **Must NOT do**:
  - Introduce NATS before outbox/event-schema stability.
  - Claim provider routing details that are not source-backed.
  - Make provider-specific SDK calls part of business logic.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is architecture documentation for events, data, and provider abstraction.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep event and provider contracts concise.
    - `software-architecture`: Preserve provider abstraction and event boundaries.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task documents contracts, not implementing them.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 4, 5, 7, 8
  - **Blocks**: Tasks 9-10
  - **Blocked By**: Tasks 1-3

  **References**:
  - `docs/future-architecture/05-knowledge-events-data.md` - Event/data/provider source.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Provider abstraction and bounded event sourcing.
  - `docs/future-architecture/09-current-state-gaps.md` - Event outbox and provider abstraction gaps.
  - `backend/tests/test_integration_model_router.py` - Model routing integration context.
  - `backend/tests/test_integration_byok_streaming.py` - BYOK streaming context.
  - `backend/tests/test_mission_executor.py` - Mission execution context.
  - `backend/tests/test_mission_execution_api.py` - Execution API context.

  **Acceptance Criteria**:
  - [ ] `05` includes event schema v1 and outbox transaction boundary.
  - [ ] `05` includes RabbitMQ compatibility and NATS as future Phase 4 only.
  - [ ] `05` includes provider abstraction, provider registry, and local/cloud routing rules.
  - [ ] `05` explicitly flags provider routing research as unresolved.
  - [ ] Validation harness reports `05` as valid.

  **QA Scenarios**:

  ```
  Scenario: Event/provider document validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `05-knowledge-events-data.md: valid` appears.
    Expected Result: Event/provider document validates successfully.
    Failure Indicators: Missing event schema, outbox, provider abstraction, or unresolved research flag.
    Evidence: `.sisyphus/evidence/task-6-event-provider-valid.txt`

  Scenario: Provider routing unresolved flag is present
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Grep `05` for `provider routing research` or equivalent unresolved research flag.
      2. Assert the phrase appears.
    Expected Result: Provider routing research is explicitly unresolved.
    Failure Indicators: Provider routing is described as solved without source-backed evidence.
    Evidence: `.sisyphus/evidence/task-6-provider-unresolved.txt`
  ```

  **Evidence to Capture**:
  - [ ] Event/provider validation output
  - [ ] Provider unresolved flag output

  **Commit**: YES - group 6
  - Message: `docs(future-architecture): align knowledge and provider layer`
  - Files: `docs/future-architecture/05-knowledge-events-data.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [x] 7. Align `06-observability-deployment.md` with self-hosted/SaaS split

  **What to do**:
  - Update `06` to define required identifiers, trace/metric/log/event/alert layers, replay levels, SLOs, self-hosted Docker Compose baseline, SaaS Kubernetes-ready packaging, no service mesh for homelab, and health/deep-health expectations.
  - Add a TDD contract checklist for request/run/task/event correlation IDs, worker availability SLO, event append latency SLO, model fallback success SLO, and self-hosted health checks.
  - Add explicit deployment stop gate: Kubernetes is optional, not mandatory for self-hosting.

  **Must NOT do**:
  - Introduce service mesh for homelab.
  - Make Kubernetes mandatory for self-hosted deployments.
  - Claim observability is complete without deep-health checks.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is architecture documentation for observability and deployment.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep deployment and observability rules concise.
    - `software-architecture`: Preserve self-hosted/SaaS split and observability boundaries.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task documents contracts, not implementing them.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 4, 5, 6, 8
  - **Blocks**: Tasks 9-10
  - **Blocked By**: Tasks 1-3

  **References**:
  - `docs/future-architecture/06-observability-deployment.md` - Observability/deployment source.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Self-hosted simplicity and SaaS readiness.
  - `docs/future-architecture/09-current-state-gaps.md` - Deployment and observability gaps.
  - `docs/REBUILD-ROADMAP.md` - CI and observability/deep-health active roadmap items.
  - `backend/tests/test_health.py` - Health endpoint context.
  - `backend/tests/test_workspace_audit_logging.py` - Audit logging context.
  - `backend/tests/test_usage_api.py` - Usage API context.

  **Acceptance Criteria**:
  - [ ] `06` includes required identifiers and SLOs.
  - [ ] `06` includes self-hosted Docker Compose baseline and optional SaaS Kubernetes packaging.
  - [ ] `06` explicitly says no service mesh for homelab.
  - [ ] `06` includes deep-health expectations.
  - [ ] Validation harness reports `06` as valid.

  **QA Scenarios**:

  ```
  Scenario: Observability/deployment document validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `06-observability-deployment.md: valid` appears.
    Expected Result: Observability/deployment document validates successfully.
    Failure Indicators: Missing identifiers, SLOs, self-hosted baseline, or deep-health expectations.
    Evidence: `.sisyphus/evidence/task-7-observability-deployment-valid.txt`

  Scenario: No service mesh for homelab is documented
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Grep `06` for `service mesh`.
      2. Assert it appears only as a non-goal or future exclusion.
    Expected Result: Service mesh is not presented as homelab requirement.
    Failure Indicators: Service mesh appears as current or required homelab infrastructure.
    Evidence: `.sisyphus/evidence/task-7-no-service-mesh.txt`
  ```

  **Evidence to Capture**:
  - [ ] Observability/deployment validation output
  - [ ] No-service-mesh grep output

  **Commit**: YES - group 7
  - Message: `docs(future-architecture): align observability and deployment`
  - Files: `docs/future-architecture/06-observability-deployment.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [ ] 8. Align `07-roadmap-risks-not-build.md` with the active rebuild roadmap

  **What to do**:
  - Update `07` to map each active `REBUILD-ROADMAP.md` item to future-architecture impact.
  - Add explicit stop gates and risk mitigations for code_execute production issue, CI pipeline hardening, Sentry/Jaeger/deep-health baseline, Blueprint+Run unification, substrate executor/chaos tests, and chat UX fixes.
  - Add a 12/24-month roadmap and 5-year vision section.
  - Add a "What NOT to Build" section that mirrors `01` non-goals.

  **Must NOT do**:
  - Supersede the active rebuild roadmap.
  - Add new roadmap phases without explicit approval.
  - Turn this into a feature backlog.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is roadmap and risk documentation.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep roadmap and risk sections crisp.
    - `software-architecture`: Preserve roadmap alignment and stop gates.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task documents roadmap alignment, not implementing it.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 4, 5, 6, 7
  - **Blocks**: Tasks 9-10
  - **Blocked By**: Tasks 1-3

  **References**:
  - `docs/future-architecture/07-roadmap-risks-not-build.md` - Roadmap/risk source.
  - `docs/REBUILD-ROADMAP.md` - Active roadmap.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Non-goals and paradigm.
  - `docs/future-architecture/08-final-recommendation.md` - Final recommendation.
  - `docs/future-architecture/09-current-state-gaps.md` - Current-state gaps.

  **Acceptance Criteria**:
  - [ ] `07` maps every active `REBUILD-ROADMAP.md` item to future-architecture impact.
  - [ ] `07` includes 12/24-month roadmap and 5-year vision.
  - [ ] `07` includes a "What NOT to Build" section.
  - [ ] `07` does not supersede the active rebuild roadmap.
  - [ ] Validation harness reports `07` as valid.

  **QA Scenarios**:

  ```
  Scenario: Roadmap alignment validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `07-roadmap-risks-not-build.md: valid` appears.
    Expected Result: Roadmap document validates successfully.
    Failure Indicators: Missing roadmap mapping, missing 12/24-month plan, or missing 5-year vision.
    Evidence: `.sisyphus/evidence/task-8-roadmap-valid.txt`

  Scenario: Active rebuild items are represented
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Grep `07` for each active rebuild item name.
      2. Assert all required names appear.
    Expected Result: Every active rebuild item is represented.
    Failure Indicators: Any active item is absent.
    Evidence: `.sisyphus/evidence/task-8-active-rebuild-items.txt`
  ```

  **Evidence to Capture**:
  - [ ] Roadmap validation output
  - [ ] Active rebuild items grep output

  **Commit**: YES - group 8
  - Message: `docs(future-architecture): align roadmap and non-goals`
  - Files: `docs/future-architecture/07-roadmap-risks-not-build.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [ ] 9. Align `08-final-recommendation.md` and `09-current-state-gaps.md`

  **What to do**:
  - Update `08` to reflect the final architecture pack, non-negotiable principles, and phased implementation stance.
  - Update `09` to connect future-state targets to current-state gaps with evidence references.
  - Add explicit unresolved gaps:
    - provider routing research
    - event outbox
    - worker leases
    - checkpointing
    - knowledge from events
    - replay UI
    - package layout
  - Add "next safe steps" that preserve the active rebuild roadmap.

  **Must NOT do**:
  - Claim implementation is complete.
  - Replace `REBUILD-ROADMAP.md`.
  - Hide unresolved gaps.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is final recommendation and gap documentation.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep final recommendation and gap tables concise.
    - `software-architecture`: Preserve phased implementation and non-goal guardrails.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task documents gaps, not implementing them.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 final pack
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1-8

  **References**:
  - `docs/future-architecture/08-final-recommendation.md` - Final recommendation source.
  - `docs/future-architecture/09-current-state-gaps.md` - Current-state gap source.
  - `docs/future-architecture/01-paradigm-evaluation.md` - Paradigm decision.
  - `docs/future-architecture/02-architecture-diagrams.md` - Diagram consistency.
  - `docs/future-architecture/03-domain-boundaries.md` - Domain boundaries.
  - `docs/future-architecture/04-execution-agent-runtime.md` - Execution/agent runtime.
  - `docs/future-architecture/05-knowledge-events-data.md` - Events/data/provider layer.
  - `docs/future-architecture/06-observability-deployment.md` - Observability/deployment.
  - `docs/future-architecture/07-roadmap-risks-not-build.md` - Roadmap/risks/not-build.
  - `docs/REBUILD-ROADMAP.md` - Active rebuild roadmap.

  **Acceptance Criteria**:
  - [ ] `08` states the final architecture as phased and implementation-ready.
  - [ ] `09` includes all unresolved current-state gaps.
  - [ ] `09` preserves the active rebuild roadmap.
  - [ ] Validation harness reports `08` and `09` as valid.
  - [ ] No unresolved gap is hidden or marked complete without evidence.

  **QA Scenarios**:

  ```
  Scenario: Final recommendation and gaps validate
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert `08-final-recommendation.md: valid` and `09-current-state-gaps.md: valid` appear.
    Expected Result: Final recommendation and current-state gap docs validate successfully.
    Failure Indicators: Missing unresolved gap or invalid cross-link.
    Evidence: `.sisyphus/evidence/task-9-final-gaps-valid.txt`

  Scenario: No hidden unresolved gaps
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Grep `09` for each unresolved gap label.
      2. Assert all labels appear.
    Expected Result: Provider routing, event outbox, worker leases, checkpointing, knowledge from events, replay UI, and package layout are explicitly listed.
    Failure Indicators: Any unresolved gap is absent.
    Evidence: `.sisyphus/evidence/task-9-unresolved-gaps.txt`
  ```

  **Evidence to Capture**:
  - [ ] Final recommendation validation output
  - [ ] Current-state gaps validation output
  - [ ] Unresolved gap grep output

  **Commit**: YES - group 9
  - Message: `docs(future-architecture): align final recommendation and gaps`
  - Files: `docs/future-architecture/08-final-recommendation.md`, `docs/future-architecture/09-current-state-gaps.md`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

- [ ] 10. Run final docs-pack QA and drift report

  **What to do**:
  - Run the full validation harness across `docs/future-architecture`.
  - Run backend substrate-critical pytest gate.
  - Run frontend TypeScript, Vitest, and Playwright checks.
  - Produce a drift report that maps every task to evidence and command output.
  - Fix any validation failures and rerun the relevant checks.

  **Must NOT do**:
  - Modify source beyond docs/scripts/tests.
  - Claim completion if any validation fails.
  - Skip frontend checks because local source is outside `/opt/flowmanner`.

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: This is final documentation QA and reporting.
  - **Skills**: [`write-concisely`, `software-architecture`]
    - `write-concisely`: Keep the drift report readable.
    - `software-architecture`: Ensure final pack remains aligned with architecture and roadmap.
  - **Skills Evaluated but Omitted**:
    - `test-driven-development`: Omitted because this task is final validation, not implementation.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 final pack
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 1-9

  **References**:
  - `docs/future-architecture/01-paradigm-evaluation.md`
  - `docs/future-architecture/02-architecture-diagrams.md`
  - `docs/future-architecture/03-domain-boundaries.md`
  - `docs/future-architecture/04-execution-agent-runtime.md`
  - `docs/future-architecture/05-knowledge-events-data.md`
  - `docs/future-architecture/06-observability-deployment.md`
  - `docs/future-architecture/07-roadmap-risks-not-build.md`
  - `docs/future-architecture/08-final-recommendation.md`
  - `docs/future-architecture/09-current-state-gaps.md`
  - `docs/REBUILD-ROADMAP.md`

  **Acceptance Criteria**:
  - [ ] Validation harness exits 0.
  - [ ] Backend substrate-critical pytest gate exits 0.
  - [ ] Frontend TypeScript, Vitest, and Playwright checks exit 0.
  - [ ] Drift report exists under `.sisyphus/evidence/`.
  - [ ] Provider routing unresolved status is explicitly captured.

  **QA Scenarios**:

  ```
  Scenario: Full docs-pack validation passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner`.
    Steps:
      1. Run `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`.
      2. Assert exit code is 0.
      3. Assert output includes `docs_validated=9`.
    Expected Result: All docs validate successfully.
    Failure Indicators: Any doc validation failure.
    Evidence: `.sisyphus/evidence/task-10-docs-pack-validation.txt`

  Scenario: Backend substrate-critical gate passes
    Tool: Bash
    Preconditions: Run from `/opt/flowmanner/backend`.
    Steps:
      1. Run the exact substrate-critical pytest command listed in the plan.
      2. Assert exit code is 0.
    Expected Result: Substrate-critical tests pass.
    Failure Indicators: Any substrate-critical test fails.
    Evidence: `.sisyphus/evidence/task-10-substrate-critical.txt`

  Scenario: Frontend checks pass
    Tool: Bash
    Preconditions: Run from `/home/glenn/FlowmannerV2-frontend`.
    Steps:
      1. Run `npx tsc --noEmit`.
      2. Run `npx vitest run`.
      3. Run `npx playwright test`.
      4. Assert all three commands exit 0.
    Expected Result: Frontend checks pass.
    Failure Indicators: TypeScript, Vitest, or Playwright failure.
    Evidence: `.sisyphus/evidence/task-10-frontend-checks.txt`
  ```

  **Evidence to Capture**:
  - [ ] Docs-pack validation output
  - [ ] Backend substrate-critical output
  - [ ] Frontend checks output
  - [ ] Drift report

  **Commit**: YES - group 10
  - Message: `docs(future-architecture): validate pack and close drift`
  - Files: `.sisyphus/evidence/task-10-*.txt`
  - Pre-commit: `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run the exact verification commands from the plan:
  - `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`
  - `cd /opt/flowmanner/backend && python -m pytest tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/test_nexus_orchestrator_singleton.py tests/chaos/test_kill_worker_mid_mission.py tests/chaos/test_kill_worker_mid_mission_process.py -v --tb=short`
  - `cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit && npx vitest run && npx playwright test`
  Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports, unsupported provider claims, and roadmap contradictions. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp).
  Output: `Docs validation [PASS/FAIL] | Backend tests [N pass/N fail] | Frontend checks [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill if UI)
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (features working together, not isolation). Test edge cases: empty state, invalid input, rapid actions. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `docs(future-architecture): add QA harness`
- **2**: `docs(future-architecture): clarify paradigm decision record`
- **3**: `docs(future-architecture): align diagrams`
- **4**: `docs(future-architecture): align domain boundaries`
- **5**: `docs(future-architecture): align execution runtime`
- **6**: `docs(future-architecture): align knowledge and provider layer`
- **7**: `docs(future-architecture): align observability and deployment`
- **8**: `docs(future-architecture): align roadmap and non-goals`
- **9**: `docs(future-architecture): align final recommendation and gaps`
- **10**: `docs(future-architecture): validate pack and close drift`

---

## Success Criteria

### Verification Commands
```bash
python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md
cd /opt/flowmanner/backend && python -m pytest tests/test_substrate_event_log.py tests/test_substrate_replay.py tests/test_failure_analyzer_budgets.py tests/test_meta_loop_orchestrator_budgets.py tests/test_trigger_bridge.py tests/test_nexus_orchestrator_singleton.py tests/chaos/test_kill_worker_mid_mission.py tests/chaos/test_kill_worker_mid_mission_process.py -v --tb=short
cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit && npx vitest run && npx playwright test
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Provider routing unresolved items are explicitly flagged
- [ ] No contradictions between `01` and `02-09`
- [ ] Roadmap alignment is complete
- [ ] Docs QA harness exits 0
