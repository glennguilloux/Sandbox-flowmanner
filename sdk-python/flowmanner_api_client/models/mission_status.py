from enum import Enum


class MissionStatus(str, Enum):
    ABORTED = "aborted"
    APPROVED = "approved"
    COMPLETED = "completed"
    DRAFT = "draft"
    EXECUTING = "executing"
    FAILED = "failed"
    PAUSED = "paused"
    PENDING = "pending"
    PLANNED = "planned"
    PLANNED_PENDING_REVIEW = "planned_pending_review"
    PLANNING = "planning"
    QUEUED = "queued"
    RUNNING = "running"

    def __str__(self) -> str:
        return str(self.value)
