from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class UserCreate(BaseModel):
    email: str
    password: str
    username: str | None = None
    full_name: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    username: str | None = None
    full_name: str | None
    role: str
    is_admin: bool
    is_active: bool
    avatar_url: str | None = None
    created_at: datetime
    onboarding_step: str | None = None
    onboarding_completed: bool = False
    onboarding_completed_at: datetime | None = None
    onboarding_data: str | None = None
    last_login_at: datetime | None = None
    login_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str | None = None
    username: str | None = None
    username_or_email: str | None = None
    password: str

    @model_validator(mode="after")
    def validate_email_or_username(self):
        if not self.email and not self.username and not self.username_or_email:
            raise ValueError("Either email, username, or username_or_email must be provided")
        return self


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
