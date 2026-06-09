"""
Failure Repository for Autonomous Self-Improvement System.

This module provides database persistence for failure telemetry,
enabling historical analysis and pattern detection across sessions.

Phase 5C of the Autonomous Self-Improvement Architecture.
"""

import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)

# Import failure types from Phase 1
from .failure_types import (
    FailureContext,
    FailureSeverity,
    FailureType,
)

# ============================================================================
# DATABASE MODEL (SQLAlchemy)
# ============================================================================

try:
    from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()

    class FailureContextModel(Base):
        """
        Database model for storing failure contexts.

        This maps to a 'failure_contexts' table in the database.
        """

        __tablename__ = "failure_contexts"

        id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
        failure_id = Column(String(36), unique=True, nullable=False, index=True)

        # Classification
        failure_type = Column(String(50), nullable=False, index=True)
        severity = Column(String(20), nullable=False)
        is_infrastructure = Column(Boolean, default=False)

        # Context
        agent_id = Column(String(100), index=True)
        mission_id = Column(String(36), index=True)
        task_id = Column(String(36))
        tool_name = Column(String(100), index=True)

        # Timing
        timestamp = Column(DateTime, nullable=False, index=True)
        latency_ms = Column(Float)

        # Error details
        error_message = Column(Text)
        error_type = Column(String(100))
        stack_trace = Column(Text)

        # Input/Output samples (truncated for storage)
        input_sample = Column(JSON)
        output_sample = Column(JSON)

        # Additional context
        context = Column(JSON)

        # Resolution tracking
        resolved = Column(Boolean, default=False)
        resolved_at = Column(DateTime)
        resolution_strategy = Column(String(100))

        # Metadata
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        def to_failure_context(self) -> FailureContext:
            """Convert database model to FailureContext dataclass."""
            return FailureContext(
                failure_id=self.failure_id,
                failure_type=FailureType(self.failure_type),
                severity=FailureSeverity(self.severity),
                timestamp=self.timestamp,
                agent_id=self.agent_id,
                mission_id=self.mission_id,
                task_id=self.task_id,
                tool_name=self.tool_name,
                error_message=self.error_message,
                error_type=self.error_type,
                stack_trace=self.stack_trace,
                input_sample=self.input_sample,
                output_sample=self.output_sample,
                latency_ms=self.latency_ms,
                context=self.context or {},
            )

    DATABASE_AVAILABLE = True

except ImportError:
    logger.warning("SQLAlchemy not available, using in-memory storage")
    DATABASE_AVAILABLE = False
    FailureContextModel = None


# ============================================================================
# FAILURE REPOSITORY
# ============================================================================


class FailureRepository:
    """
    Repository for persisting and querying failure contexts.

    Provides both database-backed and in-memory storage options.
    """

    def __init__(self, db_session=None):
        """
        Initialize the failure repository.

        Args:
            db_session: Optional database session for persistence
        """
        self.db = db_session
        self._memory_store: dict[str, FailureContext] = {}
        self._failure_index: dict[str, list[str]] = {
            "by_agent": {},
            "by_type": {},
            "by_tool": {},
            "by_mission": {},
        }

    async def save(self, context: FailureContext) -> str:
        """
        Save a failure context to the repository.

        Args:
            context: The failure context to save

        Returns:
            The failure ID
        """
        # Always save to memory
        self._memory_store[context.failure_id] = context
        self._update_indices(context)

        # Also save to database if available
        if DATABASE_AVAILABLE and self.db:
            try:
                await self._save_to_database(context)
            except Exception as e:
                logger.warning('Failed to save failure to database: %s', e)

        logger.debug('Saved failure %s of type %s', context.failure_id, context.failure_type.value)
        return context.failure_id

    async def get(self, failure_id: str) -> FailureContext | None:
        """
        Get a failure context by ID.

        Args:
            failure_id: The failure ID

        Returns:
            The failure context, or None if not found
        """
        # Check memory first
        if failure_id in self._memory_store:
            return self._memory_store[failure_id]

        # Check database if available
        if DATABASE_AVAILABLE and self.db:
            try:
                return await self._get_from_database(failure_id)
            except Exception as e:
                logger.warning('Failed to get failure from database: %s', e)

        return None

    async def get_failures_in_window(
        self,
        start_time: datetime,
        end_time: datetime,
        agent_id: str | None = None,
        failure_type: FailureType | None = None,
        limit: int = 100,
    ) -> list[FailureContext]:
        """
        Get failures within a time window.

        Args:
            start_time: Start of time window
            end_time: End of time window
            agent_id: Optional agent ID filter
            failure_type: Optional failure type filter
            limit: Maximum number of results

        Returns:
            List of matching failure contexts
        """
        results = []

        # Query from memory
        for context in self._memory_store.values():
            if context.timestamp < start_time or context.timestamp > end_time:
                continue
            if agent_id and context.agent_id != agent_id:
                continue
            if failure_type and context.failure_type != failure_type:
                continue
            results.append(context)

        # Also query database if available
        if DATABASE_AVAILABLE and self.db:
            try:
                db_results = await self._query_database(
                    start_time, end_time, agent_id, failure_type, limit
                )
                # Merge results, avoiding duplicates
                existing_ids = {c.failure_id for c in results}
                for context in db_results:
                    if context.failure_id not in existing_ids:
                        results.append(context)
            except Exception as e:
                logger.warning('Failed to query failures from database: %s', e)

        # Sort by timestamp descending and limit
        results.sort(key=lambda c: c.timestamp, reverse=True)
        return results[:limit]

    async def get_failures_by_type(
        self,
        failure_type: FailureType,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[FailureContext]:
        """
        Get failures by type.

        Args:
            failure_type: The failure type to filter by
            agent_id: Optional agent ID filter
            limit: Maximum number of results

        Returns:
            List of matching failure contexts
        """
        results = []
        type_key = failure_type.value

        # Use index for faster lookup
        if type_key in self._failure_index["by_type"]:
            for fid in self._failure_index["by_type"][type_key]:
                if fid in self._memory_store:
                    context = self._memory_store[fid]
                    if agent_id is None or context.agent_id == agent_id:
                        results.append(context)

        # Also query database if available
        if DATABASE_AVAILABLE and self.db:
            try:
                db_results = await self._get_by_type_from_database(
                    failure_type, agent_id, limit
                )
                existing_ids = {c.failure_id for c in results}
                for context in db_results:
                    if context.failure_id not in existing_ids:
                        results.append(context)
            except Exception as e:
                logger.warning('Failed to query failures by type from database: %s', e)

        results.sort(key=lambda c: c.timestamp, reverse=True)
        return results[:limit]

    async def get_failures_by_agent(
        self,
        agent_id: str,
        time_window: timedelta = timedelta(hours=24),
        limit: int = 100,
    ) -> list[FailureContext]:
        """
        Get failures for a specific agent.

        Args:
            agent_id: The agent ID
            time_window: Time window to look back
            limit: Maximum number of results

        Returns:
            List of matching failure contexts
        """
        end_time = datetime.now(UTC)
        start_time = end_time - time_window
        return await self.get_failures_in_window(
            start_time, end_time, agent_id=agent_id, limit=limit
        )

    async def get_failure_count_by_type(
        self,
        time_window: timedelta = timedelta(hours=24),
        agent_id: str | None = None,
    ) -> dict[str, int]:
        """
        Get count of failures by type.

        Args:
            time_window: Time window to look back
            agent_id: Optional agent ID filter

        Returns:
            Dictionary mapping failure type to count
        """
        end_time = datetime.now(UTC)
        start_time = end_time - time_window

        failures = await self.get_failures_in_window(
            start_time, end_time, agent_id=agent_id, limit=1000
        )

        counts: dict[str, int] = {}
        for failure in failures:
            key = failure.failure_type.value
            counts[key] = counts.get(key, 0) + 1

        return counts

    async def mark_resolved(
        self,
        failure_id: str,
        resolution_strategy: str,
    ) -> bool:
        """
        Mark a failure as resolved.

        Args:
            failure_id: The failure ID
            resolution_strategy: Description of how it was resolved

        Returns:
            True if successful, False otherwise
        """
        # Update in memory
        if failure_id in self._memory_store:
            context = self._memory_store[failure_id]
            # Create updated context with resolution info
            self._memory_store[failure_id] = FailureContext(
                **{k: v for k, v in asdict(context).items() if k != "context"},
                context={
                    **context.context,
                    "resolved": True,
                    "resolved_at": datetime.now(UTC).isoformat(),
                    "resolution_strategy": resolution_strategy,
                },
            )

        # Update in database if available
        if DATABASE_AVAILABLE and self.db:
            try:
                await self._mark_resolved_in_database(failure_id, resolution_strategy)
            except Exception as e:
                logger.warning('Failed to mark failure resolved in database: %s', e)

        return True

    async def get_unresolved_failures(
        self,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[FailureContext]:
        """
        Get unresolved failures.

        Args:
            agent_id: Optional agent ID filter
            limit: Maximum number of results

        Returns:
            List of unresolved failure contexts
        """
        results = []

        for context in self._memory_store.values():
            if context.context.get("resolved"):
                continue
            if agent_id and context.agent_id != agent_id:
                continue
            results.append(context)

        results.sort(key=lambda c: c.timestamp, reverse=True)
        return results[:limit]

    async def clear_old_failures(
        self, older_than: timedelta = timedelta(days=30)
    ) -> int:
        """
        Clear failures older than the specified age.

        Args:
            older_than: Age threshold for deletion

        Returns:
            Number of failures cleared
        """
        cutoff = datetime.now(UTC) - older_than
        cleared = 0

        # Clear from memory
        to_remove = [
            fid
            for fid, context in self._memory_store.items()
            if context.timestamp < cutoff
        ]

        for fid in to_remove:
            del self._memory_store[fid]
            cleared += 1

        # Rebuild indices
        self._rebuild_indices()

        logger.info('Cleared %s failures older than %s', cleared, older_than)
        return cleared

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _update_indices(self, context: FailureContext) -> None:
        """Update in-memory indices for faster lookups."""
        fid = context.failure_id

        # Index by agent
        if context.agent_id:
            if context.agent_id not in self._failure_index["by_agent"]:
                self._failure_index["by_agent"][context.agent_id] = []
            self._failure_index["by_agent"][context.agent_id].append(fid)

        # Index by type
        type_key = context.failure_type.value
        if type_key not in self._failure_index["by_type"]:
            self._failure_index["by_type"][type_key] = []
        self._failure_index["by_type"][type_key].append(fid)

        # Index by tool
        if context.tool_name:
            if context.tool_name not in self._failure_index["by_tool"]:
                self._failure_index["by_tool"][context.tool_name] = []
            self._failure_index["by_tool"][context.tool_name].append(fid)

        # Index by mission
        if context.mission_id:
            if context.mission_id not in self._failure_index["by_mission"]:
                self._failure_index["by_mission"][context.mission_id] = []
            self._failure_index["by_mission"][context.mission_id].append(fid)

    def _rebuild_indices(self) -> None:
        """Rebuild all in-memory indices."""
        self._failure_index = {
            "by_agent": {},
            "by_type": {},
            "by_tool": {},
            "by_mission": {},
        }

        for context in self._memory_store.values():
            self._update_indices(context)

    async def _save_to_database(self, context: FailureContext) -> None:
        """Save failure context to database."""
        if not DATABASE_AVAILABLE or not self.db:
            return

        model = FailureContextModel(
            failure_id=context.failure_id,
            failure_type=context.failure_type.value,
            severity=context.severity.value,
            is_infrastructure=context.is_infrastructure,
            agent_id=context.agent_id,
            mission_id=context.mission_id,
            task_id=context.task_id,
            tool_name=context.tool_name,
            timestamp=context.timestamp,
            latency_ms=context.latency_ms,
            error_message=context.error_message,
            error_type=context.error_type,
            stack_trace=context.stack_trace,
            input_sample=context.input_sample,
            output_sample=context.output_sample,
            context=context.context,
        )

        self.db.add(model)
        await self.db.commit()

    async def _get_from_database(self, failure_id: str) -> FailureContext | None:
        """Get failure context from database."""
        if not DATABASE_AVAILABLE or not self.db:
            return None

        model = (
            self.db.query(FailureContextModel)
            .filter(FailureContextModel.failure_id == failure_id)
            .first()
        )

        return model.to_failure_context() if model else None

    async def _query_database(
        self,
        start_time: datetime,
        end_time: datetime,
        agent_id: str | None,
        failure_type: FailureType | None,
        limit: int,
    ) -> list[FailureContext]:
        """Query failures from database."""
        if not DATABASE_AVAILABLE or not self.db:
            return []

        query = self.db.query(FailureContextModel).filter(
            FailureContextModel.timestamp >= start_time,
            FailureContextModel.timestamp <= end_time,
        )

        if agent_id:
            query = query.filter(FailureContextModel.agent_id == agent_id)

        if failure_type:
            query = query.filter(FailureContextModel.failure_type == failure_type.value)

        models = query.order_by(FailureContextModel.timestamp.desc()).limit(limit).all()

        return [m.to_failure_context() for m in models]

    async def _get_by_type_from_database(
        self,
        failure_type: FailureType,
        agent_id: str | None,
        limit: int,
    ) -> list[FailureContext]:
        """Get failures by type from database."""
        if not DATABASE_AVAILABLE or not self.db:
            return []

        query = self.db.query(FailureContextModel).filter(
            FailureContextModel.failure_type == failure_type.value
        )

        if agent_id:
            query = query.filter(FailureContextModel.agent_id == agent_id)

        models = query.order_by(FailureContextModel.timestamp.desc()).limit(limit).all()

        return [m.to_failure_context() for m in models]

    async def _mark_resolved_in_database(
        self,
        failure_id: str,
        resolution_strategy: str,
    ) -> None:
        """Mark failure as resolved in database."""
        if not DATABASE_AVAILABLE or not self.db:
            return

        model = (
            self.db.query(FailureContextModel)
            .filter(FailureContextModel.failure_id == failure_id)
            .first()
        )

        if model:
            model.resolved = True
            model.resolved_at = datetime.now(UTC)
            model.resolution_strategy = resolution_strategy
            await self.db.commit()


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_failure_repository: FailureRepository | None = None


def get_failure_repository() -> FailureRepository:
    """Get the singleton failure repository instance."""
    global _failure_repository
    if _failure_repository is None:
        _failure_repository = FailureRepository()
    return _failure_repository


def initialize_failure_repository(db_session=None) -> FailureRepository:
    """Initialize the failure repository with a database session."""
    global _failure_repository
    _failure_repository = FailureRepository(db_session)
    return _failure_repository
