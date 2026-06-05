"""2FA request/response schemas."""

from pydantic import BaseModel, field_validator


class TOTPSetupResponse(BaseModel):
    """Response for 2FA setup initiation."""

    secret: str
    provisioning_uri: str
    qr_code_base64: str


class TOTPVerifySetupRequest(BaseModel):
    """Request to verify and enable 2FA."""

    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Code must be a 6-digit number")
        return v


class TOTPVerifySetupResponse(BaseModel):
    """Response after successful 2FA setup."""

    backup_codes: list[str]
    message: str = (
        "2FA enabled successfully. Save your backup codes — they won't be shown again."
    )


class TOTPDisableRequest(BaseModel):
    """Request to disable 2FA."""

    password: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Code must be a 6-digit number")
        return v


class TOTPRegenerateBackupCodesRequest(BaseModel):
    """Request to regenerate backup codes."""

    password: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Code must be a 6-digit number")
        return v


class User2FAStatusResponse(BaseModel):
    """2FA status for current user."""

    totp_enabled: bool
    backup_codes_count: int
    totp_verified_at: str | None = None


class TOTPLoginRequest(BaseModel):
    """Request to complete 2FA login."""

    temp_token: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Code must be a 6-digit number")
        return v


class TOTPRegenerateResponse(BaseModel):
    """Response for backup code regeneration."""

    backup_codes: list[str]
    message: str = "New backup codes generated. Old codes are now invalid."
