"""
Research & Knowledge Retrieval Tools — Fact Check Validator.

fact_check_validator → Cross-reference claims against known truth databases
    using the Google Fact Check Tools API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

FACT_CHECK_API_KEY = os.getenv("GOOGLE_API_KEY", os.getenv("FACT_CHECK_API_KEY", ""))
FACT_CHECK_API_BASE = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
FACT_CHECK_TIMEOUT = int(os.getenv("FACT_CHECK_TIMEOUT", "30"))

# ── Helpers ───────────────────────────────────────────────────────────


# ── Input ─────────────────────────────────────────────────────────────

FACT_CHECK_ACTIONS = (
    "check_claim",
    "search_claims",
)


class FactCheckValidatorInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action: 'check_claim' (single claim) or 'search_claims' (broad search)",
    )
    claim: str | None = Field(
        None,
        description="The claim or statement to fact-check (spec-compliant name).",
    )
    query: str | None = Field(
        None,
        description="DEPRECATED: use 'claim' instead. Accepted for backward compatibility.",
    )
    language: str = Field(
        "en",
        description="Language code for the claim (e.g., 'en', 'fr', 'de')",
    )
    max_results: int = Field(10, ge=1, le=50, description="Maximum fact-check reviews to return")

    @property
    def resolved_query(self) -> str:
        value = self.claim or self.query or ""
        if not value:
            raise ValueError("Either 'claim' or 'query' is required")
        return value


# ── Tool ──────────────────────────────────────────────────────────────


class FactCheckValidatorTool(BaseTool):
    """Cross-reference claims against known fact-check databases."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="fact_check_validator",
            name="Fact Check Validator",
            description=(
                "Cross-reference claims and statements against known truth databases "
                "using the Google Fact Check Tools API. Returns fact-check reviews "
                "with ratings, publishers, and source URLs. "
                "Requires GOOGLE_API_KEY env var."
            ),
            category="research-knowledge-retrieval",
            input_schema=FactCheckValidatorInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "claims": {"type": "array"},
                    "total_results": {"type": "integer"},
                    "query": {"type": "string"},
                },
            },
            tags=["fact-check", "truth", "verification", "claims", "research"],
            requires_auth=True,
            timeout_seconds=FACT_CHECK_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = FactCheckValidatorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in FACT_CHECK_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(FACT_CHECK_ACTIONS)}",
            )

        if not FACT_CHECK_API_KEY:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Fact Check API not configured. Set GOOGLE_API_KEY env var.",
            )

        if is_placeholder(FACT_CHECK_API_KEY):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Fact Check API not configured. Replace placeholder value for GOOGLE_API_KEY with a real API key.",
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Fact Check API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Fact Check API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("fact_check_validator failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: FactCheckValidatorInput) -> dict[str, Any]:
        if validated.action == "check_claim":
            return await self._check_claim(validated)
        elif validated.action == "search_claims":
            return await self._search_claims(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Helpers ──────────────────────────────────────────────────

    def _parse_review(self, review: dict) -> dict[str, Any]:
        """Extract key fields from a fact-check review."""
        publisher = review.get("publisher", {})
        claim = review.get("claimReview", [])

        # Collect ratings
        ratings = []
        for cr in claim:
            ratings.append(
                {
                    "rating": cr.get("textualRating", "Unrated"),
                    "source": cr.get("url", ""),
                    "title": cr.get("title", ""),
                }
            )

        return {
            "text": review.get("text", ""),
            "claimant": review.get("claimant", ""),
            "claim_date": review.get("claimDate", ""),
            "publisher_name": publisher.get("name", ""),
            "publisher_site": publisher.get("site", ""),
            "review_url": review.get("url", ""),
            "language": review.get("languageCode", ""),
            "ratings": ratings,
        }

    # ── Action handlers ──────────────────────────────────────────

    async def _check_claim(self, validated: FactCheckValidatorInput) -> dict[str, Any]:
        """Check a single claim against fact-check databases."""
        params: dict[str, Any] = {
            "key": FACT_CHECK_API_KEY,
            "query": validated.resolved_query,
            "languageCode": validated.language,
            "pageSize": min(validated.max_results, 20),
        }

        async with httpx.AsyncClient(timeout=FACT_CHECK_TIMEOUT) as client:
            resp = await client.get(FACT_CHECK_API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        claims = data.get("claims", [])
        reviews = [self._parse_review(c) for c in claims]

        # Compute confidence summary
        ratings_summary: dict[str, int] = {}
        for r in reviews:
            for rating in r["ratings"]:
                label = rating["rating"].lower()
                ratings_summary[label] = ratings_summary.get(label, 0) + 1

        # Determine overall assessment
        total_ratings = sum(ratings_summary.values())
        if total_ratings == 0:
            assessment = "No ratings found"
            confidence = "unknown"
        else:
            true_signal = sum(
                v for k, v in ratings_summary.items() if k in ("true", "mostly true", "correct", "accurate")
            )
            false_signal = sum(
                v
                for k, v in ratings_summary.items()
                if k
                in (
                    "false",
                    "mostly false",
                    "incorrect",
                    "inaccurate",
                    "fake",
                    "misleading",
                )
            )

            if false_signal > true_signal * 2:
                assessment = "Likely false or misleading"
                confidence = "high"
            elif false_signal > true_signal:
                assessment = "Potentially misleading"
                confidence = "medium"
            elif true_signal > false_signal * 2:
                assessment = "Likely accurate"
                confidence = "high"
            elif true_signal > false_signal:
                assessment = "Potentially accurate"
                confidence = "medium"
            else:
                assessment = "Mixed or disputed"
                confidence = "low"

        return {
            "action": "check_claim",
            "query": validated.query,
            "total_reviews": len(reviews),
            "ratings_summary": ratings_summary,
            "assessment": assessment,
            "confidence": confidence,
            "reviews": reviews,
        }

    async def _search_claims(self, validated: FactCheckValidatorInput) -> dict[str, Any]:
        """Search for recent fact-checks on a broad topic."""
        params: dict[str, Any] = {
            "key": FACT_CHECK_API_KEY,
            "query": validated.resolved_query,
            "languageCode": validated.language,
            "pageSize": validated.max_results,
        }

        async with httpx.AsyncClient(timeout=FACT_CHECK_TIMEOUT) as client:
            resp = await client.get(FACT_CHECK_API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        claims = data.get("claims", [])
        reviews = [self._parse_review(c) for c in claims]

        return {
            "action": "search_claims",
            "query": validated.query,
            "total_reviews": len(reviews),
            "reviews": reviews,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(FactCheckValidatorTool())
