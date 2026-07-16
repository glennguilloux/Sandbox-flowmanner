# LABEL-SCHEMA.md — Churn-Risk Gold Label Schema

This document defines EXACTLY how the gold `risk_level` label is derived for the
churn-candidate evaluation harness, so that the per-case accuracy reported by
`app.services.substrate.evaluate_harness` is **honest** and reproducible.

It is the contract behind `$EVAL_DATA_DIR/{split}.jsonl` (one JSON object per
line). The shim reads each line as a "case": every key except `risk_level` is an
**input feature** serialized into the answer node's prompt; `risk_level` is the
**gold label** scored by `score_case()`.

---

## 1. Canonical gold-label derivation rule (jq-parity)

The canonical schema mirrors the production `transform-4cr` rule in
`backend/seed_templates.py:2497`:

```jq
{ risk: .matches | (if length > 3 then "high" else "low" end), ... }
```

i.e. a case is **`high`** risk iff it has **strictly more than 3** retrieved RAG
matches, else **`low`**.

Because the candidate fixes `memory.top_k = 5`, the `answer` node retrieves at
most 5 chunks from `churn_history`. With `top_k = 5`:

> **Gold `risk_level == "high"`  ⇔  at least 4 of the 5 retrieved chunks are
> truly relevant churn cases (>= 4 matches).**
> **Gold `risk_level == "low"`   ⇔  0–3 of the 5 retrieved chunks are relevant
> (< 4 matches).**

This is the parity definition: the harness optimizer is judged against the same
threshold the seed template's `transform-4cr` → `condition-4cr` decision uses.

### Why `>= 4`, not `>= 3`
`length > 3` is `>= 4`. The threshold is anchored to the seed template's exact
jq expression so the candidate's learned boundary is comparable to the
hand-built template's boundary. Do NOT silently change it to `>= 3` — that would
break parity with `seed_templates.py`.

### Relevance = "truly a churn case"
A retrieved chunk is a **relevant match** when it is a genuine prior churn /
churn-risk record for the evaluated account (or a labeled exemplar in
`churn_history`), not noise. Relevance is decided by the dataset author at
ingest time (see §3), NOT by the model. The label is fixed before the run.

---

## 2. Alternative admissible schema (hand-labeled truth)

A second admissible label source is a **human/domain label** supplied directly
by a domain expert (e.g. a CSM who knows the account).

- Canonical for THIS harness run: **jq-parity (§1)** — it needs no human in the
  loop and is deterministic from the retrieved set.
- Hand-labeled truth MAY be used to *seed* or *audit* the jq-parity labels, but
  when both exist, **jq-parity wins** for the accuracy number, and any
  divergence is logged as a finding (not silently overwritten).

If a dataset is hand-labeled only (no RAG match count available), the label
source MUST be recorded in the dataset's sidecar `LABEL-SOURCE=<method>` note
and the `risk_level` values must still be drawn from `{"high","low"}` (plus
`"unknown"` only if explicitly present in the seed; the shim accepts
`high|low|unknown` but the gold set should use `high|low`).

---

## 3. JSONL line schema

Every line in `$EVAL_DATA_DIR/{split}.jsonl` is one JSON object:

```json
{
  "risk_level": "high" | "low",
  "<feature_1>": <value>,
  "<feature_2>": <value>,
  "...": "..."
}
```

- **`risk_level`** (required, string): the GOLD label. Admissible values:
  `"high"` or `"low"`. (`"unknown"` is accepted by the predictor parser but
  should not appear as a gold label; reserve it for model output only.)
- **All other keys** are INPUT FEATURES. They are serialized (sorted,
  ensure_ascii=False) by `_format_case_prompt` into a `[CASE INPUT]{...}[/CASE
  INPUT]` block and appended to the answer node's base prompt. The live model
  sees them; they are NOT otherwise interpreted by the shim.
- Feature values may be scalars, strings, lists, or nested objects — anything
  JSON-serializable. Keep each line self-contained (no cross-line references).

Example lines:

```json
{"risk_level": "high", "account_age_days": 412, "open_tickets": 3, "last_login_days_ago": 96, "plan": "pro"}
{"risk_level": "low",  "account_age_days": 1203, "open_tickets": 0, "last_login_days_ago": 4, "plan": "enterprise"}
```

### How the label reaches the file
At dataset-build time (Card B — out of scope for this card), the author runs the
same RAG retrieval the candidate uses (`collection=churn_history`, `top_k=5`),
counts relevant matches, and emits `risk_level` per §1. The retrieval params in
the dataset builder MUST match the candidate (`top_k=5`,
`similarity_threshold`/collection identical) or parity is invalid.

---

## 4. What the `answer` node must emit to score correct

The shim's `_predict_risk_level` (`evaluate_harness.py:400`) extracts the
prediction in this order:

1. If the answer node's output dict contains a top-level `risk_level` key, that
   value is the prediction.
2. Else if the output has a `content` string, it scans for
   `"risk_level": "high"` (or `low`/`unknown`) — a cheap fallback.

Therefore the **`answer` node MUST produce a JSON object whose top-level
`risk_level` field is one of `high | low | unknown`** to be scored deterministically:

```json
{"risk_level": "high", "basis": "...", "recommended_action": "..."}
```

A case is scored **correct** iff `predicted == label` (both non-null), where
`label` is the gold `risk_level` from the JSONL line
(`score_case`, `evaluate_harness.py:343`).

- Gold `high` is correct only when the model emits `risk_level: "high"`.
- Gold `low` is correct only when the model emits `risk_level: "low"`.
- `unknown` predictions never match `high`/`low` gold (counted incorrect) —
  which is the desired behavior: guessing "unknown" is not a free pass.

---

## 5. Accuracy is never fabricated

- With NO `{split}.jsonl` present, `evaluate` runs once and emits
  `accuracy: 0.0` with `source: "none"` (NOT a fake number).
- With the golden set present, accuracy = (correctly predicted cases) /
  (total cases), `source: "per_case"`.
- A case whose run fails or returns no prediction counts as **incorrect** — the
  harness never credits a case it could not actually predict.
