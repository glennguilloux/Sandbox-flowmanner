"""
Cross-Agent Knowledge Transfer for Autonomous Self-Improvement System.

This module enables sharing of learned knowledge between agents,
allowing successful strategies to propagate across the agent fleet.

Phase 6D of the Autonomous Self-Improvement Architecture.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Import from previous phases
from .failure_types import FailureType
from .strategy_evolution import StrategyStatus

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class TransferStatus(str, Enum):
    """Status of a knowledge transfer."""
    PENDING = "pending"          # Queued for transfer
    IN_PROGRESS = "in_progress"  # Currently being transferred
    APPLIED = "applied"          # Successfully applied
    VERIFIED = "verified"        # Verified to work in target
    FAILED = "failed"            # Transfer failed
    REJECTED = "rejected"        # Rejected by target agent


class TransferType(str, Enum):
    """Types of knowledge that can be transferred."""
    STRATEGY = "strategy"        # Strategy variant
    PATTERN = "pattern"          # Success pattern
    KNOB_CONFIG = "knob_config"  # Knob configuration
    FAILURE_MAPPING = "failure_mapping"  # Failure → strategy mapping


class AgentSimilarity(str, Enum):
    """Similarity level between agents."""
    IDENTICAL = "identical"      # Same model, same tools
    HIGH = "high"                # Same model, similar tools
    MEDIUM = "medium"            # Similar model, some shared tools
    LOW = "low"                  # Different model, few shared tools
    INCOMPATIBLE = "incompatible"  # Cannot transfer


@dataclass
class AgentProfile:
    """Profile of an agent for similarity matching."""
    agent_id: str
    model_name: str | None = None
    model_provider: str | None = None
    tools: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    
    # Performance metrics
    total_missions: int = 0
    success_rate: float = 0.0
    avg_latency: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "agent_id": self.agent_id,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "tools": self.tools,
            "capabilities": self.capabilities,
            "config": self.config,
            "total_missions": self.total_missions,
            "success_rate": self.success_rate,
            "avg_latency": self.avg_latency,
        }


@dataclass
class TransferableKnowledge:
    """Knowledge that can be transferred between agents."""
    knowledge_id: str
    transfer_type: TransferType
    source_agent_id: str
    
    # The actual knowledge
    content: dict[str, Any]
    
    # Transfer metadata
    confidence: float = 0.5
    source_success_rate: float = 0.0
    source_applications: int = 0
    
    # Adaptation requirements
    requires_adaptation: bool = False
    adaptation_hints: dict[str, Any] = field(default_factory=dict)
    
    # Transfer constraints
    min_similarity: AgentSimilarity = AgentSimilarity.MEDIUM
    compatible_models: list[str] = field(default_factory=list)
    incompatible_models: list[str] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "knowledge_id": self.knowledge_id,
            "transfer_type": self.transfer_type.value,
            "source_agent_id": self.source_agent_id,
            "content": self.content,
            "confidence": self.confidence,
            "source_success_rate": self.source_success_rate,
            "source_applications": self.source_applications,
            "requires_adaptation": self.requires_adaptation,
            "adaptation_hints": self.adaptation_hints,
            "min_similarity": self.min_similarity.value,
            "compatible_models": self.compatible_models,
            "incompatible_models": self.incompatible_models,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class TransferResult:
    """Result of a knowledge transfer attempt."""
    transfer_id: str
    knowledge: TransferableKnowledge
    target_agent_id: str
    status: TransferStatus
    
    # Similarity assessment
    similarity: AgentSimilarity = AgentSimilarity.MEDIUM
    similarity_score: float = 0.0
    
    # Adaptation applied
    adaptation_applied: bool = False
    adapted_content: dict[str, Any] | None = None
    
    # Outcome (if verified)
    verification_outcome: bool | None = None
    target_success_rate: float | None = None
    
    # Timing
    transferred_at: datetime | None = None
    verified_at: datetime | None = None
    
    # Error info
    error_message: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "transfer_id": self.transfer_id,
            "knowledge_id": self.knowledge.knowledge_id,
            "target_agent_id": self.target_agent_id,
            "status": self.status.value,
            "similarity": self.similarity.value,
            "similarity_score": self.similarity_score,
            "adaptation_applied": self.adaptation_applied,
            "adapted_content": self.adapted_content,
            "verification_outcome": self.verification_outcome,
            "target_success_rate": self.target_success_rate,
            "transferred_at": self.transferred_at.isoformat() if self.transferred_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "error_message": self.error_message,
        }


# ============================================================================
# KNOWLEDGE TRANSFER AGENT
# ============================================================================

class KnowledgeTransferAgent:
    """
    Manages knowledge transfer between agents.
    
    This class identifies transferable knowledge, assesses agent
    similarity, adapts knowledge for target agents, and tracks
    transfer success.
    """
    
    # Similarity thresholds
    SIMILARITY_THRESHOLDS = {
        AgentSimilarity.IDENTICAL: 0.95,
        AgentSimilarity.HIGH: 0.75,
        AgentSimilarity.MEDIUM: 0.50,
        AgentSimilarity.LOW: 0.25,
        AgentSimilarity.INCOMPATIBLE: 0.0,
    }
    
    # Minimum confidence for transfer
    MIN_TRANSFER_CONFIDENCE = 0.6
    MIN_SOURCE_APPLICATIONS = 5
    
    def __init__(
        self,
        knowledge_graph=None,
        strategy_evolver=None,
        success_learner=None,
    ):
        """
        Initialize the knowledge transfer agent.
        
        Args:
            knowledge_graph: Optional knowledge graph
            strategy_evolver: Optional strategy evolver
            success_learner: Optional success learner
        """
        self.knowledge_graph = knowledge_graph
        self.strategy_evolver = strategy_evolver
        self.success_learner = success_learner
        
        # Agent profiles
        self._agent_profiles: dict[str, AgentProfile] = {}
        
        # Transfer tracking
        self._transfers: dict[str, TransferResult] = {}
        self._transfer_history: list[TransferResult] = []
        
        # Knowledge cache
        self._transferable_knowledge: dict[str, TransferableKnowledge] = {}
    
    # ========================================================================
    # AGENT PROFILE MANAGEMENT
    # ========================================================================
    
    async def register_agent(
        self,
        agent_id: str,
        model_name: str | None = None,
        model_provider: str | None = None,
        tools: list[str] | None = None,
        capabilities: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> AgentProfile:
        """
        Register or update an agent profile.
        
        Args:
            agent_id: The agent ID
            model_name: Optional model name
            model_provider: Optional model provider
            tools: Optional list of tools
            capabilities: Optional list of capabilities
            config: Optional configuration
            
        Returns:
            The agent profile
        """
        profile = AgentProfile(
            agent_id=agent_id,
            model_name=model_name,
            model_provider=model_provider,
            tools=tools or [],
            capabilities=capabilities or [],
            config=config or {},
        )
        
        self._agent_profiles[agent_id] = profile
        
        logger.debug(f"Registered agent profile for {agent_id}")
        return profile
    
    def get_agent_profile(self, agent_id: str) -> AgentProfile | None:
        """Get an agent profile."""
        return self._agent_profiles.get(agent_id)
    
    async def update_agent_metrics(
        self,
        agent_id: str,
        total_missions: int | None = None,
        success_rate: float | None = None,
        avg_latency: float | None = None,
    ) -> None:
        """Update agent performance metrics."""
        profile = self._agent_profiles.get(agent_id)
        if not profile:
            return
        
        if total_missions is not None:
            profile.total_missions = total_missions
        if success_rate is not None:
            profile.success_rate = success_rate
        if avg_latency is not None:
            profile.avg_latency = avg_latency
    
    # ========================================================================
    # SIMILARITY ASSESSMENT
    # ========================================================================
    
    async def calculate_similarity(
        self,
        source_agent_id: str,
        target_agent_id: str,
    ) -> tuple[AgentSimilarity, float]:
        """
        Calculate similarity between two agents.
        
        Args:
            source_agent_id: Source agent ID
            target_agent_id: Target agent ID
            
        Returns:
            Tuple of (similarity_level, similarity_score)
        """
        source = self._agent_profiles.get(source_agent_id)
        target = self._agent_profiles.get(target_agent_id)
        
        if not source or not target:
            return AgentSimilarity.INCOMPATIBLE, 0.0
        
        scores = []
        
        # Model similarity (weight: 0.3)
        model_score = self._calculate_model_similarity(source, target)
        scores.append((model_score, 0.3))
        
        # Tool overlap (weight: 0.4)
        tool_score = self._calculate_tool_similarity(source, target)
        scores.append((tool_score, 0.4))
        
        # Capability overlap (weight: 0.2)
        capability_score = self._calculate_capability_similarity(source, target)
        scores.append((capability_score, 0.2))
        
        # Performance similarity (weight: 0.1)
        performance_score = self._calculate_performance_similarity(source, target)
        scores.append((performance_score, 0.1))
        
        # Weighted average
        total_weight = sum(w for _, w in scores)
        weighted_score = sum(s * w for s, w in scores) / total_weight
        
        # Determine similarity level
        similarity_level = AgentSimilarity.INCOMPATIBLE
        for level, threshold in self.SIMILARITY_THRESHOLDS.items():
            if weighted_score >= threshold:
                similarity_level = level
                break
        
        return similarity_level, weighted_score
    
    def _calculate_model_similarity(
        self,
        source: AgentProfile,
        target: AgentProfile,
    ) -> float:
        """Calculate model similarity."""
        # Same model name = high similarity
        if source.model_name and target.model_name:
            if source.model_name == target.model_name:
                return 1.0
            
            # Same provider = medium similarity
            if source.model_provider and target.model_provider:
                if source.model_provider == target.model_provider:
                    return 0.7
            
            # Different models from same family
            source_family = source.model_name.split("-")[0]
            target_family = target.model_name.split("-")[0]
            if source_family == target_family:
                return 0.5
        
        return 0.2  # Default low similarity
    
    def _calculate_tool_similarity(
        self,
        source: AgentProfile,
        target: AgentProfile,
    ) -> float:
        """Calculate tool overlap similarity."""
        if not source.tools and not target.tools:
            return 1.0  # Both have no tools
        
        if not source.tools or not target.tools:
            return 0.0  # One has tools, one doesn't
        
        source_tools = set(source.tools)
        target_tools = set(target.tools)
        
        intersection = len(source_tools & target_tools)
        union = len(source_tools | target_tools)
        
        if union == 0:
            return 1.0
        
        return intersection / union
    
    def _calculate_capability_similarity(
        self,
        source: AgentProfile,
        target: AgentProfile,
    ) -> float:
        """Calculate capability overlap similarity."""
        if not source.capabilities and not target.capabilities:
            return 1.0
        
        if not source.capabilities or not target.capabilities:
            return 0.5
        
        source_caps = set(source.capabilities)
        target_caps = set(target.capabilities)
        
        intersection = len(source_caps & target_caps)
        union = len(source_caps | target_caps)
        
        if union == 0:
            return 1.0
        
        return intersection / union
    
    def _calculate_performance_similarity(
        self,
        source: AgentProfile,
        target: AgentProfile,
    ) -> float:
        """Calculate performance similarity."""
        if source.success_rate == 0 and target.success_rate == 0:
            return 1.0
        
        if source.success_rate == 0 or target.success_rate == 0:
            return 0.5
        
        # Similar success rates = higher similarity
        rate_diff = abs(source.success_rate - target.success_rate)
        return 1.0 - rate_diff
    
    # ========================================================================
    # KNOWLEDGE IDENTIFICATION
    # ========================================================================
    
    async def identify_transferable_knowledge(
        self,
        source_agent_id: str,
        knowledge_type: TransferType = TransferType.STRATEGY,
        min_confidence: float = None,
        min_applications: int = None,
    ) -> list[TransferableKnowledge]:
        """
        Identify knowledge that can be transferred from an agent.
        
        Args:
            source_agent_id: Source agent ID
            knowledge_type: Type of knowledge to identify
            min_confidence: Minimum confidence threshold
            min_applications: Minimum applications threshold
            
        Returns:
            List of transferable knowledge items
        """
        min_confidence = min_confidence or self.MIN_TRANSFER_CONFIDENCE
        min_applications = min_applications or self.MIN_SOURCE_APPLICATIONS
        
        transferable = []
        
        if knowledge_type == TransferType.STRATEGY:
            transferable.extend(
                await self._identify_strategy_knowledge(
                    source_agent_id, min_confidence, min_applications
                )
            )
        
        elif knowledge_type == TransferType.PATTERN:
            transferable.extend(
                await self._identify_pattern_knowledge(
                    source_agent_id, min_confidence, min_applications
                )
            )
        
        elif knowledge_type == TransferType.FAILURE_MAPPING:
            transferable.extend(
                await self._identify_failure_mapping_knowledge(
                    source_agent_id, min_confidence
                )
            )
        
        return transferable
    
    async def _identify_strategy_knowledge(
        self,
        source_agent_id: str,
        min_confidence: float,
        min_applications: int,
    ) -> list[TransferableKnowledge]:
        """Identify transferable strategy knowledge."""
        knowledge_items = []
        
        if not self.strategy_evolver:
            return knowledge_items
        
        # Get all established variants for this agent
        variants = self.strategy_evolver.get_all_variants(
            status=StrategyStatus.ESTABLISHED
        )
        
        for variant in variants:
            if variant.confidence < min_confidence:
                continue
            
            if variant.applications < min_applications:
                continue
            
            knowledge = TransferableKnowledge(
                knowledge_id=f"strategy_{variant.variant_id}",
                transfer_type=TransferType.STRATEGY,
                source_agent_id=source_agent_id,
                content={
                    "strategy_type": variant.base_strategy_type.value,
                    "parameters": variant.parameters,
                    "success_rate": variant.success_rate,
                },
                confidence=variant.confidence,
                source_success_rate=variant.success_rate,
                source_applications=variant.applications,
                min_similarity=AgentSimilarity.MEDIUM,
            )
            
            knowledge_items.append(knowledge)
            self._transferable_knowledge[knowledge.knowledge_id] = knowledge
        
        return knowledge_items
    
    async def _identify_pattern_knowledge(
        self,
        source_agent_id: str,
        min_confidence: float,
        min_applications: int,
    ) -> list[TransferableKnowledge]:
        """Identify transferable success patterns."""
        knowledge_items = []
        
        if not self.success_learner:
            return knowledge_items
        
        patterns = await self.success_learner.get_patterns_for_agent(
            source_agent_id,
            min_confidence=min_confidence,
        )
        
        for pattern in patterns:
            if pattern.success_count < min_applications:
                continue
            
            knowledge = TransferableKnowledge(
                knowledge_id=f"pattern_{pattern.pattern_id}",
                transfer_type=TransferType.PATTERN,
                source_agent_id=source_agent_id,
                content=pattern.to_dict(),
                confidence=pattern.confidence,
                source_success_rate=pattern.confidence,
                source_applications=pattern.success_count,
                requires_adaptation=True,
                adaptation_hints={
                    "tool_sequence": "May need adjustment for target tools",
                    "config_snapshot": "Values may need scaling for target model",
                },
                min_similarity=AgentSimilarity.HIGH,
            )
            
            knowledge_items.append(knowledge)
            self._transferable_knowledge[knowledge.knowledge_id] = knowledge
        
        return knowledge_items
    
    async def _identify_failure_mapping_knowledge(
        self,
        source_agent_id: str,
        min_confidence: float,
    ) -> list[TransferableKnowledge]:
        """Identify transferable failure-to-strategy mappings."""
        knowledge_items = []
        
        if not self.knowledge_graph:
            return knowledge_items
        
        # Query knowledge graph for successful mappings
        for failure_type in FailureType:
            strategies = await self.knowledge_graph.get_strategies_for_failure(
                failure_type
            )
            
            for strategy_node, success_rate in strategies:
                if success_rate < min_confidence:
                    continue
                
                knowledge = TransferableKnowledge(
                    knowledge_id=f"mapping_{failure_type.value}_{strategy_node.node_key}",
                    transfer_type=TransferType.FAILURE_MAPPING,
                    source_agent_id=source_agent_id,
                    content={
                        "failure_type": failure_type.value,
                        "strategy_type": strategy_node.node_key,
                        "success_rate": success_rate,
                    },
                    confidence=success_rate,
                    source_success_rate=success_rate,
                    min_similarity=AgentSimilarity.LOW,  # Mappings are widely applicable
                )
                
                knowledge_items.append(knowledge)
                self._transferable_knowledge[knowledge.knowledge_id] = knowledge
        
        return knowledge_items
    
    # ========================================================================
    # KNOWLEDGE TRANSFER
    # ========================================================================
    
    async def transfer_knowledge(
        self,
        source_agent_id: str,
        target_agent_id: str,
        knowledge_type: str = "strategies",
    ) -> list[TransferResult]:
        """
        Transfer learned knowledge from source to target agent.
        
        Args:
            source_agent_id: Source agent ID
            target_agent_id: Target agent ID
            knowledge_type: Type of knowledge to transfer
            
        Returns:
            List of transfer results
        """
        results = []
        
        # Calculate similarity
        similarity, similarity_score = await self.calculate_similarity(
            source_agent_id, target_agent_id
        )
        
        if similarity == AgentSimilarity.INCOMPATIBLE:
            logger.warning(
                f"Agents {source_agent_id} and {target_agent_id} are incompatible"
            )
            return results
        
        # Identify transferable knowledge
        transfer_type = TransferType(knowledge_type.rstrip("s"))  # Handle plural
        knowledge_items = await self.identify_transferable_knowledge(
            source_agent_id, transfer_type
        )
        
        for knowledge in knowledge_items:
            # Check minimum similarity
            similarity_levels = list(AgentSimilarity)
            min_idx = similarity_levels.index(knowledge.min_similarity)
            actual_idx = similarity_levels.index(similarity)
            
            if actual_idx > min_idx:
                logger.debug(
                    f"Skipping {knowledge.knowledge_id}: similarity {similarity.value} "
                    f"below minimum {knowledge.min_similarity.value}"
                )
                continue
            
            # Create transfer result
            transfer_id = f"transfer_{knowledge.knowledge_id}_to_{target_agent_id}"
            
            result = TransferResult(
                transfer_id=transfer_id,
                knowledge=knowledge,
                target_agent_id=target_agent_id,
                status=TransferStatus.PENDING,
                similarity=similarity,
                similarity_score=similarity_score,
            )
            
            # Adapt knowledge if needed
            if knowledge.requires_adaptation:
                adapted_content = await self._adapt_knowledge(
                    knowledge, target_agent_id, similarity_score
                )
                result.adaptation_applied = True
                result.adapted_content = adapted_content
            
            # Apply knowledge
            success = await self._apply_knowledge(result)
            
            if success:
                result.status = TransferStatus.APPLIED
                result.transferred_at = datetime.now(UTC)
            else:
                result.status = TransferStatus.FAILED
            
            self._transfers[transfer_id] = result
            self._transfer_history.append(result)
            results.append(result)
        
        return results
    
    async def _adapt_knowledge(
        self,
        knowledge: TransferableKnowledge,
        target_agent_id: str,
        similarity_score: float,
    ) -> dict[str, Any]:
        """
        Adapt knowledge for target agent.
        
        Args:
            knowledge: The knowledge to adapt
            target_agent_id: Target agent ID
            similarity_score: Similarity score
            
        Returns:
            Adapted content
        """
        content = knowledge.content.copy()
        target_profile = self._agent_profiles.get(target_agent_id)
        
        if not target_profile:
            return content
        
        # Adapt based on knowledge type
        if knowledge.transfer_type == TransferType.PATTERN:
            # Adapt tool sequence
            if "tool_sequence" in content:
                source_tools = set(content["tool_sequence"])
                target_tools = set(target_profile.tools)
                
                # Keep only tools that target has
                adapted_sequence = [
                    t for t in content["tool_sequence"]
                    if t in target_tools
                ]
                
                # Find alternatives for missing tools
                missing_tools = source_tools - target_tools
                for tool in missing_tools:
                    alternative = self._find_tool_alternative(tool, target_tools)
                    if alternative:
                        adapted_sequence.append(alternative)
                
                content["tool_sequence"] = adapted_sequence
            
            # Scale config values based on model
            if "config_snapshot" in content and target_profile.model_name:
                # Adjust timeouts and rate limits for different models
                if "timeout" in content["config_snapshot"]:
                    # Scale by similarity
                    content["config_snapshot"]["timeout"] *= (0.8 + 0.4 * similarity_score)
        
        return content
    
    def _find_tool_alternative(
        self,
        tool: str,
        available_tools: set[str],
    ) -> str | None:
        """Find an alternative tool."""
        # Simple mapping of common alternatives
        alternatives = {
            "web_search": ["search", "browser_search"],
            "code_execution": ["execute_code", "run_code"],
            "file_read": ["read_file", "get_file"],
            "file_write": ["write_file", "save_file"],
        }
        
        for alt in alternatives.get(tool, []):
            if alt in available_tools:
                return alt
        
        return None
    
    async def _apply_knowledge(self, result: TransferResult) -> bool:
        """
        Apply transferred knowledge to target agent.
        
        Args:
            result: The transfer result
            
            Returns:
            True if applied successfully
        """
        content = result.adapted_content or result.knowledge.content
        
        try:
            # Store in knowledge graph
            if self.knowledge_graph:
                from .knowledge_graph import NodeType
                
                # Create node for transferred knowledge
                await self.knowledge_graph.add_node(
                    NodeType.PATTERN,
                    result.transfer_id,
                    properties={
                        "source_agent": result.knowledge.source_agent_id,
                        "target_agent": result.target_agent_id,
                        "content": content,
                        "transferred_at": result.transferred_at.isoformat() if result.transferred_at else None,
                    },
                )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to apply knowledge: {e}")
            result.error_message = str(e)
            return False
    
    # ========================================================================
    # VERIFICATION
    # ========================================================================
    
    async def verify_transfer(
        self,
        transfer_id: str,
        outcome: bool,
        success_rate: float | None = None,
    ) -> TransferResult | None:
        """
        Verify a transferred knowledge item.
        
        Args:
            transfer_id: The transfer ID
            outcome: Whether the transfer was successful
            success_rate: Optional success rate after transfer
            
        Returns:
            Updated transfer result
        """
        result = self._transfers.get(transfer_id)
        if not result:
            return None
        
        result.verification_outcome = outcome
        result.target_success_rate = success_rate
        result.verified_at = datetime.now(UTC)
        
        if outcome:
            result.status = TransferStatus.VERIFIED
        else:
            result.status = TransferStatus.FAILED
        
        return result
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def get_transfer_statistics(self) -> dict[str, Any]:
        """Get transfer statistics."""
        status_counts = defaultdict(int)
        for result in self._transfer_history:
            status_counts[result.status.value] += 1
        
        return {
            "total_transfers": len(self._transfer_history),
            "by_status": dict(status_counts),
            "registered_agents": len(self._agent_profiles),
            "transferable_knowledge_items": len(self._transferable_knowledge),
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_knowledge_transfer: KnowledgeTransferAgent | None = None


def get_knowledge_transfer() -> KnowledgeTransferAgent:
    """Get the singleton knowledge transfer instance."""
    global _knowledge_transfer
    if _knowledge_transfer is None:
        _knowledge_transfer = KnowledgeTransferAgent()
    return _knowledge_transfer


def initialize_knowledge_transfer(
    knowledge_graph=None,
    strategy_evolver=None,
    success_learner=None,
) -> KnowledgeTransferAgent:
    """Initialize the knowledge transfer agent."""
    global _knowledge_transfer
    _knowledge_transfer = KnowledgeTransferAgent(
        knowledge_graph, strategy_evolver, success_learner
    )
    return _knowledge_transfer
