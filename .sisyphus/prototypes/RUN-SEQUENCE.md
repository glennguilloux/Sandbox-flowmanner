# RUN-SEQUENCE — Offline per-case harness-evolution eval

How to reproduce the honest, no-fabrication per-case evaluation of a
harness-evolution candidate **once the three missing infra artifacts exist**.
This document is the operational counterpart to
`backend/app/tests/test_evaluate_harness.py::TestPerCaseContract` (the offline
contract lock) and to `backend/app/services/substrate/evaluate_harness.py`
(the shim under test).

Everything live runs through `UnifiedExecutor` → Postgres + Qdrant + llamacpp.
The ONLY seam the offline test replaces is `run_executor`
(`evaluate_harness.py:204`), monkeypatched in the test so no live infra is
touched. Real runs need the infra + the 3 artifacts below.

---

## 1. CONFIRMED GAPS (what is still missing — Card A / Card B deliverables)

The per-case contract in `evaluate_harness.py:480-548` is fully implemented and
offline-testable today. What is NOT yet in the tree:

### Gap 1 — seed churn template has no `answer` node (Card A)
The seed churn workflow template does not declare an `answer` node. The
per-case loop locates `answer_node = next(n for n in workflow.nodes if n.id ==
"answer")` (`evaluate_harness.py:482`) and injects each case's features into
`answer_node.config["prompt"]` via `_format_case_prompt`. Without an `answer`
node, `base_prompt` falls back to `""` and no prediction is produced — every
case scores wrong. Card A authors the standalone candidate (with the `answer`
node) so `build_workflow` (`evaluate_harness.py:109`) materializes a real
`Workflow` with that node.

### Gap 2 — `churn_history` collection has no ingest path (Card B)
The `churn_history` collection (the golden-case source: tenure / logins /
risk labels) exists as a concept but has no population script. Card B authors
`ingest_churn_history.py`, which writes the labeled records that become
`EVAL_DATA_DIR/<split>.jsonl`. Until it exists, the golden sets must be
authored by hand (see Gap-A schema).

### Gap 3 — `harness-config.yaml` is absent from the tree (Card A)
`harness_meta_optimizer.py` references `.sisyphus/prototypes/harness-config.yaml`
at lines 20 and 24 (the `--config` input). The static gate
`verify_candidate` (loaded by the shim via `harness_verify.py`) and therefore
the `safety_check` branch in `evaluate()` REQUIRE the candidate to carry a
`routing.catalog` (the gate reads `config["routing"]["catalog"]`, else it
raises `KeyError` → recorded as a *skip*). `harness-config.yaml` is the file
that defines that catalog + the mutation space. Card A authors it. Without it,
`--config harness-config.yaml` cannot be passed and a bare candidate trips the
gate.

> NOTE (real contract subtlety): a candidate *without* `routing.catalog` makes
> `verify_candidate` raise `KeyError`, which `safety_check` catches and records
> as a **skip** (documented as "does NOT fail safety"). However `evaluate()`'s
> `overall_safety` aggregation (`evaluate_harness.py:522-525`) treats ANY
> non-empty `safety_failures` list — including a skip string — as a failure, so
> `safety_pass` ends up `False`. The honest fix is to always supply a valid
> candidate (catalog + `answer.assigned_model`); the offline test
> `TestPerCaseContract::test_per_case_safety_true_only_when_every_case_safe`
> encodes exactly this.

---

## 1b. MODEL ID & API-KEY PLUMBING (how to actually use deepseek-v4-flash etc.)

`verify_candidate` only checks that `answer.assigned_model` is present in
`routing.catalog`. That is a *structural* gate — it does NOT guarantee the
model runs at runtime. The runtime resolution lives in
`app/services/llm_providers._resolve_provider` and has a real subtlety:

- **Slash-form ids bind a dedicated key env:**
  `deepseek/deepseek-v4-flash` → `DEEPSEEK_API_KEY`,
  `llamacpp/Qwen3.6-27B` → no key ($0 local),
  `anthropic/...` → `ANTHROPIC_API_KEY`.
- **Bare ids** (`deepseek-v4-flash`, `claude-3-haiku`, `glennguilloux-demo-llm`,
  `openrouter-gemini-2.0-flash`) yield `provider=None` and fall through to the
  **PLATFORM** `_LLM_API_KEY` / `_LLM_API_BASE` (default `api.deepseek.com/v1`).
  They do NOT consult each provider's dedicated key var.

So `routing.catalog` marking a model `enabled: true` does **not** by itself make
it runnable — the right key env must be set in the backend container. Concretely:

- The default candidate uses `llamacpp/Qwen3.6-27B` → runs keyless today ($0).
- To smoke with DeepSeek via the *dedicated* key, set `DEEPSEEK_API_KEY` AND
  switch `answer.assigned_model` to the slash form `deepseek/deepseek-v4-flash`.
- Bare `deepseek-v4-flash` will "work" only if `LLM_API_KEY` happens to be a
  DeepSeek key; otherwise it falls through to an unset platform key and the
  router hard-refuses (per the no-fabrication guard).

`mutate()` selects from `routing.catalog` (not `MODEL_CHOICES`), so the
evolution loop can pick the keyless `llamacpp/Qwen3.6-27B` or any catalog id —
but the *runtime* key env still decides whether a picked cloud model actually
runs. This is documented so a DeepSeek smoke does not silently resolve to the
wrong key.

## 2. EXACT REAL RUN SEQUENCE (after infra + the 3 artifacts exist)

```bash
# Prereq: infra already up — Postgres / Redis / Qdrant / llamacpp reachable
# from the backend container. No cloud key needed for llamacpp (model = $0).

# 1) Populate the churn_history collection (Card B script):
python .sisyphus/prototypes/ingest_churn_history.py

# 2) Author EVAL_DATA_DIR/train.jsonl + val.jsonl.
#    Schema (see LABEL-SCHEMA.md, Card A): one JSON object per line.
#    The gold label is `risk_level` (high|medium|low|unknown); EVERY other
#    key is treated as an input feature and injected into the answer node
#    prompt. The label is NEVER leaked into the prompt.
#      {"risk_level": "high", "tenure_days": 12, "logins_30d": 3}
#      {"risk_level": "low",  "tenure_days": 880, "logins_30d": 41}
#    Default EVAL_DATA_DIR: /opt/flowmanner/.sisyphus/prototypes/eval_data
#    (override with the EVAL_DATA_DIR env var).

# 3) Smoke the meta-optimizer (DATABASE_URL MUST be set; llamacpp = $0):
HARNESS_EVAL_COMMAND="bash backend/scripts/evaluate_harness.sh" \
  python .sisyphus/prototypes/harness_meta_optimizer.py \
  --config .sisyphus/prototypes/harness-config.yaml --budget 50
```

The prototype invokes `evaluate_harness.sh <candidate.json> <split>` once per
trial. That script runs `app.services.substrate.evaluate_harness` through
`UnifiedExecutor` and emits exactly one JSON line:

```json
{"accuracy": 0.0, "cost_usd": 0.0, "latency_ms": 0.0, "safety_pass": true}
```

---

## 3. NO-FABRICATION GUARANTEE

Two independent guards keep the eval honest:

1. **Refuses without `DATABASE_URL`.** `backend/scripts/evaluate_harness.sh:31-35`
   exits `2` with a clear message if `DATABASE_URL` is unset — it will NOT emit
   fabricated metrics from a fake/local run. A real run executes through
   `UnifiedExecutor` against the live backend database.

2. **Accuracy is `0.0` / `source="none"` without a golden set.**
   `score_accuracy` (`evaluate_harness.py:373-397`) returns
   `{"accuracy": 0.0, "source": "none", ...}` whenever `EVAL_DATA_DIR/<split>.jsonl`
   is absent or empty. The optimizer can still run cost/latency/safety Pareto
   fronts, but quality is never invented. Per-case mode (golden set present)
   scores `correct/total`, where a missing or wrong prediction counts WRONG.

These guarantees are locked by the offline tests
`test_accuracy_none_without_golden` and
`TestPerCaseContract` in `backend/app/tests/test_evaluate_harness.py`, which
run with NO `DATABASE_URL` and NO real LLM (only `run_executor` is monkeypatched).

---

## 4. OFFLINE CONTRACT LOCK (what the test proves, no infra)

`pytest backend/app/tests/test_evaluate_harness.py -v` (run with the backend
venv python) covers, among others, the `TestPerCaseContract` class:

- `test_per_case_accuracy_is_correct_over_total` — accuracy = correct/total
  (3/4 on a deliberately-misclassified case).
- `test_per_case_cost_summed_latency_mean` — cost is SUMMED across cases,
  latency is the MEAN (distinct per-case values observed).
- `test_per_case_safety_true_only_when_every_case_safe` — `safety_pass` is
  `True` only when EVERY case run is clean; a single forbidden-tool event
  fails the whole eval while the other cases still score.
- `test_gold_label_never_injected_into_prompt` — the per-case prompt carries
  the features but NEVER the `risk_level` key (anti-leakage so accuracy stays
  honest).
- `test_missing_prediction_counts_wrong` — a run returning no `risk_level`
  counts the case WRONG (never credited).

Run command (host, no live infra touched):

```bash
cd /opt/flowmanner/backend
export PYTHONPATH=/opt/flowmanner/backend
export OPENAI_API_KEY=test   # some imports read it at import time
/opt/flowmanner/backend/.venv/bin/python -m pytest \
  app/tests/test_evaluate_harness.py -v -p no:cacheprovider --timeout=120
```
