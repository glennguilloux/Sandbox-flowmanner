#!/usr/bin/env python3
"""
Knob Manager - Manages improvement knobs via AdaptationRuleDB

This module provides the interface for reading and writing improvement knobs
without requiring new database migrations. It uses the existing adaptation_rules
table with the action_params JSON column for flexibility.

Key Design Principle: Knobs are configuration values that can be safely adjusted,
not raw Python code. This enables safe, reversible improvements.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .causal_decomposer import (
    ImprovementStrategy,
    KnobType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# KNOB DATA STRUCTURES
# ============================================================================


@dataclass
class ImprovementKnob:
    """
    Represents an improvement knob stored in AdaptationRuleDB.

    Knobs are configuration values that can be adjusted to improve agent behavior.
    They are stored in the action_params JSON column of adaptation_rules table.
    """

    knob_name: str
    knob_type: KnobType
    current_value: Any
    default_value: Any

    # Value constraints
    value_range: dict[str, Any] | None = None  # {"min": x, "max": y} or ["option1", "option2"]

    # Auto-tuning configuration
    auto_tune_enabled: bool = True
    tuning_source: str = "manual"  # "manual", "causal_decomposer", "ab_test"

    # History tracking
    modification_history: list[dict[str, Any]] = field(default_factory=list)
    last_modified: datetime = field(default_factory=datetime.utcnow)

    # Metadata
    agent_id: str | None = None  # None = system-wide knob
    rule_id: str | None = None  # Database rule ID
    description: str = ""

    def to_action_params(self) -> dict[str, Any]:
        """Convert to action_params format for storage"""
        return {
            "knob_name": self.knob_name,
            "knob_type": self.knob_type.value,
            "current_value": self.current_value,
            "default_value": self.default_value,
            "value_range": self.value_range,
            "auto_tune_enabled": self.auto_tune_enabled,
            "tuning_source": self.tuning_source,
            "modification_history": self.modification_history[-20:],  # Keep last 20
            "last_modified": self.last_modified.isoformat(),
            "description": self.description,
        }

    @classmethod
    def from_action_params(cls, params: dict[str, Any], rule_id: str = None, agent_id: str = None) -> "ImprovementKnob":
        """Create from action_params dictionary"""
        return cls(
            knob_name=params.get("knob_name", "unknown"),
            knob_type=KnobType(params.get("knob_type", "retry_config")),
            current_value=params.get("current_value"),
            default_value=params.get("default_value"),
            value_range=params.get("value_range"),
            auto_tune_enabled=params.get("auto_tune_enabled", True),
            tuning_source=params.get("tuning_source", "manual"),
            modification_history=params.get("modification_history", []),
            last_modified=(
                datetime.fromisoformat(params["last_modified"]) if "last_modified" in params else datetime.now(UTC)
            ),
            agent_id=agent_id,
            rule_id=rule_id,
            description=params.get("description", ""),
        )

    def record_modification(self, old_value: Any, reason: str, strategy_id: str = None):
        """Record a modification in history"""
        self.modification_history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "old_value": old_value,
                "new_value": self.current_value,
                "reason": reason,
                "strategy_id": strategy_id,
            }
        )
        self.last_modified = datetime.now(UTC)


@dataclass
class KnobAdjustment:
    """Represents a planned or applied knob adjustment"""

    knob: ImprovementKnob
    old_value: Any
    new_value: Any
    strategy: ImprovementStrategy | None = None
    applied_at: datetime | None = None
    rollback_at: datetime | None = None
    success: bool | None = None  # None = not yet evaluated

    @property
    def is_applied(self) -> bool:
        return self.applied_at is not None

    @property
    def is_rolled_back(self) -> bool:
        return self.rollback_at is not None


# ============================================================================
# KNOB MANAGER - Main class for knob operations
# ============================================================================


class KnobManager:
    """
    Manages improvement knobs via the existing AdaptationRuleDB table.

    This class provides:
    - Reading knobs from the database
    - Writing/updating knobs
    - Applying strategies as knob adjustments
    - Rollback support
    - Oscillation detection
    """

    # Rule type for improvement knobs in adaptation_rules table
    RULE_TYPE_KNOB = "improvement_knob"

    def __init__(
        self,
        db_session: AsyncSession,
        oscillation_window_hours: int = 24,
        max_modifications_per_knob: int = 5,
    ):
        self.db_session = db_session
        self.oscillation_window_hours = oscillation_window_hours
        self.max_modifications_per_knob = max_modifications_per_knob

        # Cache for knobs (reduces DB queries)
        self._knob_cache: dict[str, ImprovementKnob] = {}

    async def get_knob(
        self,
        knob_type: KnobType,
        agent_id: str | None = None,
    ) -> ImprovementKnob | None:
        """
        Get a knob by type and optional agent_id.

        Args:
            knob_type: The type of knob to retrieve
            agent_id: Optional agent ID (None for system-wide knobs)

        Returns:
            ImprovementKnob or None if not found
        """
        cache_key = f"{knob_type.value}:{agent_id or 'system'}"

        # Check cache first
        if cache_key in self._knob_cache:
            return self._knob_cache[cache_key]

        # Query database
        try:
            from app.models.learning_models import AdaptationRuleDB

            stmt = select(AdaptationRuleDB).where(
                AdaptationRuleDB.rule_type == self.RULE_TYPE_KNOB,
                (AdaptationRuleDB.agent_id == agent_id if agent_id else AdaptationRuleDB.agent_id.is_(None)),
            )

            result = await self.db_session.execute(stmt)
            rules = result.scalars().all()

            # Find the matching knob
            for rule in rules:
                params = rule.action_params or {}
                if params.get("knob_type") == knob_type.value:
                    knob = ImprovementKnob.from_action_params(
                        params,
                        rule_id=str(rule.rule_id),
                        agent_id=agent_id,
                    )
                    self._knob_cache[cache_key] = knob
                    return knob

            return None

        except Exception as e:
            logger.error("Error getting knob %s: %s", knob_type.value, e)
            return None

    async def get_all_knobs(
        self,
        agent_id: str | None = None,
    ) -> list[ImprovementKnob]:
        """
        Get all knobs for an agent or system-wide.

        Args:
            agent_id: Optional agent ID (None for system-wide knobs)

        Returns:
            List of ImprovementKnob objects
        """
        try:
            from app.models.learning_models import AdaptationRuleDB

            stmt = select(AdaptationRuleDB).where(
                AdaptationRuleDB.rule_type == self.RULE_TYPE_KNOB,
            )

            if agent_id:
                stmt = stmt.where(AdaptationRuleDB.agent_id == agent_id)
            else:
                stmt = stmt.where(AdaptationRuleDB.agent_id.is_(None))

            result = await self.db_session.execute(stmt)
            rules = result.scalars().all()

            knobs = []
            for rule in rules:
                params = rule.action_params or {}
                knob = ImprovementKnob.from_action_params(
                    params,
                    rule_id=str(rule.rule_id),
                    agent_id=agent_id,
                )
                knobs.append(knob)

            return knobs

        except Exception as e:
            logger.error("Error getting all knobs: %s", e)
            return []

    async def set_knob(
        self,
        knob: ImprovementKnob,
        reason: str = "manual_update",
        strategy_id: str | None = None,
    ) -> bool:
        """
        Set/update a knob value.

        Args:
            knob: The knob to set
            reason: Reason for the change
            strategy_id: Optional strategy ID that triggered this change

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.models.learning_models import AdaptationRuleDB

            # Check for oscillation
            if await self._would_cause_oscillation(knob):
                logger.warning("Oscillation detected for knob %s, skipping update", knob.knob_name)
                return False

            # Get existing knob to record history
            existing = await self.get_knob(knob.knob_type, knob.agent_id)
            old_value = existing.current_value if existing else knob.default_value

            # Record modification
            knob.record_modification(old_value, reason, strategy_id)

            if existing and existing.rule_id:
                # Update existing rule
                stmt = (
                    update(AdaptationRuleDB)
                    .where(AdaptationRuleDB.rule_id == existing.rule_id)
                    .values(
                        action_params=knob.to_action_params(),
                        updated_at=datetime.now(UTC),
                    )
                )
                await self.db_session.execute(stmt)
            else:
                # Create new rule
                new_rule = AdaptationRuleDB(
                    rule_id=str(uuid4()),
                    agent_id=knob.agent_id,
                    rule_type=self.RULE_TYPE_KNOB,
                    condition={},  # No condition for knobs
                    action_params=knob.to_action_params(),
                    priority=100,  # Default priority
                    enabled=True,
                )
                self.db_session.add(new_rule)

            await self.db_session.commit()

            # Update cache
            cache_key = f"{knob.knob_type.value}:{knob.agent_id or 'system'}"
            self._knob_cache[cache_key] = knob

            logger.info(
                "Set knob %s to %s (reason: %s)",
                knob.knob_name,
                knob.current_value,
                reason,
            )
            return True

        except Exception as e:
            logger.error("Error setting knob %s: %s", knob.knob_name, e)
            await self.db_session.rollback()
            return False

    async def apply_strategy(
        self,
        strategy: ImprovementStrategy,
        agent_id: str | None = None,
    ) -> KnobAdjustment | None:
        """
        Apply an improvement strategy as a knob adjustment.

        Args:
            strategy: The strategy to apply
            agent_id: Optional agent ID

        Returns:
            KnobAdjustment if successful, None otherwise
        """
        # Get or create the knob
        knob = await self.get_knob(strategy.knob, agent_id)

        if not knob:
            # Create new knob with default values
            knob = ImprovementKnob(
                knob_name=strategy.knob.value,
                knob_type=strategy.knob,
                current_value=strategy.knob_value,
                default_value=strategy.rollback_value,
                auto_tune_enabled=True,
                tuning_source="causal_decomposer",
                agent_id=agent_id,
                description=strategy.description,
            )
        else:
            # Update existing knob
            old_value = knob.current_value
            knob.current_value = strategy.knob_value
            knob.tuning_source = "causal_decomposer"

        # Set the knob
        success = await self.set_knob(
            knob,
            reason=f"Strategy: {strategy.strategy_type.value}",
            strategy_id=strategy.strategy_id,
        )

        if success:
            return KnobAdjustment(
                knob=knob,
                old_value=old_value,
                new_value=strategy.knob_value,
                strategy=strategy,
                applied_at=datetime.now(UTC),
            )

        return None

    async def rollback_knob(
        self,
        knob_type: KnobType,
        agent_id: str | None = None,
        reason: str = "manual_rollback",
    ) -> bool:
        """
        Rollback a knob to its default value.

        Args:
            knob_type: The type of knob to rollback
            agent_id: Optional agent ID
            reason: Reason for rollback

        Returns:
            True if successful, False otherwise
        """
        knob = await self.get_knob(knob_type, agent_id)

        if not knob:
            logger.warning("Knob %s not found for rollback", knob_type.value)
            return False

        old_value = knob.current_value
        knob.current_value = knob.default_value

        success = await self.set_knob(knob, reason=f"Rollback: {reason}")

        if success:
            logger.info(
                "Rolled back knob %s from %s to %s",
                knob.knob_name,
                old_value,
                knob.default_value,
            )
            return True

        return False

    async def _would_cause_oscillation(self, knob: ImprovementKnob) -> bool:
        """
        Check if a knob change would cause oscillation.

        Oscillation is detected when:
        1. The same knob has been modified multiple times recently
        2. The new value is close to a recently reverted value

        Args:
            knob: The knob to check

        Returns:
            True if oscillation would occur, False otherwise
        """
        if not knob.modification_history:
            return False

        # Check recent modifications within the window
        window_start = datetime.now(UTC) - timedelta(hours=self.oscillation_window_hours)
        recent_mods = [m for m in knob.modification_history if datetime.fromisoformat(m["timestamp"]) > window_start]

        # Too many recent modifications
        if len(recent_mods) >= self.max_modifications_per_knob:
            logger.warning(
                "Oscillation risk: %s modifications to %s in last %s hours",
                len(recent_mods),
                knob.knob_name,
                self.oscillation_window_hours,
            )
            return True

        # Check if we're oscillating between values
        if len(recent_mods) >= 2:
            values = [m["new_value"] for m in recent_mods[-3:]]
            # If we're going back to a value we just left
            if knob.current_value in values[:-1]:
                logger.warning("Oscillation detected: %s returning to recent value", knob.knob_name)
                return True

        return False

    def clear_cache(self):
        """Clear the knob cache"""
        self._knob_cache.clear()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def get_knob_manager(db_session: AsyncSession) -> KnobManager:
    """Factory function to get a KnobManager instance"""
    return KnobManager(db_session=db_session)


# ============================================================================
# DEFAULT KNOBS - Initial knob configurations
# ============================================================================

DEFAULT_KNOBS: list[dict[str, Any]] = [
    # Infrastructure knobs
    {
        "knob_name": "default_retry_config",
        "knob_type": KnobType.RETRY_CONFIG,
        "current_value": {"max_retries": 2, "backoff_factor": 1.5},
        "default_value": {"max_retries": 2, "backoff_factor": 1.5},
        "value_range": {
            "max_retries": {"min": 0, "max": 5},
            "backoff_factor": {"min": 1.0, "max": 5.0},
        },
        "description": "Default retry configuration for tool calls",
    },
    {
        "knob_name": "default_timeout_ms",
        "knob_type": KnobType.TIMEOUT_MS,
        "current_value": 30000,
        "default_value": 30000,
        "value_range": {"min": 5000, "max": 120000},
        "description": "Default timeout for tool calls in milliseconds",
    },
    {
        "knob_name": "default_rate_limit",
        "knob_type": KnobType.RATE_LIMIT,
        "current_value": {"requests_per_second": 100, "burst": 200},
        "default_value": {"requests_per_second": 100, "burst": 200},
        "description": "Default rate limiting configuration",
    },
    # RAG knobs
    {
        "knob_name": "default_rag_top_k",
        "knob_type": KnobType.RAG_TOP_K,
        "current_value": 5,
        "default_value": 5,
        "value_range": {"min": 1, "max": 20},
        "description": "Default number of documents to retrieve in RAG",
    },
    {
        "knob_name": "default_rag_threshold",
        "knob_type": KnobType.RAG_THRESHOLD,
        "current_value": 0.7,
        "default_value": 0.7,
        "value_range": {"min": 0.3, "max": 0.95},
        "description": "Default similarity threshold for RAG retrieval",
    },
    # LLM knobs
    {
        "knob_name": "default_temperature",
        "knob_type": KnobType.TEMPERATURE,
        "current_value": 0.7,
        "default_value": 0.7,
        "value_range": {"min": 0.0, "max": 2.0},
        "description": "Default LLM temperature",
    },
    {
        "knob_name": "default_max_tokens",
        "knob_type": KnobType.MAX_TOKENS,
        "current_value": 4096,
        "default_value": 4096,
        "value_range": {"min": 256, "max": 32768},
        "description": "Default max tokens for LLM responses",
    },
]


async def initialize_default_knobs(db_session: AsyncSession, agent_id: str | None = None) -> int:
    """
    Initialize default knobs for an agent or system-wide.

    Args:
        db_session: Database session
        agent_id: Optional agent ID (None for system-wide)

    Returns:
        Number of knobs initialized
    """
    manager = KnobManager(db_session=db_session)
    initialized = 0

    for knob_data in DEFAULT_KNOBS:
        knob = ImprovementKnob(
            knob_name=knob_data["knob_name"],
            knob_type=knob_data["knob_type"],
            current_value=knob_data["current_value"],
            default_value=knob_data["default_value"],
            value_range=knob_data.get("value_range"),
            description=knob_data.get("description", ""),
            agent_id=agent_id,
        )

        # Check if already exists
        existing = await manager.get_knob(knob.knob_type, agent_id)
        if not existing:
            success = await manager.set_knob(knob, reason="initialization")
            if success:
                initialized += 1

    return initialized


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Constants
    "DEFAULT_KNOBS",
    # Dataclasses
    "ImprovementKnob",
    "KnobAdjustment",
    # Classes
    "KnobManager",
    # Functions
    "get_knob_manager",
    "initialize_default_knobs",
]
