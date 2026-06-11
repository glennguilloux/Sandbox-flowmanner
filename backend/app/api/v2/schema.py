# mypy: disable-error-code=call-arg
# Strawberry GraphQL decorator-generated types confuse mypy's argument
# inference (86+ [call-arg] errors on MissionType/AgentType/ChatThreadType
# constructors). The runtime types are correct; this is a static-only escape.
"""Strawberry GraphQL schema for v2.

Covers: missions CRUD, agents catalog, chat threads + messages,
workspaces + teams, user profile, usage analytics.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info


@strawberry.type
class PageInfo:
    total: int
    page: int
    per_page: int
    pages: int


@strawberry.type
class UserType:
    id: int
    email: str
    username: str | None
    full_name: str | None
    role: str
    is_admin: bool
    is_active: bool
    avatar_url: str | None
    created_at: str | None


@strawberry.type
class MissionType:
    id: str
    user_id: int
    title: str
    description: str
    mission_type: str | None
    status: str | None
    priority: str | None
    plan: JSON | None
    results: JSON | None
    error_message: str | None
    tokens_used: int | None
    estimated_cost: float | None
    actual_cost: float | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None
    updated_at: str | None


@strawberry.type
class MissionTaskType:
    id: str
    mission_id: str
    title: str
    description: str | None
    task_type: str
    status: str | None
    input_data: JSON | None
    output_data: JSON | None
    tokens_used: int | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None


@strawberry.type
class AgentType:
    id: str
    name: str
    owner_id: str
    description: str | None
    system_prompt: str | None
    model_preference: str | None
    config: str | None
    created_at: str | None
    updated_at: str | None


@strawberry.type
class AgentTemplateType:
    template_id: str
    name: str
    description: str | None
    agent_type: str
    system_prompt: str | None
    model_config: JSON | None
    is_active: bool
    created_at: str | None


@strawberry.type
class ChatThreadType:
    id: int
    user_id: int
    username: str
    title: str
    folder_id: int | None
    is_archived: bool | None
    message_count: int | None
    created_at: str | None
    updated_at: str | None


@strawberry.type
class ChatMessageType:
    id: int
    thread_id: int
    user_id: int | None
    role: str
    content: str
    created_at: str | None


@strawberry.type
class WorkspaceType:
    id: str
    name: str
    slug: str
    owner_id: int
    plan: str
    created_at: str | None
    updated_at: str | None


@strawberry.type
class TeamType:
    id: str
    workspace_id: str
    name: str
    description: str
    created_at: str | None


@strawberry.type
class MissionConnection:
    items: list[MissionType]
    page_info: PageInfo


@strawberry.type
class AgentConnection:
    items: list[AgentType]
    page_info: PageInfo


@strawberry.type
class ChatThreadConnection:
    items: list[ChatThreadType]
    page_info: PageInfo


@strawberry.type
class UsageAnalyticsType:
    total_missions: int
    success_rate: float
    avg_completion_time: float | None
    total_tokens_used: int


@strawberry.input
class MissionCreateInput:
    title: str
    description: str = ""
    mission_type: str | None = None
    priority: str | None = None


@strawberry.input
class MissionUpdateInput:
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None


@strawberry.input
class AgentCreateInput:
    name: str
    description: str | None = None
    system_prompt: str | None = None
    model_preference: str | None = None
    config: str | None = None


@strawberry.input
class ChatThreadCreateInput:
    title: str
    model_preference: str | None = None


@strawberry.input
class ChatMessageCreateInput:
    role: str
    content: str


def _dt_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _mission_to_gql(m) -> MissionType:
    return MissionType(
        id=str(m.id),
        user_id=m.user_id,
        title=m.title,
        description=m.description,
        mission_type=m.mission_type,
        status=m.status,
        priority=m.priority,
        plan=m.plan,
        results=m.results,
        error_message=m.error_message,
        tokens_used=m.tokens_used,
        estimated_cost=m.estimated_cost,
        actual_cost=m.actual_cost,
        started_at=_dt_str(m.started_at),
        completed_at=_dt_str(m.completed_at),
        created_at=_dt_str(m.created_at),
        updated_at=_dt_str(m.updated_at),
    )


def _agent_to_gql(a) -> AgentType:
    return AgentType(
        id=str(a.id),
        name=a.name,
        owner_id=str(a.owner_id),
        description=a.description,
        system_prompt=a.system_prompt,
        model_preference=a.model_preference,
        config=a.config,
        created_at=_dt_str(a.created_at),
        updated_at=_dt_str(a.updated_at),
    )


def _thread_to_gql(t) -> ChatThreadType:
    return ChatThreadType(
        id=t.id,
        user_id=t.user_id,
        username=t.username,
        title=t.title,
        folder_id=t.folder_id,
        is_archived=t.is_archived,
        message_count=t.message_count,
        created_at=_dt_str(t.created_at),
        updated_at=_dt_str(t.updated_at),
    )


def _msg_to_gql(m) -> ChatMessageType:
    return ChatMessageType(
        id=m.id,
        thread_id=m.thread_id,
        user_id=m.user_id,
        role=m.role,
        content=m.content,
        created_at=_dt_str(m.created_at),
    )


def _get_user(info: Info):
    user = info.context.get("user")
    if not user:
        raise ValueError("Authentication required")
    return user


def _get_db(info: Info):
    db = info.context.get("db")
    if not db:
        raise ValueError("Database session not available")
    return db


@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: Info) -> UserType:
        user = _get_user(info)
        return UserType(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_admin=user.is_admin,
            is_active=user.is_active,
            avatar_url=user.avatar_url,
            created_at=_dt_str(user.created_at),
        )

    @strawberry.field
    async def missions(self, info: Info, page: int = 1, per_page: int = 20) -> MissionConnection:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.mission_service import list_missions

        offset = (page - 1) * per_page
        items, total = await list_missions(db, user.id, offset=offset, limit=per_page)
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return MissionConnection(
            items=[_mission_to_gql(m) for m in items],
            page_info=PageInfo(total=total, page=page, per_page=per_page, pages=pages),
        )

    @strawberry.field
    async def mission(self, info: Info, id: str) -> MissionType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.mission_service import get_mission

        mission = await get_mission(db, uuid.UUID(id))
        if mission is None or mission.user_id != user.id:
            raise ValueError("Mission not found")
        return _mission_to_gql(mission)

    @strawberry.field
    async def agents(self, info: Info, page: int = 1, per_page: int = 20) -> AgentConnection:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.agent_service import list_agents

        offset = (page - 1) * per_page
        items, total = await list_agents(db, str(user.id), offset=offset, limit=per_page)
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return AgentConnection(
            items=[_agent_to_gql(a) for a in items],
            page_info=PageInfo(total=total, page=page, per_page=per_page, pages=pages),
        )

    @strawberry.field
    async def agent(self, info: Info, id: str) -> AgentType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.agent_service import get_agent

        agent = await get_agent(db, id)  # type: ignore[arg-type]
        if agent is None or str(agent.owner_id) != str(user.id):
            raise ValueError("Agent not found")
        return _agent_to_gql(agent)

    @strawberry.field
    async def chat_threads(self, info: Info, page: int = 1, per_page: int = 20) -> ChatThreadConnection:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.chat_service import list_chat_threads

        offset = (page - 1) * per_page
        items, total = await list_chat_threads(db, user.id, offset=offset, limit=per_page)
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return ChatThreadConnection(
            items=[_thread_to_gql(t) for t in items],
            page_info=PageInfo(total=total, page=page, per_page=per_page, pages=pages),
        )

    @strawberry.field
    async def chat_thread(self, info: Info, id: int) -> ChatThreadType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.chat_service import get_chat_thread

        thread = await get_chat_thread(db, id)
        if thread is None or thread.user_id != user.id:
            raise ValueError("Thread not found")
        return _thread_to_gql(thread)

    @strawberry.field
    async def chat_messages(self, info: Info, thread_id: int) -> list[ChatMessageType]:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.chat_service import get_chat_messages, get_chat_thread

        thread = await get_chat_thread(db, thread_id)
        if thread is None or thread.user_id != user.id:
            raise ValueError("Thread not found")
        messages = (await get_chat_messages(db, thread_id))[0]
        return [_msg_to_gql(m) for m in messages]

    @strawberry.field
    async def workspaces(self, info: Info) -> list[WorkspaceType]:
        user = _get_user(info)
        db = _get_db(info)
        from sqlalchemy import select

        from app.models.workspace_models import Workspace, WorkspaceMember

        result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
        memberships = result.scalars().all()
        workspace_ids = [m.workspace_id for m in memberships]
        if not workspace_ids:
            return []
        result = await db.execute(select(Workspace).where(Workspace.id.in_(workspace_ids)))
        workspaces = result.scalars().all()
        return [
            WorkspaceType(
                id=ws.id,
                name=ws.name,
                slug=ws.slug,
                owner_id=ws.owner_id,
                plan=ws.plan,
                created_at=_dt_str(ws.created_at),
                updated_at=_dt_str(ws.updated_at),
            )
            for ws in workspaces
        ]

    @strawberry.field
    async def workspace(self, info: Info, id: str) -> WorkspaceType:
        user = _get_user(info)
        db = _get_db(info)
        from sqlalchemy import select

        from app.models.workspace_models import Workspace, WorkspaceMember

        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == id,
                WorkspaceMember.user_id == user.id,
            )
        )
        if not result.scalar_one_or_none():
            raise ValueError("Workspace not found")
        result = await db.execute(select(Workspace).where(Workspace.id == id))
        ws = result.scalar_one_or_none()
        if not ws:
            raise ValueError("Workspace not found")
        return WorkspaceType(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            created_at=_dt_str(ws.created_at),
            updated_at=_dt_str(ws.updated_at),
        )

    @strawberry.field
    async def usage_analytics(self, info: Info) -> UsageAnalyticsType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.mission_analytics import get_mission_analytics

        analytics = await get_mission_analytics(db, user.id)
        return UsageAnalyticsType(
            total_missions=analytics.get("total_missions", 0),
            success_rate=analytics.get("success_rate", 0.0),
            avg_completion_time=analytics.get("avg_completion_time"),
            total_tokens_used=analytics.get("total_tokens_used", 0),
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_mission(self, info: Info, input: MissionCreateInput) -> MissionType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.mission_service import create_mission

        mission = await create_mission(
            db,
            input.title,
            input.description,
            input.mission_type,
            input.priority,
            user.id,
            "pending",
        )
        return _mission_to_gql(mission)

    @strawberry.mutation
    async def update_mission(self, info: Info, id: str, input: MissionUpdateInput) -> MissionType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.mission_service import get_mission, update_mission

        mission = await get_mission(db, uuid.UUID(id))
        if mission is None or mission.user_id != user.id:
            raise ValueError("Mission not found")
        updated = await update_mission(
            db,
            uuid.UUID(id),
            input.title,
            input.description,
            input.status,
            input.priority,
            None,
            None,
            None,
            None,
            None,
        )
        if updated is None:
            raise ValueError("Update failed")
        return _mission_to_gql(updated)

    @strawberry.mutation
    async def delete_mission(self, info: Info, id: str) -> bool:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.mission_service import delete_mission, get_mission

        mission = await get_mission(db, uuid.UUID(id))
        if mission is None or mission.user_id != user.id:
            raise ValueError("Mission not found")
        return await delete_mission(db, uuid.UUID(id))

    @strawberry.mutation
    async def create_agent(self, info: Info, input: AgentCreateInput) -> AgentType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.agent_service import create_agent

        agent = await create_agent(
            db,
            input.name,
            str(user.id),
            input.description,
            input.system_prompt,
            input.model_preference,
            input.config,  # type: ignore[arg-type]
        )
        return _agent_to_gql(agent)

    @strawberry.mutation
    async def delete_agent(self, info: Info, id: str) -> bool:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.agent_service import delete_agent, get_agent

        agent = await get_agent(db, id)  # type: ignore[arg-type]
        if agent is None or str(agent.owner_id) != str(user.id):
            raise ValueError("Agent not found")
        return await delete_agent(db, id)  # type: ignore[arg-type]

    @strawberry.mutation
    async def create_chat_thread(self, info: Info, input: ChatThreadCreateInput) -> ChatThreadType:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.chat_service import create_chat_thread

        thread = await create_chat_thread(db, user.id, user.username, input.title, input.model_preference)
        return _thread_to_gql(thread)

    @strawberry.mutation
    async def delete_chat_thread(self, info: Info, id: int) -> bool:
        user = _get_user(info)
        db = _get_db(info)
        from app.services.chat_service import delete_chat_thread, get_chat_thread

        thread = await get_chat_thread(db, id)
        if thread is None or thread.user_id != user.id:
            raise ValueError("Thread not found")
        return await delete_chat_thread(db, id)


schema = strawberry.Schema(query=Query, mutation=Mutation)
