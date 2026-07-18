#!/usr/bin/env python3
"""
OpenWhisk Integration Controller

Manages deployment, updates, and monitoring of OpenWhisk actions.
Handles action lifecycle, versioning, and rollback.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .auth import OpenWhiskAuthManager
from .client import OpenWhiskClient

logger = logging.getLogger(__name__)


@dataclass
class ActionDeployment:
    """Action deployment record"""

    action_name: str
    version: str
    deployed_at: datetime
    status: str = "deployed"  # deployed, updating, failed, rollback
    code_hash: str | None = None
    activation_count: int = 0
    error_count: int = 0
    average_duration_ms: float = 0.0


@dataclass
class DeploymentStatus:
    """Overall deployment status"""

    total_actions: int
    deployed_actions: int
    failed_actions: int
    pending_actions: int
    start_time: datetime
    end_time: datetime | None = None
    errors: list[str] = field(default_factory=list)


class OpenWhiskIntegrationController:
    """
    Controller for managing OpenWhisk integration lifecycle

    Responsibilities:
    - Deploy actions to OpenWhisk
    - Update existing actions
    - Monitor action health
    - Manage versioning
    - Handle rollback
    - Collect deployment metrics
    """

    def __init__(self, client: OpenWhiskClient, auth_manager: OpenWhiskAuthManager):
        """
        Initialize integration controller

        Args:
            client: OpenWhisk client instance
            auth_manager: Auth manager instance
        """
        self.client = client
        self.auth_manager = auth_manager
        self.deployments: dict[str, ActionDeployment] = {}
        self.current_deployment: DeploymentStatus | None = None

        logger.info("OpenWhiskIntegrationController initialized")

    async def deploy_all_actions(
        self,
        actions_dir: str = "/run/media/glenn/web1/workflows/apps/backend/app/workers/actions",
    ) -> DeploymentStatus:
        """
        Deploy all worker actions to OpenWhisk

        Args:
            actions_dir: Directory containing action files

        Returns:
            DeploymentStatus with results
        """
        logger.info("Starting deployment of actions from %s", actions_dir)

        status = DeploymentStatus(
            total_actions=0,
            deployed_actions=0,
            failed_actions=0,
            pending_actions=0,
            start_time=datetime.now(UTC),
        )

        # List all action files
        action_files = await self._discover_actions(actions_dir)
        status.total_actions = len(action_files)

        # Deploy each action
        for action_file in action_files:
            try:
                action_name = action_file["name"]
                code = action_file["code"]
                main_fn = action_file.get("main", "main")
                kind = action_file.get("kind", "python:3.11")

                # Read description if available
                description = action_file.get("description", f"Auto-deployed: {action_name}")

                # Deploy action
                await self.client.create_action(
                    action_name=action_name,
                    code=code,
                    main=main_fn,
                    kind=kind,
                    description=description,
                )

                # Record deployment
                self.deployments[action_name] = ActionDeployment(
                    action_name=action_name,
                    version="1.0.0",
                    deployed_at=datetime.now(UTC),
                    code_hash=self._hash_code(code),
                    status="deployed",
                )

                status.deployed_actions += 1
                logger.info("Action %s deployed successfully", action_name)

            except Exception as e:
                status.failed_actions += 1
                status.errors.append(f"{action_file.get('name', 'unknown')}: {e!s}")
                logger.error("Failed to deploy action %s: %s", action_file.get("name"), e)

        status.end_time = datetime.now(UTC)
        duration = (status.end_time - status.start_time).total_seconds()
        logger.info(
            "Deployment completed: %s/%s actions in %ss",
            status.deployed_actions,
            status.total_actions,
            duration,
        )

        self.current_deployment = status
        return status

    async def update_action(self, action_name: str, code: str | None = None, description: str | None = None) -> bool:
        """
        Update an existing action

        Args:
            action_name: Name of action to update
            code: New code (optional)
            description: New description (optional)

        Returns:
            True if update successful
        """
        logger.info("Updating action: %s", action_name)

        if action_name not in self.deployments:
            logger.warning("Action %s not deployed, cannot update", action_name)
            return False

        try:
            deployment = self.deployments[action_name]

            # Mark as updating
            deployment.status = "updating"

            # Update in OpenWhisk
            await self.client.update_action(action_name=action_name, code=code, description=description)

            # Update deployment record
            if code is not None:
                deployment.code_hash = self._hash_code(code)
                deployment.version = self._increment_version(deployment.version)

            deployment.deployed_at = datetime.now(UTC)
            deployment.status = "deployed"

            logger.info("Action %s updated to %s", action_name, deployment.version)
            return True

        except Exception as e:
            deployment.status = "failed"
            deployment.error_count += 1
            logger.error("Failed to update action %s: %s", action_name, e)
            return False

    async def rollback_action(self, action_name: str, target_version: str | None = None) -> bool:
        """
        Rollback action to previous version

        Args:
            action_name: Name of action to rollback
            target_version: Version to rollback to (optional, use latest if None)

        Returns:
            True if rollback successful
        """
        logger.warning("Rolling back action: %s to %s", action_name, target_version or "previous")

        if action_name not in self.deployments:
            logger.error("Cannot rollback: action %s not deployed", action_name)
            return False

        try:
            deployment = self.deployments[action_name]
            deployment.status = "rollback"

            # For this implementation, we'll need to store code history
            # For now, we'll mark as failed and require manual redeployment
            deployment.status = "failed_rollback"
            deployment.error_count += 1

            logger.warning("Rollback requires manual intervention for %s", action_name)
            return False

        except Exception as e:
            logger.error("Rollback failed for %s: %s", action_name, e)
            return False

    async def get_action_status(self, action_name: str) -> dict[str, Any] | None:
        """
        Get status of a specific action

        Args:
            action_name: Name of action

        Returns:
            Status dictionary or None if not found
        """
        if action_name not in self.deployments:
            return None

        deployment = self.deployments[action_name]

        # Get live status from OpenWhisk
        try:
            action_info = await self.client.get_action(action_name)

            return {
                "action_name": action_name,
                "deployment_version": deployment.version,
                "live_version": action_info.version,
                "status": deployment.status,
                "deployed_at": deployment.deployed_at.isoformat(),
                "code_hash": deployment.code_hash,
                "activation_count": deployment.activation_count,
                "error_count": deployment.error_count,
                "average_duration_ms": deployment.average_duration_ms,
                "live_namespace": action_info.namespace,
                "live_updated": action_info.updated.isoformat(),
            }
        except Exception as e:
            logger.error("Error getting status for %s: %s", action_name, e)
            return {"action_name": action_name, "error": str(e), "status": "unknown"}

    async def health_check_all_actions(self) -> dict[str, Any]:
        """
        Health check for all deployed actions

        Returns:
            Health check summary
        """
        logger.info("Performing health check on all actions")

        healthy_count = 0
        unhealthy_count = 0
        action_statuses = []

        for action_name in self.deployments:
            try:
                status = await self.get_action_status(action_name)

                if status and status.get("status") == "deployed":
                    healthy_count += 1
                    action_statuses.append({"name": action_name, "status": "healthy"})
                else:
                    unhealthy_count += 1
                    action_statuses.append({"name": action_name, "status": "unhealthy"})

            except Exception as e:
                unhealthy_count += 1
                action_statuses.append({"name": action_name, "status": "error", "error": str(e)})

        total = len(self.deployments)

        return {
            "total_actions": total,
            "healthy_actions": healthy_count,
            "unhealthy_actions": unhealthy_count,
            "health_percentage": (healthy_count / total * 100) if total > 0 else 0,
            "action_statuses": action_statuses,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def remove_action(self, action_name: str) -> bool:
        """
        Remove an action from OpenWhisk and local tracking

        Args:
            action_name: Name of action to remove

        Returns:
            True if removal successful
        """
        logger.warning("Removing action: %s", action_name)

        try:
            # Delete from OpenWhisk
            success = await self.client.delete_action(action_name)

            if success:
                # Remove from local tracking
                self.deployments.pop(action_name, None)
                logger.info("Action %s removed successfully", action_name)

            return success

        except Exception as e:
            logger.error("Error removing action %s: %s", action_name, e)
            return False

    async def _discover_actions(self, actions_dir: str) -> list[dict[str, Any]]:
        """
        Discover all action files in directory

        Args:
            actions_dir: Directory to scan

        Returns:
            List of action file info
        """
        import os

        action_files: list[dict[str, Any]] = []

        if not os.path.exists(actions_dir):
            logger.warning("Actions directory not found: %s", actions_dir)
            return action_files

        for filename in os.listdir(actions_dir):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = os.path.join(actions_dir, filename)
            action_name = filename.replace(".py", "")

            try:
                with open(filepath, "r") as f:
                    code = f.read()

                action_files.append(
                    {
                        "name": action_name,
                        "code": code,
                        "main": "main",  # OpenWhisk default
                        "kind": "python:3.11",
                        "description": f"Worker action: {action_name}",
                    }
                )

            except Exception as e:
                logger.error("Error reading action file %s: %s", filename, e)

        logger.info("Discovered %s action files", len(action_files))
        return action_files

    def _hash_code(self, code: str) -> str:
        """Generate hash of code for change detection"""
        import hashlib

        return hashlib.sha256(code.encode()).hexdigest()[:16]

    def _increment_version(self, version: str) -> str:
        """Increment version number (simplified)"""
        try:
            parts = version.split(".")
            patch = int(parts[-1]) + 1
            return ".".join([*parts[:-1], str(patch)])
        except Exception:
            logger.debug("Failed to parse version for increment: %s", version)
            return f"{version}.1"

    def get_deployment_summary(self) -> dict[str, Any]:
        """
        Get summary of current deployment

        Returns:
            Deployment summary dictionary
        """
        total_deployments = len(self.deployments)
        healthy = sum(1 for d in self.deployments.values() if d.status == "deployed")
        failed = sum(1 for d in self.deployments.values() if d.status.startswith("failed"))

        return {
            "total_deployments": total_deployments,
            "healthy_actions": healthy,
            "failed_actions": failed,
            "deployment_health": ((healthy / total_deployments * 100) if total_deployments > 0 else 0),
            "deployment_timestamp": (
                self.current_deployment.start_time.isoformat() if self.current_deployment else None
            ),
            "errors": self.current_deployment.errors if self.current_deployment else [],
        }


def create_integration_controller(
    client: OpenWhiskClient | None = None,
    auth_manager: OpenWhiskAuthManager | None = None,
) -> OpenWhiskIntegrationController | None:
    """
    Factory function to create integration controller

    Args:
        client: OpenWhisk client or None (auto-create)
        auth_manager: Auth manager or None (auto-create)

    Returns:
        OpenWhiskIntegrationController instance or None if not configured

    Example:
        >>> controller = create_integration_controller()
        >>> if controller:
        >>>     status = await controller.deploy_all_actions()
    """
    try:
        if client is None:
            from .client import get_openwhisk_client

            client = get_openwhisk_client()

        if auth_manager is None:
            from .auth import get_auth_manager

            auth_manager = get_auth_manager()

        if not client or not auth_manager:
            logger.warning("Cannot create controller: missing client or auth")
            return None

        controller = OpenWhiskIntegrationController(client=client, auth_manager=auth_manager)

        logger.info("Integration controller created successfully")
        return controller

    except Exception as e:
        logger.error("Error creating integration controller: %s", e)
        return None
