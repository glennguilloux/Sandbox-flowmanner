"""Pydantic schemas for mission triggers (FLO-118)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator, model_validator

if TYPE_CHECKING:
    from datetime import datetime


class TriggerCreate(BaseModel):
    trigger_type: str  # "cron" | "webhook"
    name: str
    mission_id: str
    cron_expression: str | None = None
    cron_timezone: str = "UTC"
    webhook_secret: str | None = None
    config: dict | None = None

    @field_validator("trigger_type")
    @classmethod
    def validate_trigger_type(cls, v: str) -> str:
        if v not in ("cron", "webhook"):
            raise ValueError("trigger_type must be 'cron' or 'webhook'")
        return v

    @model_validator(mode="after")
    def validate_trigger_fields(self):
        if self.trigger_type == "cron" and not self.cron_expression:
            raise ValueError("cron_expression is required for cron triggers")
        if self.trigger_type == "webhook" and not self.webhook_secret:
            raise ValueError("webhook_secret is required for webhook triggers")
        return self


class TriggerUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    cron_timezone: str | None = None
    config: dict | None = None
    status: str | None = None


class TriggerResponse(BaseModel):
    id: str
    user_id: int
    mission_id: str
    trigger_type: str
    name: str
    status: str
    cron_expression: str | None = None
    cron_timezone: str = "UTC"
    webhook_path: str | None = None
    config: dict | None = None
    fire_count: int = 0
    last_fired_at: datetime | None = None
    next_fire_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TriggerListResponse(BaseModel):
    triggers: list[TriggerResponse]
    total: int


class TriggerLogResponse(BaseModel):
    id: str
    trigger_id: str
    mission_run_id: str | None = None
    status: str
    trigger_type: str
    error_message: str | None = None
    duration_ms: int | None = None
    webhook_signature_valid: bool | None = None
    fired_at: datetime | None = None

    model_config = {"from_attributes": True}


class TriggerLogListResponse(BaseModel):
    logs: list[TriggerLogResponse]
    total: int


class WebhookFireResponse(BaseModel):
    trigger_id: str
    mission_id: str
    log_id: str
    status: str
