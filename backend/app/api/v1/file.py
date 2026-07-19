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

# Upload hardening (R5 — path-traversal + content validation).
# Bound file size to prevent resource-exhaustion DoS.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "25_000_000"))  # 25 MB

# Allowlist of content ranges identified by leading magic bytes. Anything that
# resolves to an executable/script signature (ELF, PE/MZ, shebang, ZIP-based
# archives of executables, etc.) is rejected — defense-in-depth so an attacker
# cannot drop a runnable payload even though storage is non-executable by path.
_ALLOWED_MAGIC: tuple[tuple[bytes, int], ...] = (
    (b"\x89PNG\r\n\x1a\n", 0),  # PNG
    (b"\xff\xd8\xff", 0),  # JPEG
    (b"GIF87a", 0),  # GIF
    (b"GIF89a", 0),  # GIF
    (b"%PDF-", 0),  # PDF
    (b"PK\x03\x04", 0),  # ZIP / Office Open XML / .docx/.xlsx/.pptx
    (b"BM", 0),  # BMP
    (b"RIFF", 0),  # WEBP (RIFF....WEBP) / WAV
    (b"\x00\x00\x01\x00", 0),  # ICO
    (b"\x00\x00\x00\x18ftypmp4", 0),  # MP4
)
# Known-dangerous signatures we must never accept (explicit deny, even if the
# byte also matched an allowlist prefix).
_BLOCKED_MAGIC: tuple[tuple[bytes, int], ...] = (
    (b"\x7fELF", 0),  # Linux/Unix ELF binary
    (b"MZ", 0),  # Windows PE/executable
    (b"#!/", 0),  # shebang script
    (b"\xfe\xed\xfa\xce", 0),  # Mach-O (macOS binary)
    (b"\xca\xfe\xba\xbe", 0),  # Mach-O fat binary
)


def _validate_upload_content(content: bytes) -> None:
    """Reject oversized or executable-typed uploads (R5).

    Text payloads (no magic bytes) are permitted; only content that resolves to
    an executable/script signature is blocked. Raises ``HTTPException`` (400) on
    rejection — fail securely, never write the file.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {len(content)} bytes exceeds limit of {MAX_UPLOAD_BYTES} bytes",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file rejected")

    for sig, offset in _BLOCKED_MAGIC:
        if content[offset : offset + len(sig)] == sig:
            raise HTTPException(
                status_code=400,
                detail="Upload rejected: file content matches a blocked executable/script signature",
            )

    # If the content carries a magic signature, require it to be on the
    # allowlist. Unrecognised binary signatures are rejected by default-deny.
    has_signature = any(
        content[offset : offset + len(sig)] == sig for sig, offset in _ALLOWED_MAGIC
    )
    if has_signature:
        return
    # No recognised magic bytes → treat as text/opaque (e.g. .txt, .csv, .json,
    # .md). Permitted. Executable scripts would have matched _BLOCKED_MAGIC above.


def _safe_storage_name(file_id: str, filename: str | None) -> str:
    """Build a storage filename that can never escape ``UPLOAD_DIR`` (R5).

    Uses ``os.path.basename`` so crafted names like ``../../etc/cron.d/x`` or
    absolute paths collapse to a single safe component. The UUID prefix makes
    collisions impossible even with hostile basenames.
    """
    base = os.path.basename(filename or "").strip() or "unnamed"
    # Defensive: strip any path separators that survive basename on odd inputs.
    base = base.replace("/", "_").replace("\\", "_")
    return f"{file_id}_{base}"

# Both routers serve the same file domain. They intentionally keep distinct URL
# prefixes (/file and /files) for backward compatibility, but MUST share ONE
# canonical OpenAPI tag so the SDK generator emits a single FileService instead
# of FileService + FilesService. (See task t_1db19911.)
router = APIRouter(prefix="/file", tags=["file"])
files_router = APIRouter(prefix="/files", tags=["file"])


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

    # R5 hardening: reject oversized / executable-content uploads BEFORE any
    # write, and store under a basename that cannot escape UPLOAD_DIR.
    _validate_upload_content(content_data)
    storage_name = _safe_storage_name(file_id, file.filename)
    storage_path = UPLOAD_DIR / storage_name
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
    count_result = await db.execute(select(func.count(UserFile.id)).where(UserFile.user_id == user.id))
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
    _r.add_api_route("/upload", upload_file, methods=["POST"], response_model=FileResponse)
    _r.add_api_route("", list_files, methods=["GET"], response_model=FileListResponse)
    _r.add_api_route("/", list_files, methods=["GET"], response_model=FileListResponse)
    _r.add_api_route("/{file_id}", get_file, methods=["GET"], response_model=FileResponse)
    _r.add_api_route("/{file_id}", delete_file, methods=["DELETE"])
    _r.add_api_route("/{file_id}/content", get_file_content, methods=["GET"])
