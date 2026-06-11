"""Tests for Phase 4: Playground sandbox creation, claiming, and cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.playground_models import PlaygroundSandbox, PlaygroundSandboxStatus

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_sandboxd_client():
    """Mock sandboxd client that returns fake sandbox IDs."""
    client = AsyncMock()
    client.create.return_value = {
        "id": "sandbox-test-001",
        "project_id": "playground-test-001",
        "status": "running",
    }
    client.get.return_value = {
        "id": "sandbox-test-001",
        "status": "running",
        "preview": {"url": "http://s-test-001-3000.preview.localhost:3000"},
    }
    client.delete.return_value = None
    client.health_check.return_value = {"status": "ok"}
    client.list_files.return_value = [
        {"name": "App.tsx", "path": "src/App.tsx", "type": "file", "size": 1024},
        {"name": "src", "path": "src", "type": "directory"},
    ]
    client.read_file.return_value = "console.log('hello');"
    return client


@pytest.fixture
def mock_db_session():
    """Mock async database session with execute/add/commit/refresh."""
    session = AsyncMock()
    # Make execute return a result with scalar_one_or_none returning None by default
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    execute_result.scalars.return_value.all.return_value = []
    session.execute.return_value = execute_result
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def sample_playground_sandbox():
    """A sample PlaygroundSandbox instance."""
    now = datetime.now(UTC)
    return PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000001",
        sandbox_id="sandbox-test-001",
        user_id=None,
        session_token="test-session-token-abc123",
        workspace_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        claimed_at=None,
        status=PlaygroundSandboxStatus.RUNNING.value,
        template="react-standard",
        project_id="playground-test-001",
        is_persistent=False,
        last_active_at=None,
        anonymous_ip="203.0.113.1",
    )


# ── PlaygroundService tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_anonymous_sandbox(mock_db_session, mock_sandboxd_client):
    """Anonymous sandbox creation returns session_token and TTL."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    # Mock db.add to capture the created object
    created_pg = None

    def capture_add(obj):
        nonlocal created_pg
        created_pg = obj

    mock_db_session.add.side_effect = capture_add

    # Mock refresh to set the id
    async def mock_refresh(obj):
        obj.id = "00000000-0000-0000-0000-000000000001"

    mock_db_session.refresh.side_effect = mock_refresh

    pg = await service.create_anonymous_sandbox(
        db=mock_db_session,
        client_ip="203.0.113.1",
    )

    assert created_pg is not None
    assert created_pg.sandbox_id == "sandbox-test-001"
    assert created_pg.session_token is not None
    assert len(created_pg.session_token) > 20
    assert created_pg.user_id is None
    assert created_pg.status == PlaygroundSandboxStatus.RUNNING.value
    assert created_pg.anonymous_ip == "203.0.113.1"
    assert created_pg.template == "python.img"

    # TTL should be ~30 minutes from now
    expected_expiry = datetime.now(UTC) + timedelta(minutes=30)
    assert abs((created_pg.expires_at - expected_expiry).total_seconds()) < 5

    mock_sandboxd_client.create.assert_called_once()
    mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_sandbox_calls_sandboxd(mock_db_session, mock_sandboxd_client):
    """Sandboxd client is called with correct parameters."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)
    mock_db_session.add = MagicMock()
    mock_db_session.refresh = AsyncMock()

    await service.create_anonymous_sandbox(
        db=mock_db_session,
        template="python",
        client_ip="10.0.0.1",
    )

    call_kwargs = mock_sandboxd_client.create.call_args
    assert call_kwargs.kwargs["user_id"] == "anonymous"
    assert call_kwargs.kwargs["template"] == "python"
    assert call_kwargs.kwargs["project_id"].startswith("playground-")


@pytest.mark.asyncio
async def test_claim_sandbox(sample_playground_sandbox, mock_db_session, mock_sandboxd_client):
    """Claiming transfers ownership and extends TTL to 24 hours."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    # Mock get_by_session_token to return our sample sandbox
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = sample_playground_sandbox
    mock_db_session.execute.return_value = execute_result

    claimed = await service.claim_sandbox(
        "test-session-token-abc123",
        42,
        db=mock_db_session,
    )

    assert claimed.user_id == 42
    assert claimed.status == PlaygroundSandboxStatus.CLAIMED.value
    assert claimed.is_persistent is True
    assert claimed.claimed_at is not None

    # TTL should be ~24 hours from now
    expected_expiry = datetime.now(UTC) + timedelta(hours=24)
    assert abs((claimed.expires_at - expected_expiry).total_seconds()) < 5


@pytest.mark.asyncio
async def test_claim_already_claimed_raises(mock_db_session, mock_sandboxd_client):
    """Claiming an already-claimed sandbox raises ValueError."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    # Create a claimed sandbox
    now = datetime.now(UTC)
    claimed_sandbox = PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000002",
        sandbox_id="sandbox-test-002",
        user_id=123,  # Already claimed
        session_token="test-session-token-claimed",
        workspace_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        claimed_at=now,
        status=PlaygroundSandboxStatus.CLAIMED.value,
        template="react-standard",
        project_id="playground-test-002",
        is_persistent=True,
        anonymous_ip=None,
    )

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = claimed_sandbox
    mock_db_session.execute.return_value = execute_result

    with pytest.raises(ValueError, match="already claimed"):
        await service.claim_sandbox("test-session-token-claimed", 456, db=mock_db_session)


@pytest.mark.asyncio
async def test_claim_not_found_raises(mock_db_session, mock_sandboxd_client):
    """Claiming a non-existent sandbox raises ValueError."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = execute_result

    with pytest.raises(ValueError, match="not found"):
        await service.claim_sandbox("nonexistent-token", 123, db=mock_db_session)


@pytest.mark.asyncio
async def test_purge_expired(mock_db_session, mock_sandboxd_client):
    """Purge removes sandboxes past their TTL."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    # Create an expired sandbox
    now = datetime.now(UTC)
    expired = PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000003",
        sandbox_id="sandbox-expired-001",
        user_id=None,
        session_token="expired-token",
        workspace_id=None,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
        expires_at=now - timedelta(minutes=1),  # Expired
        claimed_at=None,
        status=PlaygroundSandboxStatus.RUNNING.value,
        template="react-standard",
        project_id="playground-expired-001",
        is_persistent=False,
        anonymous_ip="192.168.1.1",
    )

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [expired]

    # First call returns expired list, second call returns the sandbox for purge_sandbox
    single_result = MagicMock()
    single_result.scalar_one_or_none.return_value = expired

    mock_db_session.execute.side_effect = [execute_result, single_result]

    count = await service.purge_expired(db=mock_db_session)
    assert count == 1

    mock_sandboxd_client.delete.assert_called_once_with("sandbox-expired-001")
    assert expired.status == PlaygroundSandboxStatus.PURGED.value


@pytest.mark.asyncio
async def test_count_recent_by_ip(mock_db_session, mock_sandboxd_client):
    """Rate-limit counting works correctly."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
    mock_db_session.execute.return_value = execute_result

    count = await service.count_recent_by_ip("10.0.0.1", minutes=60, db=mock_db_session)
    assert count == 2


@pytest.mark.asyncio
async def test_list_files(mock_db_session, mock_sandboxd_client, sample_playground_sandbox):
    """File listing delegates to sandboxd client."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = sample_playground_sandbox
    mock_db_session.execute.return_value = execute_result

    files = await service.list_files("sandbox-test-001", db=mock_db_session)
    assert len(files) == 2
    assert files[0]["name"] == "App.tsx"
    mock_sandboxd_client.list_files.assert_called_once_with("sandbox-test-001", path="")


@pytest.mark.asyncio
async def test_read_file(mock_db_session, mock_sandboxd_client, sample_playground_sandbox):
    """File reading delegates to sandboxd client."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = sample_playground_sandbox
    mock_db_session.execute.return_value = execute_result

    content = await service.read_file("sandbox-test-001", "src/App.tsx", db=mock_db_session)
    assert content == "console.log('hello');"
    mock_sandboxd_client.read_file.assert_called_once_with("sandbox-test-001", path="src/App.tsx")


@pytest.mark.asyncio
async def test_is_sandboxd_healthy(mock_sandboxd_client):
    """Health check returns True when sandboxd responds."""
    from app.services.playground_service import PlaygroundService

    service = PlaygroundService(client=mock_sandboxd_client)
    assert await service.is_sandboxd_healthy() is True


@pytest.mark.asyncio
async def test_is_sandboxd_healthy_unavailable(mock_sandboxd_client):
    """Health check returns False when sandboxd is unreachable."""
    from app.services.playground_service import PlaygroundService

    mock_sandboxd_client.health_check.side_effect = ConnectionError("refused")
    service = PlaygroundService(client=mock_sandboxd_client)
    assert await service.is_sandboxd_healthy() is False


# ── Model property tests ─────────────────────────────────────────────


def test_playground_sandbox_is_expired():
    """is_expired returns True when expires_at is in the past."""
    now = datetime.now(UTC)
    pg = PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000010",
        sandbox_id="sandbox-prop-test",
        user_id=None,
        session_token="prop-test-token",
        workspace_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now - timedelta(minutes=1),
        claimed_at=None,
        status=PlaygroundSandboxStatus.RUNNING.value,
        template="react-standard",
        project_id=None,
        is_persistent=False,
        anonymous_ip=None,
    )
    assert pg.is_expired is True


def test_playground_sandbox_is_not_expired():
    """is_expired returns False when expires_at is in the future."""
    now = datetime.now(UTC)
    pg = PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000011",
        sandbox_id="sandbox-prop-test-2",
        user_id=None,
        session_token="prop-test-token-2",
        workspace_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        claimed_at=None,
        status=PlaygroundSandboxStatus.RUNNING.value,
        template="react-standard",
        project_id=None,
        is_persistent=False,
        anonymous_ip=None,
    )
    assert pg.is_expired is False


def test_playground_sandbox_is_anonymous():
    """is_anonymous returns True when user_id is None."""
    now = datetime.now(UTC)
    pg = PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000012",
        sandbox_id="sandbox-anon-test",
        user_id=None,
        session_token="anon-test-token",
        workspace_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
        claimed_at=None,
        status=PlaygroundSandboxStatus.RUNNING.value,
        template="react-standard",
        project_id=None,
        is_persistent=False,
        anonymous_ip=None,
    )
    assert pg.is_anonymous is True


def test_playground_sandbox_is_not_anonymous():
    """is_anonymous returns False when user_id is set."""
    now = datetime.now(UTC)
    pg = PlaygroundSandbox(
        id="00000000-0000-0000-0000-000000000013",
        sandbox_id="sandbox-claimed-test",
        user_id=42,
        session_token="claimed-test-token",
        workspace_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        claimed_at=now,
        status=PlaygroundSandboxStatus.CLAIMED.value,
        template="react-standard",
        project_id=None,
        is_persistent=True,
        anonymous_ip=None,
    )
    assert pg.is_anonymous is False


# ── Workspace sandbox tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_workspace_sandbox(mock_db_session, mock_sandboxd_client):
    """Workspace sandbox creation uses workspace prefix and long TTL."""
    from app.services.sandbox_service import SandboxService

    service = SandboxService(client=mock_sandboxd_client)

    created_pg = None

    def capture_add(obj):
        nonlocal created_pg
        created_pg = obj

    mock_db_session.add.side_effect = capture_add

    sandbox_id = await service.create_workspace_sandbox(
        "ws-abc-123",
        "42",
        db=mock_db_session,
        template="node",
    )

    assert sandbox_id == "sandbox-test-001"
    assert created_pg is not None
    assert created_pg.is_persistent is True
    assert created_pg.user_id == 42
    assert created_pg.workspace_id == "ws-abc-123"
    assert created_pg.status == PlaygroundSandboxStatus.RUNNING.value

    # TTL should be ~30 days from now
    expected_expiry = datetime.now(UTC) + timedelta(days=30)
    assert abs((created_pg.expires_at - expected_expiry).total_seconds()) < 60


@pytest.mark.asyncio
async def test_get_workspace_sandboxes(mock_db_session, mock_sandboxd_client):
    """Listing workspace sandboxes filters by workspace_id."""
    from app.services.sandbox_service import SandboxService

    service = SandboxService(client=mock_sandboxd_client)

    now = datetime.now(UTC)
    mock_sandbox = MagicMock()
    mock_sandbox.sandbox_id = "sandbox-ws-001"
    mock_sandbox.status = PlaygroundSandboxStatus.RUNNING.value
    mock_sandbox.template = "react-standard"
    mock_sandbox.created_at = now
    mock_sandbox.last_active_at = now

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mock_sandbox]
    mock_db_session.execute.return_value = execute_result

    result = await service.get_workspace_sandboxes("ws-abc-123", db=mock_db_session)
    assert len(result) == 1
    assert result[0]["sandbox_id"] == "sandbox-ws-001"
    assert result[0]["status"] == "running"
