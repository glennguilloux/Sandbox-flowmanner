"""Intervention Distance metric — measure actual autonomy (Phase 0.5).

Computes how many autonomous actions occur between human interventions.
A higher intervention distance means more autonomous operation.

This is a category-defining metric: "We measure how autonomous your agents are."
"""

from __future__ import annotations

from typing import Any

from app.models.substrate_models import SubstrateEvent, SubstrateEventType


def compute_intervention_distance(
    events: list[SubstrateEvent],
) -> dict[str, Any]:
    """Measure autonomous actions between human interventions.

    Args:
        events: List of substrate events for a run, ordered by sequence

    Returns:
        Dict with:
        - total_actions: All non-HITL events
        - human_interventions: Count of HITL resolved events
        - autonomous_actions: Total actions minus interventions
        - intervention_distance: Avg actions between interventions
        - autonomy_score: 0.0 to 1.0 (1.0 = fully autonomous)
    """
    total_actions = 0
    human_interventions = 0
    actions_since_last_intervention = 0
    distances: list[int] = []

    for event in events:
        if event.type == SubstrateEventType.HUMAN_INTERRUPT_RESOLVED:
            human_interventions += 1
            distances.append(actions_since_last_intervention)
            actions_since_last_intervention = 0
        elif event.type not in (
            SubstrateEventType.HUMAN_INTERRUPT_RAISED,
            # Don't count the raised event itself as an action
        ):
            total_actions += 1
            actions_since_last_intervention += 1

    # Add final segment (actions after last intervention)
    distances.append(actions_since_last_intervention)

    avg_distance = sum(distances) / len(distances) if distances else 0.0
    autonomy_score = 1.0 - (human_interventions / max(total_actions, 1))
    autonomy_score = max(0.0, min(1.0, autonomy_score))  # clamp to [0, 1]

    return {
        "total_actions": total_actions,
        "human_interventions": human_interventions,
        "autonomous_actions": total_actions,
        "intervention_distance": round(avg_distance, 1),
        "autonomy_score": round(autonomy_score, 3),
    }
