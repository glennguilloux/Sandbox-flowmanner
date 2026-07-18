"""V2 Chat endpoints — threads, messages, streaming, standardized envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
from app.api.v2.cursor_pagination import CursorParams, cursor_paginated
from app.database import get_db
from app.models.chat import ChatBranch, ChatFolder, ChatMessage, ChatThread
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
    ChatMessageUpdate,
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
    delete_chat_message,
    delete_chat_thread,
    get_chat_branch,
    get_chat_files,
    get_chat_messages,
    get_chat_thread,
    list_chat_branches,
    list_chat_threads,
    send_message_to_llm,
    stream_message_to_llm,
    update_chat_message,
    update_chat_thread,
)
from app.services.sse_buffer import get_stream_buffer

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


router = APIRouter(prefix="/chat", tags=["v2-chat"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _require_owner(thread, user: User) -> None:
    if thread is None or thread.user_id != user.id:
        raise _not_found()


@router.get("/folders")
async def list_folders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatFolder).where(ChatFolder.user_id == user.id).order_by(ChatFolder.name))
    folders = result.scalars().all()
    return ok([ChatFolderResponse.model_validate(f).model_dump() for f in folders])


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: ChatFolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = ChatFolder(user_id=user.id, name=payload.name)
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return ok(ChatFolderResponse.model_validate(folder).model_dump())


@router.patch("/folders/{folder_id}")
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
    return ok(ChatFolderResponse.model_validate(folder).model_dump())


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
    from sqlalchemy import update as sa_update

    await db.execute(sa_update(ChatThread).where(ChatThread.folder_id == folder_id).values(folder_id=None))
    await db.delete(folder)


@router.get("/threads")
async def list_threads_route(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, description="Opaque cursor token for keyset pagination"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if cursor:
        from app.models.chat import ChatThread as ChatThreadModel

        cp = CursorParams(cursor=cursor, direction="after", limit=per_page)
        decoded = cp.decoded
        query = (
            select(ChatThreadModel)
            .where(
                ChatThreadModel.user_id == user.id,
                ChatThreadModel.id > int(decoded["id"]),
            )
            .order_by(ChatThreadModel.id.asc())
            .limit(per_page + 1)
        )
        result = await db.execute(query)
        items = list(result.scalars().all())
        serialized = [ChatThreadResponse.model_validate(t).model_dump() for t in items]
        return cursor_paginated(
            items=serialized,
            limit=per_page,
            cursor_params=cp,
            item_id_fn=lambda x: x["id"],
            item_ts_fn=lambda x: x.get("created_at"),
        )
    offset = (page - 1) * per_page
    items, total = await list_chat_threads(db, user.id, offset=offset, limit=per_page)
    return paginated(
        items=[ChatThreadResponse.model_validate(t).model_dump() for t in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ChatThreadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await create_chat_thread(db, user.id, user.username, payload.title, payload.model_preference)
    return ok(ChatThreadResponse.model_validate(thread).model_dump())


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    return ok(ChatThreadResponse.model_validate(thread).model_dump())


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: int,
    payload: ChatThreadUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    updated = await update_chat_thread(db, thread_id, title=payload.title, is_archived=payload.is_archived)
    if updated is None:
        raise _not_found()
    return ok(ChatThreadResponse.model_validate(updated).model_dump())


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Idempotent: an already-deleted thread returns 204, not 404, so a
    # repeated/stale delete does not surface as a failure to the client.
    thread = await get_chat_thread(db, thread_id)
    if thread is None:
        return
    _require_owner(thread, user)
    await delete_chat_thread(db, thread_id)


@router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    messages = (await get_chat_messages(db, thread_id))[0]
    return ok([ChatMessageResponse.model_validate(m).model_dump() for m in messages])


@router.post(
    "/threads/{thread_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    thread_id: int,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    msg = await create_chat_message(db, thread_id, payload.role, payload.content)
    return ok(ChatMessageResponse.model_validate(msg).model_dump())


@router.get("/threads/{thread_id}/files")
async def list_files(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    files = await get_chat_files(db, thread_id)
    return ok([ChatFileResponse.model_validate(f).model_dump() for f in files])


@router.post(
    "/threads/{thread_id}/files",
    status_code=status.HTTP_201_CREATED,
)
async def create_file(
    thread_id: int,
    payload: ChatFileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    f = await create_chat_file(
        db,
        thread_id,
        payload.filename,
        payload.mime_type,
        payload.path,
        payload.size_bytes or 0,
    )
    return ok(ChatFileResponse.model_validate(f).model_dump())


@router.patch("/messages/{message_id}")
async def patch_message(
    message_id: int,
    payload: ChatMessageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise _not_found()

    thread = await get_chat_thread(db, message.thread_id)
    _require_owner(thread, user)

    if message.role != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only user messages can be edited",
        )

    updated = await update_chat_message(db, message_id, payload.content)
    if updated is None:
        raise _not_found()
    return ok(ChatMessageResponse.model_validate(updated).model_dump())


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise _not_found()

    thread = await get_chat_thread(db, message.thread_id)
    _require_owner(thread, user)

    if message.role != "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only user messages can be deleted",
        )

    # The chat_branches.parent_message_id FK is ondelete="SET NULL", so
    # deleting a referenced message does NOT raise IntegrityError — it would
    # silently orphan the branch with a NULL parent. Explicitly reject the
    # delete when any branch still references this message (Comment 2).
    branch_result = await db.execute(select(ChatBranch.id).where(ChatBranch.parent_message_id == message_id).limit(1))
    if branch_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete this message — it has branches referencing it. Delete the branches first.",
        )

    if not await delete_chat_message(db, message_id):
        raise _not_found()


@router.post("/threads/{thread_id}/branches", status_code=status.HTTP_201_CREATED)
async def create_branch(
    thread_id: int,
    payload: ChatBranchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    try:
        branch = await create_chat_branch(db, user.id, thread_id, payload.parent_message_id, payload.title)
        return ok(ChatBranchResponse.model_validate(branch).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/threads/{thread_id}/branches")
async def list_branches(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)
    branches = await list_chat_branches(db, thread_id)
    return ok([ChatBranchResponse.model_validate(b).model_dump() for b in branches])


@router.get("/branches/{branch_id}")
async def get_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch = await get_chat_branch(db, branch_id)
    if branch is None or branch.user_id != user.id:
        raise _not_found()
    return ok(ChatBranchResponse.model_validate(branch).model_dump())


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch = await get_chat_branch(db, branch_id)
    if branch is None or branch.user_id != user.id:
        raise _not_found()
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
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)

    if payload.system_prompt:
        meta = thread.metadata_ or {}
        meta["system_prompt"] = payload.system_prompt
        thread.metadata_ = meta
        await db.flush()

    user_api_key = request.headers.get("X-User-API-Key") if hasattr(request, "headers") else None
    user_base_url = request.headers.get("X-User-Base-URL") if hasattr(request, "headers") else None
    requested_model = payload.model_id or payload.model or _get_model_preference(thread)

    attachments_data = None
    if payload.attachments:
        attachments_data = [a.model_dump() for a in payload.attachments]

    result = await send_message_to_llm(
        db,
        thread_id,
        payload.content,
        user.id,
        requested_model,
        user_api_key=user_api_key,
        user_base_url=user_base_url,
        model_id=requested_model,
        attachments=attachments_data,
        web_search=payload.web_search,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "LLM request failed"),
        )

    return ok(
        {
            "content": result["content"],
            "model": result["model"],
            "token_count": result.get("token_count"),
            "message_id": result.get("message_id"),
        }
    )


async def _sse_stream(generator: AsyncGenerator) -> AsyncGenerator:
    # The canonical stream_start frame (event: stream_start) is emitted by
    # get_stream_buffer() in app/services/sse_buffer.py so the frontend can
    # wire up per-stream state before tokens arrive. Do NOT emit a second
    # bogus stream_start here.
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
    thread = await get_chat_thread(db, thread_id)
    _require_owner(thread, user)

    if payload.system_prompt:
        meta = thread.metadata_ or {}
        meta["system_prompt"] = payload.system_prompt
        thread.metadata_ = meta
        await db.flush()

    user_api_key = request.headers.get("X-User-API-Key") if hasattr(request, "headers") else None
    user_base_url = request.headers.get("X-User-Base-URL") if hasattr(request, "headers") else None
    requested_model = payload.model_id or payload.model or _get_model_preference(thread)

    attachments_data = None
    if payload.attachments:
        attachments_data = [a.model_dump() for a in payload.attachments]

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
                    attachments=attachments_data,
                    web_search=payload.web_search,
                    request=request,
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
