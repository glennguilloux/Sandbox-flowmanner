"""Alerting service for circuit breaker state changes and SLO violations.

Sends alerts through multiple configurable channels:
- webhook (Slack/Discord compatible, existing)
- ntfy (push notifications via ntfy.sh)
- email (placeholder)
- pagerduty (placeholder)

Configure channels via NOTIFY_CHANNELS env (CSV):
  NOTIFY_CHANNELS=ntfy,webhook,email,pagerduty

Per-channel settings:
  NTFY_TOPIC  — ntfy.sh topic name (e.g. "flowmanner-alerts")
  NTFY_URL    — full ntfy server URL (overrides topic-based default)

Debounces to prevent alert fatigue.
Per-channel failures are non-fatal and logged individually.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import smtplib
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ── Channel configuration ────────────────────────────────────────────────────

_NOTIFY_CHANNELS = os.getenv("NOTIFY_CHANNELS", "").lower().strip()
_ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
_ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))  # 5 min

# ntfy settings
_NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
_NTFY_URL = os.getenv("NTFY_URL", "")
_NTFY_DEFAULT_BASE = "https://ntfy.sh"


def _get_ntfy_url() -> str:
    """Resolve ntfy endpoint URL.

    Precedence: explicit NTFY_URL > topic-based default > empty string.
    """
    if _NTFY_URL:
        return _NTFY_URL
    if _NTFY_TOPIC:
        return f"{_NTFY_DEFAULT_BASE}/{_NTFY_TOPIC}"
    return ""


@dataclass
class _AlertState:
    timestamps: dict[str, float] = field(default_factory=dict)
    last_sent: float = 0.0  # kept for backward compat with get_alerting_status()
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_alert_state = _AlertState()
_slo_alert_state = _AlertState()  # H1.5: separate debounce for SLO alerts


# ── Channel resolution ───────────────────────────────────────────────────────


def _get_channels() -> list[str]:
    """Parse NOTIFY_CHANNELS into a list of channel names.

    Returns the CSV-parsed channel list from NOTIFY_CHANNELS.
    Falls back to ['webhook'] when NOTIFY_CHANNELS is unset but
    ALERT_WEBHOOK_URL is configured (backward compatibility).
    Returns [] when nothing is configured.
    """
    if _NOTIFY_CHANNELS:
        channels = [c.strip() for c in _NOTIFY_CHANNELS.split(",") if c.strip()]
        if channels:
            return channels

    # Backward compat: single webhook if URL exists but no NOTIFY_CHANNELS set
    if _ALERT_WEBHOOK_URL:
        return ["webhook"]

    return []


# ── Debounce ─────────────────────────────────────────────────────────────────


def _should_send(dependency: str, new_state: str) -> bool:
    """Debounce: skip if we alerted for this dependency+state recently."""
    key = f"{dependency}:{new_state}"
    now = time.monotonic()
    last = _alert_state.timestamps.get(key, 0.0)
    if now - last < _ALERT_COOLDOWN_SECONDS:
        logger.debug("Alert debounced for %s (cooldown)", key)
        return False
    return True


# ── Per-channel dispatchers ─────────────────────────────────────────────────


async def _send_webhook(payload: dict) -> bool:
    """Dispatch alert to webhook URL (Slack/Discord compatible).

    Uses the passed payload as-is — caller is responsible for formatting.
    """
    if not _ALERT_WEBHOOK_URL:
        logger.debug("webhook channel: no URL configured — skipping")
        return False

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(_ALERT_WEBHOOK_URL, json=payload)
        if resp.status_code < 300:
            return True
        logger.warning(
            "webhook channel returned %d: %s",
            resp.status_code,
            resp.text[:200],
        )
        return False


async def _send_ntfy(payload: dict) -> bool:
    """Dispatch alert to ntfy.sh (or self-hosted ntfy server).

    ntfy expects plain text body with optional Title/Priority/Tags headers.
    Converts the rich Slack-compatible payload to ntfy format.
    """
    ntfy_url = _get_ntfy_url()
    if not ntfy_url:
        logger.debug("ntfy channel: no URL or topic configured — skipping")
        return False

    text = payload.get("text", "")
    headers: dict[str, str] = {
        "Title": payload.get("title", payload.get("username", "Flowmanner Alert")),
    }
    priority = payload.get("priority", "default")
    if priority:
        headers["Priority"] = str(priority)
    tags = payload.get("tags", [])
    if tags:
        headers["Tags"] = ",".join(tags) if isinstance(tags, list) else str(tags)

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            ntfy_url,
            data=text.encode("utf-8"),
            headers=headers,
        )
        if resp.status_code < 300:
            return True
        logger.warning(
            "ntfy channel returned %d: %s",
            resp.status_code,
            resp.text[:200],
        )
        return False


async def _send_email(payload: dict) -> bool:
    """Dispatch alert via SMTP email.

    Uses SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD from settings.
    Falls back to log warning if SMTP is not configured.
    """
    smtp_host = getattr(settings, "SMTP_HOST", "")
    if not smtp_host:
        logger.debug("email channel: SMTP_HOST not configured — skipping")
        return False

    smtp_port = getattr(settings, "SMTP_PORT", 587)
    smtp_username = getattr(settings, "SMTP_USERNAME", "")
    smtp_password = getattr(settings, "SMTP_PASSWORD", "")
    smtp_from = smtp_username or "alerts@flowmanner.com"
    smtp_to = os.getenv("ALERT_EMAIL_TO", smtp_from)

    subject = payload.get("title", "[FlowManner Alert]")
    body_text = payload.get("text", "No details provided.")
    # Strip markdown formatting for plain-text email
    plain_text = body_text.replace("**", "").replace("`", "").replace("\n", "\r\n")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = smtp_to
    msg.attach(MIMEText(plain_text, "plain"))

    # Also attach HTML version
    html_body = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body_text)
    html_body = html_body.replace("`", "<code>").replace("\n", "<br>")
    msg.attach(MIMEText(f"<html><body><pre>{html_body}</pre></body></html>", "html"))

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            _smtp_send,
            smtp_host,
            smtp_port,
            smtp_username,
            smtp_password,
            smtp_from,
            smtp_to,
            msg,
        )
        return True
    except Exception as e:
        logger.warning("email channel failed (non-fatal): %s", e)
        return False


def _smtp_send(
    host: str,
    port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    msg: MIMEMultipart,
) -> None:
    """Synchronous SMTP send — called via run_in_executor."""
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.ehlo()
        if port != 25:
            server.starttls()
            server.ehlo()
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())


async def _send_pagerduty(payload: dict) -> bool:
    """Dispatch alert via PagerDuty Events API v2.

    Requires PAGERDUTY_INTEGRATION_KEY env var.
    Falls back to log warning if key is not configured.
    """
    integration_key = os.getenv("PAGERDUTY_INTEGRATION_KEY", "")
    if not integration_key:
        logger.debug(
            "pagerduty channel: PAGERDUTY_INTEGRATION_KEY not configured — skipping"
        )
        return False

    # Map payload severity to PagerDuty severity
    pd_severity = "info"
    priority = payload.get("priority", "default")
    if priority == "urgent":
        pd_severity = "critical"
    elif priority in ("high", "default"):
        pd_severity = "warning" if priority == "high" else "info"

    pd_payload = {
        "routing_key": integration_key,
        "event_action": "trigger",
        "payload": {
            "summary": payload.get("title", "Flowmanner Alert"),
            "source": "flowmanner-backend",
            "severity": pd_severity,
            "custom_details": {
                "text": payload.get("text", ""),
                "tags": payload.get("tags", []),
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=pd_payload,
            )
            if resp.status_code < 300:
                return True
            logger.warning(
                "pagerduty channel returned %d: %s", resp.status_code, resp.text[:200]
            )
            return False
    except Exception as e:
        logger.warning("pagerduty channel failed (non-fatal): %s", e)
        return False


# Channel dispatcher registry
_CHANNEL_DISPATCHERS: dict[str, object] = {
    "webhook": _send_webhook,
    "ntfy": _send_ntfy,
    "email": _send_email,
    "pagerduty": _send_pagerduty,
}


async def _dispatch_to_channels(
    payload: dict,
    channels: list[str] | None = None,
) -> dict[str, bool]:
    """Send a payload to all configured alert channels.

    Per-channel failures are **non-fatal** — each channel is tried
    independently and failures are logged. Other channels continue
    regardless of any individual channel failure.

    Returns a dict of channel_name → success (bool).
    """
    if channels is None:
        channels = _get_channels()

    if not channels:
        logger.debug("No alert channels configured — skipping dispatch")
        return {}

    results: dict[str, bool] = {}
    for channel in channels:
        dispatcher = _CHANNEL_DISPATCHERS.get(channel)
        if dispatcher is None:
            logger.warning("Unknown alert channel '%s' — skipping", channel)
            results[channel] = False
            continue
        try:
            results[channel] = await dispatcher(payload)  # type: ignore[operator]
        except Exception as e:
            logger.warning(
                "Alert channel '%s' failed (non-fatal): %s",
                channel,
                e,
            )
            results[channel] = False

    return results


# ── Public alert senders ─────────────────────────────────────────────────────


async def send_circuit_alert(
    dependency: str,
    old_state: str,
    new_state: str,
    failure_count: int = 0,
) -> None:
    """Send an alert about a circuit breaker state change.

    Routes through all configured channels (NOTIFY_CHANNELS).
    Fires-and-forgets. Never raises.
    """
    channels = _get_channels()
    if not channels:
        logger.debug("No alert channels configured — skipping circuit alert")
        return

    if not _should_send(dependency, new_state):
        return

    emoji = "🔴" if new_state == "open" else "🟡" if new_state == "half_open" else "🟢"
    severity = (
        "CRITICAL"
        if new_state == "open"
        else "WARNING" if new_state == "half_open" else "INFO"
    )

    # Build rich internal payload — each channel dispatcher formats as needed
    payload = {
        "text": (
            f"{emoji} **[{severity}] Circuit Breaker: {dependency}**\n"
            f"State: `{old_state}` → `{new_state}`\n"
            f"Failures: {failure_count}\n"
            f"Service: workflow-backend"
        ),
        "username": "Flowmanner Alerts",
        "icon_emoji": ":warning:",
        "title": f"[{severity}] Circuit Breaker: {dependency}",
        "priority": (
            "urgent"
            if severity == "CRITICAL"
            else "high" if severity == "WARNING" else "default"
        ),
        "tags": ["circuit_breaker", new_state],
    }

    try:
        results = await _dispatch_to_channels(payload, channels)
        if any(results.values()):
            key = f"{dependency}:{new_state}"
            _alert_state.timestamps[key] = time.monotonic()
            _alert_state.last_sent = _alert_state.timestamps[key]
        logger.info(
            "Circuit alert dispatched: %s %s→%s (failures=%d) channels=%s",
            dependency,
            old_state,
            new_state,
            failure_count,
            {ch: "ok" if ok else "fail" for ch, ok in results.items()},
        )
    except Exception as e:
        logger.warning("Circuit alert dispatch failed (non-fatal): %s", e)


async def send_slo_alert(
    slo_name: str,
    description: str,
    compliance: float,
    burn_rate: float,
    error_budget_remaining: float,
    target: float,
) -> None:
    """Send an alert about an SLO violation (H1.5).

    Triggers when:
    - Burn rate exceeds 5x (rapid budget consumption)
    - Error budget remaining drops below 10%

    Routes through all configured channels (NOTIFY_CHANNELS).
    Fires-and-forgets. Never raises.
    """
    channels = _get_channels()
    if not channels:
        return

    # Determine severity
    if burn_rate >= 10.0 or error_budget_remaining <= 0.0:
        severity = "CRITICAL"
        emoji = "🔴"
    elif burn_rate >= 5.0 or error_budget_remaining <= 0.1:
        severity = "WARNING"
        emoji = "🟡"
    else:
        return  # Don't alert on mild degradation

    # Debounce per SLO name (separate state from circuit breaker alerts)
    key = f"slo:{slo_name}:{severity}"
    now = time.monotonic()
    if now - _slo_alert_state.last_sent < _ALERT_COOLDOWN_SECONDS:
        logger.debug("SLO alert debounced for %s (cooldown)", key)
        return

    # Build rich internal payload
    payload = {
        "text": (
            f"{emoji} **[{severity}] SLO Alert: {slo_name}**\n"
            f"Target: {description} (target: {target*100:.1f}%)\n"
            f"Compliance: {compliance*100:.2f}%\n"
            f"Burn rate: {burn_rate:.1f}x\n"
            f"Error budget remaining: {error_budget_remaining*100:.1f}%\n"
            f"Service: workflow-backend (homelab)"
        ),
        "username": "Flowmanner SLO Alerts",
        "icon_emoji": ":chart_with_downwards_trend:",
        "title": f"[{severity}] SLO Alert: {slo_name}",
        "priority": "urgent" if severity == "CRITICAL" else "high",
        "tags": ["slo", slo_name, severity.lower()],
    }

    try:
        results = await _dispatch_to_channels(payload, channels)
        if any(results.values()):
            _slo_alert_state.timestamps[key] = now
            _slo_alert_state.last_sent = now
        logger.warning(
            "SLO alert dispatched: %s (compliance=%.2f%%, burn=%.1fx) channels=%s",
            slo_name,
            compliance * 100,
            burn_rate,
            {ch: "ok" if ok else "fail" for ch, ok in results.items()},
        )
    except Exception as e:
        logger.warning("SLO alert dispatch failed (non-fatal): %s", e)


# ── Status / observability ─────────────────────────────────────────────────


def get_alerting_status() -> dict:
    """Return alerting configuration for observability endpoint."""
    return {
        "channels": _get_channels(),
        "webhook_configured": bool(_ALERT_WEBHOOK_URL),
        "ntfy_configured": bool(_get_ntfy_url()),
        "email_configured": bool(getattr(settings, "SMTP_HOST", "")),
        "pagerduty_configured": bool(os.getenv("PAGERDUTY_INTEGRATION_KEY", "")),
        "cooldown_seconds": _ALERT_COOLDOWN_SECONDS,
        "last_alert_ago_seconds": (
            round(time.monotonic() - _alert_state.last_sent, 1)
            if _alert_state.last_sent > 0
            else None
        ),
        "last_slo_alert_ago_seconds": (
            round(time.monotonic() - _slo_alert_state.last_sent, 1)
            if _slo_alert_state.last_sent > 0
            else None
        ),
    }
