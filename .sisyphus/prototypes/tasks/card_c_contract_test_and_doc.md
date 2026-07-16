# Card C — Offline per-case contract test + RUN-SEQUENCE.md

## STATUS: COMPLETED (kanban-complete, owner override)
- completed_at: 2026-07-16
- verified_by: lead architect (re-ran the test independently: **16 passed**)
- deliverables committed to branch `agent/2026-07-16-substrate-churn-contract`
- acceptance: `TestPerCaseContract` GREEN (ran 16 passed via backend venv); offline (no DATABASE_URL, no real LLM); `RUN-SEQUENCE.md` lists all 3 gaps + exact run command + (added) model-id/API-key plumbing caveat.
- note: `RUN-SEQUENCE.md` was extended by the lead architect with a "Model id & API-key plumbing" section documenting the bare-vs-slash key resolution (`app/services/llm_providers._resolve_provider`) so a DeepSeek smoke does not silently fall through to the wrong key env.

## GOAL
Two deliverables that make the "honest, no-fabrication" per-case eval reproducible and
reviewable WITHOUT live infra: (1) a pytest that locks the shim's per-case contract using
a fake executor, and (2) a doc capturing the exact real run sequence + the 3 confirmed gaps.

## WHY (grounded in live source — read before coding)
- The per-case loop in `backend/app/services/substrate/evaluate_harness.py:480-548` is the
  code under test. It already has offline tests at `backend/app/tests/test_evaluate_harness.py`
  (referenced at `evaluate_harness.py:47`). EXTEND that file (do not create a second test module
  for the same subject).
- The loop's contract (verify each with a test):
  1. When `EVAL_DATA_DIR/<split>.jsonl` exists, the workflow runs ONCE PER CASE
     (`evaluate_harness.py:489` for-loop), features injected via `_format_case_prompt`
     (`:359`) into the `answer` node's `prompt`.
  2. Cost is SUMMED across cases (`:504` `total_cost +=`), latency is the MEAN
     (`:541` `sum(latencies)/len`), safety must hold for EVERY case (`:518-525`).
  3. Accuracy is the fraction of per-case `risk_level` predictions matching gold
     (`score_case` `:343`, `score_accuracy` `:373`). A failed/missing prediction counts WRONG.
  4. NO fabrication: with NO golden set, accuracy is `0.0` with `source="none"`
     (`:381-389`). This must remain true and is already covered — add a per-case contract
     test on TOP, not in place of it.
- The single infra seam is `run_executor` (`evaluate_harness.py:204`). The offline test must
  replace it with a FAKE (monkeypatch `evaluate_harness.run_executor`) that returns a canned
  `answer_output` with the right `risk_level` for a given case — exactly how
  `tests/test_evaluate_harness.py` already does it. Read that test file first to match its
  fake-executor pattern (do not invent a different seam).
- The gold label is NEVER leaked into the prompt (the assert the other session mentioned):
  confirm `_format_case_prompt` injects only non-`risk_level` keys (`:368`
  `features = {k:v for k,v in case.items() if k != "risk_level"}`).

## DELIVERABLES (uncommitted — do NOT commit/push; for Glenn's review)
1. EXTEND `backend/app/tests/test_evaluate_harness.py` with a test class
   `TestPerCaseContract` that:
   - Builds a tiny in-memory golden set (2 high + 2 low cases) written to a temp
     `EVAL_DATA_DIR/<split>.jsonl`.
   - Monkeypatches `run_executor` to return `answer_output={"risk_level": <predicted>}`
     based on the case identity (so you can assert correct/incorrect counting).
   - Asserts: per-case accuracy = correct/total; cost = sum; latency = mean;
     `safety_pass` True only when every case safe; no `risk_level` key appears in the
     injected prompt substring.
   - Use the venv python + the existing test conventions. Keep it offline (no DATABASE_URL,
     no real LLM).
2. `.sisyphus/prototypes/RUN-SEQUENCE.md` documenting:
   - The 3 CONFIRMED gaps (so Glenn sees what's still needed):
     1. Seed churn template has no `answer` node → needs the standalone candidate (Card A).
     2. `churn_history` collection has no ingest path → needs Card B's script.
     3. `harness-config.yaml` is absent from the tree (referenced by
        `harness_meta_optimizer.py:18-20` and required by `verify_candidate`/safety gate)
        → authored in Card A.
   - The exact real run sequence once infra + the 3 artifacts exist:
     ```
     # infra already up (Postgres/Redis/Qdrant/llamacpp reachable from backend container)
     # 1) populate churn_history:  python .sisyphus/prototypes/ingest_churn_history.py
     # 2) author EVAL_DATA_DIR/train.jsonl + val.jsonl (schema in LABEL-SCHEMA.md, Card A)
     # 3) smoke (DATABASE_URL must be set; llamacpp model = $0, no cloud key needed):
     HARNESS_EVAL_COMMAND="bash backend/scripts/evaluate_harness.sh" \
       python .sisyphus/prototypes/harness_meta_optimizer.py \
       --config .sisyphus/prototypes/harness-config.yaml --budget 50
     ```
   - The no-fabrication guarantee: `evaluate_harness.sh` refuses without `DATABASE_URL`
     (`exit 2`), and accuracy is `0.0/source:none` without a golden set.

## ACCEPTANCE (do NOT mark done until all hold)
- `TestPerCaseContract` runs GREEN under
  `/opt/flowmanner/backend/.venv/bin/python -m pytest backend/app/tests/test_evaluate_harness.py -v`
  (the existing tests must still pass too).
- The test does NOT touch live infra (no `DATABASE_URL`, no real LLM).
- `RUN-SEQUENCE.md` lists all 3 gaps and the exact run command block above.
- You read `tests/test_evaluate_harness.py` and followed its fake-executor pattern.

## WORKER RULE (Glenn default — OVERRIDES this repo's AGENTS.md "commit and push")
- Do NOT `git commit`. Do NOT `git push`. Do NOT deploy.
- Work only in your assigned worktree branch.
- When done + acceptance met, `kanban_block` for review (kind: needs_input). Do NOT `kanban_complete`.
- Before editing, confirm `git rev-parse --show-toplevel` ends in `.worktrees/<your-card-id>`,
  not the repo root. If it prints the root, STOP — wrong checkout.

## OUT OF SCOPE (explicitly NOT this card)
- Authoring the candidate/label-schema/config (Card A).
- Authoring the ingest script (Card B).
