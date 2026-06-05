"""HTTP Outbound Integration Executor — executes HTTP calls during mission tasks.

Provides:
- HttpIntegrationExecutor class for executing HTTP requests
- Integration with TaskExecutor via http_integration task type
- Request/response logging to HttpIntegrationLog
- Timeout, retry, and error handling
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import httpx

from app.models.integration_models import HttpIntegrationConfig, HttpIntegrationLog
from app.utils.encryption import decrypt_api_key

logger = logging.getLogger(__name__)

MAX_RESPONSE_BODY_BYTES = 1_048_576  # 1MB


class HttpIntegrationExecutor:
    """Executes HTTP requests using user-configured integration configs.

    Uses httpx for async HTTP calls with configurable timeout and retry.
    All requests/responses are logged to HttpIntegrationLog for auditability.
    """

    def _get_auth_headers(self, config: HttpIntegrationConfig) -> dict[str, str]:
        """Build auth headers from the integration config."""
        if not config.auth_type or not config.auth_config_encrypted:
            return {}

        try:
            auth_config = json.loads(decrypt_api_key(config.auth_config_encrypted))
        except Exception as e:
            logger.warning("Failed to decrypt auth config for integration %s: %s", config.id, e)
            return {}

        if config.auth_type == "bearer":
            token = auth_config.get("token", "")
            return {"Authorization": f"Bearer {token}"}
        elif config.auth_type == "basic":
            username = auth_config.get("username", "")
            password = auth_config.get("password", "")
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        elif config.auth_type == "api_key":
            key_name = auth_config.get("key_name", "X-API-Key")
            key_value = auth_config.get("key_value", "")
            return {key_name: key_value}

        return {}

    async def execute(
        self,
        db,
        config: HttpIntegrationConfig,
        method: str,
        path: str = "",
        *,
        headers: dict[str, str] | None = None,
        body: Any = None,
        query_params: dict[str, str] | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request using the integration config.

        Args:
            db: SQLAlchemy async session for logging.
            config: HttpIntegrationConfig instance.
            method: HTTP method (GET, POST, PUT, DELETE, PATCH).
            path: URL path appended to config.base_url.
            headers: Additional request headers.
            body: Request body (dict for JSON, str for raw).
            query_params: URL query parameters.
            mission_id: Optional mission ID for attribution.
            task_id: Optional task ID for attribution.

        Returns:
            Dict with success, status_code, response_body, duration_ms, error.
        """
        url = config.base_url.rstrip("/") + "/" + path.lstrip("/")
        method = method.upper()

        # Build headers
        request_headers = {**(config.default_headers or {})}
        auth_headers = self._get_auth_headers(config)
        request_headers.update(auth_headers)
        if headers:
            request_headers.update(headers)

        # Redact sensitive headers for logging
        safe_headers = {
            k: ("[REDACTED]" if k.lower() in ("authorization",) or "key" in k.lower() else v)
            for k, v in request_headers.items()
        }

        log_entry = HttpIntegrationLog(
            integration_id=str(config.id),
            mission_id=mission_id,
            task_id=task_id,
            request_method=method,
            request_url=url,
            request_headers=safe_headers,
            status="pending",
        )

        if body is not None:
            body_str = json.dumps(body) if isinstance(body, dict) else str(body)
            log_entry.request_body_preview = body_str[:1024]  # truncate to 1KB

        db.add(log_entry)

        # Execute with retry
        max_retries = config.max_retries
        last_error = None

        for attempt in range(max_retries + 1):
            start_time = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                    kwargs: dict = {"headers": request_headers}
                    if query_params:
                        kwargs["params"] = query_params
                    if body is not None:
                        if isinstance(body, dict):
                            kwargs["json"] = body
                        else:
                            kwargs["content"] = body

                    response = await client.request(method, url, **kwargs)
                    duration_ms = int((time.monotonic() - start_time) * 1000)

                    # Read and truncate response body
                    response_body = response.text
                    if len(response_body) > MAX_RESPONSE_BODY_BYTES:
                        response_body = response_body[:MAX_RESPONSE_BODY_BYTES]

                    # Update log
                    log_entry.response_status = response.status_code
                    log_entry.response_headers = dict(response.headers)
                    log_entry.response_body_preview = response_body[:1024]
                    log_entry.duration_ms = duration_ms
                    log_entry.retry_count = attempt

                    if response.is_success:
                        log_entry.status = "success"
                        await db.commit()
                        return {
                            "success": True,
                            "status_code": response.status_code,
                            "response_body": response_body,
                            "response_headers": dict(response.headers),
                            "duration_ms": duration_ms,
                        }
                    else:
                        log_entry.status = "failed"
                        log_entry.error_message = f"HTTP {response.status_code}: {response_body[:200]}"
                        await db.commit()
                        return {
                            "success": False,
                            "status_code": response.status_code,
                            "response_body": response_body,
                            "error": f"HTTP {response.status_code}",
                            "duration_ms": duration_ms,
                        }

            except httpx.TimeoutException as e:
                last_error = f"Timeout after {config.timeout_seconds}s"
                logger.warning(
                    "HTTP integration timeout (attempt %d/%d): %s %s",
                    attempt + 1, max_retries + 1, method, url,
                )
                if attempt >= max_retries:
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    log_entry.status = "timeout"
                    log_entry.error_message = last_error
                    log_entry.duration_ms = duration_ms
                    log_entry.retry_count = attempt + 1
                    await db.commit()
                    return {
                        "success": False,
                        "error": last_error,
                        "duration_ms": duration_ms,
                    }

            except Exception as e:
                last_error = str(e)
                logger.error(
                    "HTTP integration error (attempt %d/%d): %s %s — %s",
                    attempt + 1, max_retries + 1, method, url, e,
                )
                if attempt >= max_retries:
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    log_entry.status = "failed"
                    log_entry.error_message = last_error
                    log_entry.duration_ms = duration_ms
                    log_entry.retry_count = attempt + 1
                    await db.commit()
                    return {
                        "success": False,
                        "error": last_error,
                        "duration_ms": duration_ms,
                    }

        # Should never reach here, but safety net
        return {"success": False, "error": last_error or "Unknown error"}


# Module-level singleton
_executor_instance: HttpIntegrationExecutor | None = None


def get_http_integration_executor() -> HttpIntegrationExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = HttpIntegrationExecutor()
    return _executor_instance
