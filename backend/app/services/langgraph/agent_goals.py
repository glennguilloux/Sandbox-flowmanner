#!/usr/bin/env python3
"""
Agent Goals System - B4 Agent Autonomy Framework

Implements autonomous goal pursuit:
- Multi-step objectives
- Self-planning and execution
- Tool selection and evaluation
- Human-in-the-loop approval
- Progress tracking and adaptation
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GoalStatus(Enum):
    """Status of a goal"""

    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    """Status of a goal step"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GoalStep:
    """A single step in a goal plan"""

    step_id: str
    description: str
    tool_id: str | None = None
    tool_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_outcome: str | None = None
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    requires_approval: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "expected_outcome": self.expected_outcome,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "requires_approval": self.requires_approval,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
        }


@dataclass
class AgentGoal:
    """A multi-step objective for an agent"""

    goal_id: str
    title: str
    description: str
    user_id: int
    session_id: str
    status: GoalStatus = GoalStatus.PENDING
    steps: list[GoalStep] = field(default_factory=list)
    current_step_index: int = 0
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    result_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "title": self.title,
            "description": self.description,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "result_summary": self.result_summary,
        }

    @property
    def current_step(self) -> GoalStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return completed / len(self.steps)


class GoalPlanner:
    """
    Plans goal execution by decomposing objectives into steps
    """

    def __init__(self, llm=None, tool_registry=None):
        self.llm = llm
        self.tool_registry = tool_registry
        self.logger = logging.getLogger(__name__)

    async def plan_goal(self, goal: AgentGoal, available_tools: list[dict[str, Any]] = None) -> list[GoalStep]:
        """
        Generate a plan of steps to achieve the goal

        Args:
            goal: The goal to plan
            available_tools: List of available tool schemas

        Returns:
            List of GoalStep objects
        """
        if not self.llm:
            self.logger.warning("No LLM available for planning, using default plan")
            return self._create_default_plan(goal)

        # Build planning prompt
        tools_description = ""
        if available_tools:
            tools_description = "\nAvailable tools:\n"
            for tool in available_tools:
                tools_description += f"- {tool.get('tool_id')}: {tool.get('description', 'No description')}\n"

        planning_prompt = f"""You are a goal planner. Break down the following objective into executable steps.

Goal: {goal.title}
Description: {goal.description}
Context: {json.dumps(goal.context, default=str)}
{tools_description}

Create a plan with 1-5 steps. For each step, provide:
1. A clear description
2. The tool to use (if applicable)
3. Expected parameters
4. Expected outcome
5. Whether it requires human approval (true for destructive/external actions)

Respond in JSON format:
{{
  "steps": [
    {{
      "description": "...",
      "tool_id": "...",
      "parameters": {{}},
      "expected_outcome": "...",
      "requires_approval": true/false
    }}
  ]
}}
"""

        try:
            # Call LLM for planning
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(planning_prompt)
            else:
                response = self.llm.invoke(planning_prompt)

            # Parse response
            response_text = response.content if hasattr(response, "content") else str(response)

            # Extract JSON from response
            plan_data = self._extract_json(response_text)

            if plan_data and "steps" in plan_data:
                steps = []
                for i, step_data in enumerate(plan_data["steps"]):
                    step = GoalStep(
                        step_id=f"{goal.goal_id}_step_{i}",
                        description=step_data.get("description", ""),
                        tool_id=step_data.get("tool_id"),
                        tool_name=step_data.get("tool_id"),
                        parameters=step_data.get("parameters", {}),
                        expected_outcome=step_data.get("expected_outcome"),
                        requires_approval=step_data.get("requires_approval", True),
                    )
                    steps.append(step)

                self.logger.info(f"Generated {len(steps)} steps for goal {goal.goal_id}")
                return steps

        except Exception as e:
            self.logger.error(f"Error planning goal: {e}")

        return self._create_default_plan(goal)

    def _create_default_plan(self, goal: AgentGoal) -> list[GoalStep]:
        """Create a simple default plan"""
        return [
            GoalStep(
                step_id=f"{goal.goal_id}_step_0",
                description=f"Analyze and execute: {goal.description}",
                requires_approval=True,
            )
        ]

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from text"""
        import re

        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return None


class GoalExecutor:
    """
    Executes goal steps with tool handlers and approval workflow
    """

    def __init__(self, tool_registry=None, approval_workflow=None, persistence=None):
        self.tool_registry = tool_registry
        self.approval_workflow = approval_workflow
        self.persistence = persistence
        self.logger = logging.getLogger(__name__)

    async def execute_step(
        self, goal: AgentGoal, step: GoalStep, user_context: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        Execute a single goal step

        Args:
            goal: The parent goal
            step: The step to execute
            user_context: User context for permissions

        Returns:
            Execution result
        """
        self.logger.info(f"Executing step {step.step_id}: {step.description}")

        # Update step status
        step.status = StepStatus.IN_PROGRESS
        goal.updated_at = datetime.now(UTC)

        # Check if approval is needed
        if step.requires_approval and self.approval_workflow:
            step.status = StepStatus.WAITING_APPROVAL
            return {
                "success": False,
                "requires_approval": True,
                "step_id": step.step_id,
                "message": f"Step requires approval: {step.description}",
            }

        # Execute tool if specified
        if step.tool_id and self.tool_registry:
            result = await self._execute_tool(step, user_context)
            step.result = result

            if result.get("success"):
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now(UTC)
            else:
                step.status = StepStatus.FAILED
                step.error = result.get("error", "Tool execution failed")

            return result

        # No tool specified - mark as completed
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.now(UTC)
        step.result = {"success": True, "message": "Step completed (no tool required)"}

        return step.result

    async def _execute_tool(self, step: GoalStep, user_context: dict[str, Any] = None) -> dict[str, Any]:
        """Execute tool for a step"""
        if not self.tool_registry:
            return {"success": False, "error": "No tool registry available"}

        handler = self.tool_registry.get_handler(step.tool_id)
        if not handler:
            return {"success": False, "error": f"No handler for tool: {step.tool_id}"}

        try:
            result = await handler.safe_execute(step.parameters, {"user_context": user_context})
            return result
        except Exception as e:
            self.logger.error(f"Tool execution error: {e}")
            return {"success": False, "error": str(e)}

    async def approve_step(self, goal: AgentGoal, step: GoalStep, user_id: int) -> dict[str, Any]:
        """Approve and execute a waiting step"""
        if step.status != StepStatus.WAITING_APPROVAL:
            return {"success": False, "error": "Step is not waiting for approval"}

        # Execute the step
        result = await self.execute_step(goal, step, {"user_id": user_id})
        return result


class AgentGoalsManager:
    """
    Main manager for agent goals system

    Handles:
    - Goal creation and tracking
    - Planning and execution
    - Progress monitoring
    - Human-in-the-loop approval
    """

    def __init__(
        self,
        llm=None,
        tool_registry=None,
        approval_workflow=None,
        persistence=None,
        redis_client=None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.approval_workflow = approval_workflow
        self.persistence = persistence
        self.redis_client = redis_client

        self.planner = GoalPlanner(llm=llm, tool_registry=tool_registry)
        self.executor = GoalExecutor(
            tool_registry=tool_registry,
            approval_workflow=approval_workflow,
            persistence=persistence,
        )

        self.active_goals: dict[str, AgentGoal] = {}
        self.logger = logging.getLogger(__name__)

    async def create_goal(
        self,
        title: str,
        description: str,
        user_id: int,
        session_id: str,
        context: dict[str, Any] = None,
        auto_plan: bool = True,
    ) -> AgentGoal:
        """
        Create a new agent goal

        Args:
            title: Goal title
            description: Goal description
            user_id: User ID
            session_id: Session ID
            context: Additional context
            auto_plan: Whether to automatically plan the goal

        Returns:
            Created AgentGoal
        """
        goal = AgentGoal(
            goal_id=f"goal_{uuid.uuid4().hex[:12]}",
            title=title,
            description=description,
            user_id=user_id,
            session_id=session_id,
            context=context or {},
        )

        # Store goal
        self.active_goals[goal.goal_id] = goal

        # Auto-plan if requested
        if auto_plan:
            await self.plan_goal(goal)

        # Persist if available
        if self.persistence:
            self._save_goal(goal)

        self.logger.info(f"Created goal {goal.goal_id}: {title}")
        return goal

    async def plan_goal(self, goal: AgentGoal) -> list[GoalStep]:
        """
        Plan steps for a goal

        Args:
            goal: Goal to plan

        Returns:
            List of planned steps
        """
        goal.status = GoalStatus.PLANNING
        goal.updated_at = datetime.now(UTC)

        # Get available tools
        available_tools = []
        if self.tool_registry:
            available_tools = list(self.tool_registry.list_handlers().values())

        # Generate plan
        steps = await self.planner.plan_goal(goal, available_tools)
        goal.steps = steps
        goal.status = GoalStatus.PENDING
        goal.updated_at = datetime.now(UTC)

        self.logger.info(f"Planned {len(steps)} steps for goal {goal.goal_id}")
        return steps

    async def execute_goal(self, goal_id: str, user_context: dict[str, Any] = None) -> dict[str, Any]:
        """
        Execute a goal step by step

        Args:
            goal_id: Goal ID to execute
            user_context: User context for permissions

        Returns:
            Execution result
        """
        goal = self.active_goals.get(goal_id)
        if not goal:
            return {"success": False, "error": f"Goal not found: {goal_id}"}

        goal.status = GoalStatus.EXECUTING
        goal.updated_at = datetime.now(UTC)

        results = []

        for i, step in enumerate(goal.steps):
            goal.current_step_index = i

            result = await self.executor.execute_step(goal, step, user_context)
            results.append(result)

            # Check if waiting for approval
            if result.get("requires_approval"):
                goal.status = GoalStatus.WAITING_APPROVAL
                return {
                    "success": False,
                    "requires_approval": True,
                    "goal_id": goal_id,
                    "step_id": step.step_id,
                    "step_index": i,
                    "message": f"Step {i + 1} requires approval: {step.description}",
                    "goal": goal.to_dict(),
                }

            # Check for failure
            if step.status == StepStatus.FAILED:
                goal.status = GoalStatus.FAILED
                goal.result_summary = f"Failed at step {i + 1}: {step.error}"
                return {
                    "success": False,
                    "error": step.error,
                    "failed_step": i,
                    "goal": goal.to_dict(),
                }

        # All steps completed
        goal.status = GoalStatus.COMPLETED
        goal.completed_at = datetime.now(UTC)
        goal.result_summary = f"Completed {len(goal.steps)} steps successfully"

        return {
            "success": True,
            "goal_id": goal_id,
            "results": results,
            "goal": goal.to_dict(),
        }

    async def approve_step(self, goal_id: str, step_index: int, user_id: int) -> dict[str, Any]:
        """
        Approve a step and continue execution

        Args:
            goal_id: Goal ID
            step_index: Index of step to approve
            user_id: User ID approving

        Returns:
            Result after approval
        """
        goal = self.active_goals.get(goal_id)
        if not goal:
            return {"success": False, "error": f"Goal not found: {goal_id}"}

        if step_index >= len(goal.steps):
            return {"success": False, "error": "Invalid step index"}

        step = goal.steps[step_index]

        # Approve and execute
        result = await self.executor.approve_step(goal, step, user_id)

        # Continue execution if successful
        if result.get("success"):
            # Move to next step
            goal.current_step_index = step_index + 1

            # Continue with remaining steps
            for i in range(step_index + 1, len(goal.steps)):
                next_step = goal.steps[i]
                next_result = await self.executor.execute_step(goal, next_step, {"user_id": user_id})

                if next_result.get("requires_approval"):
                    return {
                        "success": False,
                        "requires_approval": True,
                        "goal_id": goal_id,
                        "step_id": next_step.step_id,
                        "step_index": i,
                        "message": f"Step {i + 1} requires approval",
                        "goal": goal.to_dict(),
                    }

                if next_step.status == StepStatus.FAILED:
                    goal.status = GoalStatus.FAILED
                    return {
                        "success": False,
                        "error": next_step.error,
                        "goal": goal.to_dict(),
                    }

            # All completed
            goal.status = GoalStatus.COMPLETED
            goal.completed_at = datetime.now(UTC)

        return {"success": True, "result": result, "goal": goal.to_dict()}

    def get_goal(self, goal_id: str) -> AgentGoal | None:
        """Get a goal by ID"""
        return self.active_goals.get(goal_id)

    def list_goals(
        self,
        user_id: int | None = None,
        session_id: str | None = None,
        status: GoalStatus | None = None,
    ) -> list[AgentGoal]:
        """List goals with optional filters"""
        goals = list(self.active_goals.values())

        if user_id:
            goals = [g for g in goals if g.user_id == user_id]
        if session_id:
            goals = [g for g in goals if g.session_id == session_id]
        if status:
            goals = [g for g in goals if g.status == status]

        return goals

    def cancel_goal(self, goal_id: str) -> dict[str, Any]:
        """Cancel a goal"""
        goal = self.active_goals.get(goal_id)
        if not goal:
            return {"success": False, "error": "Goal not found"}

        goal.status = GoalStatus.CANCELLED
        goal.updated_at = datetime.now(UTC)

        return {"success": True, "goal_id": goal_id}

    def _save_goal(self, goal: AgentGoal):
        """Save goal to persistence"""
        if self.redis_client:
            try:
                key = f"agent_goals:{goal.goal_id}"
                self.redis_client.setex(
                    key,
                    86400,
                    json.dumps(goal.to_dict(), default=str),  # 24 hours
                )
            except Exception as e:
                self.logger.warning(f"Failed to save goal to Redis: {e}")


# Global manager instance
_goals_manager = None


def get_goals_manager(
    llm=None,
    tool_registry=None,
    approval_workflow=None,
    persistence=None,
    redis_client=None,
) -> AgentGoalsManager:
    """Get singleton goals manager instance"""
    global _goals_manager
    if _goals_manager is None:
        _goals_manager = AgentGoalsManager(
            llm=llm,
            tool_registry=tool_registry,
            approval_workflow=approval_workflow,
            persistence=persistence,
            redis_client=redis_client,
        )
    return _goals_manager
