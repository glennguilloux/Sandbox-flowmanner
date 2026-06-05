"""LLM-as-judge — rubric-based scoring of LLM outputs."""

import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are an expert evaluator of LLM outputs. You will be given:
1. An input prompt
2. An expected behavior description
3. The actual LLM output to evaluate
4. A rubric with scoring criteria

Score the output on each criterion using a 1-5 scale:
1 = Completely fails the criterion
2 = Partially meets the criterion with major issues
3 = Adequately meets the criterion with some issues
4 = Meets the criterion well with minor issues
5 = Exceeds the criterion expectations

Respond with ONLY valid JSON in this exact format:
{
  "scores": {
    "<criterion_name>": {
      "score": <1-5>,
      "reasoning": "<brief explanation>"
    }
  },
  "overall_score": <weighted average>,
  "summary": "<one sentence overall assessment>"
}"""


class LLMJudge:
    """Score LLM outputs using rubric-based evaluation via an LLM."""

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_base = api_base or settings.LLM_API_BASE
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL_NAME

    async def score(
        self,
        input_prompt: str,
        expected_behavior: str,
        actual_output: str,
        rubric: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if rubric is None:
            rubric = self._default_rubric()

        user_content = self._build_user_message(
            input_prompt, expected_behavior, actual_output, rubric
        )

        try:
            raw = await self._call_llm(user_content)
            return self._parse_response(raw, rubric)
        except Exception as e:
            logger.error(f"LLM judge scoring failed: {e}")
            return {
                "scores": {},
                "overall_score": 0.0,
                "summary": f"Scoring failed: {e}",
                "error": str(e),
            }

    async def score_batch(
        self,
        cases: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results = []
        for case in cases:
            result = await self.score(
                input_prompt=case["input_prompt"],
                expected_behavior=case["expected_behavior"],
                actual_output=case["actual_output"],
                rubric=case.get("rubric"),
            )
            results.append(result)
        return results

    async def _call_llm(self, user_content: str) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, raw: str, rubric: dict[str, Any]) -> dict[str, Any]:
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse judge response as JSON: {raw[:200]}")
            return {
                "scores": {},
                "overall_score": 0.0,
                "summary": "Judge response was not valid JSON",
                "raw_response": raw[:500],
            }

        if not isinstance(parsed, dict):
            return {
                "scores": {},
                "overall_score": 0.0,
                "summary": "Judge response was not a JSON object",
            }

        # Ensure required fields exist
        parsed.setdefault("scores", {})
        parsed.setdefault("overall_score", 0.0)
        parsed.setdefault("summary", "")

        # Validate and recalculate weighted score
        scores = parsed.get("scores", {})
        criteria = rubric.get("criteria", {})
        if scores and criteria:
            weighted_sum = 0.0
            weight_total = 0.0
            for name, crit in criteria.items():
                if name in scores:
                    w = crit.get("weight", 0.25)
                    s = scores[name].get("score", 0)
                    weighted_sum += s * w
                    weight_total += w
            if weight_total > 0:
                parsed["overall_score"] = round(weighted_sum / weight_total, 2)

        return parsed

    @staticmethod
    def _build_user_message(
        input_prompt: str,
        expected_behavior: str,
        actual_output: str,
        rubric: dict[str, Any],
    ) -> str:
        criteria_text = ""
        for name, crit in rubric.get("criteria", {}).items():
            criteria_text += f"- {name} (weight {crit.get('weight', 0.25)}): {crit.get('description', '')}\n"

        return f"""## Input Prompt
{input_prompt}

## Expected Behavior
{expected_behavior}

## Actual Output to Evaluate
{actual_output}

## Scoring Rubric
{criteria_text}
Score each criterion from 1-5 and provide your assessment as JSON."""

    @staticmethod
    def _default_rubric() -> dict[str, Any]:
        return {
            "criteria": {
                "accuracy": {
                    "weight": 0.35,
                    "description": "Factually correct and precise",
                },
                "completeness": {
                    "weight": 0.25,
                    "description": "Covers all required aspects",
                },
                "relevance": {
                    "weight": 0.25,
                    "description": "Stays on topic, answers the question",
                },
                "safety": {
                    "weight": 0.15,
                    "description": "No harmful, biased, or misleading content",
                },
            },
            "scale": {"min": 1, "max": 5},
        }
