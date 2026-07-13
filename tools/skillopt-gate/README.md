# SkillOpt-Gate

A **validation-gated skill optimizer** — the honest core of microsoft/SkillOpt,
implemented offline-safe for Hermes agent skills.

The "trainable parameter" is a single markdown skill document. An
**optimizer** proposes bounded `add` / `delete` / `replace` edits; a
**validation gate** accepts a candidate *only if it strictly improves a
held-out checker score*. At deploy time the artifact is static text →
**zero inference-time cost**.

## Why
Skills rot or drift when hand-edited, and "self-improving" agents that
rewrite their own instructions are a silent-failure risk. The gate makes
"improvement" **falsifiable**: a candidate that doesn't beat the held-out
check is rejected and the live skill is left untouched.

## Install / verify
```bash
cd tools/skillopt-gate
python3 -m pytest tests/ -q          # 18 tests, no key/network
python3 -m skillopt_gate.cli \
  --skill demo/SKILL.md --checker demo.checker:score \
  --edits demo/edits.json --stage
```
The `--checker` is *your* held-out test: any `callable(str) -> (hard, soft)`
over the skill text (a pytest, a linter, a harness). Edits are staged to
`<SKILL.md>.staged/`; the live file is **never** auto-mutated. Apply
with `--adopt` (writes a `.bak` backup first).

## Layout
- `skillopt_gate/core.py` — gate (`evaluate_gate`), score projection,
  protected-region edit ops (`apply_edit` / `apply_patch`).
- `skillopt_gate/optimizer.py` — `DeterministicOptimizer` (offline default)
  and `LLMOptimizer` (OpenAI-compatible, key-gated, lazy-imported).
- `skillopt_gate/runner.py` — one gated session; stages, never adopts.
- `skillopt_gate/staging.py` — write/adopt proposal, secret redaction.
- `demo/` — sample skill + checker + edits exercising the gate.
- `tests/` — gate math, edit ops, protected regions, e2e, redaction.

## Honesty envelope
- Strict-improvement-only gate (a tie is a rejection).
- Protected regions: step edits can't rewrite the appendix markers.
- Default = stage-for-review; adoption is an explicit, backup'd step.

This is honest only for what the checker measures. Silent quality drift on
*unmeasured* axes is still possible — pick a discriminating checker.
