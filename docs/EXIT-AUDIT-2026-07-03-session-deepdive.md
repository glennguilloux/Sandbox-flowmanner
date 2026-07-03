# Exit Audit — 2026-07-03 Deep-Dive Report Implementation

=== EXIT AUDIT ===

WHAT CHANGED (one bullet per file, what + why):
  - backend/app/services/improvement/causal_decomposer.py: Replaced 3 cloud model refs (gpt-4, claude-3-opus, gpt-4-32k) with local model identifiers (qwen3.6-27b-mtp, qwopus3.6-35b-a3b-coder-mtp) per P1-C2
  - backend/app/services/evaluation/llm_judge.py: Routed LLM calls through BudgetEnforcer.call_simple() instead of direct httpx; removed dead api_base/api_key constructor params per P1-C1
  - backend/app/services/evaluation/eval_runner.py: Routed LLM calls through BudgetEnforcer.call_simple(); gated Langfuse behind settings.LANGFUSE_ENABLED; removed httpx import per P1-C1
  - backend/app/services/budget_enforcer.py: Added call_simple() convenience method for eval/judge calls; added local model pricing entries (qwen3.6-27b-mtp, qwopus3.6-35b-a3b-coder-mtp, ornith-1.0-35b) at $0.00 per P1-C1
  - backend/app/config.py: Added SENTRY_WEBHOOK_SECRET validation (>=16 chars) in production; annotated LANGFUSE_ENABLED per Glenn-8
  - docker-compose.yml: Deleted Jaeger service entirely; commented out OTLP_ENDPOINT from backend env per Glenn-7
  - docker-compose.dev.yml: Commented out OTLP_ENDPOINT per Glenn-7
  - docs/DEEP-DIVE-REPORT-2026-07-03.md: Added Glenn's answers to 8 open questions

WHAT DID NOT CHANGE BUT WAS TOUCHED:
  - .env: LANGFUSE_ENABLED changed True→False, OTLP_ENDPOINT commented out (not tracked by git — gitignored)
  - backend/.env: LANGFUSE_ENABLED changed True→False (not tracked by git — gitignored)
  - .env.staging: OTLP_ENDPOINT commented out (not tracked by git — gitignored)

TESTS RUN + RESULT:
  ```
  cd /opt/flowmanner/backend && python -m pytest tests/test_evaluation.py tests/test_sentry_integration.py -q
  ===== 33 passed in 4.19s =====
  ```

=== STATUS ===

□ git status
  On branch main
  Your branch is up to date with 'origin/main'.

  Changes not staged for commit:
    modified:   backend/app/config.py
    modified:   backend/app/services/budget_enforcer.py
    modified:   backend/app/services/evaluation/eval_runner.py
    modified:   backend/app/services/evaluation/llm_judge.py
    modified:   backend/app/services/improvement/causal_decomposer.py
    modified:   docker-compose.dev.yml
    modified:   docker-compose.yml
    modified:   docs/DEEP-DIVE-REPORT-2026-07-03.md

□ git fetch origin && git log --oneline origin/main..main
  (empty — no unpushed commits)

□ docker compose exec -T backend alembic current
  20260630_plan_candidates (head)

□ pytest results:
  33 passed in 4.19s (test_evaluation.py + test_sentry_integration.py)

=== NEXT SESSION HANDOFF ===

Completed the first wave of the deep-dive report action plan:
- P1-C1 ✅: LLM judge and eval runner now route through BudgetEnforcer (substrate guarantee #4 satisfied)
- P1-C2 ✅: STRATEGY_MAP has zero cloud model references — all point to local llama.cpp models
- Glenn-7 ✅: Jaeger deleted from docker-compose, Langfuse disabled in all .env files, OTLP_ENDPOINT removed
- Glenn-8 ✅: SENTRY_WEBHOOK_SECRET required in production (>=16 chars, validated at startup)
- Glenn-6 ✅: Extensions vs plugins deep-dive completed — they are separate systems, keep separate
- P1-B3 verified: HITL inbox frontend already fully wired (Zustand + SSE + approve/reject/clarify)
- P1-B2a verified: Reliability Center field bug already fixed (field names match backend)

NOT yet committed or deployed. The next agent should:
1. Review the diff, commit with a clear message, push to origin
2. When Glenn approves, deploy backend: `bash /opt/flowmanner/deploy-backend.sh`
3. Next priorities from the deep-dive report: P2 items (build Tool Routing Inspector UI, Plugin Manager UI, standardize React Query + apiClient, delete langchain/ legacy subpackage)
4. The .env files were also modified (LANGFUSE_ENABLED=False, OTLP_ENDPOINT removed) but are gitignored — these changes are local only and need to be replicated on any rebuild

Key gotchas:
- Jaeger service is GONE from docker-compose. If you need tracing again, you'll need to re-add it.
- Langfuse is disabled at the config level AND the .env level. The service code still exists but will no-op.
- The SENTRY_WEBHOOK_SECRET validation will REFUSE TO START in production if the secret is not set (>=16 chars). Make sure .env has it set before deploying.
- BudgetEnforcer.call_simple() creates a per-call Budget (no cross-call enforcement). This is fine for local models but could overspend on cloud models.

=== FILES THIS AGENT DID NOT TOUCH BUT EXIST ===

- Untracked files: (none observed in git status)
- Deleted files: (none)

=== END ===
