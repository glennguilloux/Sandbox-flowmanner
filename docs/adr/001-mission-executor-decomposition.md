# ADR-001: Decompose MissionExecutor into Focused Sub-Modules

**Status**: Accepted
**Date**: 2026-06-02
**Deciders**: Codebuff (via Phase 3.1)

## Context

The `MissionExecutor` class had grown to 1,362 lines, mixing concerns for cost tracking, LLM execution, browser automation, mission planning, and task dispatch. This made testing, maintenance, and reasoning about individual subsystems difficult.

## Decision

Decompose `MissionExecutor` into five focused modules, each with a single responsibility:

| Module | LOC | Responsibility |
|--------|-----|----------------|
| `cost_tracker.py` | 82 | LLM cost estimation and call recording |
| `llm_executor.py` | 165 | LLM-based task execution with agent prompts |
| `browser_task_runner.py` | 97 | Browser automation tool dispatch |
| `mission_planner.py` | 395 | LLM-driven plan generation |
| `task_executor.py` | 506 | Task execution dispatch across all backends |

`MissionExecutor` itself shrinks to ~580 LOC as a pure orchestrator.

## Alternatives Considered

1. **Keep the god class, extract only helpers** — Rejected: doesn't solve testability or cognitive complexity
2. **Split into a class hierarchy** — Rejected: inheritance introduces coupling; composition is preferred
3. **Micro-services** — Rejected: over-engineered for the current scale

## Design Patterns Used

- **Constructor injection**: All dependencies passed at init time
- **Callable pattern**: Deferred dependencies (ModelRouter, RAGService) passed as lambda/callable
- **Callback pattern**: `MissionPlanner` receives `log_callback` and `transition_callback` to avoid circular imports
- **Lazy import**: `BrowserTaskRunner` uses `_import_browser_tools()` to defer tool registry loading

## Consequences

### Positive
- Each module independently testable (128 new unit tests)
- Clear boundaries enable parallel development
- `MissionExecutor` is now readable as an orchestration script
- No circular imports despite tight coupling between planner/executor

### Negative
- More files to navigate (5 modules replace methods in 1 file)
- Constructor wiring requires awareness of dependency order

### Mitigations
- Architecture documentation (this document, `mission-architecture.md`)
- Consistent dependency injection pattern across all modules
- Google-style docstrings on all public methods
