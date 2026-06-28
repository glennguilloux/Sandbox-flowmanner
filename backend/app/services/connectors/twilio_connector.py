"""
Twilio Connector

Provides integration with Twilio REST API for:
- Account info (get_account)
- Messages (list, send)
- Calls (list, get, make)
- Phone numbers (list)
- Recordings (get, list)
- Usage (get)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

if TYPE_CHECKING:
    from app.services.twilio.twilio_client import TwilioClient

logger = logging.getLogger(__name__)


class TwilioConnector(BaseConnector):
    """Twilio SMS/Voice communication connector."""

    CONNECTOR_TYPE = "twilio"

    TWILIO_RATE_LIMIT = RateLimitConfig(
        requests_per_second=1.0,
        requests_per_minute=60,
        requests_per_hour=3000,
        burst_size=5,
    )

    ACTIONS = [
        "get_account",
        "list_messages",
        "send_message",
        "list_calls",
        "get_call",
        "make_call",
        "list_phone_numbers",
        "get_recording",
        "list_recordings",
        "get_usage",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.twilio.com/2010-04-01"
        config.auth_type = config.auth_type or AuthType.API_KEY
        config.rate_limit = config.rate_limit or self.TWILIO_RATE_LIMIT
        super().__init__(config)
        self._client: TwilioClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.config import settings
            from app.services.twilio.twilio_client import TwilioClient

            account_sid = settings.TWILIO_ACCOUNT_SID
            api_key_sid = self.config.auth_config.get("api_key_sid", "") or settings.TWILIO_API_KEY_SID
            api_key_secret = self.config.auth_config.get("api_key_secret", "") or settings.TWILIO_API_KEY_SECRET
            if not account_sid or not api_key_sid or not api_key_secret:
                logger.debug("Twilio credentials not configured — skipping validation")
                return True
            self._client = TwilioClient(
                account_sid=account_sid,
                api_key_sid=api_key_sid,
                api_key_secret=api_key_secret,
            )
            account = await self._client.get_account()
            return bool(account.get("sid"))
        except Exception as e:
            logger.warning("Twilio credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_account": self._get_account,
            "list_messages": self._list_messages,
            "send_message": self._send_message,
            "list_calls": self._list_calls,
            "get_call": self._get_call,
            "make_call": self._make_call,
            "list_phone_numbers": self._list_phone_numbers,
            "get_recording": self._get_recording,
            "list_recordings": self._list_recordings,
            "get_usage": self._get_usage,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Twilio action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_account(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        result = await self._client.get_account()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_messages(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        result = await self._client.list_messages(
            to=params.get("to"),
            from_=params.get("from"),
            page_size=params.get("page_size", 50),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _send_message(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        to = params.get("to")
        from_ = params.get("from")
        body = params.get("body")
        if not to or not from_ or not body:
            return ConnectorResponse(success=False, error="Missing: to, from, and body", status_code=400)
        result = await self._client.send_message(
            to=to,
            from_=from_,
            body=body,
            media_url=params.get("media_url"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_calls(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        result = await self._client.list_calls(
            to=params.get("to"),
            from_=params.get("from"),
            page_size=params.get("page_size", 50),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_call(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        call_sid = params.get("call_sid")
        if not call_sid:
            return ConnectorResponse(success=False, error="Missing: call_sid", status_code=400)
        result = await self._client.get_call(call_sid)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _make_call(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        to = params.get("to")
        from_ = params.get("from")
        if not to or not from_:
            return ConnectorResponse(success=False, error="Missing: to and from", status_code=400)
        result = await self._client.make_call(
            to=to,
            from_=from_,
            url=params.get("url"),
            twiml=params.get("twiml"),
        )
        return ConnectorResponse(success=True, data=result, status_code=201)

    async def _list_phone_numbers(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        result = await self._client.list_phone_numbers()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_recording(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        recording_sid = params.get("recording_sid")
        if not recording_sid:
            return ConnectorResponse(success=False, error="Missing: recording_sid", status_code=400)
        result = await self._client.get_recording(recording_sid)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _list_recordings(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        result = await self._client.list_recordings(call_sid=params.get("call_sid"))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_usage(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TwilioClient not initialized — call connect() first"
        result = await self._client.get_usage()
        return ConnectorResponse(success=True, data=result, status_code=200)
