"""2FA TOTP API endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.two_fa import (
    TOTPDisableRequest,
    TOTPRegenerateBackupCodesRequest,
    TOTPRegenerateResponse,
    TOTPSetupResponse,
    TOTPVerifySetupRequest,
    TOTPVerifySetupResponse,
    User2FAStatusResponse,
)
from app.services.auth_service import verify_password
from app.services.totp_service import (
    consume_backup_code,
    generate_backup_codes,
    generate_secret,
    get_provisioning_uri,
    get_qr_code_base64,
    verify_code,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/2fa", tags=["2fa"])


@router.post("/setup", response_model=TOTPSetupResponse)
async def setup_2fa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate TOTP secret and QR code for 2FA setup.

    The user must verify the setup with a code from their authenticator app.
    Until verified, 2FA is not enabled.
    """
    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled. Disable it first to reconfigure.",
        )

    secret = generate_secret()
    uri = get_provisioning_uri(secret, user.email)
    qr_base64 = get_qr_code_base64(uri)

    # Store the secret temporarily (not enabled until verified)
    user.totp_secret = secret
    await db.flush()

    return TOTPSetupResponse(
        secret=secret,
        provisioning_uri=uri,
        qr_code_base64=qr_base64,
    )


@router.post("/verify-setup", response_model=TOTPVerifySetupResponse)
async def verify_setup_2fa(
    payload: TOTPVerifySetupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP setup with a code from the authenticator app and enable 2FA."""
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No 2FA setup in progress. Call /setup first.",
        )

    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled.",
        )

    if not verify_code(user.totp_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Please try again.",
        )

    # Enable 2FA
    from datetime import UTC, datetime

    user.totp_enabled = True
    user.totp_verified_at = datetime.now(UTC)

    # Generate backup codes
    plain_codes, hashed_codes = generate_backup_codes(10)
    user.totp_backup_codes = json.dumps(hashed_codes)

    await db.flush()

    logger.info('2FA enabled for user %s', user.id)

    return TOTPVerifySetupResponse(backup_codes=plain_codes)


@router.post("/disable")
async def disable_2fa(
    payload: TOTPDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA. Requires password and a valid TOTP code."""
    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled.",
        )

    # Verify password
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )

    # Verify TOTP code
    if not verify_code(user.totp_secret, payload.code):
        # Also accept backup codes
        if user.totp_backup_codes:
            success, _ = consume_backup_code(payload.code, user.totp_backup_codes)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid code.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code.",
            )

    # Disable 2FA
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_backup_codes = None
    user.totp_verified_at = None

    await db.flush()

    logger.info('2FA disabled for user %s', user.id)

    return {"message": "2FA disabled successfully."}


@router.post("/backup-codes/regenerate", response_model=TOTPRegenerateResponse)
async def regenerate_backup_codes(
    payload: TOTPRegenerateBackupCodesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate backup codes. Requires password and a valid TOTP code."""
    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled.",
        )

    # Verify password
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )

    # Verify TOTP code
    if not verify_code(user.totp_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code.",
        )

    # Generate new backup codes
    plain_codes, hashed_codes = generate_backup_codes(10)
    user.totp_backup_codes = json.dumps(hashed_codes)

    await db.flush()

    return TOTPRegenerateResponse(backup_codes=plain_codes)


@router.get("/status", response_model=User2FAStatusResponse)
async def get_2fa_status(
    user: User = Depends(get_current_user),
):
    """Get current 2FA status."""
    backup_count = 0
    if user.totp_backup_codes:
        try:
            codes = json.loads(user.totp_backup_codes)
            backup_count = len(codes)
        except (json.JSONDecodeError, TypeError):
            pass

    return User2FAStatusResponse(
        totp_enabled=user.totp_enabled or False,
        backup_codes_count=backup_count,
        totp_verified_at=(
            user.totp_verified_at.isoformat() if user.totp_verified_at else None
        ),
    )
