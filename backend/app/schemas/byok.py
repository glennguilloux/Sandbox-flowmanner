from typing import Literal

from fastapi import Header
from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    context_window: int | None = None


class BYOKValidateRequest(BaseModel):
    provider: str
    api_key: str


class BYOKValidateResponse(BaseModel):
    status: Literal["valid", "invalid"]
    models: list[ModelInfo]
    error: str | None = None


def byok_key_header(x_user_api_key: str | None = Header(None)) -> str | None:
    return x_user_api_key


# Alias for import compatibility
BYOKKeyHeader = byok_key_header
