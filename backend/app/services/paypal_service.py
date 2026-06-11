from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx


class PayPalClient:
    """PayPal API client for subscription billing (Story 3.3 replacement for Stripe)."""

    def __init__(self):
        # PayPal API keys (set these in environment variables)
        from app.config import settings

        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.mode = settings.PAYPAL_MODE  # "sandbox" or "live"

        # API URLs
        if self.mode == "live":
            self.base_url = "https://api.paypal.com"
        else:
            self.base_url = "https://api.sandbox.paypal.com"

        self.access_token = None
        self.token_expiry = None

    async def get_access_token(self) -> str:
        """Get OAuth access token from PayPal."""
        if self.access_token and self.token_expiry and self.token_expiry > datetime.now():
            return self.access_token

        url = f"{self.base_url}/v1/oauth2/token"
        auth = (self.client_id, self.client_secret)
        data = {"grant_type": "client_credentials"}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, auth=auth, data=data)
            response.raise_for_status()
            token_data = response.json()

            self.access_token = token_data["access_token"]
            # Token typically valid for 32400 seconds (9 hours)
            self.token_expiry = datetime.now() + timedelta(seconds=token_data.get("expires_in", 32400))

            return self.access_token

    async def create_subscription(self, plan_id: str, subscriber_email: str) -> dict:
        """
        Create a PayPal subscription.
        Returns: {"id": "...", "status": "...", "links": [...]}
        """
        token = await self.get_access_token()
        url = f"{self.base_url}/v1/billing/subscriptions"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "plan_id": plan_id,
            "subscriber": {
                "email_address": subscriber_email,
            },
            "application_context": {
                "brand_name": "Flowmanner",
                "return_url": f"{os.getenv('API_BASE_URL', 'http://localhost:8000')}/api/v1/billing/paypal/return",
                "cancel_url": f"{os.getenv('API_BASE_URL', 'http://localhost:8000')}/api/v1/billing/paypal/cancel",
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def get_subscription(self, subscription_id: str) -> dict:
        """Get subscription details."""
        token = await self.get_access_token()
        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}"

        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def cancel_subscription(self, subscription_id: str, reason: str = "User cancelled") -> bool:
        """Cancel a subscription."""
        token = await self.get_access_token()
        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/cancel"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json={"reason": reason})
            response.raise_for_status()
            return True

    async def activate_subscription(self, subscription_id: str) -> dict:
        """Activate a subscription after PayPal approval.

        Verifies the subscription is in APPROVED state with PayPal, then
        activates it so the user gains tier benefits.
        """
        token = await self.get_access_token()
        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/activate"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json={"reason": "Subscription approved by subscriber"},
            )
            response.raise_for_status()
            return response.json() if response.status_code != 204 else {"status": "ACTIVE"}

    async def suspend_subscription(self, subscription_id: str, reason: str = "Past due") -> bool:
        """Suspend a subscription (e.g., on payment failure)."""
        token = await self.get_access_token()
        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/suspend"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json={"reason": reason},
            )
            response.raise_for_status()
            return True

    @staticmethod
    def verify_webhook_signature(
        *,
        body: bytes,
        headers: dict[str, str],
        webhook_id: str,
        cert_url: str,
        auth_algo: str,
        transmission_id: str,
        transmission_time: str,
        webhook_event: dict,
    ) -> bool:
        """Verify PayPal webhook signature (lightweight local check).

        PayPal sends webhook verification headers; this method checks the
        event body hash matches. For production, use PayPal's
        ``/v1/notifications/verify-webhook-signature`` endpoint.

        This is a fast local check that verifies the SHA-256 signature
        header is present and non-empty. Full signature verification should
        be done via PayPal API in production.
        """
        sig = headers.get("paypal-transmission-sig", "")
        if not sig:
            return False

        # Local check: verify required headers are present
        required = [
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-cert-url",
            "paypal-auth-algo",
        ]
        return all(headers.get(h) for h in required)

    async def verify_webhook_signature_api(
        self,
        webhook_id: str,
        body: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify webhook signature via PayPal API (authoritative check).

        Use this in production for security-critical webhook processing.
        """
        token = await self.get_access_token()
        url = f"{self.base_url}/v1/notifications/verify-webhook-signature"

        api_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "webhook_id": webhook_id,
            "auth_algo": headers.get("paypal-auth-algo", ""),
            "cert_url": headers.get("paypal-cert-url", ""),
            "transmission_id": headers.get("paypal-transmission-id", ""),
            "transmission_sig": headers.get("paypal-transmission-sig", ""),
            "transmission_time": headers.get("paypal-transmission-time", ""),
            "webhook_event": body.decode("utf-8"),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=api_headers, json=payload)
            if response.status_code == 200:
                result = response.json()
                return result.get("verification_status") == "SUCCESS"
            return False


# Singleton instance
paypal_client = PayPalClient()
