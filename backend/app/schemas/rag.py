from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RAGCollectionCreate(BaseModel):
    name: str
    description: str | None = None


class RAGCollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RAGCollectionResponse(BaseModel):
    id: str
    name: str
    description: str | None
    user_id: str
    document_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RAGDocumentUpload(BaseModel):
    collection_id: str
    content: str
    metadata: dict | None = None


class RAGDocumentResponse(BaseModel):
    id: str
    collection_id: str
    content: str
    metadata: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RAGSearchRequest(BaseModel):
    query: str
    collection_id: str | None = None
    top_k: int = 5


class RAGSearchResponse(BaseModel):
    results: list[dict]
    query: str
    total: int
