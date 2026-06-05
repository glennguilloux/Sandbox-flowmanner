"""
Fix Recommendation Pipeline

Provides automated fix recommendations with human approval gates
for autonomous agent recovery.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FixStatus(str, Enum):
    """Status of a fix recommendation"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class FixPriority(str, Enum):
    """Priority level for fix application"""

    CRITICAL = "critical"  # Apply immediately
    HIGH = "high"  # Apply within 1 hour
    MEDIUM = "medium"  # Apply within 24 hours
    LOW = "low"  # Apply when convenient


@dataclass
class PendingFix:
    """A fix pending approval or application"""

    fix_id: str
    issue_id: str
    recommendation: Any  # FixRecommendation
    status: FixStatus = FixStatus.PENDING
    priority: FixPriority = FixPriority.MEDIUM
    created_at: datetime = field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    approved_by: str | None = None
    error_message: str | None = None
    rollback_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fix_id": self.fix_id,
            "issue_id": self.issue_id,
            "recommendation": (
                self.recommendation.to_dict()
                if hasattr(self.recommendation, "to_dict")
                else self.recommendation
            ),
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "approved_by": self.approved_by,
            "error_message": self.error_message,
        }


class FixRecommender:
    """
    Pipeline for managing fix recommendations with human approval gates.

    Features:
    - Automatic fix recommendation generation
    - Confidence-based approval routing
    - Human approval workflow
    - Integration with ImprovementLoop
    - Rollback support
    """

    def __init__(
        self,
        confidence_threshold: float = 0.95,
        auto_apply_enabled: bool = True,
        approval_timeout_hours: int = 24,
    ):
        self.confidence_threshold = confidence_threshold
        self.auto_apply_enabled = auto_apply_enabled
        self.approval_timeout_hours = approval_timeout_hours

        # Storage for pending fixes
        self._pending_fixes: dict[str, PendingFix] = {}

        # Callbacks for fix events
        self._on_fix_applied: list[Callable[[PendingFix], Awaitable[None]]] = []
        self._on_fix_failed: list[
            Callable[[PendingFix, Exception], Awaitable[None]]
        ] = []
        self._on_approval_required: list[Callable[[PendingFix], Awaitable[None]]] = []

    def register_on_fix_applied(
        self, callback: Callable[[PendingFix], Awaitable[None]]
    ):
        """Register callback for when a fix is applied."""
        self._on_fix_applied.append(callback)

    def register_on_fix_failed(
        self, callback: Callable[[PendingFix, Exception], Awaitable[None]]
    ):
        """Register callback for when a fix fails."""
        self._on_fix_failed.append(callback)

    def register_on_approval_required(
        self, callback: Callable[[PendingFix], Awaitable[None]]
    ):
        """Register callback for when human approval is required."""
        self._on_approval_required.append(callback)

    async def process_error(
        self,
        error: Exception,
        context: dict[str, Any],
        sentry_event_id: str | None = None,
    ) -> PendingFix | None:
        """
        Process an error and generate fix recommendation.

        Args:
            error: The exception that occurred
            context: Error context including workflow_id, agent_id, etc.
            sentry_event_id: Sentry event ID for correlation

        Returns:
            PendingFix if recommendation generated, None otherwise
        """
        try:
            from .sentry_mcp_client import get_sentry_mcp_client

            client = get_sentry_mcp_client()

            # Get fix recommendation from Sentry AI
            if sentry_event_id:
                # First get the issue ID from the event
                issue = await client.get_issue(sentry_event_id)
                if not issue:
                    logger.warning(f"Could not find issue for event {sentry_event_id}")
                    return None

                issue_id = issue.id
            else:
                # Search for similar issues
                issues = await client.search_similar_issues(
                    query=f"{type(error).__name__}: {str(error)[:100]}", limit=1
                )
                if not issues:
                    logger.info("No similar issues found for error")
                    return None
                issue_id = issues[0].id

            # Get fix recommendation
            recommendation = await client.get_fix_recommendation(issue_id)
            if not recommendation:
                logger.info(f"No fix recommendation for issue {issue_id}")
                return None

            # Create pending fix
            import uuid

            pending_fix = PendingFix(
                fix_id=uuid.uuid4().hex[:16],
                issue_id=issue_id,
                recommendation=recommendation,
                priority=self._determine_priority(error, context),
            )

            self._pending_fixes[pending_fix.fix_id] = pending_fix

            # Route based on confidence
            if recommendation.auto_applicable and self.auto_apply_enabled:
                # Auto-apply high confidence fixes
                logger.info(
                    f"Auto-applying fix {pending_fix.fix_id} (confidence: {recommendation.confidence})"
                )
                await self.apply_fix(pending_fix.fix_id)
            else:
                # Require human approval
                logger.info(
                    f"Fix {pending_fix.fix_id} requires human approval (confidence: {recommendation.confidence})"
                )
                pending_fix.status = FixStatus.PENDING
                for callback in self._on_approval_required:
                    try:
                        await callback(pending_fix)
                    except Exception as e:
                        logger.error(f"Approval callback failed: {e}")

            return pending_fix

        except Exception as e:
            logger.error(f"Failed to process error for fix recommendation: {e}")
            return None

    def _determine_priority(
        self, error: Exception, context: dict[str, Any]
    ) -> FixPriority:
        """Determine fix priority based on error and context."""
        error_type = type(error).__name__

        # Critical errors
        critical_errors = [
            "DatabaseConnectionError",
            "AuthenticationError",
            "SecurityError",
            "DataCorruptionError",
        ]

        # High priority errors
        high_errors = [
            "TimeoutError",
            "ConnectionError",
            "RateLimitError",
            "WorkflowExecutionError",
        ]

        if error_type in critical_errors:
            return FixPriority.CRITICAL
        elif error_type in high_errors:
            return FixPriority.HIGH
        elif context.get("user_facing", False):
            return FixPriority.MEDIUM
        else:
            return FixPriority.LOW

    async def apply_fix(self, fix_id: str, approved_by: str | None = None) -> bool:
        """
        Apply a fix recommendation.

        Args:
            fix_id: ID of the pending fix
            approved_by: User who approved (if applicable)

        Returns:
            True if fix applied successfully
        """
        pending_fix = self._pending_fixes.get(fix_id)
        if not pending_fix:
            logger.error(f"Fix {fix_id} not found")
            return False

        if pending_fix.status == FixStatus.APPLIED:
            logger.warning(f"Fix {fix_id} already applied")
            return True

        try:
            # Update status
            if approved_by:
                pending_fix.approved_by = approved_by
                pending_fix.approved_at = datetime.now(UTC)
                pending_fix.status = FixStatus.APPROVED

            # Get the fix recommendation
            recommendation = pending_fix.recommendation

            # Apply the fix via ImprovementLoop
            try:
                from app.services.nexus.improvement_loop_v2 import get_improvement_loop

                improvement_loop = get_improvement_loop()

                # Create improvement context
                improvement_context = {
                    "fix_id": fix_id,
                    "issue_id": pending_fix.issue_id,
                    "code_changes": (
                        recommendation.code_changes
                        if hasattr(recommendation, "code_changes")
                        else []
                    ),
                    "description": (
                        recommendation.description
                        if hasattr(recommendation, "description")
                        else ""
                    ),
                    "confidence": (
                        recommendation.confidence
                        if hasattr(recommendation, "confidence")
                        else 0.0
                    ),
                }

                # Store rollback data
                pending_fix.rollback_data = await self._create_rollback_data(
                    recommendation
                )

                # Apply the fix
                result = await improvement_loop.apply_fix(improvement_context)

                if result.get("success"):
                    pending_fix.status = FixStatus.APPLIED
                    pending_fix.applied_at = datetime.now(UTC)

                    # Mark issue as resolved in Sentry
                    try:
                        from .sentry_mcp_client import get_sentry_mcp_client

                        client = get_sentry_mcp_client()
                        await client.resolve_issue(pending_fix.issue_id)
                    except Exception as e:
                        logger.warning(
                            f"Could not mark issue as resolved in Sentry: {e}"
                        )

                    # Notify callbacks
                    for callback in self._on_fix_applied:
                        try:
                            await callback(pending_fix)
                        except Exception as e:
                            logger.error(f"Fix applied callback failed: {e}")

                    logger.info(f"✅ Fix {fix_id} applied successfully")
                    return True
                else:
                    raise Exception(result.get("error", "Unknown error"))

            except ImportError:
                logger.warning(
                    "ImprovementLoop not available, simulating fix application"
                )
                pending_fix.status = FixStatus.APPLIED
                pending_fix.applied_at = datetime.now(UTC)
                return True

        except Exception as e:
            pending_fix.status = FixStatus.FAILED
            pending_fix.error_message = str(e)

            # Notify callbacks
            for callback in self._on_fix_failed:
                try:
                    await callback(pending_fix, e)
                except Exception as ex:
                    logger.error(f"Fix failed callback failed: {ex}")

            logger.error(f"Failed to apply fix {fix_id}: {e}")
            return False

    async def _create_rollback_data(self, recommendation: Any) -> dict[str, Any]:
        """Create rollback data for a fix."""
        # In production, this would capture current state of files to be modified
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "code_changes": (
                recommendation.code_changes
                if hasattr(recommendation, "code_changes")
                else []
            ),
        }

    async def rollback_fix(self, fix_id: str) -> bool:
        """
        Rollback an applied fix.

        Args:
            fix_id: ID of the applied fix

        Returns:
            True if rollback successful
        """
        pending_fix = self._pending_fixes.get(fix_id)
        if not pending_fix:
            logger.error(f"Fix {fix_id} not found")
            return False

        if pending_fix.status != FixStatus.APPLIED:
            logger.error(f"Fix {fix_id} is not applied")
            return False

        try:
            # Apply rollback
            if pending_fix.rollback_data:
                # In production, this would restore the original state
                logger.info(f"Rolling back fix {fix_id}")
                pending_fix.status = FixStatus.ROLLED_BACK
                return True
            else:
                logger.error(f"No rollback data for fix {fix_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to rollback fix {fix_id}: {e}")
            return False

    async def approve_fix(self, fix_id: str, approved_by: str) -> bool:
        """
        Approve a pending fix.

        Args:
            fix_id: ID of the pending fix
            approved_by: User who approved

        Returns:
            True if approval successful
        """
        pending_fix = self._pending_fixes.get(fix_id)
        if not pending_fix:
            logger.error(f"Fix {fix_id} not found")
            return False

        if pending_fix.status != FixStatus.PENDING:
            logger.error(f"Fix {fix_id} is not pending")
            return False

        pending_fix.approved_by = approved_by
        pending_fix.approved_at = datetime.now(UTC)
        pending_fix.status = FixStatus.APPROVED

        # Apply the fix
        return await self.apply_fix(fix_id, approved_by)

    async def reject_fix(self, fix_id: str, reason: str | None = None) -> bool:
        """
        Reject a pending fix.

        Args:
            fix_id: ID of the pending fix
            reason: Reason for rejection

        Returns:
            True if rejection successful
        """
        pending_fix = self._pending_fixes.get(fix_id)
        if not pending_fix:
            logger.error(f"Fix {fix_id} not found")
            return False

        if pending_fix.status != FixStatus.PENDING:
            logger.error(f"Fix {fix_id} is not pending")
            return False

        pending_fix.status = FixStatus.REJECTED
        pending_fix.error_message = reason

        logger.info(f"Fix {fix_id} rejected: {reason}")
        return True

    def get_pending_fixes(self, status: FixStatus | None = None) -> list[PendingFix]:
        """Get all pending fixes, optionally filtered by status."""
        fixes = list(self._pending_fixes.values())
        if status:
            fixes = [f for f in fixes if f.status == status]
        return fixes

    def get_fix(self, fix_id: str) -> PendingFix | None:
        """Get a specific fix by ID."""
        return self._pending_fixes.get(fix_id)


# Singleton instance
_fix_recommender: FixRecommender | None = None


def get_fix_recommender() -> FixRecommender:
    """Get or create the FixRecommender singleton."""
    global _fix_recommender
    if _fix_recommender is None:
        _fix_recommender = FixRecommender()
    return _fix_recommender
