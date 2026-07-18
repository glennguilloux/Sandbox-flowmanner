"""Mission advanced routes: templates, node groups, versions, export/import."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.mission_advanced_models import (
    MissionTemplate,
    MissionVersion,
    NodeGroup,
)
from app.models.mission_models import Mission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/missions/advanced", tags=["mission_advanced"])


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ─── Schemas ──────────────────────────────────────────────────────────────────


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    is_public: bool = False
    default_plan: dict | None = None
    default_tasks: dict | None = None
    default_constraints: dict | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    is_public: bool | None = None
    default_plan: dict | None = None
    default_tasks: dict | None = None
    default_constraints: dict | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    category: str | None
    is_public: bool
    user_id: int
    default_plan: dict | list | None = None
    default_tasks: dict | list | None = None
    default_constraints: dict | list | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NodeGroupCreate(BaseModel):
    name: str
    description: str | None = None
    group_type: str | None = None
    config: dict | None = None


class NodeGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    group_type: str | None = None
    config: dict | None = None


class NodeGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    group_type: str | None
    config: dict | None
    owner_id: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VersionCreate(BaseModel):
    change_summary: str | None = None
    flow_data: dict | None = None  # Optional nodes/edges snapshot


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: uuid.UUID
    mission_id: uuid.UUID
    version: int = Field(serialization_alias="version_number")
    snapshot: dict | None
    change_summary: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RestoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    message: str
    version_id: uuid.UUID
    version: int = Field(serialization_alias="version_number")
    snapshot: dict | None = None


class ImportPayload(BaseModel):
    data: dict
    title_override: str | None = None


class ImportResponse(BaseModel):
    mission_id: str
    title: str
    tasks_imported: int


class UseTemplateResponse(BaseModel):
    mission_id: str
    title: str


# ─── Templates ────────────────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates(
    category: str | None = None,
    include_public: bool = True,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * per_page
    query = select(MissionTemplate)
    count_query = select(func.count(MissionTemplate.id))

    if include_public:
        query = query.where((MissionTemplate.user_id == user.id) | (MissionTemplate.is_public == True))
        count_query = count_query.where((MissionTemplate.user_id == user.id) | (MissionTemplate.is_public == True))
    else:
        query = query.where(MissionTemplate.user_id == user.id)
        count_query = count_query.where(MissionTemplate.user_id == user.id)

    if category:
        query = query.where(MissionTemplate.category == category)
        count_query = count_query.where(MissionTemplate.category == category)

    query = query.order_by(MissionTemplate.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    pages = (total + per_page - 1) // per_page

    return {
        "items": [TemplateResponse.model_validate(t) for t in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tpl = MissionTemplate(
        name=payload.name,
        description=payload.description or "",
        category=payload.category,
        is_public=payload.is_public,
        user_id=user.id,
        default_plan=payload.default_plan,
        default_tasks=payload.default_tasks,
        default_constraints=payload.default_constraints,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(MissionTemplate).where(MissionTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if tpl is None or (tpl.user_id != user.id and not tpl.is_public):
        raise _not_found()
    return tpl


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(MissionTemplate).where(MissionTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if tpl is None or tpl.user_id != user.id:
        raise _not_found()

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tpl, field, value)

    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(MissionTemplate).where(MissionTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if tpl is None or tpl.user_id != user.id:
        raise _not_found()
    await db.delete(tpl)
    await db.commit()


@router.post("/templates/{template_id}/use", response_model=UseTemplateResponse)
async def use_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(MissionTemplate).where(MissionTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if tpl is None or (tpl.user_id != user.id and not tpl.is_public):
        raise _not_found()

    mission = Mission(
        title=tpl.name,
        description=tpl.description or "",
        user_id=user.id,
        status="draft",
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return UseTemplateResponse(mission_id=str(mission.id), title=mission.title)


# ─── Node Groups ──────────────────────────────────────────────────────────────


@router.get("/node-groups")
async def list_node_groups(
    category: str | None = None,
    include_public: bool = True,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * per_page
    query = select(NodeGroup)
    count_query = select(func.count(NodeGroup.id))

    # NodeGroup doesn't have a dedicated is_public column; filter by owner only
    query = query.where(NodeGroup.owner_id == user.id)
    count_query = count_query.where(NodeGroup.owner_id == user.id)

    if category:
        query = query.where(NodeGroup.group_type == category)
        count_query = count_query.where(NodeGroup.group_type == category)

    query = query.order_by(NodeGroup.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    pages = (total + per_page - 1) // per_page

    return {
        "items": [NodeGroupResponse.model_validate(ng) for ng in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post(
    "/node-groups",
    response_model=NodeGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_node_group(
    payload: NodeGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ng = NodeGroup(
        name=payload.name,
        description=payload.description,
        group_type=payload.group_type,
        config=payload.config,
        owner_id=user.id,
    )
    db.add(ng)
    await db.commit()
    await db.refresh(ng)
    return ng


@router.get("/node-groups/{group_id}", response_model=NodeGroupResponse)
async def get_node_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(NodeGroup).where(NodeGroup.id == group_id))
    ng = result.scalar_one_or_none()
    if ng is None or ng.owner_id != user.id:
        raise _not_found()
    return ng


@router.patch("/node-groups/{group_id}", response_model=NodeGroupResponse)
async def update_node_group(
    group_id: uuid.UUID,
    payload: NodeGroupUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(NodeGroup).where(NodeGroup.id == group_id))
    ng = result.scalar_one_or_none()
    if ng is None or ng.owner_id != user.id:
        raise _not_found()

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ng, field, value)

    await db.commit()
    await db.refresh(ng)
    return ng


@router.delete("/node-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(NodeGroup).where(NodeGroup.id == group_id))
    ng = result.scalar_one_or_none()
    if ng is None or ng.owner_id != user.id:
        raise _not_found()
    await db.delete(ng)
    await db.commit()


# ─── Versions ─────────────────────────────────────────────────────────────────


@router.get("/missions/{mission_id}/versions")
async def list_versions(
    mission_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify mission ownership
    mission_result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission_result.scalar_one_or_none()
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    offset = (page - 1) * per_page
    query = (
        select(MissionVersion)
        .where(MissionVersion.mission_id == mission_id)
        .order_by(MissionVersion.version.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count(MissionVersion.id)).where(MissionVersion.mission_id == mission_id)
    )
    total = count_result.scalar() or 0
    pages = (total + per_page - 1) // per_page

    return {
        "items": [VersionResponse.model_validate(v) for v in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post(
    "/missions/{mission_id}/versions",
    response_model=VersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    mission_id: uuid.UUID,
    payload: VersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify mission ownership
    mission_result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission_result.scalar_one_or_none()
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    # Get next version number
    max_ver_result = await db.execute(
        select(func.max(MissionVersion.version)).where(MissionVersion.mission_id == mission_id)
    )
    next_version = (max_ver_result.scalar() or 0) + 1

    version = MissionVersion(
        mission_id=mission_id,
        version=next_version,
        title=mission.title,
        description=mission.description,
        plan=payload.flow_data,
        change_summary=payload.change_summary,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


@router.post(
    "/missions/{mission_id}/versions/{version_id}/restore",
    response_model=RestoreResponse,
)
async def restore_version(
    mission_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify mission ownership
    mission_result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission_result.scalar_one_or_none()
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    # Get version
    ver_result = await db.execute(
        select(MissionVersion).where(
            MissionVersion.id == version_id,
            MissionVersion.mission_id == mission_id,
        )
    )
    version = ver_result.scalar_one_or_none()
    if version is None:
        raise _not_found()

    # Restore snapshot
    if version.snapshot:
        mission.title = version.snapshot.get("title", mission.title)
        mission.description = version.snapshot.get("description", mission.description)
        mission.status = version.snapshot.get("status", mission.status)

    await db.commit()
    return RestoreResponse(
        message=f"Restored to version {version.version}",
        version_id=uuid.UUID(version.id),
        version=version.version,
        snapshot=version.snapshot,
    )


# ─── Export / Import ──────────────────────────────────────────────────────────


@router.get("/missions/{mission_id}/export")
async def export_mission(
    mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mission_result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = mission_result.scalar_one_or_none()
    if mission is None or mission.user_id != user.id:
        raise _not_found()

    return {
        "version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(),
        "mission": {
            "id": str(mission.id),
            "title": mission.title,
            "description": mission.description,
            "status": mission.status,
        },
        "tasks": [],
    }


@router.post(
    "/missions/import",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_mission(
    payload: ImportPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mission_data = payload.data.get("mission", {})
    title = payload.title_override or mission_data.get("title", "Imported Mission")

    mission = Mission(
        title=title,
        description=mission_data.get("description", ""),
        user_id=user.id,
        status="draft",
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)

    tasks = payload.data.get("tasks", [])
    return ImportResponse(
        mission_id=str(mission.id),
        title=mission.title,
        tasks_imported=len(tasks),
    )
