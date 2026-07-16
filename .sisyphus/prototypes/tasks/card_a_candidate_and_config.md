# Card A — Author the churn candidate JSON, LABEL-SCHEMA.md, and harness-config.yaml

## STATUS: COMPLETED (kanban-complete, owner override)
- completed_at: 2026-07-16
- verified_by: lead architect (independent re-check of worker deliverables)
- deliverables committed to branch `agent/2026-07-16-substrate-churn-candidate`
- acceptance: `verify_candidate(churn_candidate.json)` → `[]` errors; `answer.assigned_model: llamacpp/Qwen3.6-27B` present in `routing.catalog`; PyYAML parses `harness-config.yaml` with `routing.catalog`; `LABEL-SCHEMA.md` defines jq-parity gold rule + JSONL schema.
- note: worker's original `assigned_model` was `llamacpp-qwen3.6-27b` (hyphen) which FAILED `verify_candidate` (gate requires slash form); corrected to `llamacpp/Qwen3.6-27B` by reviewer before completion.

## GOAL
Produce the three artifacts that let the harness-evolution meta-optimizer run a REAL
per-case churn eval through the live `UnifiedExecutor`. These artifacts are currently
MISSING or non-conforming, so accuracy stays at `0.0 / source:none`.

## WHY (grounded in live source — read before designing)
- The evaluator shim is `backend/app/services/substrate/evaluate_harness.py`
  (invoked via `backend/scripts/evaluate_harness.sh "<candidate.json>" <split>`).
- `evaluate_harness.py:482` requires a workflow node with `id == "answer"`. There is
  NO such node in the seed template `Churn Risk Auto-Intervention`
  (`backend/seed_templates.py:2432`) — that template ends at `transform-4cr` →
  `condition-4cr` → `task-outreach-4cr`/`log-4cr` and never emits `risk_level`. So the
  seed template is NOT consumable by the shim as-is. A dedicated candidate carrying an
  `answer` LLM node MUST be authored.
- `_extract_answer_output` (`evaluate_harness.py:267`) reads the `NODE_COMPLETED`
  substrate event whose `node_id == "answer"`. `score_case`/`_predict_risk_level`
  (`:343`/`:400`) parse a `risk_level` field. So the `answer` node MUST emit
  `risk_level` (one of `high|low|unknown`).
- `build_workflow` (`:109`) maps short node types via `NODE_TYPE_ALIASES`
  (`llm`/`llm_call` → `LLM_CALL`). The candidate SHOULD use `type: "llm_call"` for the
  answer node, or `type: "llm"`.
- `harness-config.yaml` is referenced by the run command
  (`.sisyphus/prototypes/harness_meta_optimizer.py:18-20`) and by `verify_candidate`
  (which needs `routing.catalog`), but **does not exist in the tree**. The optimizer
  cannot run without it. Author it.
- `llm_router.py:242` HARD-REFUSES empty/placeholder API keys unless the model is in
  the `llamacpp/*` family. Therefore the candidate's `answer.assigned_model` MUST be a
  `llamacpp/*` model (local, $0) to pass the live smoke with no cloud key — e.g.
  `llamacpp-qwen3.6-27b` (mirror `MODEL_CHOICES` in the prototype, line 47). Do NOT pick
  a cloud model on this card; that needs a key Glenn must supply.

## DELIVERABLES (uncommitted files — do NOT commit/push; this is for Glenn's review)
1. `.sisyphus/prototypes/churn_candidate.json`
   - Shape consumed by `build_workflow` + `score_case`:
     ```json
     {
       "workspace_id": null,
       "workflow": {
         "nodes": [
           {"id": "rag",  "type": "rag_query", "title": "Retrieve churn cases",
            "config": {"collection": "churn_history", "query": "<placeholder, overwritten per-case>", "top_k": 5},
            "effect_class": "reversible"},
           {"id": "answer", "type": "llm_call", "title": "Score churn risk",
            "assigned_model": "llamacpp-qwen3.6-27b",
            "config": {
              "prompt": "<system-style instruction: from the retrieved cases, emit JSON {risk_level, basis, recommended_action}; risk_level in {high,low,unknown}>",
              "temperature": 0.0,
              "system_prompt": "<one of the SYSTEM_PROMPT_VARIANTS in harness_meta_optimizer.py:57-69>",
              "tool_ids": []
            },
            "effect_class": "reversible"}
         ],
         "edges": [{"source": "rag", "target": "answer"}]
       },
       "memory": {"top_k": 5, "similarity_threshold": 0.0, "reranker": false},
       "verification": {"forbidden_tools": ["delete_data", "send_email", "delete_collection"]}
     }
     ```
   - The `answer` node's `prompt` will be OVERRIDDEN per-case by the shim's
     `_format_case_prompt` (`evaluate_harness.py:359`) which injects `[CASE INPUT]{...}[/CASE INPUT]`.
     So the candidate prompt is the base instruction only; do not try to embed case features.
   - Edge targets must reference existing node ids. Do NOT add a condition/outreach node
     (those are the seed template's concern, not the shim's — the shim only scores `answer`).
2. `.sisyphus/prototypes/LABEL-SCHEMA.md`
   - Document EXACTLY how the gold `risk_level` label in `EVAL_DATA_DIR/{split}.jsonl`
     is derived, so accuracy is honest. Two admissible schemas (pick/define both, note which is canonical):
     - **jq-parity**: gold `high` iff `>=4` RAG matches in `churn_history` (mirrors
       `transform-4cr` at `seed_templates.py:2497`: `.matches | if length > 3 then "high" else "low"`).
       State that with `top_k=5`, a case is `high` when >=4 of the 5 retrieved chunks are
       truly relevant churn cases.
     - **hand-labeled truth**: gold from a human/domain label; document the labeling source.
   - Specify the JSONL line schema: `{"risk_level": "high"|"low", "<feature>": <val>, ...}`
     where every key except `risk_level` is an input feature serialized into the prompt.
   - State the mapping the `answer` node must produce to be scored correct
     (`_predict_risk_level` at `evaluate_harness.py:400` checks for `"risk_level": "..."`).
3. `.sisyphus/prototypes/harness-config.yaml`
   - YAML config for `harness_meta_optimizer.py --config harness-config.yaml --budget 50`.
   - MUST contain at minimum:
     - `routing.catalog`: a dict mapping model name → spec, including `llamacpp-qwen3.6-27b`
       (and a couple of the `MODEL_CHOICES` cloud models behind keys) so `verify_candidate`
       (prototype `:210-212`) can validate `answer.assigned_model` is in the catalog.
     - the optimizer's mutation axes matching the shim's LIVE axes
       (`answer.assigned_model`, `answer.config.temperature`, `answer.config.system_prompt`,
       `answer.config.tool_ids`) per `evaluate_harness.py:21-23` docstring.
     - budget / trials knobs the prototype reads (inspect `load_config` + `main` in the
       prototype to learn the exact keys; do not invent keys the prototype never reads).
   - Read `.sisyphus/prototypes/harness_meta_optimizer.py` top-to-bottom before authoring
     this file; the YAML keys must match what `load_config`/the optimizer actually consume.

## ACCEPTANCE (do NOT mark done until all hold)
- `churn_candidate.json` parses as JSON; has an `answer` node with `id:"answer"`,
  `type` ∈ {llm_call, llm}, `assigned_model` starting with `llamacpp/`; an `edges` entry
  whose `target` is `answer`; and `verification.forbidden_tools` is a non-empty list.
- A dry import works: from a python shell,
  `from app.services.substrate.evaluate_harness import build_workflow;
   build_workflow(json.load(open('.sisyphus/prototypes/churn_candidate.json')))`
  returns a `Workflow` whose `.nodes` includes an `answer` node (no exception).
  (Run this inside `/opt/flowmanner/backend` with the venv python
  `/opt/flowmanner/backend/.venv/bin/python`.)
- `harness-config.yaml` parses with PyYAML and contains `routing.catalog` with a
  `llamacpp-qwen3.6-27b` entry.
- `LABEL-SCHEMA.md` explicitly defines the gold-label derivation rule and the JSONL line schema.
- `pytest` on the backend venv still imports cleanly where touched (no import breakage).

## WORKER RULE (Glenn default — OVERRIDES this repo's AGENTS.md "commit and push")
- Do NOT `git commit`. Do NOT `git push`. Do NOT deploy.
- Work only in your assigned worktree branch.
- When done + acceptance met, `kanban_block` for review (kind: needs_input). Do NOT `kanban_complete`.
- Before editing, confirm `git rev-parse --show-toplevel` ends in `.worktrees/<your-card-id>`,
  not the repo root. If it prints the root, STOP — wrong checkout.

## OUT OF SCOPE (explicitly NOT this card)
- Populating `churn_history` (that is Card B — a separate one-off ingest script).
- Writing infra/run docs (that is Card C).
- Touching `seed_templates.py` (the seed template is left as-is; the candidate is a NEW
  standalone artifact, not a patch to the seed).
