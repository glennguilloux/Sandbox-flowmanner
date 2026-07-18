from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatFolderCreate(BaseModel):
    name: str


class ChatFolderUpdate(BaseModel):
    name: str


class ChatFolderResponse(BaseModel):
    id: int
    name: str
    user_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatThreadCreate(BaseModel):
    title: str
    model_preference: str | None = None


class ChatThreadUpdate(BaseModel):
    title: str | None = None
    is_archived: bool | None = None


class ChatThreadResponse(BaseModel):
    id: int
    title: str
    user_id: int
    username: str
    is_archived: bool | None = None
    message_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(BaseModel):
    content: str
    role: str = "user"
    model: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None
    attachments: list[Any] | None = None
    web_search: bool | None = None


class ChatMessageResponse(BaseModel):
    id: int
    thread_id: int
    role: str
    content: str
    user_id: int | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatFileCreate(BaseModel):
    filename: str
    mime_type: str | None = None
    path: str = ""
    size_bytes: int | None = None


class ChatFileResponse(BaseModel):
    id: int
    chat_id: int
    filename: str
    mime_type: str | None = None
    path: str
    size_bytes: int | None = None
    uploaded_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatBranchCreate(BaseModel):
    parent_thread_id: int
    parent_message_id: int
    title: str


class ChatBranchResponse(BaseModel):
    id: int
    thread_id: int
    parent_thread_id: int
    parent_message_id: int
    user_id: int
    title: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ChatTemplateResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    created_by: int
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ChatTemplateInstantiate(BaseModel):
    title: str = "New Chat"


class ChatMessageUpdate(BaseModel):
    content: str | None = None
    role: str | None = None
    model: str | None = None
    model_id: str | None = None


class ReactionIn(BaseModel):
    reaction: str
