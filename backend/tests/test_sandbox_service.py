"""Unit tests for SandboxService — mission-scoped sandbox lifecycle."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestEnsureSandboxForMission:
    """create_for_mission — idempotent sandbox creation."""

    @pytest.mark.asyncio
    async def test_creates_sandbox_and_stores_mapping(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.create = AsyncMock(return_value={"id": "sb-new", "status": "starting"})
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
        )

        svc = SandboxService(client=mock_client)
        sandbox_id = await svc.ensure_sandbox_for_mission(str(uuid4()), "user-1", db=mock_db)

        assert sandbox_id == "sb-new"
        mock_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_sandbox_if_already_created(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_db = AsyncMock()
        # Simulate existing mapping
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-existing"
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))
            )
        )

        svc = SandboxService(client=mock_client)
        sandbox_id = await svc.ensure_sandbox_for_mission(str(uuid4()), "user-1", db=mock_db)

        assert sandbox_id == "sb-existing"
        mock_client.create.assert_not_called()


class TestReapSandbox:
    """reap_sandbox — soft-stop on mission terminal state."""

    @pytest.mark.asyncio
    async def test_stops_sandbox_preserving_workspace(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.stop = AsyncMock(return_value={"status": "stopped"})
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))
            )
        )

        svc = SandboxService(client=mock_client)
        await svc.reap_sandbox(str(uuid4()), db=mock_db)

        mock_client.stop.assert_called_once_with("sb-abc")

    @pytest.mark.asyncio
    async def test_noop_when_no_sandbox_exists(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.stop = AsyncMock()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
        )

        svc = SandboxService(client=mock_client)
        await svc.reap_sandbox(str(uuid4()), db=mock_db)

        mock_client.stop.assert_not_called()


class TestPurgeSandbox:
    """purge_sandbox — full destroy."""

    @pytest.mark.asyncio
    async def test_deletes_sandbox_and_clears_mapping(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.delete = AsyncMock(return_value=None)
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))
            )
        )

        svc = SandboxService(client=mock_client)
        await svc.purge_sandbox(str(uuid4()), db=mock_db)

        mock_client.delete.assert_called_once_with("sb-abc")


class TestSandboxServiceSnapshots:
    """Snapshot operations via SandboxService."""

    @pytest.mark.asyncio
    async def test_create_snapshot_delegates_to_client(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.create_snapshot = AsyncMock(return_value={"id": "snap-1"})
        mock_db = AsyncMock()
        existing_row = MagicMock()
        existing_row.sandbox_id = "sb-abc"
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_row)))
            )
        )

        svc = SandboxService(client=mock_client)
        result = await svc.create_snapshot(str(uuid4()), "checkpoint", db=mock_db)

        assert result["id"] == "snap-1"
        mock_client.create_snapshot.assert_called_once_with("sb-abc", "checkpoint")


class TestSandboxServiceHealth:
    """Health check delegation."""

    @pytest.mark.asyncio
    async def test_is_sandboxd_healthy_true(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value={"status": "ok"})

        svc = SandboxService(client=mock_client)
        assert await svc.is_sandboxd_healthy() is True

    @pytest.mark.asyncio
    async def test_is_sandboxd_healthy_false_on_error(self):
        from app.services.sandbox_service import SandboxService

        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(side_effect=Exception("connection refused"))

        svc = SandboxService(client=mock_client)
        assert await svc.is_sandboxd_healthy() is False
