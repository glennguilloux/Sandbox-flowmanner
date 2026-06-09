import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.usage_service import UsageService, get_usage_service


def test_usage_service_record_usage():
    """UsageService records usage correctly."""
    service = UsageService()
    record = service.record_usage(
        user_id="user-42",
        model_id="gpt-4",
        provider="openai",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert record.user_id == "user-42"
    assert record.model_id == "gpt-4"
    assert record.prompt_tokens == 1000
    assert record.completion_tokens == 500
    assert record.cost > 0


def test_usage_service_get_summary():
    """UsageService returns correct summary."""
    service = UsageService()
    service.record_usage("user-1", "gpt-4", "openai", 100, 50)
    service.record_usage("user-1", "gpt-4", "openai", 200, 100)
    summary = service.get_summary("user-1", period="day")
    assert summary.total_tokens == (100 + 50) + (200 + 100)
    assert summary.total_cost > 0
    assert len(summary.breakdown) == 1


def test_usage_service_get_timeseries():
    """UsageService returns timeseries data."""
    service = UsageService()
    service.record_usage("user-1", "gpt-4", "openai", 100, 50)
    timeseries = service.get_timeseries("user-1", period="day", granularity="hour")
    assert len(timeseries) >= 1
    assert "tokens" in timeseries[0]
    assert "cost" in timeseries[0]


def test_get_usage_service_singleton():
    """get_usage_service returns singleton instance."""
    service1 = get_usage_service()
    service2 = get_usage_service()
    assert service1 is service2


@pytest.mark.asyncio
async def test_sse_stream_basic():
    """Test _sse_stream only takes generator, no sink."""
    import json

    from app.api.v1.chat import _sse_stream

    async def fake_generator():
        yield json.dumps({"type": "token", "content": "Hello"})
        yield json.dumps(
            {"type": "complete", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        )

    events = []
    async for event in _sse_stream(fake_generator()):
        events.append(event)

    assert len(events) == 3  # two data events + DONE
    assert "DONE" in events[-1]


@pytest.mark.asyncio
async def test_sse_stream_no_complete_event():
    """Test _sse_stream with no complete event."""
    import json

    from app.api.v1.chat import _sse_stream

    async def fake_generator():
        yield json.dumps({"type": "token", "content": "A"})

    events = []
    async for event in _sse_stream(fake_generator()):
        events.append(event)

    assert len(events) == 2  # one data event + DONE
