"""Validation Harness — LLM-as-judge evaluation of scaffold proposals (AutoMem Phase 2).

MVP: Uses the same meta-LLM to evaluate whether a proposed scaffold
change is logically sound, addresses the identified weaknesses, and
is unlikely to cause regressions.

Future (v2): Seed mission replay — run canonical missions with old vs
new prompt and compare success rate.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from app.services.memory.meta_review_prompt import (
    DEFAULT_META_MODEL,
    MIN_CONFIDENCE_FOR_STAGE,
    MIN_SOUNDNESS_FOR_STAGE,
    build_traces_text,
)

logger = structlog.get_logger(__name__)

VALIDATION_SYSTEM_PROMPT = """You are a Scaffold Validation Judge for Flowmanner.

Your job: evaluate whether a proposed scaffold change is sound, likely
to help, and unlikely to cause regressions.

You are given:
1. The current agent prompt
2. The proposed new prompt
3. The proposer's reasoning
4. Episode traces showing the current behavior

Output ONLY valid JSON:

```json
{
  "approved": true | false,
  "confidence_score": <float 0.0-1.0>,
  "soundness_score": <float 0.0-1.0>,
  "risk_assessment": "low" | "medium" | "high",
  "reasoning": "<your evaluation>",
  "concerns": ["<list of specific concerns if any>"]
}
```

## Evaluation criteria

1. **Does the proposal address the identified weakness?**
   Check if the proposed prompt changes actually fix the patterns
   described in the reasoning.

2. **Is the reasoning sound?**
   Check for logical errors, hallucinated patterns, or over-generalization.

3. **Is the risk of regression low?**
   Check that the changes are targeted and don't break existing
   good behavior.

4. **Is the proposed prompt well-formed?**
   Check for syntax errors, contradictions, or ambiguous instructions.

Be conservative. When in doubt, reject. A missed improvement is
better than a broken agent.
"""

VALIDATION_USER_PROMPT = """Evaluate this scaffold proposal.

## Current Prompt

```
{current_prompt}
```

## Proposed Prompt

```
{proposed_prompt}
```

## Proposer's Reasoning

{reasoning}

## Episode Traces Summary

{traces_summary}

## Your Evaluation

Output ONLY the JSON object. No preamble or explanation outside the JSON block.
"""


class ValidationMetrics:
    """Result of a validation evaluation."""

    def __init__(
        self,
        *,
        approved: bool,
        confidence_score: float,
        soundness_score: float,
        risk_assessment: str,
        reasoning: str,
        concerns: list[str] | None = None,
    ) -> None:
        self.approved = approved
        self.confidence_score = confidence_score
        self.soundness_score = soundness_score
        self.risk_assessment = risk_assessment
        self.reasoning = reasoning
        self.concerns = concerns or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "confidence_score": self.confidence_score,
            "soundness_score": self.soundness_score,
            "risk_assessment": self.risk_assessment,
            "reasoning": self.reasoning,
            "concerns": self.concerns,
        }


class ValidationHarness:
    """Evaluates scaffold proposals using LLM-as-judge.

    Usage::

        harness = ValidationHarness()
        metrics = await harness.validate_proposal(
            current_prompt="...",
            proposed_prompt="...",
            reasoning="...",
            episode_traces=[...],
        )
    """

    def __init__(self, model_id: str = DEFAULT_META_MODEL) -> None:
        self._model_id = model_id

    async def validate_proposal(
        self,
        *,
        current_prompt: str,
        proposed_prompt: str,
        reasoning: str,
        episode_traces: list[dict[str, Any]],
    ) -> ValidationMetrics:
        """Validate a scaffold proposal using LLM-as-judge.

        Returns ValidationMetrics with approval decision and scores.
        """
        traces_summary = build_traces_text(episode_traces, max_traces=10)

        user_prompt = VALIDATION_USER_PROMPT.format(
            current_prompt=current_prompt,
            proposed_prompt=proposed_prompt,
            reasoning=reasoning,
            traces_summary=traces_summary,
        )

        raw = await self._call_judge(user_prompt)

        if not raw:
            logger.warning("validation_harness_empty_response")
            return ValidationMetrics(
                approved=False,
                confidence_score=0.0,
                soundness_score=0.0,
                risk_assessment="high",
                reasoning="Judge returned empty response — rejecting conservatively",
            )

        parsed = self._parse_response(raw)
        if parsed is None:
            logger.warning("validation_harness_parse_failed", raw_first_200=raw[:200])
            return ValidationMetrics(
                approved=False,
                confidence_score=0.0,
                soundness_score=0.0,
                risk_assessment="high",
                reasoning="Failed to parse judge response — rejecting conservatively",
            )

        confidence = float(parsed.get("confidence_score", 0.0))
        soundness = float(parsed.get("soundness_score", 0.0))
        risk = parsed.get("risk_assessment", "high")
        judge_approved = bool(parsed.get("approved", False))

        # Apply thresholds — override judge if scores are too low
        final_approved = (
            judge_approved
            and confidence >= MIN_CONFIDENCE_FOR_STAGE
            and soundness >= MIN_SOUNDNESS_FOR_STAGE
            and risk != "high"
        )

        if judge_approved and not final_approved:
            logger.info(
                "validation_harness_overridden",
                judge_approved=judge_approved,
                confidence=confidence,
                soundness=soundness,
                risk=risk,
            )

        return ValidationMetrics(
            approved=final_approved,
            confidence_score=confidence,
            soundness_score=soundness,
            risk_assessment=risk,
            reasoning=parsed.get("reasoning", ""),
            concerns=parsed.get("concerns", []),
        )

    async def _call_judge(self, user_prompt: str) -> str:
        """Call the judge LLM (same infra as meta review)."""
        try:
            from app.services.langgraph.llm_config import (
                get_llamacpp_base_url,
                get_llm_manager,
            )
        except Exception as exc:
            logger.warning("ValidationHarness._call_judge: LLMManager not importable: %s", exc)
            return ""

        try:
            import httpx

            manager = get_llm_manager()
            base_url = get_llamacpp_base_url(self._model_id) + "/v1"
            model_name = manager.MODEL_MAP.get(self._model_id, self._model_id)
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer not-needed"},
                )
                resp.raise_for_status()
                data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content or ""
        except Exception as exc:
            logger.warning("ValidationHarness._call_judge failed: %s", exc)
            return ""

    def _parse_response(self, raw: str) -> dict[str, Any] | None:
        """Parse the judge response JSON."""
        stripped = raw.strip()

        try:
            return json.loads(stripped)
        except (ValueError, TypeError):
            pass

        for fence in ("```json", "```JSON", "```"):
            idx = stripped.find(fence)
            if idx == -1:
                continue
            start = idx + len(fence)
            end = stripped.find("```", start)
            if end == -1:
                continue
            candidate = stripped[start:end].strip()
            try:
                return json.loads(candidate)
            except (ValueError, TypeError):
                continue

        depth = 0
        start_idx = None
        for i, ch in enumerate(stripped):
            if ch == "{":
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start_idx is not None:
                        candidate = stripped[start_idx : i + 1]
                        try:
                            return json.loads(candidate)
                        except (ValueError, TypeError):
                            start_idx = None
                            continue

        return None
