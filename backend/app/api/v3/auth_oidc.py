from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/auth", tags=["v3-auth-oidc"])


async def _require_oidc_enabled(db: AsyncSession) -> None:
    from sqlalchemy import text

    result = await db.execute(text("SELECT enabled_globally FROM feature_flags WHERE key = 'AUTH_V3_OIDC'"))
    if not result.scalar():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


@router.post("/oidc/{provider}/login", status_code=status.HTTP_200_OK)
async def oidc_login(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_oidc_enabled(db)
    return ok(
        {
            "authorization_url": f"https://example.com/oauth/{provider}/authorize",
            "state": "pending",
        }
    )


@router.get("/oidc/{provider}/callback", status_code=status.HTTP_302_FOUND)
async def oidc_callback(
    provider: str,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    await _require_oidc_enabled(db)
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/")
