"""Browser tool execution — extracted from MissionExecutor.

Dispatches browser automation tasks (navigate, click, type, scroll,
screenshot, snapshot, close) to the registered tool implementations.

Usage::

    runner = BrowserTaskRunner()
    result = await runner.execute_browser_tool(task, {"url": "https://..."})
"""

import logging
from typing import Any

from app.services.mission_errors import PermanentMissionError, RetryableMissionError

logger = logging.getLogger(__name__)

BROWSER_TASK_TYPES = [
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_scroll",
    "browser_screenshot",
    "browser_close",
]


def _import_browser_tools():
    """Lazy import to avoid circular dependencies.

    Returns:
        tuple: (ToolRegistry, BrowserNavigateInput, BrowserSnapshotInput,
        BrowserClickInput, BrowserTypeInput, BrowserScrollInput).

    Raises:
        ImportError: If any tool module is not available at runtime.
    """
    from app.tools.base import ToolRegistry
    from app.tools.browser_click import BrowserClickInput
    from app.tools.browser_navigate import BrowserNavigateInput
    from app.tools.browser_scroll import BrowserScrollInput
    from app.tools.browser_snapshot import BrowserSnapshotInput
    from app.tools.browser_type import BrowserTypeInput

    return (
        ToolRegistry,
        BrowserNavigateInput,
        BrowserSnapshotInput,
        BrowserClickInput,
        BrowserTypeInput,
        BrowserScrollInput,
    )


class BrowserTaskRunner:
    """Executes browser-based tasks (navigate, click, type, scroll, etc.).

    All tool classes are loaded lazily via :func:`_import_browser_tools` to
    avoid circular imports at module-load time.

    Example:
        >>> runner = BrowserTaskRunner()
        >>> result = await runner.execute_browser_tool(
        ...     task, {"url": "https://example.com"}, mission=mission
        ... )
        >>> assert result["success"] is True
    """

    async def execute_browser_tool(self, task, input_data: dict[str, Any], mission=None) -> dict[str, Any]:
        """Execute a browser tool for the given task.

        The tool is selected by ``task.task_type``, which must be one of the
        values in :data:`BROWSER_TASK_TYPES`.

        Args:
            task: Task-like object with ``.task_type`` (str) and ``.id``.
            input_data: Tool-specific input (``url`` for navigate, ``ref``
                for click, ``ref``/``text``/``submit`` for type, ``x``/``y``
                for scroll).
            mission: Optional mission object providing ``.user_id`` for the
                browser context.  Defaults to ``"system"`` when ``None``.

        Returns:
            Dict with:
                - ``success`` (bool)
                - ``output`` (Any) — tool result data on success
                - ``error`` (str) — error message on failure
                - ``permanent`` (bool, optional) — ``True`` for
                  non-retryable errors

        Raises:
            RetryableMissionError: Re-raised from the tool layer; caller
                should retry with back-off.
        """
        (
            ToolRegistry,
            BrowserNavigateInput,
            BrowserSnapshotInput,
            BrowserClickInput,
            BrowserTypeInput,
            BrowserScrollInput,
        ) = _import_browser_tools()

        tool_name = task.task_type
        tool = ToolRegistry.get(tool_name)

        if tool is None:
            return {
                "success": False,
                "error": f"Browser tool not registered: {tool_name}",
            }

        user_id = str(mission.user_id) if mission and mission.user_id else "system"
        context = {"user_id": user_id}

        try:
            tool_input = {}
            if tool_name == "browser_navigate":
                tool_input = {"url": input_data.get("url", "")}
            elif tool_name == "browser_click":
                tool_input = {"ref": input_data.get("ref", "")}
            elif tool_name == "browser_type":
                tool_input = {
                    "ref": input_data.get("ref", ""),
                    "text": input_data.get("text", ""),
                    "submit": input_data.get("submit", False),
                }
            elif tool_name == "browser_scroll":
                tool_input = {
                    "x": input_data.get("x", 0),
                    "y": input_data.get("y", 300),
                }

            result = await tool.run(tool_input, context)

            if result.status.value == "success":
                return {"success": True, "output": result.data}
            else:
                return {"success": False, "error": result.error}

        except RetryableMissionError as e:
            logger.warning("Retryable browser error in task %s: %s", task.id, e)
            raise
        except PermanentMissionError as e:
            logger.error("Permanent browser error in task %s: %s", task.id, e)
            return {"success": False, "error": str(e), "permanent": True}
        except Exception as e:
            logger.error("Browser tool %s failed: %s", tool_name, e)
            return {"success": False, "error": str(e)}
