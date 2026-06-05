"""PipelinePhase and PipelineStatus enums for the 7-phase NEXUS pipeline."""

from enum import Enum


class PipelinePhase(str, Enum):
    DISPATCH = "dispatch"
    RESEARCH = "research"
    DRAFT = "draft"
    DEBATE = "debate"
    CONSENSUS = "consensus"
    SYNTHESIS = "synthesis"
    REVIEW = "review"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
