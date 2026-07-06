"""Consolidated inbound webhook router — receives events from external services.

Replaces 22 individual ``*_webhook.py`` files with a single data-driven
dispatcher.  Each provider's verification method, secret setting, and
signature header are declared in ``PROVIDERS``; the generic
``handle_provider_webhook`` endpoint does the rest.

**This file does NOT touch user-created webhooks** (``webhooks.py``)
or the trigger endpoint (``triggers.py``).
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integration-webhooks"])


# ── Provider Configuration ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderConfig:
    """Declares how to verify and parse an inbound provider webhook."""

    name: str
    secret_setting: str  # attribute name on ``settings``
    auth_type: str  # "hmac_sha256", "hmac_sha256_base64", "hmac_sha1",
    # "token_header", "token_query", "hmac_timestamp", "hmac_slack",
    # "challenge", "none"
    signature_header: str = ""  # header that carries the signature/token
    algorithm: str = "sha256"
    prefix: str = ""  # expected prefix on the signature value, e.g. "sha256="
    timestamp_header: str = ""  # for replay-protected providers
    max_timestamp_drift: int = 300  # seconds
    # Custom verify function for non-standard schemes
    custom_verify: Callable[..., bool] | None = None
    # Extracts (event_type, event_id, payload_dict) from the parsed body
    extract_event: Callable[[dict[str, str], dict[str, Any]], tuple[str, str, dict[str, Any]]] = field(
        default=lambda headers, body: ("unknown", "", body),
    )


def _extract_github(headers: dict, body: dict) -> tuple[str, str, dict]:
    return (headers.get("x-github-event", "unknown"), headers.get("x-github-delivery", ""), body)


def _extract_stripe(headers: dict, body: dict) -> tuple[str, str, dict]:
    return (body.get("type", "unknown"), body.get("id", ""), body.get("data", {}).get("object", body))


def _extract_slack(headers: dict, body: dict) -> tuple[str, str, dict]:
    event = body.get("event", {})
    return (event.get("type", body.get("type", "unknown")), body.get("event_id", ""), body)


def _extract_generic_event_key(key: str) -> Callable[[dict, dict], tuple[str, str, dict]]:
    def _extract(headers: dict, body: dict) -> tuple[str, str, dict]:
        return (body.get(key, "unknown"), "", body)

    return _extract


def _extract_gitlab(headers: dict, body: dict) -> tuple[str, str, dict]:
    return (body.get("object_kind", "unknown"), str(body.get("id", "")), body)


def _extract_sentry(headers: dict, body: dict) -> tuple[str, str, dict]:
    return (body.get("action", body.get("event", "unknown")), "", body)


def _extract_shopify(headers: dict, body: dict) -> tuple[str, str, dict]:
    topic = headers.get("x-shopify-topic", "unknown")
    return (topic, str(body.get("id", "")), body)


def _extract_monday(headers: dict, body: dict) -> tuple[str, str, dict]:
    # Monday.com sends a challenge on first connect
    if body.get("challenge"):
        return ("challenge", "", body)
    return (body.get("event", {}).get("type", "unknown"), "", body)


def _extract_twilio(headers: dict, body: dict) -> tuple[str, str, dict]:
    return (body.get("SmsStatus", body.get("CallStatus", "unknown")), "", body)


def _extract_zendesk(headers: dict, body: dict) -> tuple[str, str, dict]:
    return (body.get("type", body.get("event", "unknown")), "", body)


def _extract_linear(headers: dict, body: dict) -> tuple[str, str, dict]:
    action = body.get("action", "unknown")
    entity_type = body.get("type", "")
    return (f"{entity_type}.{action}" if entity_type else action, "", body)


# ── Custom verification functions ─────────────────────────────────────────────


def _verify_stripe(body: bytes, headers: dict[str, str], secret: str | None) -> bool:
    """Stripe: HMAC-SHA256 of ``{timestamp}.{body}`` parsed from ``Stripe-Signature``."""
    if not secret:
        return True
    sig_header = headers.get("stripe-signature", "")
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts = parts.get("t", "")
    sig = parts.get("v1", "")
    if not ts or not sig:
        return False
    try:
        if abs(time.time() - int(ts)) > 300:
            logger.warning("Stripe webhook timestamp too old: %s", ts)
            return False
    except ValueError:
        return False
    expected = hmac.new(secret.encode("utf-8"), f"{ts}.{body.decode('utf-8')}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _verify_slack(body: bytes, headers: dict[str, str], secret: str | None) -> bool:
    """Slack: HMAC-SHA256 with 5-min timestamp replay protection."""
    if not secret:
        return True
    timestamp = headers.get("x-slack-request-timestamp", "")
    sig_header = headers.get("x-slack-signature", "")
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            logger.warning("Slack webhook timestamp too old: %s", timestamp)
            return False
    except ValueError:
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def _verify_twilio(body: bytes, headers: dict[str, str], secret: str | None, request_url: str = "") -> bool:
    """Twilio HMAC-SHA1 verification.

    Twilio signs webhooks by computing HMAC-SHA1 of the full request URL
    concatenated with sorted form parameters, using the auth token as key.
    """
    if not secret:
        return True  # Verification disabled (dev/test only)

    sig = headers.get("x-twilio-signature", "")
    if not sig:
        return False

    if not request_url:
        # Fallback: header presence check only (no URL available)
        return bool(sig)

    # Parse form-encoded body and sort params alphabetically
    from urllib.parse import parse_qs

    body_str = body.decode("utf-8") if body else ""
    params = parse_qs(body_str)
    flat_params = {k: v[0] for k, v in params.items()}
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(flat_params.items()))

    # Build signed string: URL + sorted params
    signed_string = request_url + sorted_params

    # HMAC-SHA1 with the Twilio auth token
    expected = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            signed_string.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    # Timing-safe comparison
    return hmac.compare_digest(expected, sig)


def _verify_monday(body: bytes, headers: dict[str, str], secret: str | None) -> bool:
    """Monday.com: no signature verification (challenge-response or IP-based)."""
    return True


# ── Provider Registry ─────────────────────────────────────────────────────────

PROVIDERS: dict[str, ProviderConfig] = {
    "github": ProviderConfig(
        name="github",
        secret_setting="GITHUB_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-hub-signature-256",
        prefix="sha256=",
        extract_event=_extract_github,
    ),
    "gitlab": ProviderConfig(
        name="gitlab",
        secret_setting="GITLAB_WEBHOOK_SECRET",
        auth_type="token_header",
        signature_header="x-gitlab-token",
        extract_event=_extract_gitlab,
    ),
    "stripe": ProviderConfig(
        name="stripe",
        secret_setting="STRIPE_WEBHOOK_SECRET",
        auth_type="custom",
        custom_verify=_verify_stripe,
        extract_event=_extract_stripe,
    ),
    "slack": ProviderConfig(
        name="slack",
        secret_setting="SLACK_SIGNING_SECRET",
        auth_type="custom",
        custom_verify=_verify_slack,
        extract_event=_extract_slack,
    ),
    "twilio": ProviderConfig(
        name="twilio",
        secret_setting="TWILIO_WEBHOOK_SECRET",
        auth_type="custom",
        custom_verify=_verify_twilio,
        extract_event=_extract_twilio,
    ),
    "telegram": ProviderConfig(
        name="telegram",
        secret_setting="TELEGRAM_WEBHOOK_SECRET",
        auth_type="token_header",
        signature_header="x-telegram-bot-api-secret-token",
        extract_event=_extract_generic_event_key("update_id"),
    ),
    "sentry": ProviderConfig(
        name="sentry",
        secret_setting="SENTRY_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-sentry-signature",
        extract_event=_extract_sentry,
    ),
    "vercel": ProviderConfig(
        name="vercel",
        secret_setting="VERCEL_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-vercel-signature",
        extract_event=_extract_generic_event_key("type"),
    ),
    "datadog": ProviderConfig(
        name="datadog",
        secret_setting="DATADOG_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-datadog-signature",
        extract_event=_extract_generic_event_key("alertType"),
    ),
    "airtable": ProviderConfig(
        name="airtable",
        secret_setting="AIRTABLE_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-airtable-content-mac",
        extract_event=_extract_generic_event_key("webhook"),
    ),
    "hubspot": ProviderConfig(
        name="hubspot",
        secret_setting="HUBSPOT_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-hubspot-signature-v3",
        extract_event=_extract_generic_event_key("subscriptionType"),
    ),
    "intercom": ProviderConfig(
        name="intercom",
        secret_setting="INTERCOM_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-hub-signature-256",
        extract_event=_extract_generic_event_key("type"),
    ),
    "asana": ProviderConfig(
        name="asana",
        secret_setting="ASANA_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-hook-signature",
        extract_event=_extract_generic_event_key("events"),
    ),
    "clickup": ProviderConfig(
        name="clickup",
        secret_setting="CLICKUP_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-signature",
        extract_event=_extract_generic_event_key("event"),
    ),
    "pagerduty": ProviderConfig(
        name="pagerduty",
        secret_setting="PAGERDUTY_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-pagerduty-signature",
        extract_event=_extract_generic_event_key("event"),
    ),
    "shopify": ProviderConfig(
        name="shopify",
        secret_setting="SHOPIFY_WEBHOOK_SECRET",
        auth_type="hmac_sha256_base64",
        signature_header="x-shopify-hmac-sha256",
        extract_event=_extract_shopify,
    ),
    "zendesk": ProviderConfig(
        name="zendesk",
        secret_setting="ZENDESK_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="x-zendesk-webhook-signature",
        extract_event=_extract_zendesk,
    ),
    "monday": ProviderConfig(
        name="monday",
        secret_setting="",
        auth_type="custom",
        custom_verify=_verify_monday,
        extract_event=_extract_monday,
    ),
    "linear": ProviderConfig(
        name="linear",
        secret_setting="LINEAR_WEBHOOK_SECRET",
        auth_type="hmac_sha256",
        signature_header="linear-signature",
        extract_event=_extract_linear,
    ),
    "jira": ProviderConfig(
        name="jira",
        secret_setting="JIRA_WEBHOOK_SECRET",
        auth_type="token_query",
        signature_header="x-jira-webhook-secret",
        extract_event=_extract_generic_event_key("webhookEvent"),
    ),
    "confluence": ProviderConfig(
        name="confluence",
        secret_setting="CONFLUENCE_WEBHOOK_SECRET",
        auth_type="token_query",
        signature_header="x-confluence-webhook-secret",
        extract_event=_extract_generic_event_key("webhookEvent"),
    ),
    "figma": ProviderConfig(
        name="figma",
        secret_setting="FIGMA_WEBHOOK_SECRET",
        auth_type="token_query",
        signature_header="x-figma-webhook-secret",
        extract_event=_extract_generic_event_key("event_type"),
    ),
}


# ── Generic Verification ──────────────────────────────────────────────────────


def _verify_hmac_sha256(
    body: bytes,
    headers: dict[str, str],
    secret: str,
    header_name: str,
    prefix: str = "",
) -> bool:
    """Standard HMAC-SHA256 verification."""
    sig_header = headers.get(header_name.lower(), "")
    if not sig_header:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if prefix:
        expected = f"{prefix}{expected}"
    return hmac.compare_digest(expected, sig_header)


def _verify_hmac_sha256_base64(
    body: bytes,
    headers: dict[str, str],
    secret: str,
    header_name: str,
) -> bool:
    """HMAC-SHA256 with Base64-encoded digest (Shopify)."""
    import base64

    sig_header = headers.get(header_name.lower(), "")
    if not sig_header:
        return False
    expected = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("utf-8")
    return hmac.compare_digest(expected, sig_header)


def _verify_token_header(headers: dict[str, str], secret: str, header_name: str) -> bool:
    """Simple token comparison via header."""
    provided = headers.get(header_name.lower(), "")
    return hmac.compare_digest(provided, secret) if provided else False


def _verify_token_query(
    request: Request,
    headers: dict[str, str],
    secret: str,
    header_name: str,
) -> bool:
    """Token comparison via header OR query param."""
    provided = headers.get(header_name.lower(), "")
    if not provided:
        provided = request.query_params.get("secret", "")
    return hmac.compare_digest(provided, secret) if provided else False


def verify_webhook(
    config: ProviderConfig,
    request: Request,
    body: bytes,
    headers: dict[str, str],
) -> bool:
    """Dispatch verification based on auth_type. Returns True if valid or no secret configured."""
    secret = getattr(settings, config.secret_setting, None) if config.secret_setting else None
    if not secret:
        return True

    if config.auth_type == "custom" and config.custom_verify:
        return config.custom_verify(body, headers, secret, str(request.url))

    if config.auth_type == "hmac_sha256":
        return _verify_hmac_sha256(body, headers, secret, config.signature_header, config.prefix)

    if config.auth_type == "hmac_sha256_base64":
        return _verify_hmac_sha256_base64(body, headers, secret, config.signature_header)

    if config.auth_type == "token_header":
        return _verify_token_header(headers, secret, config.signature_header)

    if config.auth_type == "token_query":
        return _verify_token_query(request, headers, secret, config.signature_header)

    # Fallback: no verification
    return True


# ── Generic Endpoint ──────────────────────────────────────────────────────────


@router.post("/{provider}/webhook")
async def handle_provider_webhook(provider: str, request: Request):
    """Generic inbound webhook endpoint for all integrated providers.

    1. Looks up provider config from ``PROVIDERS`` registry.
    2. Verifies the request signature/token per the provider's auth_type.
    3. Parses JSON body and extracts (event_type, event_id, payload).
    4. Returns ``{"status": "ok"}`` or provider-specific response.
    """
    config = PROVIDERS.get(provider)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown webhook provider: {provider}")

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Verify signature
    if not verify_webhook(config, request, body, headers):
        logger.warning("%s webhook signature verification failed", provider)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse body
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Handle Monday.com challenge-response
    if provider == "monday" and payload.get("challenge"):
        return JSONResponse({"challenge": payload["challenge"]})

    # Extract event info
    event_type, event_id, _data = config.extract_event(headers, payload)

    logger.info(
        "%s webhook: event_type=%s event_id=%s",
        provider,
        event_type,
        event_id or "n/a",
    )

    # TODO: Route to external_events durable bus when integration is wired
    # For now, log and acknowledge — the same behavior as the individual files.
    return {"status": "ok", "provider": provider, "event_type": event_type}
