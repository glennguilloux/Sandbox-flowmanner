"""Regression tests for BYOK SSRF in chat_service.py.

Any authenticated user could previously store a ``base_url`` pointing at the
cloud metadata service (http://169.254.169.254/) or an internal service
(http://localhost:<port>) and have the backend issue the outbound request with
their own Authorization header. These tests assert that a stored BYOK
``base_url`` is SSRF-validated BEFORE it is handed to AsyncOpenAI, and that an
unsafe URL is dropped in favour of the platform default (fail-closed, safe
default). They also assert a normal public https base_url is accepted.

NO live network: socket.getaddrinfo is monkeypatched, and literal-IP URLs need
no resolution.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.chat_service as cs

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# --- Direct unit tests of the SSRF guard helper (no DB, no net) ---


@pytest.mark.asyncio
async def test_helper_rejects_metadata_ip():
    """Link-local 169.254.169.254 must be rejected (literal IP, no DNS)."""
    out = await cs._safe_effective_base_url("http://169.254.169.254/latest/meta-data", "https://api.openai.com/v1")
    assert out == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_helper_rejects_loopback_ip():
    """Loopback 127.0.0.1 must be rejected (literal IP, no DNS)."""
    out = await cs._safe_effective_base_url("http://127.0.0.1:5432/v1", "https://api.openai.com/v1")
    assert out == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_helper_rejects_rfc1918_ip():
    """Private RFC1918 (10.x) must be rejected (literal IP, no DNS)."""
    out = await cs._safe_effective_base_url("http://10.0.0.1:8080/v1", "https://api.openai.com/v1")
    assert out == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_helper_rejects_bad_scheme():
    """Non-http(s) scheme must be rejected."""
    out = await cs._safe_effective_base_url("file:///etc/passwd", "https://api.openai.com/v1")
    assert out == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_helper_accepts_public_https_literal():
    """A literal public IP over https is accepted (no DNS)."""
    out = await cs._safe_effective_base_url("https://8.8.8.8/v1", "https://api.openai.com/v1")
    assert out == "https://8.8.8.8/v1"


@pytest.mark.asyncio
async def test_helper_rejects_hostname_resolving_to_loopback(monkeypatch):
    """A hostname whose DNS points at loopback must be rejected (DNS-rebinding)."""
    monkeypatch.setattr(
        "app.services.chat_service.socket.getaddrinfo",
        lambda host, port: [(None, None, None, None, ("127.0.0.1", 0))],
    )
    out = await cs._safe_effective_base_url("https://internal.example/v1", "https://api.openai.com/v1")
    assert out == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_helper_accepts_hostname_resolving_to_public(monkeypatch):
    """A hostname whose DNS points at a public IP is accepted."""
    monkeypatch.setattr(
        "app.services.chat_service.socket.getaddrinfo",
        lambda host, port: [(None, None, None, None, ("1.2.3.4", 0))],
    )
    out = await cs._safe_effective_base_url("https://my.valid-proxy.example/v1", "https://api.openai.com/v1")
    assert out == "https://my.valid-proxy.example/v1"


@pytest.mark.asyncio
async def test_helper_returns_default_when_none():
    """No custom base_url -> platform default is used unchanged."""
    out = await cs._safe_effective_base_url(None, "https://api.openai.com/v1")
    assert out == "https://api.openai.com/v1"


# --- End-to-end: the AsyncOpenAI client must NOT receive an unsafe base_url ---
#
# These run WITHOUT any live service (Redis/DB net): the prompt/usage Redis
# paths are mocked, the LLM client is mocked, and only the SSRF decision at the
# client-build site is exercised.


def _fake_response():
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None))]
    resp.usage = MagicMock(total_tokens=5, prompt_tokens=2, completion_tokens=3)
    return resp


@pytest.mark.asyncio
async def test_send_message_drops_unsafe_metadata_base_url(monkeypatch):
    """send_message_to_llm must NOT pass a metadata-IP base_url to AsyncOpenAI."""
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 1
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg)))

    fake_resp = _fake_response()
    captured = {}

    def _record_init(api_key=None, base_url=None, **kwargs):
        captured["base_url"] = base_url
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=fake_resp)
        return client

    with (
        patch("app.services.chat_service.AsyncOpenAI", side_effect=_record_init),
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
        patch("app.services.chat_service.create_chat_message_fresh_session", new_callable=AsyncMock),
        patch("app.services.chat_service._build_chat_messages", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_chat_openai_tools", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_prompt_redis", new=AsyncMock(return_value=None)),
        patch("app.services.usage_service.get_usage_service", return_value=MagicMock(record_usage=MagicMock())),
        patch("app.tasks.memory_extraction_tasks.extract_memory_claims_task") as mock_mt,
    ):
        mock_msg.return_value = MagicMock(id=1)
        result = await cs.send_message_to_llm(
            db=db,
            thread_id=1,
            content="hi",
            user_id=7,
            user_api_key="sk-byok-test",
            user_base_url="http://169.254.169.254/latest/meta-data",
            model_id="gpt-4o",
        )

    assert result["success"] is True
    # The malicious base_url must NOT have reached the client.
    assert captured["base_url"] != "http://169.254.169.254/latest/meta-data"
    # Fail-safe: platform default base_url used instead.
    assert captured["base_url"] == cs._LLM_API_BASE


@pytest.mark.asyncio
async def test_send_message_drops_unsafe_loopback_base_url(monkeypatch):
    """send_message_to_llm must NOT pass a localhost base_url to AsyncOpenAI."""
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 1
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg)))

    fake_resp = _fake_response()
    captured = {}

    def _record_init(api_key=None, base_url=None, **kwargs):
        captured["base_url"] = base_url
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=fake_resp)
        return client

    with (
        patch("app.services.chat_service.AsyncOpenAI", side_effect=_record_init),
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
        patch("app.services.chat_service.create_chat_message_fresh_session", new_callable=AsyncMock),
        patch("app.services.chat_service._build_chat_messages", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_chat_openai_tools", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_prompt_redis", new=AsyncMock(return_value=None)),
        patch("app.services.usage_service.get_usage_service", return_value=MagicMock(record_usage=MagicMock())),
        patch("app.tasks.memory_extraction_tasks.extract_memory_claims_task") as mock_mt,
    ):
        mock_msg.return_value = MagicMock(id=1)
        result = await cs.send_message_to_llm(
            db=db,
            thread_id=1,
            content="hi",
            user_id=7,
            user_api_key="sk-byok-test",
            user_base_url="http://localhost:5432/v1",
            model_id="gpt-4o",
        )

    assert result["success"] is True
    assert captured["base_url"] != "http://localhost:5432/v1"
    assert captured["base_url"] == cs._LLM_API_BASE


@pytest.mark.asyncio
async def test_send_message_accepts_public_https_base_url(monkeypatch):
    """A normal public https base_url IS passed through to AsyncOpenAI."""
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 1
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg)))

    fake_resp = _fake_response()
    captured = {}

    def _record_init(api_key=None, base_url=None, **kwargs):
        captured["base_url"] = base_url
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=fake_resp)
        return client

    with (
        patch("app.services.chat_service.AsyncOpenAI", side_effect=_record_init),
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
        patch("app.services.chat_service.create_chat_message_fresh_session", new_callable=AsyncMock),
        patch("app.services.chat_service._build_chat_messages", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_chat_openai_tools", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_prompt_redis", new=AsyncMock(return_value=None)),
        patch("app.services.usage_service.get_usage_service", return_value=MagicMock(record_usage=MagicMock())),
        patch("app.tasks.memory_extraction_tasks.extract_memory_claims_task") as mock_mt,
    ):
        mock_msg.return_value = MagicMock(id=1)
        result = await cs.send_message_to_llm(
            db=db,
            thread_id=1,
            content="hi",
            user_id=7,
            user_api_key="sk-byok-test",
            user_base_url="https://8.8.8.8/v1",
            model_id="gpt-4o",
        )

    assert result["success"] is True
    assert captured["base_url"] == "https://8.8.8.8/v1"


@pytest.mark.asyncio
async def test_stream_message_drops_unsafe_metadata_base_url(monkeypatch):
    """stream_message_to_llm must NOT pass a metadata-IP base_url to AsyncOpenAI."""
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 1
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg)))

    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]

    captured = {}

    def _record_init(api_key=None, base_url=None, **kwargs):
        captured["base_url"] = base_url
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=MagicMock(__aiter__=lambda: iter([chunk])))
        return client

    with (
        patch("app.services.chat_service.AsyncOpenAI", side_effect=_record_init),
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
        patch("app.services.chat_service._build_chat_messages", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_chat_openai_tools", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._get_prompt_redis", new=AsyncMock(return_value=None)),
        patch("app.services.usage_service.get_usage_service", return_value=MagicMock(record_usage=MagicMock())),
        patch("app.tasks.memory_extraction_tasks.extract_memory_claims_task") as mock_mt,
    ):
        mock_msg.return_value = MagicMock(id=1)
        async for _ in cs.stream_message_to_llm(
            db=db,
            thread_id=1,
            content="hi",
            user_id=7,
            user_api_key="sk-byok-test",
            user_base_url="http://169.254.169.254/latest/meta-data",
            model_id="gpt-4o",
        ):
            pass

    assert captured["base_url"] != "http://169.254.169.254/latest/meta-data"
    assert captured["base_url"] == cs._LLM_API_BASE
