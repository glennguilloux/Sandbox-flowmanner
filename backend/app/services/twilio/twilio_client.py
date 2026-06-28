"""
Twilio REST API Client

Async client for Twilio's REST API.
Used by the user-facing Twilio integration — agents interact with the USER's
Twilio account for SMS messages, calls, phone numbers, recordings, and usage.

Auth: API Key (HTTP Basic Auth: username=API_KEY_SID, password=API_KEY_SECRET).

API Base: https://api.twilio.com/2010-04-01
Quirk: REST API uses date-versioned URLs. Account SID is part of the path.
"""

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioAPIError(Exception):
    """Twilio API error."""

    pass


class TwilioClient:
    """Async REST client for Twilio REST API."""

    def __init__(
        self,
        account_sid: str,
        api_key_sid: str,
        api_key_secret: str,
        base_url: str = TWILIO_API_BASE,
    ):
        self.base_url = base_url.rstrip("/")
        self.account_sid = account_sid
        self.api_key_sid = api_key_sid
        self.api_key_secret = api_key_secret

        # HTTP Basic Auth: username=API_KEY_SID, password=API_KEY_SECRET
        credentials = base64.b64encode(f"{api_key_sid}:{api_key_secret}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request."""
        url = f"{self.base_url}{path}"
        headers = dict(self._headers)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=headers, params=params, data=data)
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after", "?")
                raise TwilioAPIError(f"Twilio rate limited: {method} {path} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise TwilioAPIError(f"Twilio API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()

    # ── Account ─────────────────────────────────────────────────

    async def get_account(self) -> dict[str, Any]:
        """GET /Accounts/{AccountSid} — Get account info (credential validation)."""
        return await self._request("GET", f"/Accounts/{self.account_sid}.json")  # type: ignore[return-value]

    # ── Messages ────────────────────────────────────────────────

    async def list_messages(
        self,
        to: str | None = None,
        from_: str | None = None,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/Messages — List SMS/MMS messages."""
        params: dict[str, Any] = {"PageSize": page_size}
        if to:
            params["To"] = to
        if from_:
            params["From"] = from_
        return await self._request("GET", f"/Accounts/{self.account_sid}/Messages.json", params=params)  # type: ignore[return-value]

    async def send_message(
        self,
        to: str,
        from_: str,
        body: str,
        media_url: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /Accounts/{AccountSid}/Messages — Send an SMS/MMS."""
        form_data: dict[str, Any] = {"To": to, "From": from_, "Body": body}
        if media_url:
            for url in media_url:
                form_data["MediaUrl"] = url
        return await self._request(
            "POST",
            f"/Accounts/{self.account_sid}/Messages.json",
            data=form_data,
        )  # type: ignore[return-value]

    # ── Calls ───────────────────────────────────────────────────

    async def list_calls(
        self,
        to: str | None = None,
        from_: str | None = None,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/Calls — List calls."""
        params: dict[str, Any] = {"PageSize": page_size}
        if to:
            params["To"] = to
        if from_:
            params["From"] = from_
        return await self._request("GET", f"/Accounts/{self.account_sid}/Calls.json", params=params)  # type: ignore[return-value]

    async def get_call(self, call_sid: str) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/Calls/{Sid} — Get call details."""
        return await self._request("GET", f"/Accounts/{self.account_sid}/Calls/{call_sid}.json")  # type: ignore[return-value]

    async def make_call(
        self,
        to: str,
        from_: str,
        url: str | None = None,
        twiml: str | None = None,
    ) -> dict[str, Any]:
        """POST /Accounts/{AccountSid}/Calls — Initiate an outbound call."""
        form_data: dict[str, Any] = {"To": to, "From": from_}
        if url:
            form_data["Url"] = url
        if twiml:
            form_data["Twiml"] = twiml
        return await self._request(
            "POST",
            f"/Accounts/{self.account_sid}/Calls.json",
            data=form_data,
        )  # type: ignore[return-value]

    # ── Phone Numbers ───────────────────────────────────────────

    async def list_phone_numbers(self) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/IncomingPhoneNumbers — List purchased phone numbers."""
        return await self._request("GET", f"/Accounts/{self.account_sid}/IncomingPhoneNumbers.json")  # type: ignore[return-value]

    # ── Recordings ──────────────────────────────────────────────

    async def get_recording(self, recording_sid: str) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/Recordings/{Sid} — Get a recording."""
        return await self._request("GET", f"/Accounts/{self.account_sid}/Recordings/{recording_sid}.json")  # type: ignore[return-value]

    async def list_recordings(self, call_sid: str | None = None) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/Recordings — List recordings."""
        params: dict[str, Any] = {}
        if call_sid:
            params["CallSid"] = call_sid
        return await self._request("GET", f"/Accounts/{self.account_sid}/Recordings.json", params=params)  # type: ignore[return-value]

    # ── Usage ───────────────────────────────────────────────────

    async def get_usage(self) -> dict[str, Any]:
        """GET /Accounts/{AccountSid}/Usage/Records — Get usage/billing records."""
        return await self._request("GET", f"/Accounts/{self.account_sid}/Usage/Records.json")  # type: ignore[return-value]
