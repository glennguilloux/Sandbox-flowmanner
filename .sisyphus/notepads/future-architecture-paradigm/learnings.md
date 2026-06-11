# future-architecture-paradigm learnings

## Session conventions
- Plan selected because Task 1 was already checked in the plan.
- No inherited wisdom yet; append task findings after each verified delegation.

## 2026-06-11 Task 1 non-goal harness fix
- `scripts/validate_future_arch_docs.py` now checks exact required stop-gate phrases in `docs/future-architecture/01-paradigm-evaluation.md` instead of broad regexes that could match the decision paragraph.
- Missing stop gates now fail validation with the missing non-goal label and exact phrase, e.g. `missing non-goal/stop gate: no microservices default (No microservices default.)`.
- Added focused pytest coverage in `scripts/tests/test_validate_future_arch_docs.py` for current-pack success and removed Stop Gates failure.
- Verified with `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md`, a temporary-copy negative run, and `python -m pytest scripts/tests/test_validate_future_arch_docs.py -q`.

## 2026-06-11 Task 1 NATS stop-gate wording fix
- `REQUIRED_NON_GOALS` now accepts both NATS gate wordings: `No NATS before outbox and event-schema stability.` and `No NATS before outbox/event-schema stability.`
- Missing NATS gate errors now include the label plus both accepted exact phrases, so single-line removal cannot pass silently.
- Focused pytest now covers current-pack success, slash-variant acceptance, full Stop Gates removal, and single NATS gate removal.
- Verified with real-pack validation, `python scripts/validate_future_arch_docs.py --self-test`, focused pytest, and temp-copy negative checks for single NATS removal plus full Stop Gates removal.

## 2026-06-11 Task 2 ADR decision record rewrite
- Rewrote `docs/future-architecture/01-paradigm-evaluation.md` as an explicit ADR with Context, Decision, Rationale, Alternatives Rejected, Consequences, Non-Goals, Stop Gates, and Roadmap Relationship.
- Preserved the hybrid decision text `Modular Monolith + Event-Driven Durable Substrate + Distributed Worker Plane` and all six exact stop-gate phrases.
- Added `docs/REBUILD-ROADMAP.md` as the active near-term source of truth and kept provider routing unresolved until source-backed research lands.
- Saved validation evidence in `.sisyphus/evidence/task-2-decision-record-valid.txt` and stop-gate evidence in `.sisyphus/evidence/task-2-stop-gates.txt`.
- Verified with `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md --evidence .sisyphus/evidence/task-2-decision-record-valid.txt`; output reported `01-paradigm-evaluation.md: valid`.
- Markdown LSP diagnostics were unavailable because no `.md` language server is configured in this environment.

## 2026-06-11 Task 3 diagram alignment
- Updated `docs/future-architecture/02-architecture-diagrams.md` with a Current/Future legend near the top.
- Labeled the main diagram with current, future, future Phase 4, and future SaaS packaging markers.
- Kept RabbitMQ as the current compatibility layer and NATS JetStream as a future Phase 4 dependency only.
- Added an explicit note that the diagram is not a microservice diagram and that domain boxes are modules inside one modular monolith backend.
- Added deployment labels for the self-hosted Docker Compose baseline and Kubernetes-ready SaaS packaging later.
- Verified with `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md --evidence .sisyphus/evidence/task-3-diagram-validation.txt`; output reported `02-architecture-diagrams.md: valid`.
- Saved forbidden topology and dash evidence to `.sisyphus/evidence/task-3-forbidden-topology.txt`.


## 2026-06-11 Task 4 domain boundaries
- Expanded `docs/future-architecture/03-domain-boundaries.md` with a domain ownership matrix that includes public APIs, emitted events, invariants, and required tests for User, Workspace, Agent, Workflow, Execution, Tool, Knowledge, Billing, and Observability.
- Made anti-corruption layers explicit for legacy v1 mission APIs, Celery/RabbitMQ compatibility, external AI provider SDKs, and sandbox/tool boundaries.
- Corrected module dependency direction so domain services depend on ports only and infrastructure adapters depend on ports, never the reverse.
- Added boundary-test expectations and a package layout migration roadmap that requires incremental, test-backed moves rather than a one-shot restructure.
- Verified with `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md --evidence .sisyphus/evidence/task-4-domain-boundaries-valid.txt`; output reported `03-domain-boundaries.md: valid`.
- Saved targeted boundary evidence in `.sisyphus/evidence/task-4-boundary-tests.txt` and dash-style evidence in `.sisyphus/evidence/task-4-dash-style.txt`.


## 2026-06-11 Task 5 runtime durable execution doc
- Updated `docs/future-architecture/04-execution-agent-runtime.md` to make durable execution explicit: state machine, worker leases, stale-lease reclaim, checkpoint boundaries, crash-before-checkpoint handling, retry/failure taxonomy, HITL pause/resume, idempotency keys, replay, agent lifecycle, context builder rules, and tool capability checks.
- Added TDD checklist coverage for worker crash before checkpoint, lease expiry and stale-lease reclaim, idempotent task execution, replay determinism, and HITL pause/resume.
- Added substrate and chaos references: `backend/tests/test_substrate_event_log.py`, `backend/tests/test_substrate_replay.py`, `backend/tests/chaos/test_kill_worker_mid_mission.py`, and `backend/tests/chaos/test_kill_worker_mid_mission_process.py`.
- Removed em dash and en dash characters from `04-execution-agent-runtime.md` and avoided actor-framework lock-in language.
- Verified with `python scripts/validate_future_arch_docs.py --root docs/future-architecture --roadmap docs/REBUILD-ROADMAP.md --evidence .sisyphus/evidence/task-5-runtime-valid.txt`; output reported `04-execution-agent-runtime.md: valid`.
- Saved targeted substrate evidence to `.sisyphus/evidence/task-5-substrate-critical.txt`.
