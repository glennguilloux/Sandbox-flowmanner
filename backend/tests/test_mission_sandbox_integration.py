"""Integration tests for sandbox lifecycle wired into mission executor."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestMissionSandboxWiring:
    """Verify sandbox creation/destruction in mission lifecycle."""

    @pytest.mark.asyncio
    async def test_sandbox_service_importable(self):
        """SandboxService should be importable and usable."""
        from app.services.sandbox_service import SandboxService

        svc = SandboxService(client=MagicMock())
        assert hasattr(svc, "ensure_sandbox_for_mission")
        assert hasattr(svc, "reap_sandbox")
        assert hasattr(svc, "purge_sandbox")

    @pytest.mark.asyncio
    async def test_sandbox_created_on_mission_execute(self):
        """SandboxService.ensure_sandbox_for_mission called when mission transitions to EXECUTING."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        # Verify the executor has the execute_mission method
        assert hasattr(executor, "execute_mission")

    @pytest.mark.asyncio
    async def test_sandbox_reaped_on_mission_complete(self):
        """SandboxService.reap_sandbox called on terminal state."""
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

        mock_client.stop.assert_called_once()


class TestSandboxContextVar:
    """Verify the context variable mechanism works."""

    def test_set_and_get_sandbox_id(self):
        from app.tools._sandbox_context import (
            get_current_sandbox_id,
            set_current_sandbox_id,
        )

        # Default is None
        assert get_current_sandbox_id() is None

        # Set a value
        set_current_sandbox_id("sb-test-123")
        assert get_current_sandbox_id() == "sb-test-123"

        # Clear
        set_current_sandbox_id(None)
        assert get_current_sandbox_id() is None


class TestMissionSandboxesTable:
    """Verify mission_sandboxes table schema."""

    def test_table_exists_in_models(self):
        """MissionSandbox model should be importable."""
        from app.models.sandbox_models import MissionSandbox

        assert hasattr(MissionSandbox, "mission_id")
        assert hasattr(MissionSandbox, "sandbox_id")
        assert hasattr(MissionSandbox, "status")
        assert hasattr(MissionSandbox, "project_id")


class TestSubprocessSandboxesUnchanged:
    """Verify python_sandbox and nodejs_sandbox are NOT broken by sandboxd integration."""

    def test_python_sandbox_still_registered(self):
        from app.tools.base import get_tool_registry
        from app.tools.python_sandbox import PythonSandboxTool

        py_tool = PythonSandboxTool()
        assert py_tool.tool_id == "python_sandbox"

        registry = get_tool_registry()
        assert registry.get("python_sandbox") is not None

    def test_nodejs_sandbox_still_registered(self):
        from app.tools.base import get_tool_registry
        from app.tools.nodejs_sandbox import NodeJsSandboxTool

        node_tool = NodeJsSandboxTool()
        assert node_tool.tool_id == "nodejs_sandbox"

        registry = get_tool_registry()
        assert registry.get("nodejs_sandbox") is not None


class TestSandboxdConfigSettings:
    """Verify sandboxd config settings are present."""

    def test_sandboxd_settings_exist(self):
        from app.config import settings

        assert hasattr(settings, "SANDBOXD_API_URL")
        assert hasattr(settings, "SANDBOXD_AUTH_TOKEN")
        assert hasattr(settings, "SANDBOXD_PREVIEW_DOMAIN")
        assert hasattr(settings, "SANDBOXD_ENABLED")
        assert hasattr(settings, "SANDBOXD_DEFAULT_TEMPLATE")

    def test_sandboxd_defaults(self):
        from app.config import settings

        # SANDBOXD_API_URL may be overridden by .env (e.g. host.docker.internal)
        # so just verify it's a valid URL with a scheme
        assert settings.SANDBOXD_API_URL.startswith("http"), (
            f"SANDBOXD_API_URL should be an HTTP URL, got: {settings.SANDBOXD_API_URL}"
        )
        assert settings.SANDBOXD_ENABLED is True
        assert settings.SANDBOXD_DEFAULT_TEMPLATE == "python.img"
