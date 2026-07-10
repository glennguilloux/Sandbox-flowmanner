# Task: Cost-Aware Plan Selection (K-Plan Scored Pick)

**Date:** 2026-06-30
**Estimated effort:** 2–3 days
**Priority:** High — turns "cost-aware" from marketing claim into a shipped behavior

---

## ⚠️ REPO PATH WARNING

This task touches the FastAPI backend at `/opt/flowmanner/backend/`.
Do NOT edit anywhere else. Verify with `pwd` — it MUST print `/opt/flowmanner` at start.
The frontend lives at `/home/glenn/FlowmannerV2-frontend/` — DO NOT touch it for this task.

---

## 1. Thesis

FlowManner markets itself as "cost-aware, interruptible, resumable agentic workflows." The first and last of those are real — `BudgetEnforcer` (substrate) clamps every LLM call and substrate events log every cost. But the **middle** is missing: when `MissionPlanner` (`backend/app/services/mission_planner.py`) generates a plan, the LLM proposes ONE plan and we run it. If a user wants the cheapest plan that's still ≥ 80% as good, or the second-best plan, there is no mechanism — we discover cost overruns mid-execution and abort.

This task closes that gap by adding **K-Plan generation + cost-quaility scoring + user pick** to the planner. It makes the cost-aware claim verifiable end-to-end with a 5-minute demo.

---

## 2. What Already Exists (DO NOT REBUILD)

Verified 2026-06-30 — these all work:

| Component | Location | What it does |
|-----------|----------|--------------|
| `MissionPlanner` | `backend/app/services/mission_planner.py` | Single-shot LLM plan generation |
| `BudgetEnforcer.call()` | `backend/app/services/substrate/budget_enforcer.py` | Clamps every LLM call to remaining budget |
| `CostTracker` | `backend/app/services/cost_tracker.py` | Per-step `LLMCallRecord` + Prometheus metrics |
| `SubstrateEventLog` | `backend/app/services/substrate/events.py` | Replayable per-step event stream |
| `FailureAnalyzer` | `backend/app/services/failure_analyzer.py` | Already scores plan quality post-hoc |
| `HeapEpisodicMemory` | `backend/app/services/episodic_memory.py` | Retrieves past episodes for prompt context |
| `_op` + `wrap_command()` | `backend/app/api/_mission_cqrs/base.py` | Transaction wrapper for command handlers |
| `dry_run_path` | `backend/app/services/substrate/dry_run.py` | Already estimates cost without executing |

The dry-run estimator is the seed we need. We just don't expose it as a selection loop.

---

## 3. Goal

When `MissionPlanner` plans a mission with cost-aware budget selection enabled:

1. **Generate K=3 plans** in parallel (cheap heuristic + LLM-A + LLM-B persona).
2. **Score each plan** with the existing dry-run estimator (tokens, cost, latency, risk).
3. **Pick a winner** by a deterministic policy: `minimize(cost) subject to quality_score ≥ threshold`.
4. **Persist the full ranked list** so the UI can show "we picked plan 2 of 3 (saved ~$0.12, -8% quality)."
5. **Record the choice** as a `plan_selected` substrate event for replay.

### Three modes

- `BUDGET_AWARE_PLAN_SELECTION=off` (default, zero behavior change) → single-plan as today.
- `BUDGET_AWARE_PLAN_SELECTION=on` → user picks from UI dropdown.
- `BUDGET_AWARE_PLAN_SELECTION=auto` → system picks by policy (above), UI shows the choice rationale.

---

## 4. Files to Touch

### 4.1 New: `backend/app/services/plan_selection/__init__.py`

Empty package marker.

### 4.2 New: `backend/app/services/plan_selection/plan_candidate.py`

```python
@dataclass(slots=True)
class PlanCandidate:
    plan_id: str               # "heuristic_v1", "llm_persona_a", "llm_persona_b"
    generation_strategy: str   # one of "heuristic" | "llm_persona" | "llm_default"
    tasks: list[dict]          # serialized MissionTask list
    estimated_cost_usd: float
    estimated_latency_ms: int
    estimated_tokens: int
    quality_score: float       # 0.0–1.0 from heuristic pre-check
    risk_flags: list[str]      # ["unbounded_retry", "human_input_blocking", ...]
    rationale: str             # human-readable explanation of how this plan differs
```

### 4.3 New: `backend/app/services/plan_selection/plan_generator.py`

Public entry: `async def generate_plan_candidates(mission: Mission, k: int = 3) -> list[PlanCandidate]`.

- **Strategy A — heuristic**: Build a minimal linear plan from the user's prompt + a rule-based task classifier (`scripts/classify_intent.py` exists already).
- **Strategy B — LLM persona A**: existing planner prompt, system prompt framed as "concise engineer."
- **Strategy C — LLM persona B**: existing planner prompt, system prompt framed as "thorough strategist."

Each generator returns one `PlanCandidate`. K defaults to 3.

For each, call `dry_run_path(candidate.tasks)` to fill `estimated_cost_usd`, `estimated_latency_ms`, `estimated_tokens`.

### 4.4 New: `backend/app/services/plan_selection/plan_scorer.py`

Public entry: `def score_plan(candidate: PlanCandidate) -> float`.

Deterministic heuristic scoring (NOT LLM, runs in <10ms):

| Signal | Weight | Notes |
|--------|--------|-------|
| `estimated_cost_usd` normalized 0–1 | -0.30 | Cheaper is better. Lower = higher score. |
| `risk_flags` count | -0.10 per flag, capped at -0.30 | "unbounded_retry", "human_input_blocking", "no_fallback" |
| Task count (normalized) | -0.05 | Fewer tasks is slightly better (less to fail). |
| Has fallback for every tool-using task | +0.20 | Critical for plan resilience. |
| Estimated retries (off profile) | -0.05 | Penalize plans likely to retry >2x. |
| Has `max_budget` declared | +0.10 | Self-aware about cost. |

Returns float 0.0–1.0.

### 4.5 New: `backend/app/services/plan_selection/plan_selector.py`

Public entry:

```python
async def select_plan(
    candidates: list[PlanCandidate],
    policy: str = "auto",  # "auto" | "min_cost" | "max_quality" | "balanced"
    min_quality_threshold: float = 0.6,
) -> tuple[PlanCandidate, list[PlanCandidate]]:
    """Returns (winner, all_sorted_desc_by_score)."""
```

Implementations of policies:

- `"min_cost"`: argmin `cost` among those with `quality ≥ threshold`.
- `"max_quality"`: argmax `score`.
- `"balanced"` (default): argmax `score`, score already includes cost penalty.
- `"auto"`: same as `"balanced"` today (room to grow into a learned policy).

### 4.6 Edit: `backend/app/services/mission_planner.py`

- Read `settings.BUDGET_AWARE_PLAN_SELECTION` (default `"off"`).
- If `"off"` (or unset): current single-shot behavior. **Zero behavior change.**
- If `"on"` or `"auto"`:
  1. Call `await generate_plan_candidates(mission, k=settings.PLAN_SELECTION_K)`.
  2. Call `await select_plan(candidates, policy="on" if mode == "on" else "balanced")`.
  3. Persist the full ranked list to a new `MissionPlanCandidate` row (see §4.7).
  4. Emit a `plan_selected` substrate event with `{winner_id, ranked_ids, rationale, cost_saved_usd, quality_delta}`.
  5. Return the winner's tasks to the executor.

The chosen candidate's `plan_id` must be attached to the resulting `Mission.plan_metadata["plan_selection"]` for auditability.

### 4.7 Edit: `backend/app/models/mission_advanced_models.py` (or new `mission_plan_models.py` if cleaner)

Add:

```python
class MissionPlanCandidate(Base):
    __tablename__ = "mission_plan_candidates"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("missions.id", ondelete="CASCADE"))
    plan_id: Mapped[str]                                              # "heuristic_v1" etc
    generation_strategy: Mapped[str]                                  # "heuristic" | "llm_persona" | "llm_default"
    tasks_json: Mapped[dict]                                          # serialized task list
    estimated_cost_usd: Mapped[float]
    estimated_latency_ms: Mapped[int]
    estimated_tokens: Mapped[int]
    quality_score: Mapped[float]
    risk_flags: Mapped[list[str]] = mapped_column(JSON)
    rationale: Mapped[str]
    rank: Mapped[int]                                                 # 1 = winner; tiebreak by cost
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
```

Add Alembic migration: `backend/alembic/versions/xxxx_add_mission_plan_candidate_table.py`.
Use the scaffold pattern from the most recent migration in that directory.

### 4.8 Edit: `backend/app/config.py`

Add at the bottom of `Settings`:

```python
BUDGET_AWARE_PLAN_SELECTION: Literal["off", "on", "auto"] = "off"
PLAN_SELECTION_K: int = 3
PLAN_SELECTION_MIN_QUALITY: float = 0.6
```

### 4.9 Edit: `backend/app/services/mission_executor.py`

In `execute_async` (or wherever plans are fetched), if the chosen candidate ID is in the new `MissionPlanCandidate` table and `mode == "on"`, return the candidate's tasks (not a freshly generated plan). This is the fix that makes `on` mode actually round-trippable.

### 4.10 Frontend wiring — DEFERRED

Do NOT touch the frontend. The mission page just falls through to the existing single-plan path. A follow-up ticket will wire the comparison UI after this lands.

---

## 5. Tests (must pass before commit)

In `backend/tests/`:

| Test file | Cases |
|-----------|-------|
| `test_plan_candidate.py` (new) | PlanCandidate dataclass serialization; Pydantic round-trip |
| `test_plan_scorer.py` (new) | Lower cost → higher score; risk flags penalize; thresholds correct |
| `test_plan_selector.py` (new) | `min_cost` policy prefers cheaper; `max_quality` prefers higher score; threshold filter |
| `test_plan_generator.py` (new) | K=3 always returns 3 candidates (heuristic + 2 personas); dry-run fields populated |
| `test_cost_aware_plan_selection_e2e.py` (new) | Integration: planner with `BUDGET_AWARE_PLAN_SELECTION=auto` persists 3 candidates, picks winner, emits `plan_selected` event, attaches winner to mission. **Hard requirement: read the candidates from DB and assert the chosen plan's rank is 1 and quality ≥ threshold.** |
| `test_mission_planner.py` (existing) | Add 1 case: with `BUDGET_AWARE_PLAN_SELECTION=off`, behavior is identical to today (zero regression). |

All new tests must run in <30s and not require external LLM calls (mock the LLM with `lambda: "PLANNER_FIXTURE_JSON"`).

---

## 6. Backend verification

Run from `/opt/flowmanner`:

```bash
cd backend
ruff check app/services/plan_selection/ app/services/mission_planner.py
mypy app/services/plan_selection/ app/services/mission_planner.py
pytest -xvs tests/test_plan_candidate.py tests/test_plan_scorer.py \
                 tests/test_plan_selector.py tests/test_plan_generator.py \
                 tests/test_cost_aware_plan_selection_e2e.py \
                 tests/test_mission_planner.py
```

All must be green.

Build the image:

```bash
cd /opt/flowmanner && bash deploy-backend.sh --dry-run
```

`--dry-run` exits 0 if the new module imports cleanly.

---

## 7. Constraints (HARD)

1. **Self-hosted LLM only.** All three personas (heuristic + 2 LLM personas) must run against `llamacpp/` (Qwen3-27B on `:11434`). Do not call OpenAI/Anthropic/Google anywhere in this code path.
2. **No `db.commit()` inside `plan_selection/`.** All commits happen in the enclosing `wrap_command()` transaction. Match the existing pattern in `_mission_cqrs/commands.py`.
3. **`off` mode is byte-for-byte identical** to current behavior. Use a flag check at the top of `mission_planner.plan()` — if off, return the existing single-plan path immediately.
4. **No backend `httpx` calls to external services** (SearXNG, etc) in the candidate generator unless already used by the planner today.
5. **The dry-run estimator must be deterministic.** If it isn't currently, document the non-determinism in the candidate `rationale` field rather than hiding it.
6. **Migration is additive only.** `MissionPlanCandidate` is a new table. No existing column changes.
7. **Do not break any of the 5 working sets documented in `.sisyphus/handoffs/exit-audit-2026-06-26-cutover-mypy-reconcile-exercise.md`.**
8. **If a downstream file uses `# noqa: E402`** because of import order, that pattern already exists in the project — preserve it on the new files too.

---

## 8. Subagent self-verification (MUST run, MUST pass)

Before reporting done:

```bash
cd /opt/flowmanner/backend
ruff check app/services/plan_selection/ app/services/mission_planner.py app/models/mission_advanced_models.py
mypy app/services/plan_selection/ app/services/mission_planner.py
pytest -x tests/test_plan_candidate.py tests/test_plan_scorer.py \
           tests/test_plan_selector.py tests/test_plan_generator.py \
           tests/test_cost_aware_plan_selection_e2e.py \
           tests/test_mission_planner.py
bash /opt/flowmanner/deploy-backend.sh --dry-run
```

All six must exit 0. Save the output to `/tmp/deepseek-plan-selection-verify.txt` and include the path in your handoff.

---

## 9. Hand-off format

Write your handoff to `.sisyphus/handoffs/exit-audit-2026-06-30-plan-selection.md` with:

1. **What changed** — file-by-file diff summary.
2. **Verification output** — paste the contents of `/tmp/deepseek-plan-selection-verify.txt`.
3. **Demo steps** — exactly how Glenn can see this in action:
   - Set `BUDGET_AWARE_PLAN_SELECTION=auto` in `.env`.
   - Restart backend.
   - Submit a mission.
   - Run `psql -c "select plan_id, generation_strategy, estimated_cost_usd, quality_score, rank from mission_plan_candidates order by rank;"`.
   - Confirm 3 rows, rank=1 is the winner, quality ≥ 0.6.
4. **What is NOT done** — explicitly say "no frontend wiring yet."
5. **What I broke / am unsure about** — NEVER hide anything. If you're unsure a check passed, say so and quote the output.

---

## 10. Stop-the-line rules

- **If `wrap_command()` pattern doesn't fit cleanly** for any reason, STOP and document; do not invent a parallel transaction path.
- **If `FailureAnalyzer` returns an LLM-graded quality score that conflicts with `plan_scorer.py`'s deterministic score** (e.g., one says 0.7, another 0.4), STOP — this means my heuristic is wrong. Document the conflict in the handoff; do not silently pick the larger or smaller number.
- **If the migration fails on first run** (FK target wrong, JSON column not supported), STOP and report the exact Postgres error verbatim.
- **If the existing `mission_planner.py` has imports that depend on order requiring `noqa: E402`**, preserve those — do not "clean up" imports in this PR. Out of scope.

---

## 11. What "done" means

- All 6 verification commands in §8 exit 0.
- Handoff written to `.sisyphus/handoffs/exit-audit-2026-06-30-plan-selection.md`.
- **You do NOT commit.** The session ritual per `AGENTS.md` says Glenn reviews and Hermes commits. Stop at the handoff.
