#!/usr/bin/env python3
"""Seed consulting-grade mission templates for the A+E Plan.

These templates are the foundation of the consulting deliverables.
Each one runs on DeepSeek V4 Flash (or any capable model) and produces
a real deliverable that can be shared with clients via the replay export.

Usage:
    cd /opt/flowmanner
    docker compose exec backend python scripts/seed_consulting_templates.py
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Template definitions ──────────────────────────────────────────

TEMPLATES = [
    {
        "name": "Code Review Agent",
        "description": (
            "Automated PR review with severity ratings, suggested fixes, and risk assessment. "
            "Analyzes code changes for bugs, security issues, performance problems, and style violations. "
            "Produces a structured report suitable for sharing with engineering teams."
        ),
        "category": "consulting",
        "icon": "🔍",
        "is_public": True,
        "is_builtin": True,
        "mission_type": "solo",
        "priority": "high",
        "tags": ["code-review", "consulting", "deliverable", "engineering"],
        "default_tasks": [
            {
                "title": "Analyze code changes and produce structured review",
                "description": (
                    "You are a senior software engineer conducting a code review. "
                    "Analyze the provided code changes and produce a structured review report.\n\n"
                    "For each issue found, include:\n"
                    "- **Severity**: Critical / High / Medium / Low / Info\n"
                    "- **Category**: Bug / Security / Performance / Style / Architecture\n"
                    "- **File and line**: Where the issue is\n"
                    "- **Description**: What's wrong\n"
                    "- **Suggested fix**: How to fix it\n\n"
                    "At the end, provide:\n"
                    "- Overall risk assessment (Low / Medium / High / Critical)\n"
                    "- Summary of findings\n"
                    "- Recommendation (Approve / Request Changes / Block)\n\n"
                    "Format as a clean markdown report."
                ),
                "task_type": "llm",
                "model_id": "deepseek-v4-flash",
                "max_tokens": 4000,
                "temperature": 0.3,
            }
        ],
        "default_plan": {
            "strategy": "solo",
            "description": "Single-agent code review with structured output",
        },
        "default_constraints": {
            "max_cost_usd": 0.50,
            "max_iterations": 5,
            "max_wall_time_seconds": 120,
        },
        "expected_behaviors": [
            {
                "name": "produces_structured_report",
                "description": "Output contains severity ratings and categories",
                "check_type": "contains",
                "check_value": "Severity",
            },
            {
                "name": "includes_recommendation",
                "description": "Output ends with an approve/reject recommendation",
                "check_type": "contains_any",
                "check_value": ["Approve", "Request Changes", "Block"],
            },
        ],
    },
    {
        "name": "Competitive Intelligence Report",
        "description": (
            "Market analysis and competitor comparison for a given product or company. "
            "Produces a structured report with SWOT analysis, competitive landscape, "
            "market positioning, and strategic recommendations. Delivered in minutes, not weeks."
        ),
        "category": "consulting",
        "icon": "📊",
        "is_public": True,
        "is_builtin": True,
        "mission_type": "solo",
        "priority": "high",
        "tags": ["competitive-intelligence", "consulting", "deliverable", "strategy"],
        "default_tasks": [
            {
                "title": "Research and analyze competitive landscape",
                "description": (
                    "You are a competitive intelligence analyst. Based on the company/product "
                    "described below, produce a comprehensive competitive intelligence report.\n\n"
                    "Include the following sections:\n\n"
                    "## Executive Summary\n"
                    "One paragraph summarizing the competitive position.\n\n"
                    "## Competitor Profiles\n"
                    "For each major competitor (3-5):\n"
                    "- Company name and description\n"
                    "- Key strengths\n"
                    "- Key weaknesses\n"
                    "- Market share / traction (if known)\n"
                    "- Pricing model\n\n"
                    "## SWOT Analysis\n"
                    "- Strengths\n"
                    "- Weaknesses\n"
                    "- Opportunities\n"
                    "- Threats\n\n"
                    "## Market Positioning\n"
                    "Where the target sits relative to competitors.\n\n"
                    "## Strategic Recommendations\n"
                    "3-5 actionable recommendations based on the analysis.\n\n"
                    "Format as a clean markdown report. Be specific and actionable."
                ),
                "task_type": "llm",
                "model_id": "deepseek-v4-flash",
                "max_tokens": 4000,
                "temperature": 0.5,
            }
        ],
        "default_plan": {
            "strategy": "solo",
            "description": "Single-agent competitive analysis with structured output",
        },
        "default_constraints": {
            "max_cost_usd": 0.50,
            "max_iterations": 5,
            "max_wall_time_seconds": 180,
        },
        "expected_behaviors": [
            {
                "name": "includes_swot",
                "description": "Output contains SWOT analysis",
                "check_type": "contains",
                "check_value": "SWOT",
            },
            {
                "name": "includes_recommendations",
                "description": "Output contains strategic recommendations",
                "check_type": "contains_any",
                "check_value": ["Recommendation", "Strategic", "Action"],
            },
        ],
    },
    {
        "name": "Document Q&A System",
        "description": (
            "RAG-based question answering over a document corpus. "
            "Upload documents, ask questions, and get cited answers. "
            "Suitable for legal, compliance, finance, and research use cases."
        ),
        "category": "consulting",
        "icon": "📚",
        "is_public": True,
        "is_builtin": True,
        "mission_type": "solo",
        "priority": "high",
        "tags": ["rag", "document-qa", "consulting", "deliverable", "knowledge"],
        "default_tasks": [
            {
                "title": "Answer questions based on retrieved document context",
                "description": (
                    "You are a document analysis expert. Answer the user's question "
                    "based ONLY on the provided document context.\n\n"
                    "Rules:\n"
                    "1. Only use information from the provided context\n"
                    "2. Cite the specific document/section where you found each answer\n"
                    "3. If the context doesn't contain enough information, say so clearly\n"
                    "4. Be precise and factual — do not speculate\n"
                    "5. Format answers in clean markdown with citations\n\n"
                    "For each answer, include:\n"
                    "- The direct answer\n"
                    "- Citation (document name + section/page)\n"
                    "- Confidence level (High / Medium / Low)\n"
                    "- Any caveats or limitations\n\n"
                    "If multiple documents are relevant, synthesize across them."
                ),
                "task_type": "rag",
                "model_id": "deepseek-v4-flash",
                "max_tokens": 3000,
                "temperature": 0.2,
                "collection": "default",
            }
        ],
        "default_plan": {
            "strategy": "solo",
            "description": "RAG-augmented document Q&A with citations",
        },
        "default_constraints": {
            "max_cost_usd": 0.30,
            "max_iterations": 10,
            "max_wall_time_seconds": 120,
        },
        "expected_behaviors": [
            {
                "name": "includes_citations",
                "description": "Output includes document citations",
                "check_type": "contains_any",
                "check_value": ["document", "section", "page", "source"],
            },
            {
                "name": "handles_missing_info",
                "description": "Output acknowledges when context is insufficient",
                "check_type": "contains_any",
                "check_value": ["context", "provided", "information", "not enough"],
            },
        ],
    },
]


async def seed_templates():
    """Insert consulting templates into the database."""
    from app.database import AsyncSessionLocal
    from app.models.mission_advanced_models import MissionTemplate

    async with AsyncSessionLocal() as db:
        # Get system user ID (first user or create one)
        from app.models.user import User

        result = await db.execute(select(User).order_by(User.id).limit(1))
        system_user = result.scalar_one_or_none()

        if system_user is None:
            logger.error("No users found in database. Create a user first.")
            return

        user_id = system_user.id
        logger.info("Using user ID %d for template ownership", user_id)

        for tmpl in TEMPLATES:
            # Check if template already exists
            existing = await db.execute(select(MissionTemplate).where(MissionTemplate.name == tmpl["name"]))
            if existing.scalar_one_or_none() is not None:
                logger.info("Template '%s' already exists — skipping", tmpl["name"])
                continue

            template = MissionTemplate(
                id=str(uuid4()),
                user_id=user_id,
                name=tmpl["name"],
                description=tmpl["description"],
                category=tmpl["category"],
                icon=tmpl["icon"],
                is_public=tmpl["is_public"],
                is_builtin=tmpl["is_builtin"],
                mission_type=tmpl["mission_type"],
                priority=tmpl["priority"],
                default_tasks=tmpl["default_tasks"],
                default_plan=tmpl["default_plan"],
                default_constraints=tmpl["default_constraints"],
                tags=tmpl["tags"],
                expected_behaviors=tmpl.get("expected_behaviors", []),
                usage_count=0,
                rating=5.0,
            )
            db.add(template)
            logger.info("Created template: %s", tmpl["name"])

        await db.commit()
        logger.info("Done — %d consulting templates seeded", len(TEMPLATES))


if __name__ == "__main__":
    asyncio.run(seed_templates())
