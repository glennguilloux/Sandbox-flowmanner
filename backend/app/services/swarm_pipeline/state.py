"""State machine for pipeline phase transitions."""

from app.services.swarm_pipeline.enums import PipelinePhase, PipelineStatus

_PHASE_ORDER: list[PipelinePhase] = [
    PipelinePhase.DISPATCH,
    PipelinePhase.RESEARCH,
    PipelinePhase.DRAFT,
    PipelinePhase.DEBATE,
    PipelinePhase.CONSENSUS,
    PipelinePhase.SYNTHESIS,
    PipelinePhase.REVIEW,
]

VALID_TRANSITIONS: dict[PipelinePhase, list[PipelinePhase]] = {
    PipelinePhase.DISPATCH: [PipelinePhase.RESEARCH],
    PipelinePhase.RESEARCH: [PipelinePhase.DRAFT],
    PipelinePhase.DRAFT: [PipelinePhase.DEBATE],
    PipelinePhase.DEBATE: [PipelinePhase.CONSENSUS],
    PipelinePhase.CONSENSUS: [PipelinePhase.SYNTHESIS],
    PipelinePhase.SYNTHESIS: [PipelinePhase.REVIEW],
    PipelinePhase.REVIEW: [PipelinePhase.DEBATE],
}

VALID_STATUS_TRANSITIONS: dict[PipelineStatus, list[PipelineStatus]] = {
    PipelineStatus.PENDING: [PipelineStatus.RUNNING],
    PipelineStatus.RUNNING: [
        PipelineStatus.PAUSED,
        PipelineStatus.COMPLETED,
        PipelineStatus.FAILED,
        PipelineStatus.CANCELLED,
    ],
    PipelineStatus.PAUSED: [PipelineStatus.RUNNING, PipelineStatus.CANCELLED],
}


def get_next_phase(current: PipelinePhase) -> PipelinePhase | None:
    idx = _PHASE_ORDER.index(current)
    if idx + 1 < len(_PHASE_ORDER):
        return _PHASE_ORDER[idx + 1]
    return None


def validate_transition(from_phase: PipelinePhase, to_phase: PipelinePhase) -> bool:
    return to_phase in VALID_TRANSITIONS.get(from_phase, [])


def validate_status_transition(from_status: PipelineStatus, to_status: PipelineStatus) -> bool:
    return to_status in VALID_STATUS_TRANSITIONS.get(from_status, [])


def is_retry_transition(from_phase: PipelinePhase, to_phase: PipelinePhase) -> bool:
    return from_phase == PipelinePhase.REVIEW and to_phase == PipelinePhase.DEBATE
