"""Tests for multi-channel alerting dispatch (H3).

Covers:
- channel parsing from NOTIFY_CHANNELS env
- ntfy payload formatting (topic URL construction, headers)
- multi-channel fanout behavior
- per-channel failure isolation
- backward compatibility fallback to webhook-only
"""

from __future__ import annotations

import asyncio
import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MODULE_PATH = "app.services.alerting"


# ── Helpers ────────────────────────────────────────────────────────


def _reload_alerting(**env_overrides: str | None) -> object:
    """Reload the alerting module with given env vars set.

    Returns the fresh module so tests can inspect its state.
    """
    for k, v in env_overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    import app.services.alerting as am

    importlib.reload(am)
    return am


def _make_payload() -> dict:
    """Return a representative circuit-breaker payload."""
    return {
        "text": "🔴 **[CRITICAL] Circuit Breaker: test-db**\nState: `closed` → `open`\nFailures: 3\nService: workflow-backend",
        "username": "Flowmanner Alerts",
        "icon_emoji": ":warning:",
        "title": "[CRITICAL] Circuit Breaker: test-db",
        "priority": "urgent",
        "tags": ["circuit_breaker", "open"],
    }


def _make_slo_payload() -> dict:
    """Return a representative SLO alert payload."""
    return {
        "text": "🟡 **[WARNING] SLO Alert: mission_success_rate**\nTarget: Mission execution success rate > 95% (target: 95.0%)\nCompliance: 87.50%\nBurn rate: 6.2x\nError budget remaining: 8.3%\nService: workflow-backend (homelab)",
        "username": "Flowmanner SLO Alerts",
        "icon_emoji": ":chart_with_downwards_trend:",
        "title": "[WARNING] SLO Alert: mission_success_rate",
        "priority": "high",
        "tags": ["slo", "mission_success_rate", "warning"],
    }


# ═══════════════════════════════════════════════════════════════════
# Channel parsing from env
# ═══════════════════════════════════════════════════════════════════


class TestChannelParsing:
    @pytest.mark.parametrize(
        "env_val,expected",
        [
            ("ntfy,webhook", ["ntfy", "webhook"]),
            ("ntfy", ["ntfy"]),
            ("webhook,email,pagerduty,ntfy", ["webhook", "email", "pagerduty", "ntfy"]),
            (" ntfy , webhook ", ["ntfy", "webhook"]),
            ("NTFY,WEBHOOK", ["ntfy", "webhook"]),
            ("", []),
            ("   ", []),
            ("unknown_channel", ["unknown_channel"]),
        ],
    )
    def test_parses_notify_channels_csv(self, env_val, expected):
        """_get_channels() correctly parses NOTIFY_CHANNELS env."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=env_val or None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
            NTFY_URL="",
        )
        result = am._get_channels()
        assert result == expected

    def test_falls_back_to_webhook_when_url_set_but_no_channels(self):
        """Backward compat: webhook URL set but no NOTIFY_CHANNELS → returns ['webhook']."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
            NTFY_TOPIC="",
            NTFY_URL="",
        )
        assert am._get_channels() == ["webhook"]

    def test_returns_empty_when_nothing_configured(self):
        """No channels and no webhook URL → returns []."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
            NTFY_URL="",
        )
        assert am._get_channels() == []


# ═══════════════════════════════════════════════════════════════════
# ntfy URL/payload formatting
# ═══════════════════════════════════════════════════════════════════


class TestNtfyFormatting:
    def test_ntfy_url_from_topic(self):
        """NTFY_TOPIC=my-topic → https://ntfy.sh/my-topic"""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="flowmanner-alerts",
            NTFY_URL="",
        )
        assert am._get_ntfy_url() == "https://ntfy.sh/flowmanner-alerts"

    def test_ntfy_url_from_explicit_url(self):
        """NTFY_URL takes precedence over NTFY_TOPIC."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="flowmanner-alerts",
            NTFY_URL="https://ntfy.selfhosted.example.com/flowmanner",
        )
        assert am._get_ntfy_url() == "https://ntfy.selfhosted.example.com/flowmanner"

    def test_ntfy_url_empty_when_nothing_set(self):
        """No topic or URL → empty string."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
            NTFY_URL="",
        )
        assert am._get_ntfy_url() == ""

    @pytest.mark.asyncio
    async def test_ntfy_send_formats_correct_payload(self):
        """_send_ntfy() POSTs plain text with Title/Priority/Tags headers."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="test-topic",
            NTFY_URL="",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=mock_response)

        payload = _make_payload()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await am._send_ntfy(payload)

        assert result is True
        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["data"] == payload["text"].encode("utf-8")
        assert call_kwargs["headers"]["Title"] == payload["title"]
        assert call_kwargs["headers"]["Priority"] == "urgent"
        assert call_kwargs["headers"]["Tags"] == "circuit_breaker,open"

    @pytest.mark.asyncio
    async def test_ntfy_skips_when_no_url(self):
        """_send_ntfy() returns False when no ntfy URL/topic configured."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
            NTFY_URL="",
        )
        payload = _make_payload()
        result = await am._send_ntfy(payload)
        assert result is False

    @pytest.mark.asyncio
    async def test_ntfy_handles_non_2xx(self):
        """_send_ntfy() returns False on non-2xx status."""
        am = _reload_alerting(NTFY_TOPIC="test-topic")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await am._send_ntfy(_make_payload())

        assert result is False


# ═══════════════════════════════════════════════════════════════════
# Webhook channel
# ═══════════════════════════════════════════════════════════════════


class TestWebhookChannel:
    @pytest.mark.asyncio
    async def test_webhook_sends_json_payload(self):
        """_send_webhook() POSTs the payload as JSON to ALERT_WEBHOOK_URL."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
            NTFY_TOPIC="",
            NTFY_URL="",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=mock_response)

        payload = _make_payload()

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await am._send_webhook(payload)

        assert result is True
        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["json"] == payload

    @pytest.mark.asyncio
    async def test_webhook_skips_when_no_url(self):
        """_send_webhook() returns False when no URL configured."""
        am = _reload_alerting(ALERT_WEBHOOK_URL="", NTFY_TOPIC="")
        result = await am._send_webhook(_make_payload())
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# Placeholder channels
# ═══════════════════════════════════════════════════════════════════


class TestPlaceholderChannels:
    @pytest.mark.asyncio
    async def test_email_returns_false(self):
        """email channel is placeholder — returns False."""
        am = _reload_alerting()
        result = await am._send_email({})
        assert result is False

    @pytest.mark.asyncio
    async def test_pagerduty_returns_false(self):
        """pagerduty channel is placeholder — returns False."""
        am = _reload_alerting()
        result = await am._send_pagerduty({})
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# Multi-channel dispatch + failure isolation
# ═══════════════════════════════════════════════════════════════════


class TestMultiChannelDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_to_all_configured_channels(self):
        """_dispatch_to_channels() sends to every channel in the list."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="ntfy,webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
            NTFY_TOPIC="test-topic",
        )

        call_log = []

        async def fake_ntfy(payload):
            call_log.append("ntfy")
            return True

        async def fake_webhook(payload):
            call_log.append("webhook")
            return True

        # Patch the dispatcher registry dict so patches flow through
        with patch.dict(
            am._CHANNEL_DISPATCHERS,
            {
                "ntfy": fake_ntfy,
                "webhook": fake_webhook,
            },
        ):
            results = await am._dispatch_to_channels(
                _make_payload(), channels=["ntfy", "webhook"]
            )

        assert results == {"ntfy": True, "webhook": True}
        assert "ntfy" in call_log
        assert "webhook" in call_log

    @pytest.mark.asyncio
    async def test_channel_failure_does_not_block_others(self):
        """One channel failing does not prevent other channels from dispatching."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="ntfy,webhook,email",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
            NTFY_TOPIC="test-topic",
        )

        results_tracker = {"ntfy_ok": False, "webhook_ok": False, "email_ok": False}

        async def fake_ntfy(payload):
            results_tracker["ntfy_ok"] = True
            raise RuntimeError("simulated ntfy failure")

        async def fake_webhook(payload):
            results_tracker["webhook_ok"] = True
            return True

        async def fake_email(payload):
            results_tracker["email_ok"] = True
            return False  # placeholder

        with patch.dict(
            am._CHANNEL_DISPATCHERS,
            {
                "ntfy": fake_ntfy,
                "webhook": fake_webhook,
                "email": fake_email,
            },
        ):
            dispatch_results = await am._dispatch_to_channels(
                _make_payload(), channels=["ntfy", "webhook", "email"]
            )

        assert dispatch_results == {"ntfy": False, "webhook": True, "email": False}
        assert results_tracker["ntfy_ok"] is True
        assert results_tracker["webhook_ok"] is True
        assert results_tracker["email_ok"] is True

    @pytest.mark.asyncio
    async def test_unknown_channel_skipped(self):
        """Unknown channel names are skipped with a warning, not an error."""
        am = _reload_alerting()
        results = await am._dispatch_to_channels(
            _make_payload(), channels=["nonexistent_channel"]
        )
        assert results == {"nonexistent_channel": False}

    @pytest.mark.asyncio
    async def test_empty_channels_returns_empty_dict(self):
        """No channels → empty result dict."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
        )
        results = await am._dispatch_to_channels(_make_payload())
        assert results == {}


# ═══════════════════════════════════════════════════════════════════
# Circuit alert end-to-end
# ═══════════════════════════════════════════════════════════════════


class TestCircuitAlertEndToEnd:
    @pytest.mark.asyncio
    async def test_send_circuit_alert_dispatches_to_channels(self):
        """send_circuit_alert() dispatches through _dispatch_to_channels."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
        )
        am._alert_state.timestamps.clear()

        async def fake_dispatch(payload, channels):
            return {"webhook": True}

        with patch.object(
            am, "_dispatch_to_channels", side_effect=fake_dispatch
        ) as mock_dispatch:
            await am.send_circuit_alert("test-db", "closed", "open", 3)

        mock_dispatch.assert_awaited_once()
        payload = mock_dispatch.call_args.args[0]
        assert "test-db" in payload["text"]
        assert payload["priority"] == "urgent"
        assert payload["tags"] == ["circuit_breaker", "open"]

    @pytest.mark.asyncio
    async def test_send_circuit_alert_skips_when_no_channels(self):
        """send_circuit_alert() returns quietly when nothing configured."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
        )
        am._alert_state.timestamps.clear()

        dispatched = False

        async def fake_dispatch(payload, channels):
            nonlocal dispatched
            dispatched = True
            return {}

        with patch.object(am, "_dispatch_to_channels", side_effect=fake_dispatch):
            await am.send_circuit_alert("test-db", "closed", "open", 3)

        assert dispatched is False

    @pytest.mark.asyncio
    async def test_send_circuit_alert_debounces(self):
        """Repeated alerts for same dependency+state are debounced."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
        )
        am._alert_state.timestamps.clear()

        call_count = 0

        async def fake_dispatch(payload, channels):
            nonlocal call_count
            call_count += 1
            return {"webhook": True}

        with patch.object(am, "_dispatch_to_channels", side_effect=fake_dispatch):
            await am.send_circuit_alert("test-db", "closed", "open", 3)
            await am.send_circuit_alert("test-db", "closed", "open", 3)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_send_circuit_alert_not_debounced_for_different_state(self):
        """Different state transitions are not debounced."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
        )
        am._alert_state.timestamps.clear()

        call_count = 0

        async def fake_dispatch(payload, channels):
            nonlocal call_count
            call_count += 1
            return {"webhook": True}

        with patch.object(am, "_dispatch_to_channels", side_effect=fake_dispatch):
            await am.send_circuit_alert("test-db", "closed", "open", 3)
            await am.send_circuit_alert("test-db", "open", "half_open", 2)

        assert call_count == 2


# ═══════════════════════════════════════════════════════════════════
# SLO alert end-to-end
# ═══════════════════════════════════════════════════════════════════


class TestSLOAlertEndToEnd:
    @pytest.mark.asyncio
    async def test_send_slo_alert_dispatches_to_channels(self):
        """send_slo_alert() dispatches through _dispatch_to_channels."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="webhook,ntfy",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
            NTFY_TOPIC="test-topic",
        )
        am._slo_alert_state.timestamps.clear()

        async def fake_dispatch(payload, channels):
            return {"webhook": True, "ntfy": True}

        with patch.object(
            am, "_dispatch_to_channels", side_effect=fake_dispatch
        ) as mock_dispatch:
            await am.send_slo_alert(
                slo_name="mission_success_rate",
                description="Mission execution success rate > 95%",
                compliance=0.875,
                burn_rate=6.2,
                error_budget_remaining=0.083,
                target=0.95,
            )

        mock_dispatch.assert_awaited_once()
        payload = mock_dispatch.call_args.args[0]
        assert "mission_success_rate" in payload["text"]
        assert payload["tags"] == ["slo", "mission_success_rate", "warning"]

    @pytest.mark.asyncio
    async def test_send_slo_alert_skips_on_mild_degradation(self):
        """SLO alert is not sent when severity is below WARNING threshold."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
        )
        am._slo_alert_state.timestamps.clear()

        dispatched = False

        async def fake_dispatch(payload, channels):
            nonlocal dispatched
            dispatched = True
            return {}

        with patch.object(am, "_dispatch_to_channels", side_effect=fake_dispatch):
            await am.send_slo_alert(
                slo_name="sse_token_latency_p99",
                description="p99 SSE token delivery latency < 300ms",
                compliance=0.995,
                burn_rate=4.0,
                error_budget_remaining=0.5,
                target=0.999,
            )

        assert dispatched is False

    @pytest.mark.asyncio
    async def test_send_slo_alert_debounces(self):
        """Repeated SLO alerts for same slo+severity are debounced."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
        )
        am._slo_alert_state.timestamps.clear()

        call_count = 0

        async def fake_dispatch(payload, channels):
            nonlocal call_count
            call_count += 1
            return {"webhook": True}

        with patch.object(am, "_dispatch_to_channels", side_effect=fake_dispatch):
            await am.send_slo_alert(
                slo_name="mission_success_rate",
                description="test",
                compliance=0.80,
                burn_rate=10.0,
                error_budget_remaining=0.0,
                target=0.95,
            )
            await am.send_slo_alert(
                slo_name="mission_success_rate",
                description="test",
                compliance=0.80,
                burn_rate=10.0,
                error_budget_remaining=0.0,
                target=0.95,
            )

        assert call_count == 1


# ═══════════════════════════════════════════════════════════════════
# get_alerting_status()
# ═══════════════════════════════════════════════════════════════════


class TestAlertingStatus:
    def test_status_includes_channels_and_config(self):
        """get_alerting_status() reports channel configuration."""
        am = _reload_alerting(
            NOTIFY_CHANNELS="ntfy,webhook",
            ALERT_WEBHOOK_URL="https://hooks.slack.com/test",
            NTFY_TOPIC="test-topic",
        )
        status = am.get_alerting_status()
        assert status["channels"] == ["ntfy", "webhook"]
        assert status["webhook_configured"] is True
        assert status["ntfy_configured"] is True
        assert status["cooldown_seconds"] == 300
        assert "last_alert_ago_seconds" in status
        assert "last_slo_alert_ago_seconds" in status

    def test_status_reports_unconfigured(self):
        """get_alerting_status() correctly reports nothing configured."""
        am = _reload_alerting(
            NOTIFY_CHANNELS=None,
            ALERT_WEBHOOK_URL="",
            NTFY_TOPIC="",
            NTFY_URL="",
        )
        status = am.get_alerting_status()
        assert status["channels"] == []
        assert status["webhook_configured"] is False
        assert status["ntfy_configured"] is False
