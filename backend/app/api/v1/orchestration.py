"""Orchestration routes — queries REAL orchestration_agents/teams/tasks tables.

These tables already exist in the database with proper schemas.
No migrations needed — just seed data.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


# ── Response models matching frontend TypeScript types ────────────────


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    tools: list = []
    team_id: str | None = None
    is_active: bool = True
    created_at: str
    updated_at: str


class TeamResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    agent_ids: list = []
    strategy: str = "sequential"
    created_at: str
    updated_at: str


class TaskResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    agent_id: str | None = None
    status: str = "pending"
    input: dict = {}
    output: dict = {}
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


def _json(val) -> dict | list:
    if not val:
        return {} if isinstance(val, str) else []
    try:
        return json.loads(val) if isinstance(val, str) else val
    except Exception:
        return {}


def _dt(dt) -> str | None:
    return dt.isoformat() if dt else None


def _status_to_bool(status: str) -> bool:
    return status and status.upper() not in ("OFFLINE", "ERROR", "MAINTENANCE")


def _task_status_map(status: str) -> str:
    mapping = {
        "PENDING": "pending",
        "ASSIGNED": "pending",
        "IN_PROGRESS": "running",
        "BLOCKED": "pending",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
    }
    return mapping.get(status.upper(), "pending") if status else "pending"


# ── Stats ─────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = user.id
    agents_count = await db.execute(
        text("SELECT COUNT(*) FROM orchestration_agents WHERE user_id=:uid"),
        {"uid": uid},
    )
    active_count = await db.execute(
        text(
            "SELECT COUNT(*) FROM orchestration_agents WHERE user_id=:uid AND status='IDLE'"
        ),
        {"uid": uid},
    )
    teams_count = await db.execute(
        text("SELECT COUNT(*) FROM orchestration_teams WHERE user_id=:uid"),
        {"uid": uid},
    )
    tasks_count = await db.execute(
        text("SELECT COUNT(*) FROM orchestration_tasks WHERE user_id=:uid"),
        {"uid": uid},
    )
    # Real task status aggregation
    status_q = await db.execute(
        text(
            "SELECT status, COUNT(*) FROM orchestration_tasks WHERE user_id=:uid GROUP BY status"
        ),
        {"uid": uid},
    )
    _status_map = {
        "PENDING": "pending",
        "ASSIGNED": "pending",
        "IN_PROGRESS": "running",
        "BLOCKED": "pending",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
    }
    tasks_by_status: dict[str, int] = {}
    for row_s in status_q.fetchall():
        key = _status_map.get(row_s[0], "pending") if row_s[0] else "pending"
        tasks_by_status[key] = tasks_by_status.get(key, 0) + row_s[1]

    # Average task duration for completed tasks (completed_at - created_at)
    duration_q = await db.execute(
        text(
            "SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at)) * 1000) "
            "FROM orchestration_tasks WHERE user_id=:uid AND completed_at IS NOT NULL"
        ),
        {"uid": uid},
    )
    avg_task_duration_ms = round(duration_q.scalar() or 0)

    return {
        "total_agents": agents_count.scalar() or 0,
        "active_agents": active_count.scalar() or 0,
        "total_teams": teams_count.scalar() or 0,
        "total_tasks": tasks_count.scalar() or 0,
        "tasks_by_status": tasks_by_status,
        "avg_task_duration_ms": avg_task_duration_ms,
    }


# ── Agents ────────────────────────────────────────────────────────────


@router.get("/agents")
async def list_agents(
    page: int = Query(1),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit
    count_r = await db.execute(
        text("SELECT COUNT(*) FROM orchestration_agents WHERE user_id=:uid"),
        {"uid": user.id},
    )
    rows_r = await db.execute(
        text(
            "SELECT id, name, description, role, status, capabilities, config, created_at, updated_at FROM orchestration_agents WHERE user_id=:uid ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        ),
        {"uid": user.id, "lim": limit, "off": offset},
    )
    agents = []
    for r in rows_r.fetchall():
        caps = _json(r[5])
        tools = caps.get("tools", []) if isinstance(caps, dict) else []
        config = _json(r[6]) if r[6] else {}
        agents.append(
            {
                "id": str(r[0]),
                "name": r[1],
                "description": r[2],
                "model": r[3] or "deepseek-v4-flash",
                "system_prompt": (
                    config.get("system_prompt") if isinstance(config, dict) else None
                ),
                "tools": tools,
                "team_id": None,
                "is_active": _status_to_bool(r[4]),
                "created_at": _dt(r[7]) or "",
                "updated_at": _dt(r[8]) or "",
            }
        )
    return {"agents": agents, "total": count_r.scalar() or 0}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await db.execute(
        text(
            "SELECT id, name, description, role, status, capabilities, config, created_at, updated_at FROM orchestration_agents WHERE id=:id AND user_id=:uid"
        ),
        {"id": agent_id, "uid": user.id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Agent not found")
    caps = _json(row[5])
    config = _json(row[6]) if row[6] else {}
    return {
        "agent": {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "model": row[3] or "deepseek-v4-flash",
            "system_prompt": (
                config.get("system_prompt") if isinstance(config, dict) else None
            ),
            "tools": caps.get("tools", []) if isinstance(caps, dict) else [],
            "team_id": None,
            "is_active": _status_to_bool(row[4]),
            "created_at": _dt(row[7]) or "",
            "updated_at": _dt(row[8]) or "",
        }
    }


@router.post("/agents")
async def create_agent(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import uuid

    aid = str(uuid.uuid4())
    caps = json.dumps({"tools": data.get("capabilities", data.get("tools", []))})
    config = (
        json.dumps({"system_prompt": data.get("system_prompt")})
        if data.get("system_prompt")
        else "{}"
    )
    await db.execute(
        text(
            "INSERT INTO orchestration_agents (id, name, description, role, status, capabilities, config, user_id, created_at, updated_at) VALUES (:id, :name, :desc, :role, 'IDLE', :caps, :cfg, :uid, NOW(), NOW())"
        ),
        {
            "id": aid,
            "name": data.get("name", ""),
            "desc": data.get("description"),
            "role": data.get("role", "WORKER"),
            "caps": caps,
            "cfg": config,
            "uid": user.id,
        },
    )
    await db.commit()
    return await get_agent(aid, db, user)


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Whitelist allowed fields to prevent SQL injection via column names
    ALLOWED_FIELDS = {"name", "description", "is_active"}
    sets = []
    params = {"id": agent_id, "uid": user.id}
    if "name" in data:
        if not isinstance(data["name"], str):
            raise HTTPException(400, "name must be a string")
        sets.append("name = :name")
        params["name"] = data["name"]
    if "description" in data:
        if not isinstance(data["description"], str):
            raise HTTPException(400, "description must be a string")
        sets.append("description = :desc")
        params["desc"] = data["description"]
    if "is_active" in data:
        sets.append("status = :status")
        params["status"] = "IDLE" if data["is_active"] else "INACTIVE"
    if not sets:
        raise HTTPException(400, "No valid fields to update")
    sets.append("updated_at = NOW()")
    await db.execute(
        text(
            "UPDATE orchestration_agents SET "
            + ", ".join(sets)
            + " WHERE id = :id AND user_id = :uid"
        ),
        params,
    )
    await db.commit()
    return await get_agent(agent_id, db, user)


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await db.execute(
        text("DELETE FROM orchestration_agents WHERE id=:id AND user_id=:uid"),
        {"id": agent_id, "uid": user.id},
    )
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(404)
    return {"ok": True}


# ── Teams ─────────────────────────────────────────────────────────────


@router.get("/teams")
async def list_teams(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    count_r = await db.execute(
        text("SELECT COUNT(*) FROM orchestration_teams WHERE user_id=:uid"),
        {"uid": user.id},
    )
    rows_r = await db.execute(
        text(
            "SELECT id, name, description, members, status, created_at, updated_at FROM orchestration_teams WHERE user_id=:uid ORDER BY created_at DESC"
        ),
        {"uid": user.id},
    )
    teams = []
    for r in rows_r.fetchall():
        members = _json(r[3])
        agent_ids = (
            [m.get("id", m) if isinstance(m, dict) else m for m in members]
            if isinstance(members, list)
            else []
        )
        teams.append(
            {
                "id": str(r[0]),
                "name": r[1],
                "description": r[2],
                "agent_ids": agent_ids,
                "strategy": r[4] or "sequential",
                "created_at": _dt(r[5]) or "",
                "updated_at": _dt(r[6]) or "",
            }
        )
    return {"teams": teams, "total": count_r.scalar() or 0}


@router.get("/teams/{team_id}")
async def get_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await db.execute(
        text(
            "SELECT id, name, description, members, status, created_at, updated_at FROM orchestration_teams WHERE id=:id AND user_id=:uid"
        ),
        {"id": team_id, "uid": user.id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Team not found")
    members = _json(row[3])
    agent_ids = (
        [m.get("id", m) if isinstance(m, dict) else m for m in members]
        if isinstance(members, list)
        else []
    )
    return {
        "team": {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "agent_ids": agent_ids,
            "strategy": row[4] or "sequential",
            "created_at": _dt(row[5]) or "",
            "updated_at": _dt(row[6]) or "",
        }
    }


@router.post("/teams")
async def create_team(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import uuid

    tid = str(uuid.uuid4())
    members = json.dumps(data.get("members", data.get("agent_ids", [])))
    await db.execute(
        text(
            "INSERT INTO orchestration_teams (id, name, description, members, status, user_id, created_at, updated_at) VALUES (:id, :name, :desc, :members, 'ACTIVE', :uid, NOW(), NOW())"
        ),
        {
            "id": tid,
            "name": data.get("name", ""),
            "desc": data.get("description"),
            "members": members,
            "uid": user.id,
        },
    )
    await db.commit()
    return await get_team(tid, db, user)


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await db.execute(
        text("DELETE FROM orchestration_teams WHERE id=:id AND user_id=:uid"),
        {"id": team_id, "uid": user.id},
    )
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(404)
    return {"ok": True}


# ── Tasks ─────────────────────────────────────────────────────────────


@router.get("/tasks")
async def list_tasks(
    page: int = Query(1),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit
    count_r = await db.execute(
        text("SELECT COUNT(*) FROM orchestration_tasks WHERE user_id=:uid"),
        {"uid": user.id},
    )
    rows_r = await db.execute(
        text(
            "SELECT id, name, description, assigned_agent_id, status, input, output, error, created_at, started_at, completed_at FROM orchestration_tasks WHERE user_id=:uid ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        ),
        {"uid": user.id, "lim": limit, "off": offset},
    )
    tasks = []
    for r in rows_r.fetchall():
        tasks.append(
            {
                "id": str(r[0]),
                "name": r[1],
                "description": r[2],
                "agent_id": str(r[3]) if r[3] else None,
                "status": _task_status_map(r[4]),
                "input": _json(r[5]) or {},
                "output": _json(r[6]) or {},
                "error": r[7],
                "created_at": _dt(r[8]) or "",
                "started_at": _dt(r[9]),
                "completed_at": _dt(r[10]),
            }
        )
    return {
        "tasks": tasks,
        "total": count_r.scalar() or 0,
        "page": page,
        "limit": limit,
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await db.execute(
        text(
            "SELECT id, name, description, assigned_agent_id, status, input, output, error, created_at, started_at, completed_at FROM orchestration_tasks WHERE id=:id AND user_id=:uid"
        ),
        {"id": task_id, "uid": user.id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    return {
        "task": {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "agent_id": str(row[3]) if row[3] else None,
            "status": _task_status_map(row[4]),
            "input": _json(row[5]) or {},
            "output": _json(row[6]) or {},
            "error": row[7],
            "created_at": _dt(row[8]) or "",
            "started_at": _dt(row[9]),
            "completed_at": _dt(row[10]),
        }
    }


@router.post("/tasks")
async def create_task(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import uuid

    tid = str(uuid.uuid4())
    inp = json.dumps(data.get("input", {}))
    await db.execute(
        text(
            "INSERT INTO orchestration_tasks (id, name, description, assigned_agent_id, status, input, user_id, created_at) VALUES (:id, :name, :desc, :agent_id, 'PENDING', :inp, :uid, NOW())"
        ),
        {
            "id": tid,
            "name": data.get("name", ""),
            "desc": data.get("description"),
            "agent_id": data.get("agent_id"),
            "inp": inp,
            "uid": user.id,
        },
    )
    await db.commit()
    return await get_task(tid, db, user)


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Whitelist allowed fields to prevent SQL injection via column names
    ALLOWED_TASK_FIELDS = {"name", "description", "status"}
    sets = []
    params = {"id": task_id, "uid": user.id}
    if "name" in data:
        if not isinstance(data["name"], str):
            raise HTTPException(400, "name must be a string")
        sets.append("name = :name")
        params["name"] = data["name"]
    if "description" in data:
        if not isinstance(data["description"], str):
            raise HTTPException(400, "description must be a string")
        sets.append("description = :desc")
        params["desc"] = data["description"]
    if "status" in data:
        status_map = {
            "pending": "PENDING",
            "running": "IN_PROGRESS",
            "completed": "COMPLETED",
            "failed": "FAILED",
            "cancelled": "CANCELLED",
        }
        db_status = status_map.get(str(data["status"]), "PENDING")
        sets.append("status = :status")
        params["status"] = db_status
    if not sets:
        raise HTTPException(400, "No valid fields to update")
    sets.append("updated_at = NOW()")
    await db.execute(
        text(
            "UPDATE orchestration_tasks SET "
            + ", ".join(sets)
            + " WHERE id = :id AND user_id = :uid"
        ),
        params,
    )
    await db.commit()
    return await get_task(task_id, db, user)


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await db.execute(
        text("DELETE FROM orchestration_tasks WHERE id=:id AND user_id=:uid"),
        {"id": task_id, "uid": user.id},
    )
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(404)
    return {"ok": True}
