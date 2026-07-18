"""
AI-Powered Execution Planner - Semantic matching for intelligent agent selection

Enhances the rule-based planner with transformer-style attention matching
using Q/K/V vectors for dynamic agent topology.
"""

# Using relative imports - no sys.path hack needed

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

# Import semantic layer
from app.services.semantic.topology_manager import (
    TopologyManager,
    get_topology_manager,
)

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
    agent_id: str | None = None  # Semantic agent selection
    confidence: float = 0.0  # Match confidence


@dataclass
class ExecutionPlan:
    """A complete execution plan with multiple steps"""

    goal: str
    steps: list[ExecutionStep]
    created_at: datetime = field(default_factory=datetime.utcnow)
    estimated_cost: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    planning_method: str = "semantic"

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
                    "agent_id": step.agent_id,
                    "confidence": step.confidence,
                }
                for step in self.steps
            ],
            "estimated_cost": self.estimated_cost,
            "metadata": self.metadata,
            "planning_method": self.planning_method,
        }


class AIExecutionPlanner:
    """
    AI-Powered Execution Planner using semantic matching.

    Uses Q/K/V attention mechanism to:
    - Understand task requirements (Q vector from task)
    - Match against agent capabilities (K vector from agents)
    - Select best agent with payload (V vector)

    Falls back to rule-based planning when semantic matching unavailable.
    """

    def __init__(self, capability_registry=None, use_semantic: bool = True):
        self._capability_registry = capability_registry
        self._use_semantic = use_semantic
        self._topology_manager: TopologyManager | None = None
        self._planning_rules: list[dict[str, Any]] = []
        self._setup_default_rules()

        # Initialize semantic layer if available
        if use_semantic:
            try:
                self._topology_manager = get_topology_manager()
                logger.info("AIExecutionPlanner initialized with semantic matching")
            except Exception as e:
                logger.warning("Semantic layer unavailable, using rule-based fallback: %s", e)
                self._use_semantic = False

    def _setup_default_rules(self):
        """Setup default planning rules as fallback"""
        self._planning_rules = [
            {
                "patterns": [r"search", r"find", r"look up", r"query"],
                "capabilities": ["tool:search_knowledge"],
                "category": "knowledge",
            },
            {
                "patterns": [r"execute", r"run agent", r"perform task"],
                "capabilities": ["tool:spawn_agent"],
                "category": "agent",
            },
            {
                "patterns": [r"run workflow", r"start workflow"],
                "capabilities": ["tool:execute_workflow"],
                "category": "workflow",
            },
            {
                "patterns": [r"remember", r"store", r"save to memory"],
                "capabilities": ["tool:store_memory"],
                "category": "memory",
            },
            {
                "patterns": [r"recall", r"remember when", r"what did"],
                "capabilities": ["tool:recall_memory"],
                "category": "memory",
            },
            {
                "patterns": [r"generate image", r"create image", r"draw"],
                "capabilities": ["tool:generate_image"],
                "category": "creative",
            },
            {
                "patterns": [r"analyze", r"examine", r"review"],
                "capabilities": ["tool:analyze"],
                "category": "analysis",
            },
            {
                "patterns": [r"write code", r"implement", r"develop"],
                "capabilities": ["tool:write_code"],
                "category": "development",
            },
        ]

    async def register_agent(
        self,
        agent_id: str,
        description: str,
        capabilities: list[str],
        category: str = "general",
        personality_traits: dict[str, float] | None = None,
        endpoint: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Register an agent for semantic matching"""
        if self._topology_manager:
            try:
                await self._topology_manager.register_agent(  # type: ignore[attr-defined]
                    agent_id=agent_id,
                    description=description,
                    capabilities=capabilities,
                    category=category,
                    personality_traits=personality_traits,
                    endpoint=endpoint,
                    config=config,
                )
                logger.info("Registered agent %s for semantic matching", agent_id)
                return True
            except Exception as e:
                logger.error("Failed to register agent %s: %s", agent_id, e)
                return False
        return False

    async def create_plan(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        available_capabilities: list[str] | None = None,
        available_agents: list[str] | None = None,
    ) -> ExecutionPlan:
        """
        Create an execution plan using semantic matching.

        Args:
            goal: Natural language description of what to achieve
            context: Additional context for planning
            available_capabilities: List of available capability IDs
            available_agents: List of available agent IDs to consider

        Returns:
            ExecutionPlan with semantically-matched agents
        """
        # Try semantic matching first
        if self._use_semantic and self._topology_manager:
            return await self._create_semantic_plan(goal, context, available_agents)
        else:
            return await self._create_rule_based_plan(goal, context, available_capabilities)

    async def _create_semantic_plan(
        self,
        goal: str,
        context: dict[str, Any] | None,
        available_agents: list[str] | None,
    ) -> ExecutionPlan:
        """Create plan using semantic attention matching"""
        steps = []
        step_id = 0

        # Find best matching agents using attention
        matches = await cast("Any", self._topology_manager).find_best_agent(query=goal, max_results=5)

        # Filter by available agents if specified
        if available_agents:
            matches = [m for m in matches if m.agent_id in available_agents]

        # Create steps from top matches
        for match in matches:
            step_id += 1
            step = ExecutionStep(
                step_id=step_id,
                capability_id=match.capability_id,
                params={"goal": goal, "context": context},
                description=f"Execute {match.capability_id} via {match.agent_id} (confidence: {match.score:.2f})",
                agent_id=match.agent_id,
                confidence=match.score,
            )
            steps.append(step)

        # If no semantic matches, fall back to rule-based
        if not steps:
            logger.info("No semantic matches, falling back to rule-based planning")
            return await self._create_rule_based_plan(goal, context, None)

        # Add dependencies
        steps = self._add_dependencies(steps)

        return ExecutionPlan(
            goal=goal,
            steps=steps,
            estimated_cost=self._estimate_cost(steps),
            metadata={
                "planning_method": "semantic",
                "semantic_matches": len(matches),
                "top_confidence": matches[0].score if matches else 0,
            },
            planning_method="semantic",
        )

    async def _create_rule_based_plan(
        self,
        goal: str,
        context: dict[str, Any] | None,
        available_capabilities: list[str] | None,
    ) -> ExecutionPlan:
        """Create plan using rule-based matching (fallback)"""
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
            matched_capabilities = matched_capabilities.intersection(set(available_capabilities))

        # Create steps
        for cap_id in matched_capabilities:
            step_id += 1
            step = ExecutionStep(
                step_id=step_id,
                capability_id=cap_id,
                params={"goal": goal},
                description=f"Execute {cap_id} for: {goal[:100]}",
            )
            steps.append(step)

        # If no matches, create generic agent execution step
        if not steps:
            steps.append(
                ExecutionStep(
                    step_id=1,
                    capability_id="tool:spawn_agent",
                    params={"task": goal},
                    description=f"Execute agent task: {goal[:100]}",
                )
            )

        steps = self._add_dependencies(steps)

        return ExecutionPlan(
            goal=goal,
            steps=steps,
            estimated_cost=self._estimate_cost(steps),
            metadata={
                "planning_method": "rule-based",
                "matched_capabilities": list(matched_capabilities),
            },
            planning_method="rule-based",
        )

    def _add_dependencies(self, steps: list[ExecutionStep]) -> list[ExecutionStep]:
        """Add dependencies between steps based on capability types"""
        memory_recall_idx = None
        agent_execute_idx = None
        rag_search_idx = None

        for i, step in enumerate(steps):
            if step.capability_id == "tool:recall_memory":
                memory_recall_idx = i
            elif step.capability_id == "tool:spawn_agent":
                agent_execute_idx = i
            elif step.capability_id == "tool:search_knowledge":
                rag_search_idx = i

        if memory_recall_idx is not None and agent_execute_idx is not None:
            steps[agent_execute_idx].depends_on.append(steps[memory_recall_idx].step_id)

        if rag_search_idx is not None and agent_execute_idx is not None:
            steps[agent_execute_idx].depends_on.append(steps[rag_search_idx].step_id)

        return steps

    def _estimate_cost(self, steps: list[ExecutionStep]) -> dict[str, Any]:
        """Estimate cost of execution plan"""
        base_cost = 0.001
        llm_cost = 0.01

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
            "avg_confidence": (sum(s.confidence for s in steps) / len(steps) if steps else 0),
        }

    async def optimize_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Optimize plan for parallel execution"""
        independent_steps = [s for s in plan.steps if not s.depends_on]
        dependent_steps = [s for s in plan.steps if s.depends_on]

        optimized_steps = independent_steps + dependent_steps

        for i, step in enumerate(optimized_steps, 1):
            step.step_id = i

        plan.steps = optimized_steps
        plan.metadata["optimized"] = True

        return plan

    def get_plan_summary(self, plan: ExecutionPlan) -> str:
        """Get human-readable summary"""
        lines = [f"Execution Plan for: {plan.goal}", "=" * 50]
        lines.append(f"Method: {plan.planning_method}")
        lines.append("")

        for step in plan.steps:
            deps = f" (depends on: {step.depends_on})" if step.depends_on else ""
            agent = f" [{step.agent_id}]" if step.agent_id else ""
            conf = f" ({step.confidence:.2f})" if step.confidence > 0 else ""
            lines.append(f"  Step {step.step_id}: {step.capability_id}{agent}{conf}{deps}")

        lines.append(f"\nEstimated cost: ${plan.estimated_cost.get('estimated_usd', 0):.4f}")

        return "\n".join(lines)


def get_ai_execution_planner(use_semantic: bool = True) -> AIExecutionPlanner:
    """Get AI execution planner instance"""
    return AIExecutionPlanner(use_semantic=use_semantic)
