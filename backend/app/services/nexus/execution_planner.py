"""
Execution Planner - Plans multi-step operations across systems

Given a goal, determines which services to invoke in what order.
Supports both rule-based and AI-powered planning.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionStep:
    """A single step in an execution plan"""

    step_id: int
    capability_id: str
    params: dict[str, Any]
    description: str = ""
    depends_on: list[int] = field(default_factory=list)
    optional: bool = False
    timeout_seconds: int = 30
    retry_count: int = 0


@dataclass
class ExecutionPlan:
    """A complete execution plan with multiple steps"""

    goal: str
    steps: list[ExecutionStep]
    created_at: datetime = field(default_factory=datetime.utcnow)
    estimated_cost: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [
                {
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "params": step.params,
                    "description": step.description,
                    "depends_on": step.depends_on,
                    "optional": step.optional,
                }
                for step in self.steps
            ],
            "estimated_cost": self.estimated_cost,
            "metadata": self.metadata,
        }


class ExecutionPlanner:
    """
    Plans multi-step operations across systems.

    Given a goal, determines:
    - Which capabilities to invoke
    - In what order
    - With what parameters
    - Dependencies between steps
    """

    def __init__(self, capability_registry=None):
        self._capability_registry = capability_registry
        self._planning_rules: list[dict[str, Any]] = []
        self._capability_patterns: dict[str, list[str]] = {}
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Setup default planning rules based on common patterns"""
        self._planning_rules = [
            # Knowledge search patterns
            {
                "patterns": [r"search", r"find", r"look up", r"query"],
                "capabilities": ["tool:search_knowledge"],
                "category": "knowledge",
            },
            # Agent execution patterns
            {
                "patterns": [r"execute", r"run agent", r"perform task", r"do task"],
                "capabilities": ["tool:spawn_agent"],
                "category": "agent",
            },
            # Workflow patterns
            {
                "patterns": [r"run workflow", r"start workflow", r"execute workflow"],
                "capabilities": ["tool:execute_workflow"],
                "category": "workflow",
            },
            # Memory patterns
            {
                "patterns": [r"remember", r"store", r"save to memory"],
                "capabilities": ["tool:store_memory"],
                "category": "memory",
            },
            # Recall patterns
            {
                "patterns": [r"recall", r"remember when", r"what did", r"previous"],
                "capabilities": ["tool:recall_memory"],
                "category": "memory",
            },
            # Image generation patterns
            {
                "patterns": [
                    r"generate image",
                    r"create image",
                    r"make picture",
                    r"draw",
                ],
                "category": "generation",
            },
            # Analysis patterns
            {
                "patterns": [r"analyze", r"examine", r"review", r"assess"],
                "category": "agent",
            },
            # Code patterns
            {
                "patterns": [r"write code", r"implement", r"develop", r"code"],
                "category": "agent",
            },
        ]

    def add_planning_rule(self, rule: dict[str, Any]) -> None:
        """Add a custom planning rule"""
        self._planning_rules.append(rule)

    async def create_plan(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        available_capabilities: list[str] | None = None,
    ) -> ExecutionPlan:
        """
        Create an execution plan for a goal.

        Args:
            goal: Natural language description of what to achieve
            context: Additional context for planning
            available_capabilities: List of available capability IDs

        Returns:
            ExecutionPlan with ordered steps
        """
        goal_lower = goal.lower()
        steps = []
        step_id = 0

        # Match goal against planning rules
        matched_capabilities = set()
        for rule in self._planning_rules:
            for pattern in rule["patterns"]:
                if re.search(pattern, goal_lower):
                    for cap in rule["capabilities"]:
                        matched_capabilities.add(cap)
                    break

        # Filter by available capabilities if specified
        if available_capabilities:
            matched_capabilities = matched_capabilities.intersection(
                set(available_capabilities)
            )

        # Create steps for matched capabilities
        for cap_id in matched_capabilities:
            step_id += 1
            step = ExecutionStep(
                step_id=step_id,
                capability_id=cap_id,
                params={"goal": goal},
                description=f"Execute {cap_id} for: {goal[:100]}",
            )
            steps.append(step)

        # If no matches, create a generic agent execution step
        if not steps:
            step_id += 1
            steps.append(
                ExecutionStep(
                    step_id=step_id,
                    capability_id="tool:spawn_agent",
                    params={"task": goal},
                    description=f"Execute agent task: {goal[:100]}",
                )
            )

        # Add dependencies based on capability types
        steps = self._add_dependencies(steps)

        # Calculate estimated cost
        estimated_cost = self._estimate_cost(steps)

        return ExecutionPlan(
            goal=goal,
            steps=steps,
            estimated_cost=estimated_cost,
            metadata={
                "planning_method": "rule-based",
                "matched_capabilities": list(matched_capabilities),
                "context_provided": context is not None,
            },
        )

    def _add_dependencies(self, steps: list[ExecutionStep]) -> list[ExecutionStep]:
        """Add dependencies between steps based on capability types"""
        # Memory recall should come before agent execution
        memory_recall_idx = None
        agent_execute_idx = None

        for i, step in enumerate(steps):
            if step.capability_id == "tool:recall_memory":
                memory_recall_idx = i
            elif step.capability_id == "tool:spawn_agent":
                agent_execute_idx = i

        # Add dependency: agent execution depends on memory recall
        if memory_recall_idx is not None and agent_execute_idx is not None:
            steps[agent_execute_idx].depends_on.append(steps[memory_recall_idx].step_id)

        # RAG search should come before agent execution
        rag_search_idx = None
        for i, step in enumerate(steps):
            if step.capability_id == "tool:search_knowledge":
                rag_search_idx = i

        if rag_search_idx is not None and agent_execute_idx is not None:
            steps[agent_execute_idx].depends_on.append(steps[rag_search_idx].step_id)

        return steps

    def _estimate_cost(self, steps: list[ExecutionStep]) -> dict[str, Any]:
        """Estimate cost of execution plan"""
        # Rough estimates
        base_cost = 0.001  # $0.001 per step
        llm_cost = 0.01  # $0.01 for LLM steps

        total = 0
        for step in steps:
            if "agent" in step.capability_id or "workflow" in step.capability_id:
                total += llm_cost  # type: ignore[assignment]
            else:
                total += base_cost  # type: ignore[assignment]

        return {
            "estimated_usd": round(total, 4),
            "step_count": len(steps),
            "llm_steps": sum(1 for s in steps if "agent" in s.capability_id),
        }

    async def optimize_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """
        Optimize an execution plan for better performance.

        - Reorder independent steps for parallel execution
        - Remove redundant steps
        - Merge similar operations
        """
        # Find steps that can be parallelized
        independent_steps = [s for s in plan.steps if not s.depends_on]
        dependent_steps = [s for s in plan.steps if s.depends_on]

        # Reorder: independent steps first, then dependent
        optimized_steps = independent_steps + dependent_steps

        # Reassign step IDs
        for i, step in enumerate(optimized_steps, 1):
            step.step_id = i

        plan.steps = optimized_steps
        plan.metadata["optimized"] = True

        return plan

    def get_plan_summary(self, plan: ExecutionPlan) -> str:
        """Get a human-readable summary of the plan"""
        lines = [f"Execution Plan for: {plan.goal}", "=" * 50]

        for step in plan.steps:
            deps = f" (depends on: {step.depends_on})" if step.depends_on else ""
            lines.append(f"  Step {step.step_id}: {step.capability_id}{deps}")
            lines.append(f"           {step.description[:60]}...")

        lines.append(
            f"\nEstimated cost: ${plan.estimated_cost.get('estimated_usd', 0):.4f}"
        )

        return "\n".join(lines)
