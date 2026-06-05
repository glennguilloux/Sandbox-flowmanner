"""OpenAPI 3.1 spec for the v2 public platform API.

Serves a dedicated /api/v2/openapi.json with:
- Only v2 routes (filtered from the full app schema)
- Security schemes (Bearer JWT, API Key)
- Rate limit tier documentation
- Proper contact, license, and server info
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["v2-openapi"])


# ── Security Schemes ──────────────────────────────────────────────────────────

_SECURITY_SCHEMES = {
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT access token obtained from POST /api/v2/auth/login",
    },
    "ApiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Workspace-scoped API key (future). Currently use Bearer JWT.",
    },
}

# ── Rate Limit Tier Documentation ─────────────────────────────────────────────

_TIER_DOCS = {
    "x-rate-limit-tiers": {
        "free": {
            "description": "Default tier for new accounts",
            "requests_per_minute": 60,
            "missions_per_day": 5,
            "missions_per_month": 150,
            "concurrent_missions": 1,
            "api_access": False,
        },
        "starter": {
            "description": "Starter plan with increased limits",
            "requests_per_minute": 120,
            "missions_per_day": 20,
            "missions_per_month": 600,
            "concurrent_missions": 3,
            "api_access": True,
        },
        "pro": {
            "description": "Professional tier for power users",
            "requests_per_minute": 300,
            "missions_per_day": 100,
            "missions_per_month": 3000,
            "concurrent_missions": 10,
            "api_access": True,
        },
        "enterprise": {
            "description": "Enterprise tier with custom limits",
            "requests_per_minute": 1200,
            "missions_per_day": "unlimited",
            "missions_per_month": "unlimited",
            "concurrent_missions": 50,
            "api_access": True,
        },
    },
    "x-rate-limit-headers": {
        "X-RateLimit-Limit": "Maximum requests in the current window",
        "X-RateLimit-Remaining": "Remaining requests in the current window",
        "X-RateLimit-Reset": "Unix timestamp when the window resets",
        "Retry-After": "Seconds to wait before retrying (on 429)",
    },
}


def _build_v2_openapi(request: Request) -> dict[str, Any]:
    """Build the v2-only OpenAPI spec from the full app schema."""
    from app.main_fastapi import app

    # Get the full OpenAPI schema
    full_schema = app.openapi()

    # Filter to only v2 paths
    v2_paths = {}
    for path, methods in full_schema.get("paths", {}).items():
        if path.startswith("/api/v2"):
            # Strip the /api/v2 prefix for cleaner v2-native docs
            clean_path = path[7:] if path.startswith("/api/v2/") else "/"
            v2_paths[clean_path] = methods

    # Filter to only v2 schemas
    v2_schemas = {}
    full_schemas = (full_schema.get("components", {}) or {}).get("schemas", {}) or {}
    v2_referenced = set()

    # Collect all $ref references from v2 paths
    import json
    v2_paths_str = json.dumps(v2_paths)
    for schema_name in full_schemas:
        if f"#/components/schemas/{schema_name}" in v2_paths_str:
            v2_referenced.add(schema_name)

    # Add transitively referenced schemas
    for schema_name in list(v2_referenced):
        schema_str = json.dumps(full_schemas.get(schema_name, {}))
        for other_name in full_schemas:
            if other_name not in v2_referenced and f"#/components/schemas/{other_name}" in schema_str:
                v2_referenced.add(other_name)

    for name in v2_referenced:
        v2_schemas[name] = full_schemas[name]

    # Build the v2-specific OpenAPI spec
    base_url = str(request.base_url).rstrip("/")
    v2_spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Flowmanner Public Platform API",
            "version": "2.0.0",
            "description": (
                "## Flowmanner Platform API v2\n\n"
                "Public API for the Flowmanner AI workflow automation platform.\n\n"
                "### Authentication\n"
                "All endpoints require a valid JWT token:\n"
                "```\nAuthorization: Bearer <token>\n```\n"
                "Obtain tokens via `POST /auth/login` or `POST /auth/register`.\n\n"
                "### Rate Limiting\n"
                "Requests are rate-limited per user and per workspace tier.\n"
                "Tier limits are described in the `x-rate-limit-tiers` extension below.\n"
                "Rate limit headers are included in every response.\n\n"
                "### Response Envelope\n"
                "All v2 responses follow a standard envelope:\n"
                "```json\n"
                '{ "data": <payload>, "meta": { "request_id": "...", "timestamp": "..." }, "error": null }\n'
                "```\n\n"
                "### Pagination\n"
                "List endpoints support both offset and cursor pagination.\n"
                "- Offset: `?page=1&per_page=20`\n"
                "- Cursor: `?cursor=<token>&direction=after&limit=20`\n\n"
                "### Idempotency\n"
                "Mutation endpoints support the `Idempotency-Key` header for safe retries.\n"
            ),
            "contact": {
                "name": "Flowmanner",
                "url": "https://flowmanner.com",
                "email": "support@flowmanner.com",
            },
            "license": {
                "name": "Proprietary",
                "url": "https://flowmanner.com/terms",
            },
            **_TIER_DOCS,
        },
        "servers": [
            {"url": f"{base_url}/api/v2", "description": "Production API v2"},
        ],
        "paths": v2_paths,
        "components": {
            "securitySchemes": _SECURITY_SCHEMES,
            "schemas": v2_schemas,
        },
        "security": [{"BearerAuth": []}],
        "tags": [
            {"name": "v2-auth", "description": "Authentication — login, register, token refresh, 2FA"},
            {"name": "v2-missions", "description": "Mission lifecycle — create, execute, plan, abort, retry"},
            {"name": "v2-agents", "description": "Agent registry and template management"},
            {"name": "v2-chat", "description": "Chat threads, messages, LLM streaming, branches"},
            {"name": "v2-workspaces", "description": "Workspace, team, and member management"},
            {"name": "v2-search", "description": "Unified cross-entity search"},
            {"name": "v2-dashboard", "description": "Mission history, cost analytics, execution logs, stats"},
            {"name": "v2-integrations", "description": "HTTP outbound integration configs and execution logs"},
            {"name": "v2-integrations-oauth", "description": "OAuth app registration and connection flow"},
            {"name": "v2-integrations-actions", "description": "Discover and execute integration actions"},
        ],
    }

    return v2_spec


# ── Cached spec (built once, served from cache) ──────────────────────────────

_v2_spec_cache: dict[str, Any] | None = None
_v2_spec_server_url: str | None = None


@router.get("/openapi.json", include_in_schema=False)
async def get_v2_openapi(request: Request):
    """Serve the v2-only OpenAPI 3.1 spec.

    This provides a clean, public-facing API spec that only exposes v2 endpoints,
    with proper security schemes, rate limit tier documentation, and server info.
    Cached after first build — invalidate by restarting the server.
    """
    global _v2_spec_cache, _v2_spec_server_url

    try:
        current_base = str(request.base_url).rstrip("/")
        if _v2_spec_cache is None or _v2_spec_server_url != current_base:
            _v2_spec_cache = _build_v2_openapi(request)
            _v2_spec_server_url = current_base
        return JSONResponse(content=_v2_spec_cache, headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        })
    except Exception as e:
        logger.error("v2_openapi_build_failed", error=str(e), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to generate OpenAPI spec"},
        )


@router.get("/openapi-tiers.json", include_in_schema=False)
async def get_tier_docs():
    """Serve rate limit tier documentation as a standalone document."""
    return JSONResponse(content=_TIER_DOCS)
