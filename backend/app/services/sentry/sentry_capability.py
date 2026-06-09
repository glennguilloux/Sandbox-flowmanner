"""
Sentry Capability Registration

Registers Sentry AI capabilities with the platform's capability registry
for use by agents and workflows.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register_sentry_capabilities(registry=None) -> bool:
    """
    Register Sentry capabilities with the capability registry.

    Args:
        registry: Optional registry instance. If None, uses singleton.

    Returns:
        True if registration successful
    """
    try:
        if registry is None:
            from app.services.nexus.capability_registry import get_capability_registry

            registry = get_capability_registry()

        # Import the MCP client

        # Register error analysis capability
        registry.register(_create_analyze_error_capability())

        # Register fix recommendation capability
        registry.register(_create_fix_recommendation_capability())

        # Register issue search capability
        registry.register(_create_search_issues_capability())

        # Register issue resolution capability
        registry.register(_create_resolve_issue_capability())

        logger.info("✅ Registered Sentry capabilities")
        return True

    except Exception as e:
        logger.error("Failed to register Sentry capabilities: %s", e)
        return False


def _create_analyze_error_capability():
    """Create the error analysis capability."""
    from app.services.nexus.capability_registry import Capability

    from .sentry_mcp_client import get_sentry_mcp_client

    async def analyze_error_handler(params: dict[str, Any]) -> dict[str, Any]:
        """Handle error analysis requests."""
        issue_id = params.get("issue_id")
        if not issue_id:
            return {"error": "issue_id is required"}

        client = get_sentry_mcp_client()
        analysis = await client.analyze_with_seer(issue_id)

        if analysis:
            return analysis.to_dict()
        return {"error": "Analysis failed", "issue_id": issue_id}

    return Capability(
        id="sentry:analyze_error",
        name="Sentry AI Error Analysis",
        description="Analyze errors using Sentry Seer AI for root cause identification",
        category="monitoring",
        handler=analyze_error_handler,
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Sentry issue ID to analyze",
                }
            },
            "required": ["issue_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "root_cause": {"type": "string"},
                "confidence": {"type": "number"},
                "suggested_fix": {"type": "string"},
                "affected_components": {"type": "array", "items": {"type": "string"}},
                "similar_issues": {"type": "array", "items": {"type": "string"}},
            },
        },
        requires_auth=True,
        cost_estimate={
            "type": "api_call",
            "provider": "sentry",
            "operation": "seer_analyze",
        },
        rate_limit=60,  # 60 requests per minute
        timeout_seconds=30,
        metadata={"provider": "sentry", "feature": "seer_ai", "requires_mcp": True},
    )


def _create_fix_recommendation_capability():
    """Create the fix recommendation capability."""
    from app.services.nexus.capability_registry import Capability

    from .sentry_mcp_client import get_sentry_mcp_client

    async def fix_recommendation_handler(params: dict[str, Any]) -> dict[str, Any]:
        """Handle fix recommendation requests."""
        issue_id = params.get("issue_id")
        if not issue_id:
            return {"error": "issue_id is required"}

        client = get_sentry_mcp_client()
        recommendation = await client.get_fix_recommendation(issue_id)

        if recommendation:
            return recommendation.to_dict()
        return {"error": "Fix recommendation failed", "issue_id": issue_id}

    return Capability(
        id="sentry:fix_recommendation",
        name="Sentry AI Fix Recommendation",
        description="Get AI-generated fix recommendations for Sentry issues",
        category="monitoring",
        handler=fix_recommendation_handler,
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Sentry issue ID to get fix for",
                }
            },
            "required": ["issue_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "code_changes": {"type": "array"},
                "confidence": {"type": "number"},
                "auto_applicable": {"type": "boolean"},
                "requires_approval": {"type": "boolean"},
                "estimated_impact": {"type": "string"},
            },
        },
        requires_auth=True,
        cost_estimate={
            "type": "api_call",
            "provider": "sentry",
            "operation": "seer_fix",
        },
        rate_limit=60,
        timeout_seconds=60,
        metadata={
            "provider": "sentry",
            "feature": "seer_ai",
            "requires_mcp": True,
            "approval_threshold": 0.95,
        },
    )


def _create_search_issues_capability():
    """Create the issue search capability."""
    from app.services.nexus.capability_registry import Capability

    from .sentry_mcp_client import get_sentry_mcp_client

    async def search_issues_handler(params: dict[str, Any]) -> dict[str, Any]:
        """Handle issue search requests."""
        query = params.get("query", "")
        fingerprint = params.get("fingerprint")
        limit = params.get("limit", 10)

        client = get_sentry_mcp_client()
        issues = await client.search_similar_issues(
            fingerprint=fingerprint, query=query, limit=limit
        )

        return {"issues": [issue.to_dict() for issue in issues], "count": len(issues)}

    return Capability(
        id="sentry:search_issues",
        name="Sentry Issue Search",
        description="Search for similar issues across Sentry projects",
        category="monitoring",
        handler=search_issues_handler,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "fingerprint": {
                    "type": "string",
                    "description": "Issue fingerprint to match",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10,
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "status": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                    },
                },
                "count": {"type": "integer"},
            },
        },
        requires_auth=True,
        cost_estimate={"type": "api_call", "provider": "sentry", "operation": "search"},
        rate_limit=120,
        timeout_seconds=15,
        metadata={"provider": "sentry", "feature": "issue_search"},
    )


def _create_resolve_issue_capability():
    """Create the issue resolution capability."""
    from app.services.nexus.capability_registry import Capability

    from .sentry_mcp_client import get_sentry_mcp_client

    async def resolve_issue_handler(params: dict[str, Any]) -> dict[str, Any]:
        """Handle issue resolution requests."""
        issue_id = params.get("issue_id")
        if not issue_id:
            return {"error": "issue_id is required"}

        client = get_sentry_mcp_client()
        success = await client.resolve_issue(issue_id)

        return {
            "issue_id": issue_id,
            "resolved": success,
            "message": "Issue resolved" if success else "Failed to resolve issue",
        }

    return Capability(
        id="sentry:resolve_issue",
        name="Sentry Issue Resolution",
        description="Mark a Sentry issue as resolved",
        category="monitoring",
        handler=resolve_issue_handler,
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Sentry issue ID to resolve",
                }
            },
            "required": ["issue_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "resolved": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
        requires_auth=True,
        cost_estimate={
            "type": "api_call",
            "provider": "sentry",
            "operation": "update_issue",
        },
        rate_limit=60,
        timeout_seconds=10,
        metadata={"provider": "sentry", "feature": "issue_management"},
    )


def unregister_sentry_capabilities(registry=None) -> bool:
    """
    Unregister all Sentry capabilities from the capability registry.

    Args:
        registry: Optional registry instance. If None, uses singleton.

    Returns:
        True if unregistration successful
    """
    try:
        if registry is None:
            from app.services.nexus.capability_registry import get_capability_registry

            registry = get_capability_registry()

        capability_ids = [
            "sentry:analyze_error",
            "sentry:fix_recommendation",
            "sentry:search_issues",
            "sentry:resolve_issue",
        ]

        for cap_id in capability_ids:
            try:
                registry.unregister(cap_id)
            except Exception as e:
                logger.debug("Could not unregister capability %s: %s", cap_id, e)

        logger.info("Unregistered Sentry capabilities")
        return True

    except Exception as e:
        logger.error("Failed to unregister Sentry capabilities: %s", e)
        return False
