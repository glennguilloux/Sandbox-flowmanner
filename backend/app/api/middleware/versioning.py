"""API Versioning Middleware.

Supports version negotiation via:
- Accept-Version header
- URL path prefix (/v1/, /v2/)
- Query parameter (?version=v1)

Adds deprecation headers to responses for deprecated versions.
"""

import re
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Version configuration
SUPPORTED_VERSIONS = {"v1", "v2", "v3"}
DEPRECATED_VERSIONS: dict[str, datetime] = {
    # "v0": datetime(2025, 12, 31, tzinfo=timezone.utc),  # Example
}
DEFAULT_VERSION = "v1"
CURRENT_VERSION = "v2"

# Version header names
VERSION_HEADER = "Accept-Version"
DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
API_VERSION_HEADER = "X-API-Version"


def _extract_version_from_path(path: str) -> str | None:
    """Extract version from URL path like /api/v1/..."""
    match = re.match(r"^/api/(v\d+)/", path)
    return match.group(1) if match else None


def _negotiate_version(request: Request) -> str:
    """
    Negotiate API version from request.

    Priority:
    1. Accept-Version header
    2. URL path prefix
    3. Query parameter
    4. Default version
    """
    # 1. Check Accept-Version header
    header_version = request.headers.get(VERSION_HEADER)
    if header_version:
        version = header_version.lower().strip()
        if version in SUPPORTED_VERSIONS or version in DEPRECATED_VERSIONS:
            return version
        # Invalid version requested
        return None  # Will trigger 400

    # 2. Check URL path
    path_version = _extract_version_from_path(str(request.url.path))
    if path_version:
        return path_version

    # 3. Check query parameter
    query_version = request.query_params.get("version")
    if query_version:
        return query_version.lower().strip()

    # 4. Default
    return DEFAULT_VERSION


class APIVersioningMiddleware(BaseHTTPMiddleware):
    """Middleware for API version negotiation and deprecation headers."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip versioning for non-API paths
        path = str(request.url.path)
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip for docs, openapi, health
        if any(p in path for p in ["/docs", "/redoc", "/openapi", "/health"]):
            return await call_next(request)

        # Negotiate version
        version = _negotiate_version(request)

        # Handle invalid version
        if version is None:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_version",
                    "message": f"Unsupported API version. Supported: {sorted(SUPPORTED_VERSIONS)}",
                    "supported_versions": sorted(SUPPORTED_VERSIONS),
                },
            )

        # Handle version not in supported or deprecated
        if version not in SUPPORTED_VERSIONS and version not in DEPRECATED_VERSIONS:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_version",
                    "message": f"API version '{version}' not found. Supported: {sorted(SUPPORTED_VERSIONS)}",
                    "supported_versions": sorted(SUPPORTED_VERSIONS),
                },
            )

        # Store version in request state
        request.state.api_version = version

        # Process request
        response = await call_next(request)

        # Add version headers to response
        response.headers[API_VERSION_HEADER] = version

        # Add deprecation headers if applicable
        if version in DEPRECATED_VERSIONS:
            sunset_date = DEPRECATED_VERSIONS[version]
            response.headers[DEPRECATION_HEADER] = "true"
            response.headers[SUNSET_HEADER] = sunset_date.strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            # Add Link header to new version docs
            response.headers["Link"] = (
                f'</api/{CURRENT_VERSION}/docs>; rel="successor-version"'
            )

        return response


def get_api_version(request: Request) -> str:
    """Helper to get the negotiated API version from request state."""
    return getattr(request.state, "api_version", DEFAULT_VERSION)


def deprecated(sunset_date: datetime, replacement: str = ""):
    """Decorator to mark an endpoint as deprecated."""
    def decorator(func):
        func._deprecated = True
        func._sunset_date = sunset_date
        func._replacement = replacement
        return func
    return decorator
