from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.models.workspace_models import WorkspaceMember
from app.schemas.replay import MissionReplayResponse, ReplayEvent, ReplayPage
from app.services.mission_errors import MissionNotFoundError, MissionValidationError
from app.services.mission_service import get_mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MIN_LIMIT = 1
MAX_LIMIT = 1_000
DEFAULT_LIMIT = 1_000
NO_SUBSTRATE_RUN_MESSAGE = "Mission has no substrate run (may not have been executed with substrate)"

_KNOWN_EVENT_TYPES = frozenset(
    value
    for name, value in vars(SubstrateEventType).items()
    if not name.startswith("__") and isinstance(value, str)
)


def parse_event_types(event_type: str | None) -> list[str] | None:
    if not event_type:
        return []

    parsed: list[str] = []
    seen: set[str] = set()

    for raw_value in event_type.split(","):
        value = raw_value.strip()
        if not value:
            continue
        if value not in _KNOWN_EVENT_TYPES:
            return None
        if value not in seen:
            parsed.append(value)
            seen.add(value)

    return parsed


def serialize_replay_event(event: SubstrateEvent) -> dict:
    return ReplayEvent(
        id=str(event.id),
        sequence=event.sequence,
        run_id=str(event.run_id),
        mission_id=str(event.mission_id) if event.mission_id else None,
        task_id=str(event.task_id) if event.task_id else None,
        blueprint_id=str(event.blueprint_id) if event.blueprint_id else None,
        type=event.type,
        payload=event.payload,
        causal_parent=event.causal_parent,
        actor=event.actor,
        timestamp=event.timestamp,
    ).model_dump()


def serialize_mission_summary(mission) -> dict:
    status = getattr(mission.status, "value", mission.status)
    return {
        "id": str(mission.id),
        "title": mission.title,
        "status": status,
    }


class ReplayQueryService:
    async def list_mission_events(
        self,
        db: "AsyncSession",
        mission_id: str | UUID,
        user_id: int,
        *,
        event_type: str | None = None,
        after_sequence: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> MissionReplayResponse:
        mission = await self._require_mission_access(db, mission_id, user_id)
        run_id = self._run_id_from_mission(mission)
        if run_id is None:
            return self._empty_response(mission, None, NO_SUBSTRATE_RUN_MESSAGE)

        event_types = parse_event_types(event_type)
        page = await self.get_events_for_mission(
            db,
            mission=mission,
            run_id=run_id,
            event_types=event_types,
            after_sequence=after_sequence,
            from_sequence=0,
            to_sequence=None,
            limit=limit,
        )

        return self._response_from_page(mission, run_id, page)

    async def get_events_for_mission(
        self,
        db: "AsyncSession",
        *,
        mission,
        run_id: str,
        event_types: list[str] | None,
        after_sequence: int | None,
        from_sequence: int,
        to_sequence: int | None,
        limit: int,
    ) -> ReplayPage:
        self._validate_limit(limit)
        self._validate_cursor("after_sequence", after_sequence)
        self._validate_cursor("from_sequence", from_sequence)
        self._validate_cursor("to_sequence", to_sequence)

        if event_types is not None and not self._event_types_are_known(event_types):
            return ReplayPage(events=[], total=0)

        events = await self._fetch_events(
            db,
            run_id,
            event_types=event_types or [],
            after_sequence=after_sequence,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            limit=limit,
        )
        has_next = len(events) > limit
        page_events = [ReplayEvent(**serialize_replay_event(e)) for e in events[:limit]]
        return ReplayPage(
            events=page_events,
            total=len(page_events),
            next_after_sequence=page_events[-1].sequence if has_next and page_events else None,
        )

    async def get_event_at_sequence(
        self,
        db: "AsyncSession",
        *,
        mission,
        run_id: str,
        sequence: int,
    ) -> ReplayPage:
        return await self.get_events_for_mission(
            db,
            mission=mission,
            run_id=run_id,
            event_types=None,
            after_sequence=None,
            from_sequence=sequence,
            to_sequence=sequence,
            limit=1,
        )

    async def list_events(
        self,
        db: "AsyncSession",
        *,
        mission,
        run_id: str,
        event_types: list[str] | None,
        after_sequence: int | None,
        from_sequence: int,
        to_sequence: int | None,
        limit: int,
    ) -> ReplayPage:
        return await self.get_events_for_mission(
            db,
            mission=mission,
            run_id=run_id,
            event_types=event_types,
            after_sequence=after_sequence,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            limit=limit,
        )

    async def get_events(
        self,
        db: "AsyncSession",
        *,
        mission,
        run_id: str,
        event_types: list[str] | None,
        after_sequence: int | None,
        from_sequence: int,
        to_sequence: int | None,
        limit: int,
    ) -> ReplayPage:
        return await self.get_events_for_mission(
            db,
            mission=mission,
            run_id=run_id,
            event_types=event_types,
            after_sequence=after_sequence,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            limit=limit,
        )

    async def _require_mission_access(self, db: "AsyncSession", mission_id: str | UUID, user_id: int):
        mission = await get_mission(db, mission_id)
        if mission is None:
            raise MissionNotFoundError("Mission not found")

        if mission.workspace_id:
            result = await db.execute(
                select(WorkspaceMember)
                .where(
                    WorkspaceMember.workspace_id == mission.workspace_id,
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.is_active.is_(True),
                )
                .limit(1)
            )
            if result.scalar_one_or_none() is None:
                raise MissionNotFoundError("Mission not found")
        elif mission.user_id != user_id:
            raise MissionNotFoundError("Mission not found")

        return mission

    @staticmethod
    def _run_id_from_mission(mission) -> str | None:
        plan = mission.plan or {}
        run_id = plan.get("substrate_run_id")
        return str(run_id) if run_id else None

    async def _fetch_events(
        self,
        db: "AsyncSession",
        run_id: str,
        *,
        event_types: list[str],
        after_sequence: int | None,
        from_sequence: int,
        to_sequence: int | None,
        limit: int,
    ) -> list[SubstrateEvent]:
        lower_sequence = max(from_sequence, after_sequence + 1 if after_sequence is not None else from_sequence)
        stmt = select(SubstrateEvent).where(
            SubstrateEvent.run_id == run_id,
            SubstrateEvent.sequence >= lower_sequence,
        )
        if to_sequence is not None:
            stmt = stmt.where(SubstrateEvent.sequence <= to_sequence)
        if event_types:
            stmt = stmt.where(SubstrateEvent.type.in_(event_types))

        stmt = (
            stmt.order_by(
                SubstrateEvent.timestamp.asc(),
                SubstrateEvent.sequence.asc(),
                SubstrateEvent.id.asc(),
            )
            .limit(limit + 1)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    def _response_from_page(self, mission, run_id: str, page: ReplayPage) -> MissionReplayResponse:
        return MissionReplayResponse(
            events=page.events,
            total=page.total,
            mission=serialize_mission_summary(mission),
            run_id=run_id,
            next_after_sequence=page.next_after_sequence,
        )

    def _empty_response(self, mission, run_id: str | None, message: str | None = None) -> MissionReplayResponse:
        return MissionReplayResponse(
            events=[],
            total=0,
            mission=serialize_mission_summary(mission),
            run_id=run_id,
            message=message,
        )

    @staticmethod
    def _event_types_are_known(event_types: list[str]) -> bool:
        return all(event_type in _KNOWN_EVENT_TYPES for event_type in event_types)

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if limit < MIN_LIMIT or limit > MAX_LIMIT:
            raise MissionValidationError(f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}")

    @staticmethod
    def _validate_cursor(name: str, value: int | None) -> None:
        if value is not None and value < 0:
            raise MissionValidationError(f"{name} must be greater than or equal to 0")


_replay_query_service: ReplayQueryService | None = None


def get_replay_query_service() -> ReplayQueryService:
    global _replay_query_service
    if _replay_query_service is None:
        _replay_query_service = ReplayQueryService()
    return _replay_query_service


def get_replay_query() -> ReplayQueryService:
    return get_replay_query_service()
