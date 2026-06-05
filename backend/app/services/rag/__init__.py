from app.services.model_router import ModelRouter
from app.services.rag.chunking_service import ChunkingService
from app.services.rag.embedding_service import EmbeddingService
from app.services.rag.prompt_synthesizer import PromptSynthesizer
from app.services.rag.retrieval_service import RetrievalService
from app.services.rag.vector_store import QdrantVectorStore

_embedding_service: EmbeddingService | None = None
_vector_store: QdrantVectorStore | None = None
_chunking_service: ChunkingService | None = None
_retrieval_service: RetrievalService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_vector_store() -> QdrantVectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store


def get_chunking_service() -> ChunkingService:
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ChunkingService()
    return _chunking_service


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(
            vector_store=get_vector_store(),
            embedding_service=get_embedding_service(),
        )
    return _retrieval_service


def get_prompt_synthesizer() -> PromptSynthesizer:
    return PromptSynthesizer(
        retrieval_service=get_retrieval_service(),
        llm_router=ModelRouter(),
    )
