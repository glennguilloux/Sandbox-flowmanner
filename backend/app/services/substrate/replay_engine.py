"""ReplayEngine — rebuild RunState from the event log (H2.1).

Enables:
- Crash recovery: on worker restart, replay events to rebuild state
- Deterministic replay: replay from any checkpoint with the same model+seed
- Time-travel debugging: inspect state at any point in the run's history
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.models.substrate_models import SubstrateRunState
from app.services.substrate.event_log import EventLog, get_event_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Rebuilds RunState by replaying the event log."""

    # Events are replayed in batches for memory efficiency on large runs
    REPLAY_BATCH_SIZE = 1_000

    def __init__(self, event_log: EventLog | None = None):
        self._event_log = event_log or get_event_log()

    async def rebuild_state(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        up_to_sequence: int | None = None,
    ) -> SubstrateRunState:
        """Rebuild the full RunState by replaying all events for a run.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            up_to_sequence: If set, only replay events up to (and including)
                           this sequence number. Used for time-travel inspection.

        Returns:
            SubstrateRunState with the replayed state
        """
        state = SubstrateRunState(run_id=run_id)
        from_seq = 0

        while True:
            batch = await self._event_log.get_events(
                db,
                run_id,
                from_sequence=from_seq,
                to_sequence=up_to_sequence,
                limit=self.REPLAY_BATCH_SIZE,
            )

            if not batch:
                break

            for event in batch:
                state.apply(event)
                # Track mission_id from first event that has it
                if state.mission_id is None and event.mission_id:
                    state.mission_id = event.mission_id

            from_seq = batch[-1].sequence + 1

            if len(batch) < self.REPLAY_BATCH_SIZE:
                break

        logger.info(
            "Replayed %d events for run %s → status=%s",
            state.current_sequence,
            run_id,
            state.status,
        )
        return state

    async def rebuild_state_at_sequence(
        self,
        db: AsyncSession,
        run_id: str,
        sequence: int,
    ) -> SubstrateRunState:
        """Rebuild state as it was immediately after the given sequence number.

        This enables time-travel debugging: "what did mission X look like
        after event 42?"
        """
        return await self.rebuild_state(db, run_id, up_to_sequence=sequence)

    async def verify_determinism(self, db: AsyncSession, run_id: str) -> bool:
        """Verify that replaying the event log yields the same state.

        Replays the entire event log twice and compares the resulting states.
        Returns True if states are identical.
        """
        state1 = await self.rebuild_state(db, run_id)
        state2 = await self.rebuild_state(db, run_id)

        # Compare key fields
        same = (
            state1.status == state2.status
            and state1.current_sequence == state2.current_sequence
            and state1.completed_tasks == state2.completed_tasks
            and state1.failed_tasks == state2.failed_tasks
        )

        if not same:
            logger.warning(
                "Non-deterministic replay detected for run %s: state1=%s state2=%s",
                run_id,
                state1.to_dict(),
                state2.to_dict(),
            )

        return same

    async def get_checkpoint_sequences(self, db: AsyncSession, run_id: str) -> list[int]:
        """Get all checkpoint event sequence numbers for a run.

        Checkpoints are events of type 'substrate.checkpoint' and represent
        safe points from which replay can resume.
        """
        checkpoint_events = await self._event_log.get_events(db, run_id, event_type="substrate.checkpoint")
        return [e.sequence for e in checkpoint_events]

    async def record_episodes_used(
        self,
        db: AsyncSession,
        run_id: str,
        episode_ids: list[str],
        *,
        mission_id: str | None = None,
    ) -> None:
        """Record which episodes were retrieved and used during a run.

        Appends a read-only event to the log with the episode IDs.
        This does NOT change replay semantics — it is purely informational.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            episode_ids: List of episode UUIDs that were retrieved
            mission_id: Optional mission UUID
        """
        if not episode_ids:
            return

        await self._event_log.append(
            db,
            run_id=run_id,
            events=[
                {
                    "type": "episodic_memory.episodes_used",
                    "payload": {
                        "episode_ids": episode_ids,
                        "count": len(episode_ids),
                    },
                    "actor": "episodic_memory",
                }
            ],
            mission_id=mission_id,
        )
        logger.info(
            "Recorded %d episodes used for run %s",
            len(episode_ids), run_id,
        )


# ── Singleton ──────────────────────────────────────────────────────

_replay_engine: ReplayEngine | None = None


def get_replay_engine() -> ReplayEngine:
    """Get or create the ReplayEngine singleton."""
    global _replay_engine
    if _replay_engine is None:
        _replay_engine = ReplayEngine()
    return _replay_engine
