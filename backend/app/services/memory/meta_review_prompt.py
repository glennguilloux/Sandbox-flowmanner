"""Meta review prompt + tool whitelist (AutoMem Phase 2).

Owns the scaffold review prompt that the meta-LLM uses to propose
improvements to agent system prompts. Separated from the service
so the prompt can be iterated independently.

The meta-LLM reviews episode traces (memory actions + outcomes) and
proposes targeted rewrites of the agent's memory-related instructions.
It does NOT change the agent's task capabilities, tools, or personality.
"""

from __future__ import annotations

# ── Constants ─────────────────────────────────────────────────────────

# Minimum number of episode traces required for a meaningful review.
MIN_TRACES_FOR_REVIEW = 5

# Maximum number of traces to include in the prompt (context window).
MAX_TRACES_IN_PROMPT = 15

# Maximum characters for the proposed prompt.
MAX_PROPOSED_PROMPT_CHARS = 8000

# Default meta-LLM model (same as background reviewer).
DEFAULT_META_MODEL = "llamacpp-qwen3.6-27b"

# Validation score thresholds.
MIN_CONFIDENCE_FOR_STAGE = 0.5
MIN_SOUNDNESS_FOR_STAGE = 0.6


# ── Prompt ────────────────────────────────────────────────────────────

META_REVIEW_SYSTEM_PROMPT = """You are the Scaffold Review Agent for Flowmanner.

Your job: review episode traces for an agent and propose improvements
to its system prompt. You focus on MEMORY-RELATED instructions only —
you do not change the agent's task capabilities, tool access, or personality.

You are rigorous. You only propose changes when you see clear patterns
of memory dysfunction across multiple episodes. A single bad episode
is not enough.

## What you may propose

You may propose a REWRITE of the agent's memory-related instructions.
Output ONLY valid JSON:

```json
{
  "reasoning": "<what weakness you found across the traces and how the rewrite addresses it>",
  "proposed_prompt": "<the full rewritten agent prompt>",
  "changes_summary": "<bullet list of specific changes made>",
  "expected_impact": "<what should improve and why>",
  "confidence": <float 0.0-1.0>,
  "soundness": <float 0.0-1.0>,
  "risk_level": "low" | "medium" | "high"
}
```

## What you may NOT change

- The agent's name, role, or personality
- Tool access or capability definitions
- Non-memory-related behavioral rules
- The agent's domain expertise or knowledge
- The agent's output format or response style

## Evaluation criteria

Look for these patterns in the traces:

1. **LOW RECALL RATE** — agent doesn't consult memory when it should.
   Signs: RECALL_EPISODIC/RECALL_SEMANTIC actions are rare relative
   to task complexity.

2. **LOW LOG RATE** — agent misses important observations.
   Signs: few LOG_OBSERVATION actions, or important outcomes not logged.

3. **REDUNDANT WRITES** — agent logs things already in memory.
   Signs: LOG_OBSERVATION with action_result showing high similarity
   to existing entries.

4. **LOW CONSOLIDATION** — short-term memories never get promoted.
   Signs: no CONSOLIDATE or PROMOTE actions despite long missions.

5. **POOR IMPORTANCE CALIBRATION** — everything gets the same score.
   Signs: narrow importance distribution in memory_proficiency.

6. **HIGH FAILURE RATE** — memory operations frequently fail.
   Signs: low success rate in memory_proficiency.

## Confidence scoring

- confidence: How certain you are that the proposed change will help.
  0.0 = guessing, 1.0 = very confident based on strong patterns.
- soundness: How well-reasoned the proposal is technically.
  0.0 = flawed logic, 1.0 = solid reasoning.
- risk_level: How likely the change is to cause regressions.
  "low" = safe wording changes, "medium" = structural changes,
  "high" = fundamental restructuring.
"""

META_REVIEW_USER_PROMPT = """Review the following episode traces for agent `{agent_id}`.

## Current Agent Prompt

```
{current_prompt}
```

## Episode Traces ({trace_count} missions)

{traces_text}

## Your Task

Analyze the memory action patterns across these traces. If you see
clear, repeated dysfunction patterns, propose a rewrite of the
memory-related sections of the agent prompt.

If the memory actions look healthy and effective, return:
```json
{{
  "reasoning": "Memory actions are effective — no changes needed.",
  "proposed_prompt": "",
  "changes_summary": "",
  "expected_impact": "",
  "confidence": 0.0,
  "soundness": 1.0,
  "risk_level": "low"
}}
```

Output ONLY the JSON object. No preamble, no explanation outside the JSON block.
"""


def build_traces_text(traces: list[dict], max_traces: int = MAX_TRACES_IN_PROMPT) -> str:
    """Format episode traces into a readable text block for the prompt.

    Truncates to max_traces and summarizes each trace concisely.
    """
    parts: list[str] = []
    for i, trace in enumerate(traces[:max_traces]):
        status = "SUCCESS" if trace.get("success") else "FAILURE"
        title = trace.get("title", "Untitled")
        proficiency = trace.get("memory_proficiency", {})

        # Summarize memory actions by type
        actions = trace.get("memory_actions", [])
        action_summary: dict[str, int] = {}
        for a in actions:
            t = a.get("action_type", "unknown")
            action_summary[t] = action_summary.get(t, 0) + 1

        action_str = ", ".join(f"{k}={v}" for k, v in sorted(action_summary.items()))

        # Proficiency summary
        total = proficiency.get("total_actions", 0)
        successful = proficiency.get("successful", 0)
        prof_str = f"{successful}/{total} successful" if total > 0 else "no actions"

        parts.append(
            f"### Mission {i + 1}: {title} [{status}]\n"
            f"- Memory actions: {action_str or 'none'}\n"
            f"- Proficiency: {prof_str}\n"
            f"- Error: {trace.get('error_message', 'none')}\n"
        )

    return "\n".join(parts)
