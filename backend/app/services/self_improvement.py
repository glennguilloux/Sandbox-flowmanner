import uuid

from sqlalchemy import select

from app.models.mission_models import Mission, MissionImprovement


class SelfImprovementEngine:
    def __init__(self, db, user_id: str):
        self.db = db
        self.user_id = user_id

    async def get_improvements(self, mission_id: str) -> list[MissionImprovement]:
        result = await self.db.execute(
            select(MissionImprovement)
            .where(MissionImprovement.mission_id == mission_id)
            .order_by(MissionImprovement.created_at.desc())
        )
        return list(result.scalars().all())

    async def generate_strategy(self, mission_id: str, failure_type: str, failure_context: str) -> MissionImprovement:
        mission_result = await self.db.execute(select(Mission).where(Mission.id == mission_id))
        mission = mission_result.scalar_one_or_none()
        if not mission:
            raise ValueError("Mission not found")

        suggestion = self._analyze_failure(mission, failure_type, failure_context)

        improvement = MissionImprovement(
            id=str(uuid.uuid4()),
            mission_id=mission_id,
            suggestion=suggestion,
            priority="high" if failure_type in ["code", "api"] else "medium",
            status="pending",
            failure_type=failure_type,
            failure_context=failure_context[:500] if failure_context else None,
        )
        self.db.add(improvement)
        await self.db.flush()
        return improvement

    async def apply_strategy(self, improvement_id: str) -> bool:
        result = await self.db.execute(select(MissionImprovement).where(MissionImprovement.id == improvement_id))
        improvement = result.scalar_one_or_none()
        if not improvement:
            return False
        improvement.status = "applied"
        await self.db.flush()
        return True

    def _analyze_failure(self, mission: Mission, failure_type: str, failure_context: str) -> str:
        if failure_type == "code":
            return f"Review code execution strategy: {failure_context[:100] if failure_context else 'Task failed'}. Consider adding input validation, error handling, or switching to a more capable model."
        elif failure_type == "api":
            return f"API call failed: {failure_context[:100] if failure_context else 'Request error'}. Verify endpoint availability, add retry logic with exponential backoff, or check authentication credentials."
        elif failure_type == "rag_query":
            return "RAG query failed. Consider expanding document corpus, improving query preprocessing, or using semantic search with better embedding models."
        elif failure_type == "timeout":
            return f"Task timed out after {mission.timeout_seconds or 30}s. Increase timeout, break task into smaller subtasks, or optimize the operation."
        elif failure_type == "validation_error":
            return f"Input validation failed: {failure_context[:100] if failure_context else 'Invalid data'}. Add schema validation before task execution or provide clearer error messages to users."
        else:
            return f"Task of type '{failure_type}' failed: {failure_context[:100] if failure_context else 'Unknown error'}. Review logs for details, add error monitoring, and implement graceful degradation."
