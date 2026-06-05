"""File API router — upload, list, download, delete files (DB-backed)."""

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi import File as FastAPIFile
from fastapi.responses import FileResponse as FastAPIFileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.phase4_models import UserFile
from app.models.user import User

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/opt/flowmanner/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/file", tags=["file"])
files_router = APIRouter(prefix="/files", tags=["files"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class FileResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    user_id: str
    created_at: str

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    files: list[FileResponse]
    total: int


# ── Handlers (registered on both routers) ────────────────────────────────────


async def upload_file(
    file: UploadFile = FastAPIFile(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content_data = await file.read()
    file_id = str(uuid4())

    storage_path = UPLOAD_DIR / f"{file_id}_{file.filename or 'unnamed'}"
    storage_path.write_bytes(content_data)

    db_file = UserFile(
        id=file_id,
        user_id=user.id,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        size=len(content_data),
        storage_path=str(storage_path),
    )
    db.add(db_file)
    await db.flush()
    await db.refresh(db_file)
    return FileResponse(
        id=db_file.id,
        filename=db_file.filename,
        content_type=db_file.content_type,
        size=db_file.size,
        user_id=str(db_file.user_id),
        created_at=db_file.created_at.isoformat() if db_file.created_at else "",
    )


async def list_files(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(func.count(UserFile.id)).where(UserFile.user_id == user.id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(UserFile)
        .where(UserFile.user_id == user.id)
        .order_by(UserFile.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    files = result.scalars().all()
    return FileListResponse(
        files=[
            FileResponse(
                id=f.id,
                filename=f.filename,
                content_type=f.content_type,
                size=f.size,
                user_id=str(f.user_id),
                created_at=f.created_at.isoformat() if f.created_at else "",
            )
            for f in files
        ],
        total=total,
    )


async def get_file(
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserFile).where(UserFile.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    if file.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return FileResponse(
        id=file.id,
        filename=file.filename,
        content_type=file.content_type,
        size=file.size,
        user_id=str(file.user_id),
        created_at=file.created_at.isoformat() if file.created_at else "",
    )


async def delete_file(
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserFile).where(UserFile.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    if file.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    # Clean up the file from disk to prevent orphaned storage
    if file.storage_path:
        Path(file.storage_path).unlink(missing_ok=True)
    await db.delete(file)
    await db.flush()
    return {"status": "deleted"}


# ── Content retrieval ────────────────────────────────────────────────────────


async def get_file_content(
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserFile).where(UserFile.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    if file.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not file.storage_path or not os.path.exists(file.storage_path):
        raise HTTPException(status_code=404, detail="File content not available")
    # Return file as proper binary with its stored content type
    return FastAPIFileResponse(
        path=file.storage_path,
        media_type=file.content_type or "application/octet-stream",
        filename=file.filename,
    )


# ── Register on both routers (with trailing slash variants) ──────────────────
# ── Register on both routers (with trailing slash variants) ──────────────────

for _r in (router, files_router):
    _r.add_api_route(
        "/upload", upload_file, methods=["POST"], response_model=FileResponse
    )
    _r.add_api_route("", list_files, methods=["GET"], response_model=FileListResponse)
    _r.add_api_route("/", list_files, methods=["GET"], response_model=FileListResponse)
    _r.add_api_route(
        "/{file_id}", get_file, methods=["GET"], response_model=FileResponse
    )
    _r.add_api_route("/{file_id}", delete_file, methods=["DELETE"])
    _r.add_api_route("/{file_id}/content", get_file_content, methods=["GET"])
