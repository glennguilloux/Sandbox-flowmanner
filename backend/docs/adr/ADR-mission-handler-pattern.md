# ADR: Mission Handler Pattern for Flowmanner

**Status:** Accepted
**Date:** 2026-06-02
**Decision-maker:** Architecture review (A.4 cross-cutting concerns)

---

## Context

Flowmanner's mission API has 60+ endpoints across v1 and v2, with complex
lifecycle management (create, plan, execute, pause, resume, abort, retry)
and growing cross-cutting concerns (auditing, idempotency, rate limiting,
soft delete). We need a handler pattern that keeps routes thin, keeps
business logic testable, and accommodates cross-cutting concerns without
bloating route functions.

Three patterns were evaluated:

### Pattern A: Thin-route + shared handler layer (current)

Routes are < 10 lines. Logic lives in `_mission_cqrs/commands.py` and
`queries.py` handler classes, injected via FastAPI DI. Transactions are
explicit in handlers via `wrap_command()`. Cross-cutting concerns are
injected as optional dependencies (`AuditService`, `IdempotencyDependency`).

### Pattern B: Service-layer-only orchestration

Routes call a single orchestrator service (`MissionOrchestrator`) that
handles everything: validation, transaction management, auditing, side
effects. No CQRS separation.

### Pattern C: Repository-heavy pattern

Repository classes wrap every query. Handlers call repositories, which
call services, which call other repositories. Deep layering with full
unit-test isolation via mock injection at every boundary.

---

## Decision

**Pattern A (thin-route + CQRS handlers) is retained** with the following
augmentation: cross-cutting concerns (audit, idempotency, rate limiting)
are injected as optional, swappable dependencies into command/query
handlers via the FastAPI DI system.

---

## Evaluation

| Criterion | A (Current) | B (Service-only) | C (Repository-heavy) |
|-----------|-------------|-------------------|----------------------|
| Route thinness | ★★★ < 10 lines | ★★ depends on orchestrator | ★★ depends on DI |
| Testability | ★★★ mock handler or inject test doubles | ★★ mock orchestrator | ★★★ fully isolated |
| Cross-cutting fit | ★★★ inject into handler via DI | ★★ add to orchestrator | ★ add to every repo |
| Transaction clarity | ★★★ explicit `wrap_command()` | ★★ implicit in orchestrator | ★ hidden behind repos |
| Coupling risk | ★★ handlers depend on services | ★★★ single orchestrator | ★ every layer couples |
| onboarding cost | ★★ understand CQRS split | ★★★ find the orchestrator | ★ understand layering |

### Why we stay with Pattern A

1. **Explicit transaction boundaries.** `wrap_command()` makes it visible
   where commits happen. Pattern B hides them; Pattern C scatters them.

2. **Natural home for cross-cutting concerns.** Idempotency, rate limiting,
   and auditing slot into handlers as DI-injected dependencies without
   touching route code. Pattern B would bloat the orchestrator. Pattern C
   would need every repository to deal with them.

3. **Domain fit.** Mission mutations have distinct, non-uniform side
   effects (WebSocket emits, analytics tracking, audit logging). A
   command-handler-per-operation gives each mutation the exact set of
   concerns it needs. No one-size-fits-all orchestrator.

4. **Testability without deep mocking.** Command handlers are testable
   with a mock AsyncSession + optional mock AuditService. Pattern C
   requires mocking at every layer boundary.

### Trade-offs accepted

- **Duplication of concern wiring.** Each handler method that needs
  auditing explicitly calls `self.audit.mission_xxx()`. This is deliberate:
  it makes the audit trail visible in code rather than hidden behind
  aspect-oriented magic. The `AuditService` provides convenience helpers
  to keep calls one-liners.

- **Handler file size.** `commands.py` is long (~450 lines). This is
  acceptable because it is one coherent concern (mission mutations).
  If it grows beyond ~800 lines, split by sub-domain (e.g.,
  `commands_execution.py`, `commands_lifecycle.py`).

---

## Consequences

### Positive

- Route files stay trivially thin (validated: all under 10 lines)
- New cross-cutting concerns (audit, idempotency, rate limiting) added
  without changing route signatures
- Transaction boundaries remain explicit and reviewable
- Handlers remain testable with standard mock AsyncSession patterns

### Negative

- Handler classes grow with each new mutation operation
- CI/CD must ensure all mutation paths consistently call audit helpers
  (mitigated by integration tests that verify audit events)

### Mitigations

- Integration test: create a mission → assert audit log entry exists
- Lint rule (future): check that every `MissionCommandHandlers` method
  that calls `self.session.commit()` also calls `self.audit.record()`
