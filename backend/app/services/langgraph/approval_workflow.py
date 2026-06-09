#!/usr/bin/env python3
"""
Human Approval Workflow for Tool Execution

Handles the approval workflow for tool execution:
- Requesting approval from users
- Processing approval/rejection
- Managing approval state
- Auto-approval for safe tools
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .state import (
    AgentState,
    ToolExecution,
    create_tool_execution,
    update_tool_execution,
)
from .tool_converter import ToolConverter, get_tool_converter

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Approval status"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    CANCELLED = "cancelled"


class ApprovalRequest:
    """Represents an approval request"""

    def __init__(
        self,
        tool_execution: ToolExecution,
        session_id: str,
        user_id: int | None = None,
        timeout_seconds: int = 300,  # 5 minutes default
        request_id: str | None = None,
    ):
        self.tool_execution = tool_execution
        self.session_id = session_id
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds
        self.created_at = datetime.now(UTC)
        self.expires_at = self.created_at.timestamp() + timeout_seconds
        self.status = ApprovalStatus.PENDING
        self.approved_by: int | None = None
        self.rejection_reason: str | None = None
        self.request_id = request_id

    def is_expired(self) -> bool:
        """Check if approval request has expired"""
        return datetime.now(UTC).timestamp() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "approval_id": self.request_id,
            "tool_execution": self.tool_execution,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat(),
            "expires_at": datetime.fromtimestamp(self.expires_at).isoformat(),
            "status": self.status.value,
            "approved_by": self.approved_by,
            "rejection_reason": self.rejection_reason,
            "is_expired": self.is_expired(),
        }


class ApprovalWorkflow:
    """
    Manages the human approval workflow for tool execution.

    This class handles:
    - Creating approval requests
    - Processing user approvals/rejections
    - Auto-approving safe tools
    - Managing approval timeouts
    """

    def __init__(
        self,
        tool_converter: ToolConverter | None = None,
        auto_approve_safe: bool = True,
        default_timeout: int = 300,
        redis_client=None,
    ):
        """
        Initialize approval workflow.

        Args:
            tool_converter: Optional tool converter instance
            auto_approve_safe: Whether to auto-approve safe tools
            default_timeout: Default timeout in seconds
            redis_client: Optional Redis client for persistence
        """
        self.tool_converter = tool_converter or get_tool_converter()
        self.auto_approve_safe = auto_approve_safe
        self.default_timeout = default_timeout
        self.redis_client = redis_client
        self.pending_requests: dict[str, ApprovalRequest] = {}
        self.approval_callbacks: dict[str, list[Callable]] = {}

    def create_approval_request(
        self,
        state: AgentState,
        tool_name: str,
        tool_id: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create an approval request for tool execution.

        Args:
            state: Current agent state
            tool_name: Name of the tool
            tool_id: Tool identifier
            parameters: Tool parameters

        Returns:
            Dictionary with approval request info
        """
        # Get tool definition
        tool = self.tool_converter.get_tool(tool_id)
        if not tool:
            return {
                "success": False,
                "error": f"Tool {tool_id} not found",
            }

        # Check if auto-approval is possible
        requires_approval = tool.requires_approval
        if state["require_approval_for_all"]:
            requires_approval = True
        elif tool.is_safe and self.auto_approve_safe:
            requires_approval = False

        # Create tool execution
        tool_execution = create_tool_execution(
            tool_name=tool_name,
            tool_id=tool_id,
            parameters=parameters,
            requires_approval=requires_approval,
        )

        # Auto-approve if safe
        if not requires_approval:
            tool_execution = update_tool_execution(
                tool_execution,
                status="approved",
                approved_by=state["user_id"] or 0,  # System approval
            )

            return {
                "success": True,
                "auto_approved": True,
                "tool_execution": tool_execution,
                "message": f"Tool {tool_name} auto-approved (safe tool)",
            }

        # Create approval request
        request_id = f"{state['session_id']}:{tool_id}:{tool_execution['created_at']}"
        request = ApprovalRequest(
            tool_execution=tool_execution,
            session_id=state["session_id"],
            user_id=state["user_id"],
            timeout_seconds=self.default_timeout,
            request_id=request_id,
        )

        # Store request
        self.pending_requests[request_id] = request
        logger.info('[APPROVAL] Created approval request %s, saving to Redis: %s', request_id, self.redis_client is not None)

        # Save to Redis if available
        if self.redis_client:
            try:
                import json

                redis_key = f"langgraph:approval:{request_id}"
                redis_value = json.dumps(
                    {
                        "request_id": request_id,
                        "session_id": request.session_id,
                        "user_id": request.user_id,
                        "tool_execution": request.tool_execution,
                        "status": request.status.value,
                        "created_at": request.created_at.isoformat(),
                        "timeout_seconds": request.timeout_seconds,
                    }
                )
                self.redis_client.setex(
                    redis_key, self.default_timeout + 60, redis_value
                )
                logger.info('[APPROVAL] Successfully saved approval request %s to Redis', request_id)
            except Exception as e:
                logger.warning('[APPROVAL] Failed to save approval request to Redis: %s', e)
        else:
            logger.warning('[APPROVAL] Redis not available, approval request %s only in memory', request_id)

        # Update state
        state["awaiting_approval"] = True
        state["current_approval_request"] = tool_execution
        state["pending_tools"] = state["pending_tools"] + [tool_execution]

        logger.info('Created approval request for tool %s in session %s', tool_name, state['session_id'])

        return {
            "success": True,
            "auto_approved": False,
            "request_id": request_id,
            "approval_request": request.to_dict(),
            "tool_execution": tool_execution,
            "message": f"Approval required for tool {tool_name}",
        }

    def _load_request_from_redis(self, request_id: str) -> ApprovalRequest | None:
        """Load approval request from Redis"""
        if not self.redis_client:
            return None

        try:
            import json
            from datetime import datetime

            redis_key = f"langgraph:approval:{request_id}"
            data = self.redis_client.get(redis_key)

            if not data:
                return None

            data_dict = json.loads(data)

            # Reconstruct ApprovalRequest
            request = ApprovalRequest(
                tool_execution=data_dict["tool_execution"],
                session_id=data_dict["session_id"],
                user_id=data_dict["user_id"],
                timeout_seconds=data_dict["timeout_seconds"],
            )

            # Restore state
            request.status = ApprovalStatus(data_dict["status"])
            request.created_at = datetime.fromisoformat(data_dict["created_at"])

            logger.debug('Loaded approval request %s from Redis', request_id)
            return request
        except Exception as e:
            logger.warning('Failed to load approval request from Redis: %s', e)
            return None

    def approve(
        self,
        request_id: str,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Approve a pending tool execution.

        Args:
            request_id: Approval request ID
            user_id: User ID approving the request

        Returns:
            Dictionary with approval result
        """
        logger.info('[APPROVAL] approve() called with request_id=%s, user_id=%s, has_redis=%s', request_id, user_id, self.redis_client is not None)
        request = self.pending_requests.get(request_id)

        # Try loading from Redis if not in memory
        if not request and self.redis_client:
            request = self._load_request_from_redis(request_id)
            if request:
                # Store in memory for future use
                self.pending_requests[request_id] = request

        if not request:
            return {
                "success": False,
                "error": "Approval request not found or already processed",
            }

        if request.is_expired():
            self._remove_request(request_id)
            return {
                "success": False,
                "error": "Approval request has expired",
            }

        # Update request
        request.status = ApprovalStatus.APPROVED
        request.approved_by = user_id

        # Update tool execution
        request.tool_execution = update_tool_execution(
            request.tool_execution,
            status="approved",
            approved_by=user_id,
        )

        # Trigger callbacks
        self._trigger_callbacks(request_id, "approved", request)

        # Remove from pending and Redis
        self._remove_request(request_id)

        logger.info('Approved tool execution %s by user %s', request_id, user_id)

        return {
            "success": True,
            "tool_execution": request.tool_execution,
            "message": "Tool execution approved",
        }

    def reject(
        self,
        request_id: str,
        user_id: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Reject a pending tool execution.

        Args:
            request_id: Approval request ID
            user_id: User ID rejecting the request
            reason: Optional rejection reason

        Returns:
            Dictionary with rejection result
        """
        request = self.pending_requests.get(request_id)

        # Try loading from Redis if not in memory
        if not request and self.redis_client:
            request = self._load_request_from_redis(request_id)
            if request:
                self.pending_requests[request_id] = request

        if not request:
            return {
                "success": False,
                "error": "Approval request not found or already processed",
            }

        # Update request
        request.status = ApprovalStatus.REJECTED
        request.rejection_reason = reason

        # Update tool execution
        request.tool_execution = update_tool_execution(
            request.tool_execution,
            status="rejected",
            error=reason or "Rejected by user",
        )

        # Trigger callbacks
        self._trigger_callbacks(request_id, "rejected", request)

        # Remove from pending
        self._remove_request(request_id)

        logger.info('Rejected tool execution %s by user %s: %s', request_id, user_id, reason)

        return {
            "success": True,
            "tool_execution": request.tool_execution,
            "message": "Tool execution rejected",
        }

    def cancel(
        self,
        request_id: str,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Cancel a pending tool execution.

        Args:
            request_id: Approval request ID
            user_id: User ID cancelling the request

        Returns:
            Dictionary with cancellation result
        """
        request = self.pending_requests.get(request_id)

        # Try loading from Redis if not in memory
        if not request and self.redis_client:
            request = self._load_request_from_redis(request_id)
            if request:
                self.pending_requests[request_id] = request

        if not request:
            return {
                "success": False,
                "error": "Approval request not found or already processed",
            }

        # Update request
        request.status = ApprovalStatus.CANCELLED

        # Update tool execution
        request.tool_execution = update_tool_execution(
            request.tool_execution,
            status="rejected",
            error="Cancelled by user",
        )

        # Trigger callbacks
        self._trigger_callbacks(request_id, "cancelled", request)

        # Remove from pending
        self._remove_request(request_id)

        logger.info('Cancelled tool execution %s by user %s', request_id, user_id)

        return {
            "success": True,
            "tool_execution": request.tool_execution,
            "message": "Tool execution cancelled",
        }

    def get_pending_requests(
        self,
        session_id: str | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get pending approval requests.

        Args:
            session_id: Optional filter by session ID
            user_id: Optional filter by user ID

        Returns:
            List of pending approval requests
        """
        requests = []

        for request_id, request in self.pending_requests.items():
            # Filter expired requests
            if request.is_expired():
                self._remove_request(request_id)
                continue

            # Apply filters
            if session_id and request.session_id != session_id:
                continue
            if user_id and request.user_id != user_id:
                continue

            requests.append(request.to_dict())

        return requests

    def cleanup_expired_requests(self) -> int:
        """
        Clean up expired approval requests.

        Returns:
            Number of requests cleaned up
        """
        expired_ids = []

        for request_id, request in self.pending_requests.items():
            if request.is_expired():
                expired_ids.append(request_id)

        for request_id in expired_ids:
            request = self.pending_requests[request_id]
            request.status = ApprovalStatus.CANCELLED
            request.tool_execution = update_tool_execution(
                request.tool_execution,
                status="rejected",
                error="Approval request expired",
            )
            self._trigger_callbacks(request_id, "expired", request)
            self._remove_request(request_id)

        if expired_ids:
            logger.info('Cleaned up %s expired approval requests', len(expired_ids))

        return len(expired_ids)

    def register_callback(
        self,
        request_id: str,
        callback: Callable[[str, ApprovalStatus, ApprovalRequest], None],
    ):
        """
        Register a callback for approval status changes.

        Args:
            request_id: Approval request ID
            callback: Callback function
        """
        if request_id not in self.approval_callbacks:
            self.approval_callbacks[request_id] = []
        self.approval_callbacks[request_id].append(callback)

    def _remove_request(self, request_id: str):
        """Remove request from pending"""
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]
        if request_id in self.approval_callbacks:
            del self.approval_callbacks[request_id]

        # Remove from Redis if available
        if self.redis_client:
            try:
                redis_key = f"langgraph:approval:{request_id}"
                self.redis_client.delete(redis_key)
                logger.debug('Removed approval request %s from Redis', request_id)
            except Exception as e:
                logger.warning('Failed to remove approval request from Redis: %s', e)

    def _trigger_callbacks(
        self,
        request_id: str,
        status: str,
        request: ApprovalRequest,
    ):
        """Trigger callbacks for status change"""
        callbacks = self.approval_callbacks.get(request_id, [])
        for callback in callbacks:
            try:
                callback(request_id, ApprovalStatus(status), request)
            except Exception as e:
                logger.error('Error in approval callback: %s', e)

    def get_approval_summary(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Get approval summary for a session.

        Args:
            session_id: Session ID

        Returns:
            Approval summary
        """
        pending = self.get_pending_requests(session_id=session_id)

        return {
            "session_id": session_id,
            "pending_count": len(pending),
            "pending_requests": pending,
            "auto_approve_safe": self.auto_approve_safe,
        }


# Global workflow instance
_approval_workflow = None


def get_approval_workflow(
    tool_converter: ToolConverter | None = None,
    auto_approve_safe: bool = True,
    default_timeout: int = 300,
    redis_client=None,
) -> ApprovalWorkflow:
    """
    Get singleton approval workflow instance.

    Args:
        tool_converter: Optional tool converter
        auto_approve_safe: Whether to auto-approve safe tools
        default_timeout: Default timeout in seconds
        redis_client: Optional Redis client for persistence

    Returns:
        ApprovalWorkflow instance
    """
    global _approval_workflow
    if _approval_workflow is None:
        _approval_workflow = ApprovalWorkflow(
            tool_converter=tool_converter,
            auto_approve_safe=auto_approve_safe,
            default_timeout=default_timeout,
            redis_client=redis_client,
        )
    return _approval_workflow
