from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileCreate(BaseModel):
    filename: str
    content_type: str
    size: int


class FileUpdate(BaseModel):
    filename: str | None = None


class FileResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    user_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
