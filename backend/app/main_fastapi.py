"""Main FastAPI application with security middleware."""

import logging
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.middleware.audit import AuditMiddleware
from app.api.middleware.metrics import MetricsMiddleware
from app.api.middleware.rate_limit import GlobalRateLimitMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.v1 import api_v1_router
from app.api.v1.health import router as health_router
from app.config import settings
from app.core.exceptions import AppError
from app.core.telemetry import setup_telemetry
from app.lifespan import lifespan
from app.middleware.auth_cookie import AuthCookieMiddleware
from app.middleware.scope_validator import ScopeValidationMiddleware
from app.websocket.mission_ws import ws_app

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        (
            structlog.processors.JSONRenderer()
            if settings.APP_ENV != "development"
            else structlog.dev.ConsoleRenderer()
        ),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)

# Determine if we're in production
_is_production = settings.APP_ENV != "development" and not getattr(
    settings, "DEBUG", False
)

API_DESCRIPTION = """
## Flowmanner API

Backend API for the Flowmanner workflow automation platform. Provides endpoints for:

- **Missions** -- Create, execute, and manage AI-powered workflow missions
- **Agents** -- Register and configure specialized AI agents
- **Chat** -- Real-time chat with AI models (WebSocket + REST)
- **Workspaces** -- Multi-user collaboration with role-based access
- **Graphs** -- Visual workflow builder and execution engine
- **Analytics** -- Usage metrics, token tracking, and cost analysis

### Authentication

All endpoints require a valid JWT token in the `Authorization` header:
```
Authorization: Bearer <token>
```

Obtain tokens via `POST /api/v1/auth/login` or the OAuth flow.

### Rate Limiting

API requests are rate-limited per user. Limits are returned in response headers:
- `X-RateLimit-Limit` -- Maximum requests per window
- `X-RateLimit-Remaining` -- Remaining requests in current window
- `X-RateLimit-Reset` -- Unix timestamp when the window resets
"""

app = FastAPI(
    title="Flowmanner API",
    version="0.1.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
    docs_url=None,  # We serve custom Swagger UI below
    redoc_url=None,  # We serve custom Redoc below
    openapi_url="/openapi.json",
    redirect_slashes=False,
    contact={
        "name": "Flowmanner",
        "url": "https://flowmanner.com",
        "email": "support@flowmanner.com",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://flowmanner.com/terms",
    },
    openapi_tags=[
        {"name": "health", "description": "Health and readiness probes"},
        {"name": "auth", "description": "Authentication and authorization"},
        {"name": "missions", "description": "Mission lifecycle management"},
        {"name": "agents", "description": "Agent registry and configuration"},
        {"name": "chat", "description": "Chat threads and messaging"},
        {"name": "workspaces", "description": "Workspace and team management"},
        {"name": "graphs", "description": "Visual workflow graphs"},
        {"name": "analytics", "description": "Usage metrics and reporting"},
    ],
)

# Auth v3 — httpOnly cookie middleware
# IMPORTANT: Must be added BEFORE CORSMiddleware because Starlette executes
# middleware in reverse order. AuthCookieMiddleware runs AFTER CORS, ensuring
# cookies are readable on cross-origin requests.
app.add_middleware(AuthCookieMiddleware)
app.add_middleware(ScopeValidationMiddleware)

# CORS — tightened for production
_cors_methods = (
    ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] if _is_production else ["*"]
)
_cors_headers = (
    ["Content-Type", "Authorization", "X-Request-ID"] if _is_production else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Audit logging middleware
app.add_middleware(AuditMiddleware)

# Metrics middleware
app.add_middleware(MetricsMiddleware)

# Global rate limiting middleware
app.add_middleware(GlobalRateLimitMiddleware)


class GraphQLDeprecationMiddleware:
    """ASGI middleware that adds RFC 8594 ``Deprecation`` / ``Sunset`` /
    ``Link`` headers to responses for any path registered in
    ``app.api.v2.openapi.DEPRECATION_REGISTRY``.

    Bisect step 6 (2026-06-09): the deprecation metadata moved out of this
    class and into the central registry in ``openapi.py``. The OpenAPI spec
    builder reads from the same registry, so the headers and the spec stay
    in lockstep. To deprecate a new endpoint, add a ``DeprecationEntry`` to
    ``DEPRECATION_REGISTRY`` — no middleware edits required.

    Earlier bisect steps (1–5) hard-coded the constants in this class. The
    current design supports any number of deprecated paths, with longest-
    prefix-first matching so sub-paths work transparently.
    """

    def __init__(self, app):
        self.app = app
        # Lazy: registry import is cheap but the dict is small enough to
        # snapshot at startup. _match_deprecation re-reads the registry on
        # every request, so live changes to the registry (e.g. in tests) are
        # picked up without restarting the process.
        from app.api.v2.openapi import _match_deprecation

        self._match = _match_deprecation

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        entry = self._match(path)
        if entry is None:
            await self.app(scope, receive, send)
            return

        sunset = entry.sunset_header.encode()
        link_value = entry.link_header

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"deprecation", b"true"))
                headers.append((b"sunset", sunset))
                if link_value is not None:
                    headers.append((b"link", link_value.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# Register the GraphQL deprecation middleware.
# NOTE: The class is defined above so it is in scope at registration time.
# (Earlier bisect attempt placed the registration above the class def, which
# caused silent health-check failures — see AGENTS.md bisect record.)
app.add_middleware(GraphQLDeprecationMiddleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        deprecated_endpoint=request.url.path.startswith("/api/v2/graphql"),
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    structlog.get_logger().error("Unhandled exception", error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An error occurred. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Custom Swagger UI and Redoc (dark theme)
# ---------------------------------------------------------------------------

SWAGGER_DARK_CSS = """
<style>
  body { background-color: #1a1a2e !important; }
  .swagger-ui { background-color: #1a1a2e !important; }
  .swagger-ui .topbar { display: none !important; }
  .swagger-ui .info { margin: 20px 0 !important; }
  .swagger-ui .info .title { color: #e0e0e0 !important; }
  .swagger-ui .info .description p { color: #b0b0b0 !important; }
  .swagger-ui .info a { color: #6c63ff !important; }
  .swagger-ui .scheme-container { background-color: #16213e !important; border: 1px solid #2a2a4a !important; }
  .swagger-ui .opblock-tag { color: #e0e0e0 !important; border-bottom: 1px solid #2a2a4a !important; }
  .swagger-ui .opblock-tag:hover { background-color: #16213e !important; }
  .swagger-ui .opblock { background-color: #16213e !important; border: 1px solid #2a2a4a !important; border-radius: 8px !important; }
  .swagger-ui .opblock .opblock-summary { border-bottom: 1px solid #2a2a4a !important; }
  .swagger-ui .opblock .opblock-summary-method { border-radius: 4px !important; font-size: 12px !important; min-width: 70px !important; }
  .swagger-ui .opblock .opblock-summary-path { color: #e0e0e0 !important; }
  .swagger-ui .opblock .opblock-summary-description { color: #b0b0b0 !important; }
  .swagger-ui .opblock-body { background-color: #16213e !important; }
  .swagger-ui .opblock .tab-header .tab-item.active h4 span::after { background: #6c63ff !important; }
  .swagger-ui .model-box { background-color: #16213e !important; border: 1px solid #2a2a4a !important; }
  .swagger-ui .model { color: #e0e0e0 !important; }
  .swagger-ui .model-title { color: #e0e0e0 !important; }
  .swagger-ui table thead tr th { color: #e0e0e0 !important; border-bottom: 1px solid #2a2a4a !important; }
  .swagger-ui table thead tr td { color: #b0b0b0 !important; border-bottom: 1px solid #2a2a4a !important; }
  .swagger-ui .response-col_status { color: #e0e0e0 !important; }
  .swagger-ui .response-col_description { color: #b0b0b0 !important; }
  .swagger-ui .parameter__name { color: #e0e0e0 !important; }
  .swagger-ui .parameter__type { color: #888 !important; }
  .swagger-ui .btn { border-radius: 4px !important; }
  .swagger-ui .btn.execute { background-color: #6c63ff !important; border-color: #6c63ff !important; }
  .swagger-ui .btn.cancel { background-color: #ff4757 !important; border-color: #ff4757 !important; }
  .swagger-ui .responses-inner { background-color: #16213e !important; }
  .swagger-ui .highlight-code { background-color: #0f0f23 !important; border-radius: 4px !important; }
  .swagger-ui .microlight { background-color: #0f0f23 !important; color: #e0e0e0 !important; }
  .swagger-ui section.models { border: 1px solid #2a2a4a !important; border-radius: 8px !important; }
  .swagger-ui section.models h4 { color: #e0e0e0 !important; }
  .swagger-ui .scheme-container .schemes > label { color: #b0b0b0 !important; }
</style>
"""

REDOC_DARK_CSS = """
<style>
  body { background-color: #1a1a2e; color: #e0e0e0; }
  .menu-content { background-color: #16213e !important; }
  .menu-content label { color: #e0e0e0 !important; }
  .api-content { background-color: #1a1a2e !important; }
  h1, h2, h3, h4, h5, h6 { color: #e0e0e0 !important; }
  p, li, td, th { color: #b0b0b0 !important; }
  a { color: #6c63ff !important; }
  code { background-color: #0f0f23 !important; color: #e0e0e0 !important; }
  pre { background-color: #0f0f23 !important; border: 1px solid #2a2a4a !important; }
  .http-method { border-radius: 4px !important; }
  table { border-color: #2a2a4a !important; }
  tr { border-color: #2a2a4a !important; }
  .property-name { color: #6c63ff !important; }
  .property-type { color: #888 !important; }
  .tag-section { border-bottom: 1px solid #2a2a4a !important; }
  .sidemenu { border-right: 1px solid #2a2a4a !important; }
  .scrollbar-element::-webkit-scrollbar { width: 8px; }
  .scrollbar-element::-webkit-scrollbar-track { background: #1a1a2e; }
  .scrollbar-element::-webkit-scrollbar-thumb { background: #2a2a4a; border-radius: 4px; }
</style>
"""


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """Serve Swagger UI with dark theme styling."""
    return HTMLResponse(
        content=get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{settings.APP_NAME} -- Swagger UI",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            swagger_ui_parameters={
                "deepLinking": True,
                "displayRequestDuration": True,
                "filter": True,
                "persistAuthorization": True,
                "syntaxHighlight.theme": "monokai",
                "tryItOutEnabled": True,
            },
            custom_css=SWAGGER_DARK_CSS,
        ).body
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    """Serve Redoc documentation with dark theme styling."""
    return HTMLResponse(
        content=get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{settings.APP_NAME} -- API Reference",
            redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            with_google_fonts=False,
            custom_css=REDOC_DARK_CSS,
        ).body
    )


app.include_router(health_router)
app.include_router(health_router, prefix="/api")
app.include_router(api_v1_router)

from app.api.v2 import api_v2_router
from app.api.v2.idempotency import IdempotencyFinalizationMiddleware
from app.api.v2.middleware import register_v2_exception_handlers
from app.api.v2.rate_limit_headers import RateLimitHeadersMiddleware
from app.api.v2.validation_middleware import register_strict_validation

register_v2_exception_handlers(app)
register_strict_validation(app)
# Rate limit headers: injects X-RateLimit-* into every v2 response
app.add_middleware(RateLimitHeadersMiddleware)
# Idempotency finalization: must run AFTER routes but captures responses
app.add_middleware(IdempotencyFinalizationMiddleware)
app.include_router(api_v2_router)

# ---------------------------------------------------------------------------
# Auth v3 — register v3 routers, exception handlers, and cookie middleware
# ---------------------------------------------------------------------------
from app.api.v3 import api_v3_router
from app.api.v3.middleware import register_v3_exception_handlers

register_v3_exception_handlers(app)
app.include_router(api_v3_router)

try:
    import jwt as _jwt
    from strawberry.fastapi import GraphQLRouter

    from app.api.v2.schema import schema as gql_schema
    from app.config import settings as _settings
    from app.database import AsyncSessionLocal
    from app.services.auth_service import get_user_by_id

    async def _gql_context_getter(request: Request):
        ctx = {}
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            try:
                payload = _jwt.decode(
                    token, _settings.JWT_SECRET_KEY, algorithms=["HS256"]
                )
                user_id = payload.get("sub")
                if user_id:
                    async with AsyncSessionLocal() as session:
                        user = await get_user_by_id(session, int(user_id))
                        if user and user.is_active:
                            ctx["user"] = user
                            ctx["db"] = session
            except Exception:
                pass  # Token decode failure is expected for unauthenticated requests
        return ctx

    graphql_app = GraphQLRouter(gql_schema, context_getter=_gql_context_getter)
    app.include_router(graphql_app, prefix="/api/v2/graphql")
except ImportError:
    logging.getLogger(__name__).warning(
        "strawberry-graphql not installed — GraphQL endpoint disabled"
    )

# Extensions / Plugin API — registered independently of GraphQL
from app.api.v1.extensions import router as extensions_router

app.include_router(extensions_router, prefix="/api")

# OpenTelemetry — opt-in via OTLP_ENDPOINT env var
try:
    from app.database import engine as db_engine

    setup_telemetry(app, engine=db_engine)
except Exception as e:
    logging.getLogger(__name__).warning(f"Telemetry setup failed: {e}")


@app.get("/api/stats")
async def get_stats():
    """Return system-wide aggregate execution stats from the database.

    Falls back to zeros if the database is unavailable — the endpoint
    must never 500 from a transient DB issue.
    """
    try:
        from sqlalchemy import func, select

        from app.database import AsyncSessionLocal
        from app.models.graph import GraphExecution

        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(
                    func.count().label("total_runs"),
                    func.count()
                    .filter(GraphExecution.status == "completed")
                    .label("success"),
                    func.count()
                    .filter(GraphExecution.status == "failed")
                    .label("failed"),
                )
            )
            row = rows.one_or_none()
            if row is None:
                return {
                    "total_runs": 0,
                    "successful_runs": 0,
                    "failed_runs": 0,
                    "avg_duration_ms": 0,
                    "total_tokens": 0,
                }

            total = row.total_runs or 0
            success = row.success or 0
            # Average duration for completed executions (system-wide)
            dur_rows = await session.execute(
                select(
                    func.avg(
                        func.extract(
                            "epoch",
                            GraphExecution.completed_at - GraphExecution.started_at,
                        )
                    ).label("avg_duration")
                ).where(
                    GraphExecution.status == "completed",
                    GraphExecution.completed_at.isnot(None),
                    GraphExecution.started_at.isnot(None),
                )
            )
            avg_dur = dur_rows.scalar() or 0.0

            return {
                "total_runs": total,
                "successful_runs": success,
                "failed_runs": row.failed or 0,
                "avg_duration_ms": int(float(avg_dur) * 1000),
                "total_tokens": 0,  # TODO: aggregate from LLMCallRecord table
            }
    except Exception:
        return {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "avg_duration_ms": 0,
            "total_tokens": 0,
        }


# ---------------------------------------------------------------------------
# Resilient OpenAPI spec generation
# ---------------------------------------------------------------------------
# Many Pydantic models use `from __future__ import annotations` with types
# guarded by `if TYPE_CHECKING:`.  When FastAPI generates the OpenAPI spec it
# tries to resolve every schema eagerly, and a single unresolved forward ref
# crashes the entire spec.  The wrapper below catches the crash, then builds
# the spec incrementally — testing each API route against a known-good set
# so broken routes are skipped with a warning.

from fastapi.routing import APIRoute as _APIRoute

_original_openapi = app.openapi


def _resilient_openapi():
    """Generate OpenAPI spec, gracefully skipping routes with unresolved types."""
    cached = getattr(app, "_openapi_schema", None)
    if cached:
        return cached
    try:
        schema = _original_openapi()
        app._openapi_schema = schema
        return schema
    except Exception:
        # Full generation crashed — fall back to incremental route-by-route
        pass

    from fastapi.openapi.utils import get_openapi

    # Separate API routes (may have broken schemas) from non-API routes
    api_routes = [r for r in app.routes if isinstance(r, _APIRoute)]
    other_routes = [r for r in app.routes if not isinstance(r, _APIRoute)]

    # Test each API route against the known-good set (incremental).
    # Cap at 20 skips to avoid O(n²) blowup if many routes break.
    ok_routes = list(other_routes)
    skipped: list[str] = []
    for route in api_routes:
        if len(skipped) >= 20:
            skipped.append(f"(... and more, giving up)")
            break
        try:
            get_openapi(title="t", version="v", routes=ok_routes + [route])
            ok_routes.append(route)
        except Exception:
            skipped.append(route.path)

    if skipped:
        logging.getLogger(__name__).warning(
            "OpenAPI: %d routes skipped due to unresolved forward refs: %s",
            len(skipped),
            ", ".join(skipped[:10]),
        )

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=ok_routes,
        tags=app.openapi_tags,
    )
    app._openapi_schema = schema
    return schema


app.openapi = _resilient_openapi

app.mount("/ws", ws_app)
