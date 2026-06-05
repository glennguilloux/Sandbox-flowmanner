"""Integrations v2 API — HTTP outbound integration CRUD and logs."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select

from app.api.deps import get_current_user
from app.api.v2.base import ok, paginated
from app.database import get_db
from app.models.integration_models import HttpIntegrationConfig, HttpIntegrationLog
from app.schemas.integration_v2 import (
    HttpIntegrationConfigCreate,
    HttpIntegrationConfigResponse,
    HttpIntegrationConfigUpdate,
    HttpIntegrationLogResponse,
)
from app.utils.encryption import encrypt_api_key

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/http", tags=["v2-integrations"])


def _to_response(config: HttpIntegrationConfig) -> dict:
    return HttpIntegrationConfigResponse(
        id=str(config.id),
        user_id=config.user_id,
        name=config.name,
        base_url=config.base_url,
        default_headers=config.default_headers,
        auth_type=config.auth_type,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
        is_active=config.is_active,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    ).model_dump()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: HttpIntegrationConfigCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new HTTP outbound integration config."""
    config = HttpIntegrationConfig(
        user_id=user.id,
        name=payload.name,
        base_url=payload.base_url,
        default_headers=payload.default_headers,
        auth_type=payload.auth_type,
        timeout_seconds=payload.timeout_seconds,
        max_retries=payload.max_retries,
    )

    # Encrypt auth config if provided
    if payload.auth_config:
        try:
            encrypted = encrypt_api_key(json.dumps(payload.auth_config))
            config.auth_config_encrypted = encrypted
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to encrypt auth config: {e}",
            )

    db.add(config)
    await db.commit()
    await db.refresh(config)

    return ok(_to_response(config))


@router.get("/")
@router.get("")
async def list_integrations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all HTTP integration configs for the current user."""
    result = await db.execute(
        select(HttpIntegrationConfig)
        .where(HttpIntegrationConfig.user_id == user.id)
        .order_by(desc(HttpIntegrationConfig.created_at))
    )
    configs = result.scalars().all()
    return ok([_to_response(c) for c in configs])


@router.get("/{integration_id}")
@router.get("/{integration_id}/")
async def get_integration(
    integration_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single HTTP integration config."""
    result = await db.execute(
        select(HttpIntegrationConfig)
        .where(
            HttpIntegrationConfig.id == str(integration_id),
            HttpIntegrationConfig.user_id == user.id,
        )
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration config not found")
    return ok(_to_response(config))


@router.patch("/{integration_id}")
async def update_integration(
    integration_id: uuid.UUID,
    payload: HttpIntegrationConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an HTTP integration config."""
    result = await db.execute(
        select(HttpIntegrationConfig)
        .where(
            HttpIntegrationConfig.id == str(integration_id),
            HttpIntegrationConfig.user_id == user.id,
        )
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration config not found")

    if payload.name is not None:
        config.name = payload.name
    if payload.base_url is not None:
        config.base_url = payload.base_url
    if payload.default_headers is not None:
        config.default_headers = payload.default_headers
    if payload.auth_type is not None:
        config.auth_type = payload.auth_type
    if payload.auth_config is not None:
        try:
            config.auth_config_encrypted = encrypt_api_key(json.dumps(payload.auth_config))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to encrypt auth config: {e}",
            )
    if payload.timeout_seconds is not None:
        config.timeout_seconds = payload.timeout_seconds
    if payload.max_retries is not None:
        config.max_retries = payload.max_retries
    if payload.is_active is not None:
        config.is_active = payload.is_active

    await db.commit()
    await db.refresh(config)
    return ok(_to_response(config))


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an HTTP integration config."""
    result = await db.execute(
        select(HttpIntegrationConfig)
        .where(
            HttpIntegrationConfig.id == str(integration_id),
            HttpIntegrationConfig.user_id == user.id,
        )
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration config not found")

    await db.delete(config)
    await db.commit()


# ── Execution Logs ────────────────────────────────────────────────────────────

@router.get("/{integration_id}/logs")
@router.get("/{integration_id}/logs/")
async def list_integration_logs(
    integration_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List execution logs for an integration config."""
    # Verify ownership
    config_result = await db.execute(
        select(HttpIntegrationConfig)
        .where(
            HttpIntegrationConfig.id == str(integration_id),
            HttpIntegrationConfig.user_id == user.id,
        )
    )
    if not config_result.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration config not found")

    # Count
    total = (await db.execute(
        select(func.count()).where(HttpIntegrationLog.integration_id == str(integration_id))
    )).scalar() or 0

    # Fetch logs
    result = await db.execute(
        select(HttpIntegrationLog)
        .where(HttpIntegrationLog.integration_id == str(integration_id))
        .order_by(desc(HttpIntegrationLog.timestamp))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    logs = result.scalars().all()

    items = [
        HttpIntegrationLogResponse(
            id=str(log.id),
            integration_id=str(log.integration_id),
            request_method=log.request_method,
            request_url=log.request_url,
            request_headers=log.request_headers,
            response_status=log.response_status,
            response_body_preview=log.response_body_preview,
            status=log.status,
            error_message=log.error_message,
            duration_ms=log.duration_ms,
            timestamp=log.timestamp.isoformat() if log.timestamp else None,
        ).model_dump()
        for log in logs
    ]

    return paginated(items=items, total=total, page=page, per_page=per_page)
