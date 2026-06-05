"""
Flowmanner Integration Package

Contains external service integrations (OAuth providers, OpenWhisk, etc.).
"""
try:
    from .openwhisk.action_manager import (
        ActionMetadata,
        ActionPackage,
        OpenWhiskActionManager,
        create_action_manager,
    )
    from .openwhisk.api_gateway import (
        OpenWhiskAPIGateway,
        RequestLimiter,
        Route,
        create_gateway,
    )
    from .openwhisk.auth import (
        OpenWhiskAuthManager,
        get_auth_manager,
    )
    from .openwhisk.client import (
        ActionInfo,
        ActionInvocation,
        OpenWhiskClient,
        OpenWhiskConfig,
        get_openwhisk_client,
    )
    from .openwhisk.integration_controller import (
        ActionDeployment,
        DeploymentStatus,
        OpenWhiskIntegrationController,
        create_integration_controller,
    )
except ImportError as e:
    import logging

    logging.getLogger(__name__).warning(f"OpenWhisk imports skipped: {e}")

from .monitoring.health_check import (
    HealthCheck,
    create_health_check,
)

__all__ = [
    "ActionDeployment",
    "ActionInfo",
    "ActionInvocation",
    "ActionMetadata",
    "ActionPackage",
    "DeploymentStatus",
    "HealthCheck",
    "OpenWhiskAPIGateway",
    "OpenWhiskActionManager",
    "OpenWhiskAuthManager",
    "OpenWhiskClient",
    "OpenWhiskConfig",
    "OpenWhiskIntegrationController",
    "RequestLimiter",
    "Route",
    "create_action_manager",
    "create_gateway",
    "create_health_check",
    "create_integration_controller",
    "get_auth_manager",
    "get_openwhisk_client",
]

__version__ = "1.0.0"