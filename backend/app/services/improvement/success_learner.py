"""
Success Learning Engine for Autonomous Self-Improvement System.

This module extracts patterns from successful missions to amplify
what works, complementing the failure-based learning.

Phase 6A of the Autonomous Self-Improvement Architecture.
"""

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Import from previous phases


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class PatternStrength(str, Enum):
    """Strength of a success pattern."""

    WEAK = "weak"  # 1-2 occurrences
    MODERATE = "moderate"  # 3-5 occurrences
    STRONG = "strong"  # 6-10 occurrences
    VERY_STRONG = "very_strong"  # 10+ occurrences


class PatternType(str, Enum):
    """Types of success patterns."""

    TOOL_SEQUENCE = "tool_sequence"  # Order of tools used
    CONFIG_PROFILE = "config_profile"  # Knob values that worked
    TIMING_PATTERN = "timing_pattern"  # Latency/timing characteristics
    CONTEXT_MATCH = "context_match"  # Mission context features
    HYBRID = "hybrid"  # Combination of above


@dataclass
class SuccessPattern:
    """A pattern extracted from successful missions."""

    pattern_id: str
    pattern_type: PatternType
    agent_id: str | None

    # What made this successful
    tool_sequence: list[str] = field(default_factory=list)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    latency_profile: dict[str, float] = field(default_factory=dict)
    context_features: dict[str, Any] = field(default_factory=dict)

    # Pattern metadata
    success_count: int = 1
    failure_count: int = 0  # Times this pattern was seen in failures
    confidence: float = 0.0
    strength: PatternStrength = PatternStrength.WEAK

    # Tracking
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    mission_ids: list[str] = field(default_factory=list)

    # Derived insights
    differentiating_factors: dict[str, Any] = field(default_factory=dict)
    recommended_actions: list[str] = field(default_factory=list)

    def calculate_confidence(self) -> float:
        """Calculate confidence based on success/failure ratio."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0

        # Base confidence from success rate
        success_rate = self.success_count / total

        # Boost from sample size
        sample_boost = min(0.2, self.success_count * 0.02)

        # Penalty for low sample size
        if total < 3:
            sample_penalty = 0.3
        elif total < 5:
            sample_penalty = 0.1
        else:
            sample_penalty = 0.0

        self.confidence = max(
            0.0, min(1.0, success_rate + sample_boost - sample_penalty)
        )
        return self.confidence

    def update_strength(self) -> PatternStrength:
        """Update strength based on success count."""
        if self.success_count >= 10:
            self.strength = PatternStrength.VERY_STRONG
        elif self.success_count >= 6:
            self.strength = PatternStrength.STRONG
        elif self.success_count >= 3:
            self.strength = PatternStrength.MODERATE
        else:
            self.strength = PatternStrength.WEAK
        return self.strength

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "agent_id": self.agent_id,
            "tool_sequence": self.tool_sequence,
            "config_snapshot": self.config_snapshot,
            "latency_profile": self.latency_profile,
            "context_features": self.context_features,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "confidence": self.confidence,
            "strength": self.strength.value,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "differentiating_factors": self.differentiating_factors,
            "recommended_actions": self.recommended_actions,
        }


@dataclass
class MissionOutcome:
    """Represents a mission outcome for analysis."""

    mission_id: str
    agent_id: str
    success: bool
    tasks: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    config_at_execution: dict[str, Any] = field(default_factory=dict)
    latencies: dict[str, float] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "mission_id": self.mission_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "tools_used": self.tools_used,
            "config_at_execution": self.config_at_execution,
            "latencies": self.latencies,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "error_types": self.error_types,
        }


# ============================================================================
# SUCCESS LEARNER
# ============================================================================


class SuccessLearner:
    """
    Extracts and manages patterns from successful missions.

    This class complements failure-based learning by identifying
    what works well and amplifying those patterns.
    """

    def __init__(self, knowledge_graph=None):
        """
        Initialize the success learner.

        Args:
            knowledge_graph: Optional knowledge graph for pattern storage
        """
        self.knowledge_graph = knowledge_graph
        self._patterns: dict[str, SuccessPattern] = {}
        self._mission_history: dict[str, MissionOutcome] = {}
        self._tool_sequence_index: dict[str, set[str]] = defaultdict(set)
        self._config_profile_index: dict[str, set[str]] = defaultdict(set)

        # Configuration
        self.min_success_for_pattern = 2
        self.pattern_similarity_threshold = 0.8

    async def extract_success_pattern(
        self,
        mission_outcome: MissionOutcome,
    ) -> SuccessPattern | None:
        """
        Extract a success pattern from a mission outcome.

        Args:
            mission_outcome: The mission outcome to analyze

        Returns:
            A SuccessPattern if one can be extracted, None otherwise
        """
        if not mission_outcome.success:
            return None

        # Generate pattern ID based on key features
        pattern_key = self._generate_pattern_key(mission_outcome)

        # Check if similar pattern already exists
        existing_pattern = await self._find_similar_pattern(mission_outcome)

        if existing_pattern:
            # Update existing pattern
            existing_pattern.success_count += 1
            existing_pattern.last_seen = datetime.now(UTC)
            existing_pattern.mission_ids.append(mission_outcome.mission_id)
            existing_pattern.calculate_confidence()
            existing_pattern.update_strength()

            logger.debug("Updated existing pattern %s", existing_pattern.pattern_id)
            return existing_pattern

        # Create new pattern
        pattern = SuccessPattern(
            pattern_id=pattern_key,
            pattern_type=self._determine_pattern_type(mission_outcome),
            agent_id=mission_outcome.agent_id,
            tool_sequence=mission_outcome.tools_used.copy(),
            config_snapshot=mission_outcome.config_at_execution.copy(),
            latency_profile=mission_outcome.latencies.copy(),
            context_features=mission_outcome.context.copy(),
            mission_ids=[mission_outcome.mission_id],
        )

        pattern.calculate_confidence()
        pattern.update_strength()

        # Store pattern
        self._patterns[pattern.pattern_id] = pattern
        self._update_indices(pattern)

        # Store in knowledge graph if available
        if self.knowledge_graph:
            await self._store_pattern_in_graph(pattern)

        logger.info(
            "Extracted new success pattern %s (type=%s, confidence=%.2f)",
            pattern.pattern_id,
            pattern.pattern_type.value,
            pattern.confidence,
        )

        return pattern

    async def compare_success_vs_failure(
        self,
        success_outcomes: list[MissionOutcome],
        failure_outcomes: list[MissionOutcome],
    ) -> dict[str, Any]:
        """
        Compare successful and failed missions to identify differentiating factors.

        Args:
            success_outcomes: List of successful mission outcomes
            failure_outcomes: List of failed mission outcomes

        Returns:
            Dictionary of differentiating factors
        """
        differentiators: dict[str, Any] = {
            "tool_usage": {},
            "config_differences": {},
            "latency_patterns": {},
            "context_factors": {},
            "recommendations": [],
        }

        # Analyze tool usage differences
        success_tools: dict[str, int] = defaultdict(int)
        failure_tools: dict[str, int] = defaultdict(int)

        for outcome in success_outcomes:
            for tool in outcome.tools_used:
                success_tools[tool] += 1

        for outcome in failure_outcomes:
            for tool in outcome.tools_used:
                failure_tools[tool] += 1

        all_tools = set(success_tools.keys()) | set(failure_tools.keys())
        for tool in all_tools:
            s_rate = (
                success_tools[tool] / len(success_outcomes) if success_outcomes else 0
            )
            f_rate = (
                failure_tools[tool] / len(failure_outcomes) if failure_outcomes else 0
            )
            diff = s_rate - f_rate

            if abs(diff) > 0.2:  # Significant difference
                differentiators["tool_usage"][tool] = {
                    "success_rate": s_rate,
                    "failure_rate": f_rate,
                    "difference": diff,
                    "recommendation": "use_more" if diff > 0 else "use_less",
                }

        # Analyze config differences
        success_configs = defaultdict(list)
        failure_configs = defaultdict(list)

        for outcome in success_outcomes:
            for key, value in outcome.config_at_execution.items():
                if isinstance(value, (int, float)):
                    success_configs[key].append(value)

        for outcome in failure_outcomes:
            for key, value in outcome.config_at_execution.items():
                if isinstance(value, (int, float)):
                    failure_configs[key].append(value)

        all_config_keys = set(success_configs.keys()) | set(failure_configs.keys())
        for key in all_config_keys:
            s_vals = success_configs[key]
            f_vals = failure_configs[key]

            if s_vals and f_vals:
                s_avg = sum(s_vals) / len(s_vals)
                f_avg = sum(f_vals) / len(f_vals)
                diff_pct = (s_avg - f_avg) / f_avg if f_avg != 0 else 0

                if abs(diff_pct) > 0.1:  # 10% difference
                    differentiators["config_differences"][key] = {
                        "success_avg": s_avg,
                        "failure_avg": f_avg,
                        "difference_pct": diff_pct,
                        "recommendation": f"Set {key} closer to {s_avg:.2f}",
                    }

        # Analyze latency patterns
        success_latencies: list[float] = []
        failure_latencies: list[float] = []

        for outcome in success_outcomes:
            success_latencies.extend(outcome.latencies.values())

        for outcome in failure_outcomes:
            failure_latencies.extend(outcome.latencies.values())

        if success_latencies and failure_latencies:
            s_avg_lat = sum(success_latencies) / len(success_latencies)
            f_avg_lat = sum(failure_latencies) / len(failure_latencies)

            differentiators["latency_patterns"] = {
                "success_avg_latency": s_avg_lat,
                "failure_avg_latency": f_avg_lat,
                "difference": f_avg_lat - s_avg_lat,
            }

        # Generate recommendations
        recommendations = []

        for tool, data in differentiators["tool_usage"].items():  # type: ignore[attr-defined]
            if data["recommendation"] == "use_more":
                recommendations.append(f"Prefer using {tool} tool more often")
            else:
                recommendations.append(f"Consider alternatives to {tool} tool")

        for key, data in differentiators["config_differences"].items():  # type: ignore[attr-defined]
            recommendations.append(data["recommendation"])

        differentiators["recommendations"] = recommendations

        return differentiators

    async def get_patterns_for_agent(
        self,
        agent_id: str,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> list[SuccessPattern]:
        """
        Get success patterns for a specific agent.

        Args:
            agent_id: The agent ID
            min_confidence: Minimum confidence threshold
            limit: Maximum number of patterns to return

        Returns:
            List of matching patterns
        """
        patterns = [
            p
            for p in self._patterns.values()
            if (p.agent_id == agent_id or p.agent_id is None)
            and p.confidence >= min_confidence
        ]

        # Sort by confidence and success count
        patterns.sort(key=lambda p: (p.confidence, p.success_count), reverse=True)

        return patterns[:limit]

    async def get_patterns_for_context(
        self,
        context: dict[str, Any],
        agent_id: str | None = None,
        limit: int = 5,
    ) -> list[SuccessPattern]:
        """
        Get success patterns matching a context.

        Args:
            context: The context to match
            agent_id: Optional agent ID filter
            limit: Maximum number of patterns

        Returns:
            List of matching patterns
        """
        matching_patterns = []

        for pattern in self._patterns.values():
            if agent_id and pattern.agent_id != agent_id:
                continue

            # Calculate context similarity
            similarity = self._calculate_context_similarity(
                context, pattern.context_features
            )

            if similarity >= self.pattern_similarity_threshold:
                matching_patterns.append((pattern, similarity))

        # Sort by similarity
        matching_patterns.sort(key=lambda x: x[1], reverse=True)

        return [p for p, _ in matching_patterns[:limit]]

    async def record_mission_outcome(
        self,
        mission_outcome: MissionOutcome,
    ) -> SuccessPattern | None:
        """
        Record a mission outcome and extract/update patterns.

        Args:
            mission_outcome: The mission outcome to record

        Returns:
            SuccessPattern if successful, None otherwise
        """
        # Store in history
        self._mission_history[mission_outcome.mission_id] = mission_outcome

        # Extract pattern if successful
        if mission_outcome.success:
            return await self.extract_success_pattern(mission_outcome)
        else:
            # Update failure count for similar patterns
            similar = await self._find_similar_pattern(mission_outcome)
            if similar:
                similar.failure_count += 1
                similar.calculate_confidence()
            return None

    async def get_top_patterns(
        self,
        limit: int = 10,
        pattern_type: PatternType | None = None,
    ) -> list[SuccessPattern]:
        """
        Get top success patterns across all agents.

        Args:
            limit: Maximum number of patterns
            pattern_type: Optional pattern type filter

        Returns:
            List of top patterns
        """
        patterns = list(self._patterns.values())

        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]

        # Sort by confidence * success_count
        patterns.sort(key=lambda p: p.confidence * p.success_count, reverse=True)

        return patterns[:limit]

    def get_pattern_by_id(self, pattern_id: str) -> SuccessPattern | None:
        """Get a pattern by ID."""
        return self._patterns.get(pattern_id)

    async def apply_pattern_to_config(
        self,
        pattern: SuccessPattern,
        current_config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Apply a success pattern to a configuration.

        Args:
            pattern: The pattern to apply
            current_config: Current configuration

        Returns:
            Modified configuration
        """
        new_config = current_config.copy()

        # Apply config snapshot values
        for key, value in pattern.config_snapshot.items():
            if key in new_config:
                # Blend current and pattern values based on confidence
                if isinstance(value, (int, float)) and isinstance(
                    new_config[key], (int, float)
                ):
                    blend = pattern.confidence
                    new_config[key] = (1 - blend) * new_config[key] + blend * value
                else:
                    if pattern.confidence > 0.7:
                        new_config[key] = value

        return new_config

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _generate_pattern_key(self, outcome: MissionOutcome) -> str:
        """Generate a unique pattern key."""
        key_parts = [
            outcome.agent_id or "global",
            "-".join(outcome.tools_used[:5]),  # First 5 tools
            str(sorted(outcome.config_at_execution.items())[:3]),  # Top 3 config items
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()[:12]

    def _determine_pattern_type(self, outcome: MissionOutcome) -> PatternType:
        """Determine the type of pattern."""
        has_tools = bool(outcome.tools_used)
        has_config = bool(outcome.config_at_execution)
        has_context = bool(outcome.context)

        if has_tools and has_config and has_context:
            return PatternType.HYBRID
        elif has_tools and not has_config:
            return PatternType.TOOL_SEQUENCE
        elif has_config and not has_tools:
            return PatternType.CONFIG_PROFILE
        elif has_context:
            return PatternType.CONTEXT_MATCH
        else:
            return PatternType.HYBRID

    async def _find_similar_pattern(
        self,
        outcome: MissionOutcome,
    ) -> SuccessPattern | None:
        """Find a similar existing pattern."""
        for pattern in self._patterns.values():
            # Check agent match
            if pattern.agent_id and pattern.agent_id != outcome.agent_id:
                continue

            # Check tool sequence similarity
            if pattern.tool_sequence:
                seq_similarity = self._calculate_sequence_similarity(
                    outcome.tools_used, pattern.tool_sequence
                )
                if seq_similarity < self.pattern_similarity_threshold:
                    continue

            # Check config similarity
            if pattern.config_snapshot:
                config_similarity = self._calculate_config_similarity(
                    outcome.config_at_execution, pattern.config_snapshot
                )
                if config_similarity < self.pattern_similarity_threshold:
                    continue

            return pattern

        return None

    def _calculate_sequence_similarity(
        self,
        seq1: list[str],
        seq2: list[str],
    ) -> float:
        """Calculate similarity between two tool sequences."""
        if not seq1 and not seq2:
            return 1.0
        if not seq1 or not seq2:
            return 0.0

        # Use Jaccard similarity for sets
        set1 = set(seq1)
        set2 = set(seq2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        jaccard = intersection / union

        # Also consider order for first few elements
        order_match = 0
        min_len = min(3, len(seq1), len(seq2))
        for i in range(min_len):
            if seq1[i] == seq2[i]:
                order_match += 1

        order_score = order_match / min_len if min_len > 0 else 0

        return 0.7 * jaccard + 0.3 * order_score

    def _calculate_config_similarity(
        self,
        config1: dict[str, Any],
        config2: dict[str, Any],
    ) -> float:
        """Calculate similarity between two configurations."""
        if not config1 and not config2:
            return 1.0
        if not config1 or not config2:
            return 0.0

        common_keys = set(config1.keys()) & set(config2.keys())
        if not common_keys:
            return 0.0

        similarities = []
        for key in common_keys:
            v1, v2 = config1[key], config2[key]

            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                # Numeric similarity
                if v1 == 0 and v2 == 0:
                    similarities.append(1.0)
                elif v1 == 0 or v2 == 0:
                    similarities.append(0.0)
                else:
                    ratio = min(v1, v2) / max(v1, v2)
                    similarities.append(ratio)
            elif v1 == v2:
                similarities.append(1.0)
            else:
                similarities.append(0.0)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _calculate_context_similarity(
        self,
        context1: dict[str, Any],
        context2: dict[str, Any],
    ) -> float:
        """Calculate similarity between two contexts."""
        return self._calculate_config_similarity(context1, context2)

    def _update_indices(self, pattern: SuccessPattern) -> None:
        """Update internal indices for pattern lookup."""
        # Index by tool sequence
        if pattern.tool_sequence:
            seq_key = "-".join(pattern.tool_sequence[:3])
            self._tool_sequence_index[seq_key].add(pattern.pattern_id)

        # Index by config profile
        if pattern.config_snapshot:
            for key, value in pattern.config_snapshot.items():
                config_key = f"{key}:{value}"
                self._config_profile_index[config_key].add(pattern.pattern_id)

    async def _store_pattern_in_graph(self, pattern: SuccessPattern) -> None:
        """Store pattern in knowledge graph."""
        if not self.knowledge_graph:
            return

        try:
            await self.knowledge_graph.add_node(
                node_type="success_pattern",
                node_key=pattern.pattern_id,
                properties=pattern.to_dict(),
            )
        except Exception as e:
            logger.warning("Failed to store pattern in knowledge graph: %s", e)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_success_learner: SuccessLearner | None = None


def get_success_learner() -> SuccessLearner:
    """Get the singleton success learner instance."""
    global _success_learner
    if _success_learner is None:
        _success_learner = SuccessLearner()
    return _success_learner


def initialize_success_learner(knowledge_graph=None) -> SuccessLearner:
    """Initialize the success learner with a knowledge graph."""
    global _success_learner
    _success_learner = SuccessLearner(knowledge_graph)
    return _success_learner
