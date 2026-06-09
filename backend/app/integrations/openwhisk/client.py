#!/usr/bin/env python3
"""
OpenWhisk Client SDK

Client wrapper for Apache OpenWhisk API.
Supports self-hosted OpenWhisk with API key authentication.
Multiple region support: eu-de, eu-fr.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class OpenWhiskConfig:
    """OpenWhisk configuration"""

    api_key: str
    api_host: str
    namespace: str
    region: str = "eu-de"
    timeout: int = 30
    max_retries: int = 3

    def __post_init__(self):
        if not self.api_host.startswith(("http://", "https://")):
            raise ValueError("api_host must start with http:// or https://")


@dataclass
class ActionInvocation:
    """Action invocation result"""

    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None
    activation_id: str | None = None
    logs: list[str] | None = None


@dataclass
class ActionInfo:
    """Action metadata"""

    name: str
    version: str
    namespace: str
    kind: str
    exec: dict[str, Any]
    limits: dict[str, int]
    updated: datetime


class OpenWhiskClient:
    """
    OpenWhisk SDK client wrapper

    Handles authentication, connection, and basic operations.
    Supports self-hosted OpenWhisk with API key authentication.
    """

    def __init__(self, config: OpenWhiskConfig | None = None):
        """
        Initialize OpenWhisk client

        Args:
            config: OpenWhiskConfig object or None (load from env)
        """
        if config is None:
            config = self._load_config_from_env()

        self.config = config
        self.base_url = f"{config.api_host}/api/v1/namespaces/{config.namespace}"
        self._session: aiohttp.ClientSession | None = None

        logger.info(
            "OpenWhiskClient initialized - Region: %s, Host: %s, Namespace: %s",
            config.region,
            config.api_host,
            config.namespace,
        )

    @staticmethod
    def _load_config_from_env() -> OpenWhiskConfig:
        """Load configuration from environment variables"""
        api_key = os.getenv("OPENWHISK_API_KEY")
        api_host = os.getenv("OPENWHISK_API_HOST", "https://openwhisk.example.com")
        namespace = os.getenv("OPENWHISK_NAMESPACE", "_")
        region = os.getenv("OPENWHISK_REGION", "eu-de")
        timeout = int(os.getenv("OPENWHISK_TIMEOUT", "30"))
        max_retries = int(os.getenv("OPENWHISK_MAX_RETRIES", "3"))

        if not api_key:
            raise ValueError("OPENWHISK_API_KEY environment variable is required")

        # Validate region
        if region not in ["eu-de", "eu-fr"]:
            logger.warning("Unknown region %s, using eu-de", region)
            region = "eu-de"

        return OpenWhiskConfig(
            api_key=api_key,
            api_host=api_host,
            namespace=namespace,
            region=region,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def __aenter__(self):
        """Async context manager entry"""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._close_session()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": self.config.api_key,
                "Content-Type": "application/json",
                "User-Agent": "Workflows-Platform-OpenWhisk-Client/1.0",
            }
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)

        return self._session

    async def _close_session(self):
        """Close aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request to OpenWhisk API

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters

        Returns:
            JSON response from API

        Raises:
            aiohttp.ClientError: On network errors
            ValueError: On API errors
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        retry_count = 0
        last_error = None

        while retry_count < self.config.max_retries:
            try:
                async with session.request(
                    method=method, url=url, json=data, params=params
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 401:
                        raise ValueError(
                            "Authentication failed. Check OPENWHISK_API_KEY."
                        )
                    elif response.status == 404:
                        raise ValueError(f"Resource not found: {endpoint}")
                    else:
                        error_text = await response.text()
                        raise ValueError(f"API error {response.status}: {error_text}")

            except (TimeoutError, aiohttp.ClientError) as e:
                retry_count += 1
                last_error = e
                if retry_count < self.config.max_retries:
                    logger.warning(
                        "Request failed (attempt %s/%s), retrying... Error: %s",
                        retry_count,
                        self.config.max_retries,
                        e,
                    )
                    await asyncio.sleep(2**retry_count)  # Exponential backoff

        raise ValueError(
            f"Request failed after {self.config.max_retries} retries: {last_error}"
        )

    async def invoke_action(
        self,
        action_name: str,
        params: dict[str, Any] | None = None,
        blocking: bool = True,
        result: bool = True,
    ) -> ActionInvocation:
        """
        Invoke an OpenWhisk action

        Args:
            action_name: Name of the action (e.g., 'step_2a_generate_request')
            params: Parameters to pass to the action
            blocking: Wait for action completion (default: True)
            result: Return action result (default: True)

        Returns:
            ActionInvocation object with result

        Raises:
            ValueError: On invocation errors
        """
        logger.info("Invoking action: %s", action_name)

        start_time = datetime.now(UTC)

        try:
            payload = {"blocking": blocking, "result": result}

            if params:
                payload["params"] = params

            response = await self._request(
                method="POST", endpoint=f"/actions/{action_name}", data=payload
            )

            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            activation_id = response.get("activationId")

            # Check for errors in response
            if "response" in response and "error" in response["response"]:
                error = response["response"]["error"]
                logger.error("Action %s failed: %s", action_name, error)
                return ActionInvocation(
                    success=False,
                    error=str(error),
                    duration_ms=duration_ms,
                    activation_id=activation_id,
                    logs=response.get("logs", []),
                )

            # Extract result
            result_data = response.get("response", {}).get("result")

            logger.info(
                "Action %s completed successfully (%sms, activation: %s)",
                action_name,
                duration_ms,
                activation_id,
            )

            return ActionInvocation(
                success=True,
                result=result_data,
                duration_ms=duration_ms,
                activation_id=activation_id,
                logs=response.get("logs", []),
            )

        except Exception as e:
            logger.error("Error invoking action %s: %s", action_name, e)
            return ActionInvocation(
                success=False,
                error=str(e),
                duration_ms=int(
                    (datetime.now(UTC) - start_time).total_seconds() * 1000
                ),
            )

    async def create_action(
        self,
        action_name: str,
        code: str,
        kind: str = "python:3.11",
        main: str | None = "main",
        parameters: dict[str, Any] | None = None,
        limits: dict[str, int] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """
        Create a new OpenWhisk action

        Args:
            action_name: Name of the action
            code: Action code (Python, JavaScript, etc.)
            kind: Runtime kind (e.g., 'python:3.11')
            main: Entry point function name
            parameters: Parameter definitions
            limits: Resource limits (memory, timeout, logs)
            description: Action description

        Returns:
            API response with action info

        Raises:
            ValueError: On creation errors
        """
        logger.info("Creating action: %s", action_name)

        payload = {
            "exec": {"kind": kind, "code": code, "main": main},
            "description": description,
        }

        if parameters:
            payload["parameters"] = parameters

        if limits:
            payload["limits"] = limits

        response = await self._request(
            method="PUT",
            endpoint=f"/actions/{action_name}?overwrite=true",
            data=payload,
        )

        logger.info("Action %s created successfully", action_name)
        return response

    async def update_action(
        self, action_name: str, code: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        """
        Update an existing OpenWhisk action

        Args:
            action_name: Name of the action
            code: New code (optional)
            description: New description (optional)

        Returns:
            API response with action info

        Raises:
            ValueError: On update errors
        """
        logger.info("Updating action: %s", action_name)

        payload = {}

        if code is not None:
            payload["exec"] = {"code": code}
        if description is not None:
            payload["description"] = description

        response = await self._request(
            method="PUT", endpoint=f"/actions/{action_name}", data=payload
        )

        logger.info("Action %s updated successfully", action_name)
        return response

    async def delete_action(self, action_name: str) -> bool:
        """
        Delete an OpenWhisk action

        Args:
            action_name: Name of the action

        Returns:
            True if deleted successfully

        Raises:
            ValueError: On deletion errors
        """
        logger.info("Deleting action: %s", action_name)

        try:
            await self._request(method="DELETE", endpoint=f"/actions/{action_name}")
            logger.info("Action %s deleted successfully", action_name)
            return True
        except Exception as e:
            logger.error("Error deleting action %s: %s", action_name, e)
            return False

    async def list_actions(self) -> list[ActionInfo]:
        """
        List all actions in namespace

        Returns:
            List of ActionInfo objects

        Raises:
            ValueError: On API errors
        """
        logger.info("Listing actions")

        response = await self._request(method="GET", endpoint="/actions?limit=100")

        actions = response.get("actions", [])

        action_infos = []
        for action in actions:
            action_infos.append(
                ActionInfo(
                    name=action.get("name"),
                    version=action.get("version"),
                    namespace=action.get("namespace"),
                    kind=action.get("exec", {}).get("kind"),
                    exec=action.get("exec", {}),
                    limits=action.get("limits", {}),
                    updated=datetime.fromisoformat(
                        action.get("updated", "").replace("Z", "+00:00")
                    ),
                )
            )

        logger.info("Found %s actions", len(action_infos))
        return action_infos

    async def get_action(self, action_name: str) -> ActionInfo:
        """
        Get details of a specific action

        Args:
            action_name: Name of the action

        Returns:
            ActionInfo object

        Raises:
            ValueError: On API errors
        """
        logger.info("Getting action: %s", action_name)

        response = await self._request(method="GET", endpoint=f"/actions/{action_name}")

        action = response
        return ActionInfo(
            name=action.get("name"),
            version=action.get("version"),
            namespace=action.get("namespace"),
            kind=action.get("exec", {}).get("kind"),
            exec=action.get("exec", {}),
            limits=action.get("limits", {}),
            updated=datetime.fromisoformat(
                action.get("updated", "").replace("Z", "+00:00")
            ),
        )

    async def create_trigger(
        self, trigger_name: str, feed: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Create a trigger for events

        Args:
            trigger_name: Name of the trigger
            feed: Feed to create trigger from
            parameters: Trigger parameters

        Returns:
            API response with trigger info

        Raises:
            ValueError: On creation errors
        """
        logger.info("Creating trigger: %s", trigger_name)

        payload: dict[str, Any] = {"name": trigger_name, "feed": feed}

        if parameters:
            payload["parameters"] = parameters

        response = await self._request(
            method="PUT", endpoint=f"/triggers/{trigger_name}", data=payload
        )

        logger.info("Trigger %s created successfully", trigger_name)
        return response

    async def health_check(self) -> dict[str, Any]:
        """
        Check OpenWhisk connectivity and health

        Returns:
            Health check status
        """
        logger.info("Performing health check")

        try:
            actions = await self.list_actions()
            return {
                "status": "healthy",
                "region": self.config.region,
                "namespace": self.config.namespace,
                "action_count": len(actions),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return {
                "status": "unhealthy",
                "region": self.config.region,
                "namespace": self.config.namespace,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def batch_invoke(
        self, invocations: list[dict[str, Any]], max_concurrent: int = 10
    ) -> list[ActionInvocation]:
        """
        Invoke multiple actions concurrently

        Args:
            invocations: List of {action_name, params} dicts
            max_concurrent: Maximum concurrent invocations

        Returns:
            List of ActionInvocation results
        """
        logger.info("Batch invoking %s actions", len(invocations))

        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = []

        async def invoke_with_limit(invocation):
            async with semaphore:
                return await self.invoke_action(
                    action_name=invocation["action_name"],
                    params=invocation.get("params"),
                )

        for invocation in invocations:
            task = asyncio.create_task(invoke_with_limit(invocation))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch invocation %s failed: %s", i, result)
                processed_results.append(
                    ActionInvocation(success=False, error=str(result))
                )
            else:
                processed_results.append(result)  # type: ignore[arg-type]

        logger.info(
            "Batch invocation completed: %s success, %s failures",
            len([r for r in processed_results if r.success]),
            len([r for r in processed_results if not r.success]),
        )

        return processed_results


def get_openwhisk_client() -> OpenWhiskClient | None:
    """
    Factory function to get configured OpenWhisk client

    Returns:
        OpenWhiskClient instance or None if not configured

    Example:
        >>> client = get_openwhisk_client()
        >>> if client:
        >>>     result = await client.invoke_action('step_2a_generate_request', {...})
    """
    try:
        client = OpenWhiskClient()
        return client
    except ValueError as e:
        logger.warning("OpenWhisk not configured: %s", e)
        return None
