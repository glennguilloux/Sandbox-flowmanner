"""
Base Tool Handler Interface
All tool handlers must implement this interface
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class BaseToolHandler(ABC):
    """
    Abstract base class for all tool handlers

    Responsibilities:
    - Validate tool parameters
    - Execute tool operations
    - Handle errors gracefully
    - Return standardized results
    """

    def __init__(self, tool_id: str, tool_name: str):
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.logger = logging.getLogger(f"{__name__}.{tool_id}")

    @abstractmethod
    async def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate tool parameters

        Args:
            parameters: Tool parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        pass

    @abstractmethod
    async def execute(self, parameters: dict[str, Any], context: dict[str, Any] = None) -> dict[str, Any]:
        """
        Execute the tool with given parameters

        Args:
            parameters: Tool parameters
            context: Execution context (user_id, session_id, etc.)

        Returns:
            Execution result dictionary
        """
        pass

    @abstractmethod
    def get_tool_schema(self) -> dict[str, Any]:
        """
        Get tool schema for validation and documentation

        Returns:
            JSON schema for the tool
        """
        pass

    async def safe_execute(self, parameters: dict[str, Any], context: dict[str, Any] = None) -> dict[str, Any]:
        """
        Execute tool with error handling and logging

        Args:
            parameters: Tool parameters
            context: Execution context

        Returns:
            Standardized result dictionary
        """
        try:
            # Validate parameters
            is_valid, error_msg = await self.validate_parameters(parameters)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Parameter validation failed: {error_msg}",
                    "tool_id": self.tool_id,
                    "tool_name": self.tool_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Execute tool
            self.logger.info(f"Executing {self.tool_name} with parameters: {parameters}")
            result = await self.execute(parameters, context)

            # Standardize result
            standardized_result = {
                "success": True,
                "tool_id": self.tool_id,
                "tool_name": self.tool_name,
                "result": result,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            self.logger.info(f"{self.tool_name} execution successful")
            return standardized_result

        except Exception as e:
            self.logger.error(f"{self.tool_name} execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "tool_id": self.tool_id,
                "tool_name": self.tool_name,
                "timestamp": datetime.now(UTC).isoformat(),
            }
