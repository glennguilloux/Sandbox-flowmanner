# Handoff — Phase 6: Prompt Versioning, Eval Runs, Redis Caching

**Completed:** Earlier session (2026-07-06)
**Deployed:** ✅ Both deployed to VPS

---

## Summary

Phase 6 implemented three features:

1. **Prompt versioning** — Versioned system prompts per workspace. CRUD API at `/api/v2/prompts/`. Redis caching layer for performance. Frontend `PromptVersionDropdown` in settings.

2. **Eval runs** — Trigger eval suites against golden datasets. API at `/api/v2/eval_runs/`. Frontend `EvalSuiteManager` for creating/managing suites, `ReliabilityTab` for viewing results.

3. **Redis caching** — Prompt versions cached in Redis. Fallback to DB if Redis unavailable.

## Gotchas for Next Agent

- Redis must be running for prompt version caching
- Eval suites reference `GoldenDataset` and `GoldenTestCase` models — seed data may be needed
- The prompts API supports workspace-scoped versioning — `workspace_id` is required for all operations
