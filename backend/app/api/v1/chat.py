from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import get_current_user, get_workspace_id
from app.database import get_db
from app.models.chat import ChatFolder, ChatTemplate, ChatThread
from app.schemas.chat import (
    ChatBranchCreate,
    ChatBranchResponse,
    ChatFileCreate,
    ChatFileResponse,
    ChatFolderCreate,
    ChatFolderResponse,
    ChatFolderUpdate,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatTemplateCreate,
    ChatTemplateInstantiate,
    ChatTemplateResponse,
    ChatThreadCreate,
    ChatThreadResponse,
    ChatThreadUpdate,
)
from app.services.chat_service import (
    _get_model_preference,
    create_chat_branch,
    create_chat_file,
    create_chat_message,
    create_chat_thread,
    delete_chat_branch,
    delete_chat_thread,
    generate_thread_title,
    get_chat_branch,
    get_chat_files,
    get_chat_messages,
    list_chat_branches,
    list_chat_threads,
    require_chat_thread_access,
    send_message_to_llm,
    stream_message_to_llm,
    update_chat_thread,
)
from app.services.sse_buffer import get_stream_buffer, replay_from_buffer

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ── Folder endpoints ─────────────────────────────────────────────────────────


@router.get("/folders", response_model=list[ChatFolderResponse])
async def list_folders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatFolder).where(ChatFolder.user_id == user.id).order_by(ChatFolder.name))
    return result.scalars().all()


@router.post("/folders", response_model=ChatFolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: ChatFolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = ChatFolder(user_id=user.id, name=payload.name)
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.patch("/folders/{folder_id}", response_model=ChatFolderResponse)
async def rename_folder(
    folder_id: int,
    payload: ChatFolderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatFolder).where(ChatFolder.id == folder_id, ChatFolder.user_id == user.id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise _not_found()
    folder.name = payload.name
    await db.flush()
    await db.refresh(folder)
    return folder


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatFolder).where(ChatFolder.id == folder_id, ChatFolder.user_id == user.id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise _not_found()
    # Unset folder_id on any threads in this folder
    from sqlalchemy import update as sa_update

    await db.execute(sa_update(ChatThread).where(ChatThread.folder_id == folder_id).values(folder_id=None))
    await db.delete(folder)


# ── Thread endpoints ────────────────────────────────────────────────────────


async def _list_threads(
    db: AsyncSession,
    user: User,
    page: int,
    per_page: int,
    workspace_id: str | None = None,
):
    offset = (page - 1) * per_page
    items, total = await list_chat_threads(db, user.id, offset=offset, limit=per_page, workspace_id=workspace_id)
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/threads", response_model=list[ChatThreadResponse])
async def list_threads_route(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    result = await _list_threads(db, user, page, per_page, workspace_id=workspace_id)
    return result["items"]


@router.post("/threads", response_model=ChatThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ChatThreadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
):
    return await create_chat_thread(
        db,
        user.id,
        user.username,
        payload.title,
        payload.model_preference,
        workspace_id=workspace_id,
    )


@router.get("/threads/{thread_id}", response_model=ChatThreadResponse)
async def get_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await require_chat_thread_access(db, thread_id, user.id)


@router.patch("/threads/{thread_id}", response_model=ChatThreadResponse)
async def update_thread(
    thread_id: int,
    payload: ChatThreadUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    updated = await update_chat_thread(db, thread_id, title=payload.title, is_archived=payload.is_archived)
    if updated is None:
        raise _not_found()
    return updated


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    if not await delete_chat_thread(db, thread_id):
        raise _not_found()


@router.get("/threads/{thread_id}/messages", response_model=list[ChatMessageResponse])
async def list_messages(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    return (await get_chat_messages(db, thread_id))[0]


@router.post(
    "/threads/{thread_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    thread_id: int,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    return await create_chat_message(db, thread_id, payload.role, payload.content)


@router.get("/threads/{thread_id}/files", response_model=list[ChatFileResponse])
async def list_files(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    return await get_chat_files(db, thread_id)


@router.post(
    "/threads/{thread_id}/files",
    response_model=ChatFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_file(
    thread_id: int,
    payload: ChatFileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    return await create_chat_file(
        db,
        thread_id,
        payload.filename,
        payload.mime_type,
        payload.path,
        payload.size_bytes or 0,
    )


# --- Branch endpoints ---


@router.post(
    "/threads/{thread_id}/branches",
    response_model=ChatBranchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_branch(
    thread_id: int,
    payload: ChatBranchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    try:
        branch = await create_chat_branch(db, user.id, thread_id, payload.parent_message_id, payload.title)
        return branch
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/threads/{thread_id}/branches", response_model=list[ChatBranchResponse])
async def list_branches(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    return await list_chat_branches(db, thread_id)


@router.get("/branches/{branch_id}", response_model=ChatBranchResponse)
async def get_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch = await get_chat_branch(db, branch_id)
    if branch is None:
        raise _not_found()
    # Verify access via parent thread's workspace
    await require_chat_thread_access(db, branch.parent_thread_id, user.id)
    return branch


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch = await get_chat_branch(db, branch_id)
    if branch is None:
        raise _not_found()
    # Verify access via parent thread's workspace
    await require_chat_thread_access(db, branch.parent_thread_id, user.id)
    if not await delete_chat_branch(db, branch_id):
        raise _not_found()


@router.post("/threads/{thread_id}/chat")
async def chat_with_llm(
    thread_id: int,
    payload: ChatMessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await require_chat_thread_access(db, thread_id, user.id)

    user_api_key = request.headers.get("X-User-API-Key") if hasattr(request, "headers") else None
    user_base_url = request.headers.get("X-User-Base-URL") if hasattr(request, "headers") else None

    requested_model = payload.model_id or payload.model or _get_model_preference(thread)

    result = await send_message_to_llm(
        db,
        thread_id,
        payload.content,
        user.id,
        requested_model,
        user_api_key=user_api_key,
        user_base_url=user_base_url,
        model_id=requested_model,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "LLM request failed"),
        )

    return {
        "content": result["content"],
        "model": result["model"],
        "token_count": result.get("token_count"),
        "message_id": result.get("message_id"),
        "tool_calls": result.get("tool_calls", []),
    }


async def _sse_stream(generator: AsyncGenerator) -> AsyncGenerator:
    async for chunk in generator:
        yield f"data: {chunk}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/threads/{thread_id}/chat/stream")
async def chat_with_llm_stream(
    thread_id: int,
    payload: ChatMessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await require_chat_thread_access(db, thread_id, user.id)

    user_api_key = request.headers.get("X-User-API-Key") if hasattr(request, "headers") else None
    user_base_url = request.headers.get("X-User-Base-URL") if hasattr(request, "headers") else None

    requested_model = payload.model_id or payload.model or _get_model_preference(thread)

    # Task 1.2b: wrap with get_stream_buffer for Redis event replay
    return StreamingResponse(
        get_stream_buffer(
            _sse_stream(
                stream_message_to_llm(
                    db,
                    thread_id,
                    payload.content,
                    user.id,
                    requested_model,
                    user_api_key=user_api_key,
                    user_base_url=user_base_url,
                    model_id=requested_model,
                )
            )
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── SSE stream replay endpoint (Task 1.2b) ──────────────────────────


@router.get("/streams/{stream_id}/replay")
async def replay_stream(
    stream_id: str,
    since: int = Query(0, ge=0, description="Replay events with seq > since"),
):
    """Replay buffered SSE events for a stream (for client reconnection).

    Returns 404 if the buffer has expired (TTL 5min) or never existed.
    """
    events = await replay_from_buffer(stream_id, since_seq=since)
    if events is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream buffer not found or expired")
    return {"events": events, "stream_id": stream_id}


# Export endpoint
@router.get("/threads/{thread_id}/export")
async def export_thread(
    thread_id: int,
    format: str = Query("markdown"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from fastapi.responses import PlainTextResponse

    await require_chat_thread_access(db, thread_id, user.id)
    thread = await require_chat_thread_access(db, thread_id, user.id)
    msgs, _ = await get_chat_messages(db, thread_id)
    if format == "json":
        return {
            "thread_id": thread.id,
            "title": thread.title,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ],
        }
    lines = ["# " + (thread.title or "Untitled"), ""]
    for m in msgs:
        rl = "**User**" if m.role == "user" else "**Assistant**" if m.role == "assistant" else "**System**"
        ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
        lines.append("### " + rl + (" (" + ts + ")" if ts else ""))
        lines.append("")
        lines.append(m.content)
        lines.append("")
        lines.append("---")
        lines.append("")
    md = "\n".join(lines)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=" + (thread.title or "thread").replace(" ", "_") + ".md"},
    )


# Auto-title endpoint
@router.post("/threads/{thread_id}/title")
async def generate_title(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_chat_thread_access(db, thread_id, user.id)
    title = await generate_thread_title(db, thread_id)
    if title is None:
        return {"title": None, "message": "Not enough messages to generate a title"}
    return {"title": title}


# Metadata PATCH
@router.patch("/threads/{thread_id}/metadata")
async def update_thread_metadata(
    thread_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await require_chat_thread_access(db, thread_id, user.id)
    meta = dict(thread.metadata_) if thread.metadata_ else {}
    if "tags" in payload:
        meta["tags"] = payload["tags"]
    if "is_starred" in payload:
        meta["is_starred"] = payload["is_starred"]
    thread.metadata_ = meta
    await db.flush()
    await db.refresh(thread)
    return {"id": thread.id, "metadata": meta}


# Template CRUD
@router.get("/templates", response_model=list[ChatTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ChatTemplate).order_by(ChatTemplate.name))
    return result.scalars().all()


@router.post(
    "/templates",
    response_model=ChatTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: ChatTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = ChatTemplate(
        workspace_id=1,
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        created_by=user.id,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return t


@router.post(
    "/templates/{template_id}/instantiate",
    response_model=ChatThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def instantiate_template(
    template_id: int,
    payload: ChatTemplateInstantiate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatTemplate).where(ChatTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise _not_found()
    meta = {}
    if template.model:
        meta["model_preference"] = template.model
    if template.system_prompt:
        meta["system_prompt"] = template.system_prompt
    thread = ChatThread(title=payload.title, user_id=user.id, username=user.username, metadata_=meta)
    db.add(thread)
    await db.flush()
    await db.refresh(thread)
    return thread


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatTemplate).where(ChatTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise _not_found()
    await db.delete(template)
    await db.flush()
