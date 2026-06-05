"""
Unified Chain Executor - Real execution for tool chains

Replaces the placeholder chain execution with actual tool execution
using the UnifiedToolBridge.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import ToolChain, ToolChainExecution
from app.services.unified_tools import (
    UnifiedToolBridge,
    get_unified_bridge,
)

logger = logging.getLogger(__name__)


class ChainExecutionError(Exception):
    """Error during chain execution"""

    def __init__(self, message: str, step: int = None, tool_id: str = None):
        self.message = message
        self.step = step
        self.tool_id = tool_id
        super().__init__(message)


class UnifiedChainExecutor:
    """
    Executes tool chains using the UnifiedToolBridge.

    Features:
    - Sequential and parallel step execution
    - Context passing between steps
    - Error handling with rollback
    - Progress tracking
    - Analytics recording
    """

    def __init__(self, db: Session, bridge: UnifiedToolBridge = None):
        self.db = db
        self.bridge = bridge or get_unified_bridge(db)

    async def execute_chain(
        self,
        chain_id: uuid.UUID,
        input_data: dict[str, Any],
        user_id: int | None = None,
        session_id: str | None = None,
        execution_mode: str = "sequential",
    ) -> dict[str, Any]:
        """
        Execute a tool chain.

        Args:
            chain_id: UUID of the chain to execute
            input_data: Input data for the chain
            user_id: User executing the chain
            session_id: Session context
            execution_mode: "sequential" or "parallel"

        Returns:
            Execution result with outputs from each step
        """
        # Load chain from database
        chain = self.db.query(ToolChain).filter(ToolChain.id == chain_id).first()
        if not chain:
            raise ChainExecutionError(f"Chain not found: {chain_id}")

        steps = chain.steps or []
        if not steps:
            raise ChainExecutionError(f"Chain has no steps: {chain_id}")

        # Create execution record
        execution = ToolChainExecution(
            id=uuid.uuid4(),
            chain_id=chain_id,
            user_id=user_id,
            status="running",
            current_step=0,
            total_steps=len(steps),
            input_data=input_data,
            started_at=datetime.now(UTC),
        )
        self.db.add(execution)
        self.db.commit()

        try:
            # Execute steps
            if execution_mode == "parallel":
                result = await self._execute_parallel(
                    steps, input_data, user_id, session_id, execution
                )
            else:
                result = await self._execute_sequential(
                    steps, input_data, user_id, session_id, execution
                )

            # Mark completed
            execution.status = "completed"
            execution.output_data = result
            execution.completed_at = datetime.now(UTC)

        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.now(UTC)
            logger.error(f"Chain execution failed: {e}")
            raise

        finally:
            # Update chain usage
            chain.usage_count = (chain.usage_count or 0) + 1
            self.db.commit()
            self.db.refresh(execution)

        return {
            "execution_id": str(execution.id),
            "status": execution.status,
            "output_data": execution.output_data,
            "total_time_ms": execution.total_time_ms or 0,
            "step_outputs": execution.step_outputs or [],
        }

    async def _execute_sequential(
        self,
        steps: list[dict[str, Any]],
        input_data: dict[str, Any],
        user_id: int | None,
        session_id: str | None,
        execution: ToolChainExecution,
    ) -> dict[str, Any]:
        """Execute steps sequentially, passing context between steps."""
        context = input_data.copy()
        step_outputs = []
        total_time = 0

        for i, step in enumerate(steps):
            execution.current_step = i
            self.db.commit()

            tool_id = step.get("tool_id") or step.get("tool")
            params = self._resolve_params(step.get("params", {}), context)

            logger.info(f"Executing step {i+1}/{len(steps)}: {tool_id}")

            result = await self.bridge.execute_tool(
                tool_id=tool_id,
                params=params,
                user_id=str(user_id) if user_id else None,
                session_id=session_id,
            )

            step_output = {
                "step": i,
                "tool_id": tool_id,
                "success": result.success,
                "result": result.result,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
            }
            step_outputs.append(step_output)
            total_time += result.execution_time_ms

            if not result.success:
                raise ChainExecutionError(
                    f"Step {i+1} failed: {result.error}", step=i, tool_id=tool_id
                )

            # Update context with step output for next steps
            if result.result:
                output_key = step.get("output_key", f"step_{i}_output")
                context[output_key] = result.result

        execution.step_outputs = step_outputs
        execution.total_time_ms = int(total_time)

        return context

    async def _execute_parallel(
        self,
        steps: list[dict[str, Any]],
        input_data: dict[str, Any],
        user_id: int | None,
        session_id: str | None,
        execution: ToolChainExecution,
    ) -> dict[str, Any]:
        """Execute steps in parallel."""
        tasks = []

        for i, step in enumerate(steps):
            tool_id = step.get("tool_id") or step.get("tool")
            params = self._resolve_params(step.get("params", {}), input_data)

            tasks.append(
                self.bridge.execute_tool(
                    tool_id=tool_id,
                    params=params,
                    user_id=str(user_id) if user_id else None,
                    session_id=session_id,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        step_outputs = []
        total_time = 0
        output = {}

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                step_outputs.append(
                    {
                        "step": i,
                        "tool_id": steps[i].get("tool_id"),
                        "success": False,
                        "error": str(result),
                    }
                )
            else:
                step_outputs.append(
                    {
                        "step": i,
                        "tool_id": steps[i].get("tool_id"),
                        "success": result.success,
                        "result": result.result,
                        "error": result.error,
                        "execution_time_ms": result.execution_time_ms,
                    }
                )
                total_time += result.execution_time_ms

                if result.success and result.result:
                    output_key = steps[i].get("output_key", f"step_{i}_output")
                    output[output_key] = result.result

        execution.step_outputs = step_outputs
        execution.total_time_ms = int(total_time)

        # Check for failures
        failures = [o for o in step_outputs if not o.get("success")]
        if failures:
            raise ChainExecutionError(
                f"{len(failures)} steps failed in parallel execution"
            )

        return output

    def _resolve_params(
        self, params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve parameter references from context."""
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                # Reference to context variable
                ref_key = value[1:]
                resolved[key] = context.get(ref_key, value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, context)
            else:
                resolved[key] = value

        return resolved


def get_chain_executor(db: Session) -> UnifiedChainExecutor:
    """Factory function for chain executor."""
    return UnifiedChainExecutor(db)
