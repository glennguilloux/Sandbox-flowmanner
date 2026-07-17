"""Regression tests for BYOK key resolution in ModelRouter.

Two defects are covered here (verified 2026-07-17):

1. ``ModelRouter._get_byok_key`` previously called ``db_session.query(...)`` on
   an ``AsyncSession``. ``AsyncSession`` has no ``.query`` attribute, so the
   call raised ``AttributeError`` — which the broad ``except Exception``
   swallowed, returning ``None`` and silently billing the *platform* key
   instead of the user's stored BYOK key. The method is now async and uses
   ``select()``/``await``.

2. ``ModelRouter._execute_with_byok`` passed a user-supplied ``base_url``
   straight into the LLM client with no SSRF check. An attacker-controlled key
   could point the client at an internal/metadata endpoint. The base_url is now
   validated inline (mirroring ``app.api.v1.api_keys._is_safe_outbound_url``)
   and falls back to the provider default on rejection.

Real-DB integration tests. Each module creates its own async engine bound to
the current event loop (the conftest in this dir uses a module-scoped loop) so
we never share the process-global engine's connection pool across loops. Skip
when no live Postgres is reachable.

Run (from the backend dir of this worktree):
    DATABASE_URL='postgresql+asyncpg://flowmanner:...@localhost:5432/flowmanner' \
        .venv/bin/python -m pytest app/tests/test_byok_model_router.py -v
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.byok_models import UserAPIKey
from app.models.user import User
from app.services.model_router import ModelRouter, _is_safe_outbound_url
from app.utils.encryption import encrypt_api_key

pytestmark = pytest.mark.integration

_TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@localhost:5432/flowmanner",
)


@pytest.fixture
async def engine_and_session():
    """Create a function-local engine bound to the current test loop and ensure tables exist.

    Function scope (not module) is deliberate: it avoids the cross-loop
    "attached to a different loop" RuntimeError that arises from the deprecated
    module-scoped ``event_loop`` fixture in this dir's conftest when a single
    engine is shared across the async tests.
    """
    from app.models import Base

    eng = create_async_engine(_TEST_DB_URL, future=True, pool_pre_ping=True)
    async with eng.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    yield Session
    await eng.dispose()


def _uid() -> int:
    return 917_000_000 + (uuid.uuid4().int % 80_000_000)


async def _seed_user_and_key(Session, user_id: int, provider: str, models: list[str], base_url: str | None = None):
    async with Session() as s:
        user = User(
            id=user_id,
            email=f"byok-test-{uuid.uuid4().hex}@example.com",
            username=f"byoktest_{uuid.uuid4().hex}",
            hashed_password="x",
            role="free",
        )
        s.add(user)
        key = UserAPIKey(
            user_id=user_id,
            provider=provider,
            encrypted_key=encrypt_api_key("sk-test-byok-123"),
            is_active=True,
            base_url=base_url,
            models=json.dumps(models),
        )
        s.add(key)
        await s.commit()
        return key.id


async def _purge(Session, user_id: int):
    async with Session() as s:
        await s.execute(delete(UserAPIKey).where(UserAPIKey.user_id == user_id))
        await s.execute(delete(User).where(User.id == user_id))
        await s.commit()


@pytest.mark.asyncio
async def test_get_byok_key_returns_stored_key_on_match(engine_and_session):
    """A stored active key covering the model must be returned."""
    Session = engine_and_session
    router = ModelRouter()
    user_id = _uid()
    model = "openai/gpt-4o"
    key_id = await _seed_user_and_key(Session, user_id, "openai", [model])
    try:
        async with Session() as s:
            result = await router._get_byok_key(model, user_id, s)
        assert result is not None, "expected the stored BYOK key, got None (platform key would be billed)"
        assert isinstance(result, UserAPIKey)
        assert result.id == key_id
        assert result.provider == "openai"
        assert result.get_api_key() == "sk-test-byok-123"
    finally:
        await _purge(Session, user_id)


@pytest.mark.asyncio
async def test_get_byok_key_returns_none_on_model_mismatch(engine_and_session):
    """No active key covers the requested model -> None (falsy)."""
    Session = engine_and_session
    router = ModelRouter()
    user_id = _uid()
    await _seed_user_and_key(Session, user_id, "openai", ["openai/gpt-4o"])
    try:
        async with Session() as s:
            result = await router._get_byok_key("anthropic/claude-3-opus", user_id, s)
        assert result is None
    finally:
        await _purge(Session, user_id)


@pytest.mark.asyncio
async def test_get_byok_key_handles_byok_prefixed_model_id(engine_and_session):
    """The byok_{user}_{model} format must normalise to the original model id."""
    Session = engine_and_session
    router = ModelRouter()
    user_id = _uid()
    model = "deepseek/deepseek-chat"
    await _seed_user_and_key(Session, user_id, "deepseek", [model])
    try:
        async with Session() as s:
            result = await router._get_byok_key(f"byok_{user_id}_{model}", user_id, s)
        assert result is not None
        assert result.provider == "deepseek"
    finally:
        await _purge(Session, user_id)


@pytest.mark.asyncio
async def test_get_byok_key_uses_async_select_not_sync_query(engine_and_session):
    """Regression guard: the method must run on an AsyncSession via select()/await.

    Under the old sync impl this ``await`` would raise AttributeError
    (AsyncSession has no .query) before the broad except could swallow it.
    """
    Session = engine_and_session
    router = ModelRouter()
    user_id = _uid()
    await _seed_user_and_key(Session, user_id, "openai", ["openai/gpt-4o"])
    try:
        async with Session() as s:
            result = await router._get_byok_key("openai/gpt-4o", user_id, s)
        assert result is not None
    finally:
        await _purge(Session, user_id)


# ── SSRF validation (mirrors api_keys._is_safe_outbound_url contract) ────────


def test_is_safe_outbound_url_rejects_internal_ip():
    ok, err = _is_safe_outbound_url("http://127.0.0.1:11434/v1")
    assert ok is False and err


def test_is_safe_outbound_url_rejects_cloud_metadata():
    ok, err = _is_safe_outbound_url("https://169.254.169.254/latest/meta-data/")
    assert ok is False and err


def test_is_safe_outbound_url_rejects_non_http_scheme():
    ok, err = _is_safe_outbound_url("file:///etc/passwd")
    assert ok is False and "http" in err.lower()


def test_is_safe_outbound_url_rejects_private_hostname():
    ok, err = _is_safe_outbound_url("http://localhost:8080/v1")
    assert ok is False and err


def test_is_safe_outbound_url_allows_public_https():
    # A public hostname must pass the scheme/host pre-checks (DNS resolution is
    # performed at runtime and may be network-dependent in CI).
    ok, err = _is_safe_outbound_url("https://api.openai.com/v1")
    if not ok:
        assert "scheme" not in (err or "").lower()
        assert "blocked" not in (err or "").lower()


@pytest.mark.asyncio
async def test_execute_with_byok_rejects_unsafe_base_url_with_provider_default():
    """`_execute_with_byok` must not hand an internal base_url to the LLM client.

    When the user-supplied base_url fails the SSRF check, the method must fall
    back to the provider default before calling ``get_model_with_user_key``.
    """
    router = ModelRouter()
    captured = {}

    class _FakeLLM:
        async def ainvoke(self, messages, **kwargs):  # pragma: no cover - stub
            return type("R", (), {"content": "ok"})()

    class _FakeManager:
        def get_model_with_user_key(self, *, model_id, api_key, base_url):
            captured["base_url"] = base_url
            return _FakeLLM()

    router.llm_manager = _FakeManager()

    result = await router._execute_with_byok(
        messages=[{"role": "user", "content": "hi"}],
        model_id="openai/gpt-4o",
        api_key="sk-test",
        base_url="http://169.254.169.254:11434/v1",  # cloud metadata IP
        user_id="123",
    )
    assert result["success"] is True
    # The dangerous base_url must NOT have reached the client; the provider
    # default (openai) must have been substituted instead.
    assert captured["base_url"] == "https://api.openai.com/v1"
