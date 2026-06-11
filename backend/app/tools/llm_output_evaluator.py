"""
LLM Operations Tools — LLM Output Evaluator.

llm_output_evaluator → Use a secondary model to score primary model outputs
    for hallucination, factual accuracy, coherence, and relevance.
    P1 ⭐ DIFFERENTIATOR — cross-model quality gate with multi-model judging.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

_DEFAULT_CRITERIA: list[str] = [
    "hallucination",
    "factual_accuracy",
    "coherence",
    "relevance_to_query",
]

_VALID_CRITERIA = {
    "hallucination",
    "factual_accuracy",
    "coherence",
    "relevance_to_query",
    "conciseness",
    "completeness",
    "tone",
    "helpfulness",
}

_EVALUATOR_SYSTEM_PROMPT = """\
You are an LLM output evaluator. Your job is to critically assess another \
model's output across multiple quality dimensions and assign scores from \
0 (worst) to 10 (perfect).

For each criterion:
1. Provide a numeric score (0-10)
2. Cite specific evidence from the output that justifies your score
3. If hallucination is detected, quote the hallucinated passage and explain why

CRITICAL: Return ONLY a JSON object. No explanations outside the JSON."""


_EVALUATOR_MODELS = (
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "claude-3.5-sonnet",
    "claude-3-opus",
)

_EVALUATION_STYLES = ("numeric", "pairwise", "likert")


class EvaluationCriterion(BaseModel):
    """Single evaluation dimension with weight and rubric."""

    name: str = Field(..., min_length=1, description="Criterion name (e.g., 'hallucination')")
    description: str = Field("", description="Detailed description of what this criterion measures")
    weight: float = Field(1.0, ge=0.0, le=10.0, description="Relative weight in overall score")
    min_score: float = Field(0.0, ge=0.0, le=1.0, description="Minimum acceptable score")
    rubric: list[str] | None = Field(None, description="Scoring rubric levels (e.g., ['Poor: 0-3', 'Good: 7-10'])")


class LlmOutputEvaluatorInput(ToolInput):
    """Input schema: text, query, context, criteria, model, multi_judge, min_judges."""

    output: str = Field(
        ...,
        min_length=1,
        max_length=100000,
        description="The LLM-generated output to evaluate",
    )
    prompt: str | None = Field(
        None,
        description="The original user prompt that produced this output",
    )
    ground_truth: str | None = Field(
        None,
        description="Known correct answer to compare against",
    )
    criteria: list[EvaluationCriterion] | None = Field(
        None,
        description="Evaluation criteria with weights. Defaults: hallucination (w=2), factual_accuracy (w=2), coherence (w=1), relevance (w=1)",
    )
    evaluator_model: Literal["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "claude-3.5-sonnet", "claude-3-opus"] | None = (
        Field(
            None,
            description="Model to use as judge (cheaper models are usually sufficient)",
        )
    )
    evaluation_style: Literal["numeric", "pairwise", "likert"] = Field(
        "numeric",
        description="Evaluation style: numeric (0-10), pairwise (A vs B), likert (1-5 scale)",
    )
    output_b: str | None = Field(
        None,
        description="Second LLM output for pairwise comparison",
    )
    multi_judge: bool = Field(
        False,
        description="Run evaluation with multiple judge models and average scores",
    )
    min_judges: int = Field(
        2,
        ge=2,
        le=5,
        description="Minimum number of judges for multi_judge mode",
    )

    @model_validator(mode="after")
    def check_pairwise_requirements(self):
        if self.evaluation_style == "pairwise" and not self.output_b:
            raise ValueError("output_b is required for pairwise evaluation style")
        return self


class LlmOutputEvaluatorTool(BaseTool):
    """Evaluate LLM output quality using a secondary model as judge."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="llm_output_evaluator",
            name="LLM Output Evaluator",
            description=(
                "Use a secondary model to score primary model outputs for "
                "hallucination, factual accuracy, coherence, and relevance. "
                "Returns per-criterion scores (0-10) with evidence citations, "
                "hallucination detection, and optional multi-judge averaging "
                "for higher confidence evaluations."
            ),
            category="llm-operations",
            input_schema=LlmOutputEvaluatorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "overall_score": {"type": "number"},
                    "criteria_scores": {"type": "object"},
                    "hallucinations": {"type": "array"},
                    "hallucination_count": {"type": "integer"},
                    "issues": {"type": "array"},
                    "summary": {"type": "string"},
                    "judges": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["llm", "evaluation", "hallucination", "quality", "differentiator"],
            requires_auth=True,
            timeout_seconds=180,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = LlmOutputEvaluatorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Convert EvaluationCriterion objects to criteria dicts
        if validated.criteria:
            criteria_items = validated.criteria
            criteria_names = [c.name for c in criteria_items]
        else:
            criteria_items = [
                EvaluationCriterion(
                    name="hallucination",
                    weight=2.0,
                    description="Detect factually incorrect claims",
                ),
                EvaluationCriterion(
                    name="factual_accuracy",
                    weight=2.0,
                    description="Verify facts against ground truth",
                ),
                EvaluationCriterion(name="coherence", weight=1.0, description="Logical flow and clarity"),
                EvaluationCriterion(
                    name="relevance_to_query",
                    weight=1.0,
                    description="Response addresses the query",
                ),
            ]
            criteria_names = [c.name for c in criteria_items]

        invalid = [c.name for c in criteria_items if c.name not in _VALID_CRITERIA]
        if invalid:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid criteria: {invalid}. Valid: {sorted(_VALID_CRITERIA)}",
            )

        try:
            if validated.multi_judge:
                evaluation = await self._multi_judge_evaluate(validated, criteria_names)
            else:
                evaluation = await self._evaluate(
                    text=validated.output,
                    query=validated.prompt,
                    context=validated.ground_truth,
                    criteria=criteria_names,
                    model_preference=validated.evaluator_model,
                    evaluation_style=validated.evaluation_style,
                    output_b=validated.output_b,
                )

            # Compute weighted aggregate
            criteria_map = {c.name: c for c in criteria_items}
            detail_scores = {c["criterion"]: c["score"] for c in evaluation.get("criteria", [])}
            if detail_scores:
                weighted_sum = sum(
                    s * criteria_map.get(name, EvaluationCriterion(name=name)).weight
                    for name, s in detail_scores.items()
                )
                total_weight = sum(
                    criteria_map.get(name, EvaluationCriterion(name=name)).weight for name in detail_scores
                )
                overall = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0
            else:
                overall = 0.0
            issues = self._extract_issues(evaluation)
            hallucinations = evaluation.get("hallucinations", [])
            summary = self._build_summary(detail_scores, overall, issues, hallucinations)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "overall_score": overall,
                    "criteria_scores": detail_scores,
                    "detailed_criteria": evaluation.get("criteria", []),
                    "evaluation_style": validated.evaluation_style,
                    "hallucinations": hallucinations,
                    "hallucination_count": len(hallucinations),
                    "issues": issues,
                    "summary": summary,
                    "judges": validated.min_judges if validated.multi_judge else 1,
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("llm_output_evaluator failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _multi_judge_evaluate(self, validated: LlmOutputEvaluatorInput, criteria: list[str]) -> dict[str, Any]:
        judges = validated.min_judges
        all_criteria: list[list[dict]] = []
        all_hallucinations: list[list[dict]] = []

        for _ in range(judges):
            result = await self._evaluate(
                text=validated.output,
                query=validated.prompt,
                context=validated.ground_truth,
                criteria=criteria,
                model_preference=validated.evaluator_model,
            )
            all_criteria.append(result.get("criteria", []))
            all_hallucinations.append(result.get("hallucinations", []))

        # Average criteria scores
        merged_criteria: list[dict[str, Any]] = []
        for c in criteria:
            scores = []
            comments = []
            for judge_criteria in all_criteria:
                for jc in judge_criteria:
                    if jc.get("criterion") == c:
                        scores.append(jc.get("score", 0))
                        comments.append(jc.get("comment", ""))
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
            merged_criteria.append(
                {
                    "criterion": c,
                    "score": avg_score,
                    "comment": " | ".join(comments[:2]),
                    "judge_scores": scores,
                }
            )

        # Deduplicate hallucinations
        seen = set()
        merged_hallucinations = []
        for hl in all_hallucinations:
            for h in hl:
                passage = h.get("passage", "")
                if passage not in seen:
                    seen.add(passage)
                    merged_hallucinations.append(h)

        return {"criteria": merged_criteria, "hallucinations": merged_hallucinations}

    async def _evaluate(
        self,
        text: str,
        query: str | None,
        context: str | None,
        criteria: list[str],
        model_preference: str | None,
        evaluation_style: str = "numeric",
        output_b: str | None = None,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": _EVALUATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._build_evaluation_prompt(text, query, context, criteria, evaluation_style, output_b),
            },
        ]
        response = await self._call_evaluator(messages, model_preference)
        return self._parse_evaluation(response, criteria)

    def _build_evaluation_prompt(
        self,
        text: str,
        query: str | None,
        context: str | None,
        criteria: list[str],
        evaluation_style: str = "numeric",
        output_b: str | None = None,
    ) -> str:
        parts = [
            "Evaluate the following LLM output:\n",
            f"<output>\n{text}\n</output>\n",
        ]
        if query:
            parts.append(f"Original query:\n<query>\n{query}\n</query>\n")
        if context:
            parts.append(f"Ground-truth context:\n<context>\n{context}\n</context>\n")
        parts.append(f"Score each criterion 0-10:\n")
        for c in criteria:
            parts.append(f"- {c}")
        if evaluation_style == "pairwise":
            parts.append("\nCompare Output A vs Output B and return:\n")
            parts.append("<output_a>\n" + text + "\n</output_a>\n")
            parts.append("<output_b>\n" + (output_b or "") + "\n</output_b>\n")
            parts.append("Return JSON: {\n")
            parts.append('  "winner": "A" or "B" or "tie",')
            parts.append('  "criteria": [{"criterion": "...", "score_a": 0, "score_b": 0}]')
            parts.append("}")
        elif evaluation_style == "likert":
            parts.append("\nRate each criterion on a 1-5 Likert scale:\n")
            for c in criteria:
                parts.append(f"- {c}: 1=Strongly Disagree, 2=Disagree, 3=Neutral, 4=Agree, 5=Strongly Agree")
            parts.append("\nReturn JSON:\n{")
            parts.append('  "criteria": [{"criterion": "...", "score": 3, "comment": "..."}]')
            parts.append("}")
        else:
            parts.append("\nScore each criterion 0-10:\n")
            for c in criteria:
                parts.append(f"- {c}")
            parts.append("\nReturn JSON:\n{")
            parts.append('  "criteria": [{"criterion": "...", "score": 0, "comment": "..."}],')
            parts.append('  "hallucinations": [{"passage": "...", "description": "..."}]')
            parts.append("}")
        return "\n".join(parts)

    async def _call_evaluator(self, messages: list[dict], model_preference: str | None) -> str:
        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        result = await router.route_request(
            messages=messages,
            model_preference=model_preference,
            temperature=0.0,
            max_tokens=2048,
        )
        if isinstance(result, dict):
            if not result.get("success", False):
                raise RuntimeError(f"Evaluator error: {result.get('error', 'unknown')}")
            return result.get("content", "") or result.get("response", "")
        if not result.success:
            raise RuntimeError(f"Evaluator error: {result.error}")
        return result.content

    def _parse_evaluation(self, response: str, criteria: list[str]) -> dict[str, Any]:
        try:
            data = json.loads(response)
            # Normalize pairwise/likert results to standard format
            if "winner" in data:
                # Pairwise: convert score_a/score_b to standard score fields
                normalized_criteria = []
                for c in data.get("criteria", []):
                    score_a = c.get("score_a", 5)
                    score_b = c.get("score_b", 5)
                    normalized_criteria.append(
                        {
                            "criterion": c.get("criterion", ""),
                            "score": score_a,  # Report A's score as primary
                            "score_b": score_b,
                            "winner": data.get("winner", "tie"),
                            "comment": c.get("comment", f"A={score_a}, B={score_b}"),
                        }
                    )
                return {
                    "criteria": normalized_criteria,
                    "hallucinations": [],
                    "winner": data["winner"],
                }
            # Likert: 1-5 scale, already in standard format
            return data
        except json.JSONDecodeError:
            pass
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return self._heuristic_parse(response, criteria)

    def _heuristic_parse(self, response: str, criteria: list[str]) -> dict[str, Any]:
        parsed = []
        for c in criteria:
            pattern = c.replace("_", r"[\s_]")
            m = re.search(rf"{pattern}[:\\s]+(\\d+)(?:\\s*/\\s*10)?", response, re.IGNORECASE)
            if m:
                score = min(max(int(m.group(1)), 0), 10)
                parsed.append(
                    {
                        "criterion": c,
                        "score": score,
                        "comment": "Heuristically extracted",
                    }
                )
        return {"criteria": parsed, "hallucinations": []}

    def _extract_issues(self, evaluation: dict) -> list[dict]:
        issues = []
        for c in evaluation.get("criteria", []):
            if c["score"] < 5:
                issues.append(
                    {
                        "severity": "high" if c["score"] < 3 else "medium",
                        "criterion": c["criterion"],
                        "message": c.get("comment", f"Low score on {c['criterion']}"),
                    }
                )
        for h in evaluation.get("hallucinations", []):
            issues.append(
                {
                    "severity": "critical",
                    "criterion": "hallucination",
                    "message": h.get("description", "Hallucination detected"),
                    "passage": h.get("passage", ""),
                }
            )
        return issues

    def _build_summary(self, scores: dict, overall: float, issues: list, hallucinations: list) -> str:
        parts = [f"Overall score: {overall}/10"]
        for c, s in scores.items():
            emoji = "✅" if s >= 7 else ("⚠️" if s >= 4 else "❌")
            parts.append(f"  {emoji} {c.replace('_', ' ').title()}: {s}/10")
        if hallucinations:
            parts.append(f"\n⚠️  {len(hallucinations)} hallucination(s) detected")
        if issues:
            parts.append(f"\n{len(issues)} issue(s) found")
        return "\n".join(parts)


register_tool(LlmOutputEvaluatorTool())
