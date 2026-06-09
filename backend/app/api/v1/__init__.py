import logging
from enum import Enum

from fastapi import APIRouter

logger = logging.getLogger(__name__)


class RouterTier(Enum):
    """Import-criticality tier for router modules.

    CRITICAL: Fail startup if import fails (auth, mission, chat, graph).
    STANDARD: Log warning on import failure (most routers).
    OPTIONAL: Log info only — expected to be absent in some deployments.
    """

    CRITICAL = "critical"
    STANDARD = "standard"
    OPTIONAL = "optional"


def _import_router(module_name, attr="router", tier=RouterTier.STANDARD):
    """Import a v1 router with severity-gated error handling.

    Replaces the old _safe_import which silently swallowed **all** import
    errors.  Now CRITICAL routers raise immediately, STANDARD routers log
    a warning, and OPTIONAL routers log only at INFO level.
    """
    try:
        mod = __import__(f"app.api.v1.{module_name}", fromlist=[attr])
        return getattr(mod, attr)
    except ImportError:
        msg = f"Router import failed: app.api.v1.{module_name}"
        if tier == RouterTier.CRITICAL:
            logger.critical(msg)
            raise
        elif tier == RouterTier.OPTIONAL:
            logger.info("Optional router not available: %s", module_name)
        else:
            logger.warning("Router not available: %s", module_name)
        return None
    except Exception as e:
        msg = f"Router import failed for app.api.v1.{module_name}: {e}"
        logger.error(msg, exc_info=True)
        if tier == RouterTier.CRITICAL:
            raise RuntimeError(msg) from e
        return None


# ── CRITICAL routers: fail startup if not importable ────────────────

auth_router = _import_router("auth", tier=RouterTier.CRITICAL)
users_router = _import_router("users", tier=RouterTier.CRITICAL)
mission_router = _import_router("mission", tier=RouterTier.CRITICAL)
chat_router = _import_router("chat", tier=RouterTier.CRITICAL)
graph_router = _import_router("graph", tier=RouterTier.CRITICAL)
browser_router = _import_router("browser", tier=RouterTier.CRITICAL)

# ── STANDARD routers: warn if missing ───────────────────────────────

agent_router = _import_router("agent")
agent_registry_router = _import_router("agent_registry")
analytics_router = _import_router("analytics")
api_keys_router = _import_router("api_keys", "router")
user_keys_router = _import_router("api_keys", "user_keys_router")
byok_router = _import_router("byok")
dashboard_router = _import_router("dashboard")
file_router = _import_router("file")
files_router_obj = _import_router("file", "files_router")
flow_compat_router = _import_router("flow_compat")
llm_router = _import_router("llm")
llm_advanced_router = _import_router("llm_advanced")
memory_router = _import_router("memory")
mission_advanced_router = _import_router("mission_advanced_routes")
mission_decomposition_router = _import_router("mission_decomposition_routes")
oidc_router = _import_router("oidc")
onboarding_router = _import_router("onboarding")
delegations_router = _import_router("delegations")
roles_router = _import_router("roles")
feedback_router = _import_router("feedback_routes")
orchestration_router = _import_router("orchestration")
subscription_router = _import_router("subscription")
usage_router = _import_router("usage")
reliability_router = _import_router("reliability")
webhook_router = _import_router("webhooks")
templates_router = _import_router("templates")
trigger_router = _import_router("triggers")
roadmap_router = _import_router("roadmap")
votes_router = _import_router("votes")
admin_router = _import_router("admin")
stats_router = _import_router("stats")
workspace_router = _import_router("workspace", "workspace_router")
team_router = _import_router("workspace", "team_router")
invitation_router = _import_router("workspace", "invitation_router")
presence_router = _import_router("presence_api")
activity_router = _import_router("workspace_activity")
messages_router = _import_router("workspace_messages")
tools_router = _import_router("tools")
linear_router = _import_router("linear")
search_router = _import_router("search")
data_export_router = _import_router("data_export")
feature_flags_router = _import_router("feature_flags")
changelog_router = _import_router("changelog")
observability_router = _import_router("observability")
rate_limits_router = _import_router("rate_limits")
evaluation_router = _import_router("evaluation")
agent_capabilities_router = _import_router("agent_capabilities")
swarm_router = _import_router("swarm")
swarm_protocol_router = _import_router("swarm_protocol")
rag_router = _import_router("rag")
sandbox_router = _import_router("sandbox")
sandbox_preview_router = _import_router("sandbox_preview")
playground_router = _import_router("playground", tier=RouterTier.OPTIONAL)
admin_sandboxes_router = _import_router("admin_sandboxes", tier=RouterTier.OPTIONAL)
io_router = _import_router("io")
sessions_router = _import_router("sessions")
audit_log_router = _import_router("audit_log")
two_fa_router = _import_router("two_fa")
domain_agents_router = _import_router("domain_agents")
workspace_shares_router = _import_router("workspace_shares")
hitl_router = _import_router("hitl")
circuit_breaker_router = _import_router("circuit_breaker")
cost_attribution_router = _import_router("cost_attribution")
plugins_router = _import_router("plugins")
# ── OPTIONAL routers: info-only if missing ──────────────────────────
agent_personalities_router = _import_router(
    "agent_personalities", tier=RouterTier.OPTIONAL
)

community_router = _import_router("community", tier=RouterTier.OPTIONAL)
integrations_router = _import_router("integrations", tier=RouterTier.OPTIONAL)
marketplace_router = _import_router("marketplace", tier=RouterTier.OPTIONAL)
newsletter_router = _import_router("newsletter", tier=RouterTier.OPTIONAL)

web_search_enhanced_router = None
try:
    from app.services.web_search.web_search_routes_enhanced import (
        router as web_search_enhanced_router,
    )
except Exception as e:
    logger.warning("Skipping enhanced web search router: %s", e)

notification_router = None
try:
    from app.services.notification_service import (
        router as notification_router,
    )
except Exception as e:
    logger.warning("Skipping notification router: %s", e)

from app.api.v1.substrate import router as substrate_router  # H5.2 — replay events

api_v1_router = APIRouter(prefix="/api")

for _name, _router in [
    ("auth", auth_router),
    ("users", users_router),
    ("browser", browser_router),
    ("api_keys", api_keys_router),
    ("user_keys", user_keys_router),
    ("agent", agent_router),
    ("agent_registry", agent_registry_router),
    ("analytics", analytics_router),
    ("stats", stats_router),
    ("chat", chat_router),
    ("community", community_router),
    ("file", file_router),
    ("files", files_router_obj),
    ("flow_compat", flow_compat_router),
    ("graph", graph_router),
    ("domain_agents", domain_agents_router),
    ("llm", llm_router),
    ("llm_advanced", llm_advanced_router),
    ("memory", memory_router),
    ("mission", mission_router),
    ("mission_advanced", mission_advanced_router),
    ("mission_decomposition", mission_decomposition_router),
    ("oidc", oidc_router),
    ("delegations", delegations_router),
    ("roles", roles_router),
    ("feedback", feedback_router),
    ("orchestration", orchestration_router),
    ("subscription", subscription_router),
    ("byok", byok_router),
    ("webhooks", webhook_router),
    ("templates", templates_router),
    ("triggers", trigger_router),
    ("reliability", reliability_router),
    ("usage", usage_router),
    ("dashboard", dashboard_router),
    ("roadmap", roadmap_router),
    ("votes", votes_router),
    ("admin", admin_router),
    ("integrations", integrations_router),
    ("marketplace", marketplace_router),
    # Security routers
    ("2fa", two_fa_router),
    ("sessions", sessions_router),
    ("audit_log", audit_log_router),
    ("onboarding", onboarding_router),
    ("notification", notification_router),
    ("workspaces", workspace_router),
    ("teams", team_router),
    ("invitations", invitation_router),
    ("workspaces", presence_router),
    ("workspaces", activity_router),
    ("workspaces", messages_router),
    ("web-search", web_search_enhanced_router),
    ("linear", linear_router),
    ("newsletter", newsletter_router),
    ("tools", tools_router),
    ("search", search_router),
    ("data-export", data_export_router),
    ("feature-flags", feature_flags_router),
    ("changelog", changelog_router),
    ("observability", observability_router),
    ("rate-limits", rate_limits_router),
    ("evaluation", evaluation_router),
    ("agent-capabilities", agent_capabilities_router),
    ("swarm", swarm_router),
    ("swarm_protocol", swarm_protocol_router),
    ("rag", rag_router),
    ("sandbox", sandbox_router),
    ("sandbox-preview", sandbox_preview_router),
    ("playground", playground_router),
    ("admin-sandboxes", admin_sandboxes_router),
    ("substrate", substrate_router),
    ("io", io_router),
    ("workspace-shares", workspace_shares_router),
    ("inbox", hitl_router),
    ("circuit-breaker", circuit_breaker_router),
    ("costs", cost_attribution_router),
    ("plugins", plugins_router),
    ("agent-personalities", agent_personalities_router),
]:
    if _router:
        _prefix = None
        if _name == "swarm_protocol":
            _prefix = "/swarm"
        elif _name == "flow_compat":
            _prefix = "/flow"
        elif _name == "llm":
            _prefix = "/ai"
        elif _name == "analytics":
            _prefix = "/analytics"
        elif _name == "byok":
            _prefix = "/byok"
        elif _name == "notification":
            _prefix = "/users/me"
        if _prefix:
            api_v1_router.include_router(_router, prefix=_prefix)
        else:
            api_v1_router.include_router(_router)
