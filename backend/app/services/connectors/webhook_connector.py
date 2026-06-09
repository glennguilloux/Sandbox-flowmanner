"""
HTTP Webhook Connector

Provides generic HTTP webhook integration for:
- Sending webhooks to external URLs
- Configurable HTTP methods
- Custom headers and authentication
- Retry and timeout handling
- Signature generation for webhook verification
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

from .base import (
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class WebhookConnector(BaseConnector):
    """
    Generic HTTP webhook connector for external integrations.

    Supports:
    - POST/PUT/GET/DELETE webhooks
    - Custom headers
    - HMAC signature generation
    - Retry with exponential backoff
    - Response validation
    """

    CONNECTOR_TYPE = "webhook"

    # Default webhook rate limits
    WEBHOOK_RATE_LIMIT = RateLimitConfig(
        requests_per_second=20.0,
        requests_per_minute=1000,
        requests_per_hour=50000,
        burst_size=50,
    )

    ACTIONS = [
        "send_webhook",
        "send_json_webhook",
        "send_form_webhook",
        "get_webhook",
        "put_webhook",
        "delete_webhook",
        "send_batch_webhooks",
        "verify_signature",
        "generate_signature",
    ]

    def __init__(self, config: ConnectorConfig):
        config.rate_limit = config.rate_limit or self.WEBHOOK_RATE_LIMIT

        super().__init__(config)

        # Webhook-specific configuration
        self._default_headers = config.headers or {}
        self._signature_secret = config.auth_config.get("signature_secret")
        self._signature_algorithm = config.auth_config.get(
            "signature_algorithm", "sha256"
        )
        self._signature_header = config.auth_config.get(
            "signature_header", "X-Webhook-Signature"
        )
        self._timeout = config.timeout or 30.0

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Webhook doesn't require credential validation"""
        return True

    async def execute_action(
        self, action: str, params: dict[str, Any]
    ) -> ConnectorResponse:
        """Execute a webhook action"""

        action_handlers = {
            "send_webhook": self._send_webhook,
            "send_json_webhook": self._send_json_webhook,
            "send_form_webhook": self._send_form_webhook,
            "get_webhook": self._get_webhook,
            "put_webhook": self._put_webhook,
            "delete_webhook": self._delete_webhook,
            "send_batch_webhooks": self._send_batch_webhooks,
            "verify_signature": self._verify_signature,
            "generate_signature": self._generate_signature,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(
                success=False, error=f"Unknown action: {action}", status_code=400
            )

        return await handler(params)

    def _generate_hmac_signature(
        self, payload: str, secret: str, algorithm: str = "sha256"
    ) -> str:
        """Generate HMAC signature for payload"""
        hash_func = getattr(hashlib, algorithm, hashlib.sha256)
        signature = hmac.new(secret.encode(), payload.encode(), hash_func).hexdigest()
        return f"{algorithm}={signature}"

    def _build_webhook_headers(
        self,
        payload: str,
        custom_headers: dict[str, str] | None = None,
        include_signature: bool = True,
    ) -> dict[str, str]:
        """Build headers for webhook request"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "WorkflowsPlatform-Webhook/1.0",
            "X-Webhook-ID": str(uuid.uuid4()),
            "X-Webhook-Timestamp": str(int(time.time())),
        }

        # Add default headers
        headers.update(self._default_headers)

        # Add custom headers
        if custom_headers:
            headers.update(custom_headers)

        # Add signature if secret is configured
        if include_signature and self._signature_secret and payload:
            signature = self._generate_hmac_signature(
                payload, self._signature_secret, self._signature_algorithm
            )
            headers[self._signature_header] = signature

        return headers

    async def _send_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a generic webhook request"""
        url = params.get("url")
        method = params.get("method", "POST").upper()
        payload = params.get("payload")
        headers = params.get("headers")
        timeout = params.get("timeout", self._timeout)

        if not url:
            return ConnectorResponse(
                success=False, error="Missing required param: url", status_code=400
            )

        # Prepare payload
        if isinstance(payload, dict):
            payload_str = json.dumps(payload)
        elif payload is None:
            payload_str = ""
        else:
            payload_str = str(payload)

        # Build headers
        request_headers = self._build_webhook_headers(payload_str, headers)

        try:
            # Execute request
            return await self._execute_with_retry(
                method,
                url,
                json_data=payload if isinstance(payload, dict) else None,
                data=payload_str if not isinstance(payload, dict) else None,
                headers=request_headers,
            )
        except Exception as e:
            logger.error("Webhook failed: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=0)

    async def _send_json_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a JSON webhook"""
        url = params.get("url")
        data = params.get("data", {})
        headers = params.get("headers")
        method = params.get("method", "POST").upper()

        if not url:
            return ConnectorResponse(
                success=False, error="Missing required param: url", status_code=400
            )

        payload_str = json.dumps(data)
        request_headers = self._build_webhook_headers(payload_str, headers)
        request_headers["Content-Type"] = "application/json"

        return await self._execute_with_retry(
            method, url, json_data=data, headers=request_headers
        )

    async def _send_form_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a form-urlencoded webhook"""
        url = params.get("url")
        data = params.get("data", {})
        headers = params.get("headers")
        method = params.get("method", "POST").upper()

        if not url:
            return ConnectorResponse(
                success=False, error="Missing required param: url", status_code=400
            )

        # Build form data
        from urllib.parse import urlencode

        form_data = urlencode(data)

        request_headers = self._build_webhook_headers(form_data, headers)
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        return await self._execute_with_retry(
            method, url, data=form_data, headers=request_headers
        )

    async def _get_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a GET webhook request"""
        url = params.get("url")
        query_params = params.get("params")
        headers = params.get("headers")

        if not url:
            return ConnectorResponse(
                success=False, error="Missing required param: url", status_code=400
            )

        request_headers = self._build_webhook_headers(
            "", headers, include_signature=False
        )

        return await self._execute_with_retry(
            "GET", url, params=query_params, headers=request_headers
        )

    async def _put_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a PUT webhook request"""
        url = params.get("url")
        data = params.get("data", {})
        headers = params.get("headers")

        if not url:
            return ConnectorResponse(
                success=False, error="Missing required param: url", status_code=400
            )

        payload_str = json.dumps(data)
        request_headers = self._build_webhook_headers(payload_str, headers)

        return await self._execute_with_retry(
            "PUT", url, json_data=data, headers=request_headers
        )

    async def _delete_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a DELETE webhook request"""
        url = params.get("url")
        headers = params.get("headers")

        if not url:
            return ConnectorResponse(
                success=False, error="Missing required param: url", status_code=400
            )

        request_headers = self._build_webhook_headers(
            "", headers, include_signature=False
        )

        return await self._execute_with_retry("DELETE", url, headers=request_headers)

    async def _send_batch_webhooks(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send multiple webhooks in parallel"""
        webhooks = params.get("webhooks", [])
        max_concurrent = params.get("max_concurrent", 10)

        if not webhooks:
            return ConnectorResponse(
                success=False, error="Missing required param: webhooks", status_code=400
            )

        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def _send_single(webhook: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                response = await self._send_json_webhook(webhook)
                return {
                    "url": webhook.get("url"),
                    "success": response.success,
                    "status_code": response.status_code,
                    "error": response.error,
                    "data": response.data,
                }

        tasks = [_send_single(w) for w in webhooks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    {
                        "url": webhooks[i].get("url"),
                        "success": False,
                        "error": str(result),
                    }
                )
            else:
                processed_results.append(result)

        success_count = sum(1 for r in processed_results if r.get("success"))

        return ConnectorResponse(
            success=success_count == len(processed_results),
            data={
                "total": len(processed_results),
                "successful": success_count,
                "failed": len(processed_results) - success_count,
                "results": processed_results,
            },
            status_code=200,
        )

    async def _verify_signature(self, params: dict[str, Any]) -> ConnectorResponse:
        """Verify a webhook signature"""
        payload = params.get("payload")
        signature = params.get("signature")
        secret = params.get("secret", self._signature_secret)
        algorithm = params.get("algorithm", self._signature_algorithm)

        if not all([payload, signature, secret]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: payload, signature, and secret",
                status_code=400,
            )

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        # Generate expected signature
        expected = self._generate_hmac_signature(payload, secret, algorithm)

        # Compare signatures (constant-time comparison)
        is_valid = hmac.compare_digest(expected, signature)

        return ConnectorResponse(
            success=True,
            data={"valid": is_valid, "expected_format": f"{algorithm}=<hex_digest>"},
            status_code=200,
        )

    async def _generate_signature(self, params: dict[str, Any]) -> ConnectorResponse:
        """Generate a webhook signature"""
        payload = params.get("payload")
        secret = params.get("secret", self._signature_secret)
        algorithm = params.get("algorithm", self._signature_algorithm)

        if not all([payload, secret]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: payload and secret",
                status_code=400,
            )

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        signature = self._generate_hmac_signature(payload, secret, algorithm)

        return ConnectorResponse(
            success=True,
            data={
                "signature": signature,
                "algorithm": algorithm,
                "header": self._signature_header,
            },
            status_code=200,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics"""
        stats = super().get_stats()
        stats.update(
            {
                "signature_enabled": bool(self._signature_secret),
                "signature_algorithm": self._signature_algorithm,
                "signature_header": self._signature_header,
            }
        )
        return stats
