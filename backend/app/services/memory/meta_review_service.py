"""Meta Review Service — scaffold improvement proposals (AutoMem Phase 2).

Sibling to BackgroundReviewService. Uses the same Qwen 27B LLM
infrastructure but reviews scaffold effectiveness, not memory writes.

The meta-LLM reviews episode traces and proposes improvements to
the agent's memory-related instructions. Proposals are validated
by the ValidationHarness and staged in scaffold_proposals for
human approval.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import structlog

from app.models.scaffold_models import ScaffoldProposal, ScaffoldProposalStatus
from app.services.memory.meta_review_prompt import (
    DEFAULT_META_MODEL,
    MAX_PROPOSED_PROMPT_CHARS,
    META_REVIEW_SYSTEM_PROMPT,
    META_REVIEW_USER_PROMPT,
    MIN_TRACES_FOR_REVIEW,
    build_traces_text,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class ScaffoldProposalResult:
    """Result of a meta-LLM review."""

    def __init__(
        self,
        *,
        success: bool,
        proposal_id: str | None = None,
        reasoning: str = "",
        proposed_prompt: str = "",
        changes_summary: str = "",
        expected_impact: str = "",
        confidence: float = 0.0,
        soundness: float = 0.0,
        risk_level: str = "low",
        error: str = "",
    ) -> None:
        self.success = success
        self.proposal_id = proposal_id
        self.reasoning = reasoning
        self.proposed_prompt = proposed_prompt
        self.changes_summary = changes_summary
        self.expected_impact = expected_impact
        self.confidence = confidence
        self.soundness = soundness
        self.risk_level = risk_level
        self.error = error


class MetaReviewService:
    """Reviews episode traces and proposes scaffold improvements.

    Usage::

        service = MetaReviewService(db)
        result = await service.review_scaffold(
            agent_id="engineering-senior-developer",
            current_prompt="...",
            episode_traces=[...],
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def review_scaffold(
        self,
        *,
        agent_id: str,
        current_prompt: str,
        episode_traces: list[dict[str, Any]],
        model_id: str = DEFAULT_META_MODEL,
    ) -> ScaffoldProposalResult:
        """Review episode traces and propose a scaffold improvement.

        Returns a ScaffoldProposalResult. If no improvement is found,
        returns success=True with an empty proposed_prompt.
        """
        if len(episode_traces) < MIN_TRACES_FOR_REVIEW:
            logger.info(
                "meta_review_insufficient_traces",
                agent_id=agent_id,
                trace_count=len(episode_traces),
                min_required=MIN_TRACES_FOR_REVIEW,
            )
            return ScaffoldProposalResult(
                success=True,
                reasoning=f"Only {len(episode_traces)} traces available, need {MIN_TRACES_FOR_REVIEW}. Skipping review.",
            )

        # Build the prompt
        traces_text = build_traces_text(episode_traces)
        user_prompt = META_REVIEW_USER_PROMPT.format(
            agent_id=agent_id,
            current_prompt=current_prompt,
            trace_count=len(episode_traces),
            traces_text=traces_text,
        )

        # Call the meta-LLM
        raw_response = await self.call_meta_llm(
            system_prompt=META_REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model_id=model_id,
        )

        if not raw_response:
            return ScaffoldProposalResult(
                success=False,
                error="Meta-LLM returned empty response",
            )

        # Parse the response
        parsed = self._parse_response(raw_response)
        if parsed is None:
            return ScaffoldProposalResult(
                success=False,
                error=f"Failed to parse meta-LLM response (first 200 chars): {raw_response[:200]}",
            )

        proposed_prompt = parsed.get("proposed_prompt", "")

        # If no change proposed, return success with empty prompt
        if not proposed_prompt or not proposed_prompt.strip():
            return ScaffoldProposalResult(
                success=True,
                reasoning=parsed.get("reasoning", "No changes proposed"),
                confidence=parsed.get("confidence", 0.0),
                soundness=parsed.get("soundness", 1.0),
            )

        # Validate proposed prompt length
        if len(proposed_prompt) > MAX_PROPOSED_PROMPT_CHARS:
            logger.warning(
                "meta_review_proposed_prompt_too_long",
                agent_id=agent_id,
                length=len(proposed_prompt),
                max_chars=MAX_PROPOSED_PROMPT_CHARS,
            )
            return ScaffoldProposalResult(
                success=False,
                error=f"Proposed prompt too long ({len(proposed_prompt)} chars, max {MAX_PROPOSED_PROMPT_CHARS})",
            )

        # Create the proposal in the database
        prompt_hash = hashlib.sha256(current_prompt.encode("utf-8")).hexdigest()

        proposal = ScaffoldProposal(
            agent_id=agent_id,
            current_prompt_hash=prompt_hash,
            proposed_prompt=proposed_prompt,
            reasoning=parsed.get("reasoning", ""),
            changes_summary=parsed.get("changes_summary", ""),
            expected_impact=parsed.get("expected_impact", ""),
            validation_metrics={
                "confidence": parsed.get("confidence", 0.0),
                "soundness": parsed.get("soundness", 0.0),
                "risk_level": parsed.get("risk_level", "medium"),
            },
            status=ScaffoldProposalStatus.PENDING,
            trace_count=len(episode_traces),
            meta_model=model_id,
        )
        self._db.add(proposal)
        await self._db.flush()

        logger.info(
            "meta_review_proposal_created",
            proposal_id=proposal.id,
            agent_id=agent_id,
            confidence=parsed.get("confidence", 0.0),
            soundness=parsed.get("soundness", 0.0),
            trace_count=len(episode_traces),
        )

        return ScaffoldProposalResult(
            success=True,
            proposal_id=proposal.id,
            reasoning=parsed.get("reasoning", ""),
            proposed_prompt=proposed_prompt,
            changes_summary=parsed.get("changes_summary", ""),
            expected_impact=parsed.get("expected_impact", ""),
            confidence=parsed.get("confidence", 0.0),
            soundness=parsed.get("soundness", 0.0),
            risk_level=parsed.get("risk_level", "medium"),
        )

    async def call_meta_llm(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_id: str = DEFAULT_META_MODEL,
    ) -> str:
        """Call the meta-LLM with the review prompt.

        Uses the same LLM infrastructure as BackgroundReviewService.
        Returns empty string on failure.
        """
        try:
            from app.services.langgraph.llm_config import (
                get_llamacpp_base_url,
                get_llm_manager,
            )
        except Exception as exc:
            logger.warning("MetaReviewService.call_meta_llm: LLMManager not importable: %s", exc)
            return ""

        try:
            manager = get_llm_manager()
            model = manager.get_model(model_id)
            if model is None:
                logger.warning("MetaReviewService.call_meta_llm: model %s unavailable", model_id)
                return ""

            import httpx

            base_url = get_llamacpp_base_url(model_id) + "/v1"
            model_name = manager.MODEL_MAP.get(model_id, model_id)
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
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
            logger.warning("MetaReviewService.call_meta_llm: %s failed: %s", model_id, exc)
            return ""

    def _parse_response(self, raw: str) -> dict[str, Any] | None:
        """Parse the meta-LLM response into a structured dict.

        Tries direct JSON parse, then fenced code block extraction.
        """
        stripped = raw.strip()

        # 1. Direct parse
        try:
            return json.loads(stripped)
        except (ValueError, TypeError):
            pass

        # 2. Fenced code block
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

        # 3. First balanced {...}
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
