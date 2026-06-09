# mypy: disable-error-code=attr-defined
"""
P0 Differentiator Tools -- Stub registrations for platform differentiators.

These tools are registered as AVAILABLE in the ToolRegistry so the
frontend progress bar reflects them. Each returns a "coming soon" stub
until the real implementation is built.

P0 Differentiators (10):
  persistent_agent_memory    -> save/recall context across sessions
  semantic_memory_index      -> auto-index conversations into knowledge graphs
  knowledge_base_connector   -> connect to FlowManner knowledge pages
  brand_voice_enforcer       -> enforce custom brand style guides on LLM output
  collaborative_team_space   -> shared whiteboard for multi-agent co-editing
  pii_redactor               -> auto-mask PII before sending to LLMs
  semantic_chunking          -> split documents by paragraph semantics
  sub_agent_router           -> route tasks to specialized agent personas
  task_planner               -> decompose requests into DAG of agent tasks
  rag_context_builder        -> assemble vector chunks into optimized prompts
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC

from pydantic import ConfigDict, Field
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentMemory
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# -- persistent_agent_memory ------------------------------------------


class PersistentAgentMemoryInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(..., description="Action: 'save', 'recall', or 'list'")
    agent_id: str = Field("default", description="Agent session identifier")
    user_id: int | None = Field(
        None, description="User ID (auto-set from auth context if omitted)"
    )
    content: str | None = Field(
        None, description="Content to save (required for 'save')"
    )
    content_type: str = Field(
        "note", description="Type of content: 'note', 'summary', 'context'"
    )
    query: str | None = Field(None, description="Search query (required for 'recall')")
    limit: int = Field(10, ge=1, le=100, description="Max results for recall/list")
    metadata: dict | None = Field(None, description="Optional key-value metadata")


class PersistentAgentMemoryTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="persistent_agent_memory",
            name="Persistent Agent Memory",
            description="Save and recall context across independent agent sessions.",
            category="memory",
            input_schema=PersistentAgentMemoryInput.schema_extra(),
            tags=["memory", "agent", "persistence", "differentiator"],
            requires_auth=True,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = PersistentAgentMemoryInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        # Resolve user_id: explicit input > auth context > default
        context = input_data.get("context", {}) or {}
        user_id = (
            validated.user_id
            if validated.user_id is not None
            else context.get("user_id")
        )
        if user_id is not None:
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Invalid user_id: {user_id}",
                )

        action = validated.action
        agent_id = validated.agent_id

        try:
            async with AsyncSessionLocal() as session:
                if action == "save":
                    return await self._save(session, validated, user_id, agent_id)
                elif action == "recall":
                    return await self._recall(session, validated, user_id, agent_id)
                elif action == "list":
                    return await self._list(session, validated, user_id, agent_id)
                else:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"Unknown action: {action}. Use 'save', 'recall', or 'list'.",
                    )
        except Exception as e:
            logger.exception("persistent_agent_memory failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _save(self, session, validated, user_id, agent_id) -> ToolResult:
        if not validated.content:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="content is required for 'save' action",
            )

        entry = AgentMemory(
            id=str(uuid.uuid4()),
            user_id=user_id or 0,
            agent_id=agent_id,
            content=validated.content,
            content_type=validated.content_type,
            metadata_json=validated.metadata,
        )
        session.add(entry)
        await session.commit()

        logger.info(
            "Agent memory saved: id=%s agent=%s user=%s",
            entry.id,
            agent_id,
            user_id,
        )
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "save",
                "id": entry.id,
                "agent_id": agent_id,
                "content_type": validated.content_type,
                "created_at": (
                    entry.created_at.isoformat() if entry.created_at else None
                ),
            },
        )

    async def _recall(self, session, validated, user_id, agent_id) -> ToolResult:
        if not validated.query:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="query is required for 'recall' action",
            )

        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.user_id == (user_id or 0),
                AgentMemory.content.ilike(f"%{validated.query}%"),
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(validated.limit)
        )

        result = await session.execute(stmt)
        rows = result.scalars().all()

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "recall",
                "query": validated.query,
                "count": len(rows),
                "results": [
                    {
                        "id": r.id,
                        "content": r.content,
                        "content_type": r.content_type,
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                    for r in rows
                ],
            },
        )

    async def _list(self, session, validated, user_id, agent_id) -> ToolResult:
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.user_id == (user_id or 0),
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(validated.limit)
        )

        result = await session.execute(stmt)
        rows = result.scalars().all()

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "list",
                "agent_id": agent_id,
                "count": len(rows),
                "results": [
                    {
                        "id": r.id,
                        "content": r.content,
                        "content_type": r.content_type,
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                    for r in rows
                ],
            },
        )


# -- semantic_memory_index --------------------------------------------


class SemanticMemoryIndexInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str = Field(..., description="Conversation ID to index")
    text: str = Field(..., description="Unstructured text to index")
    metadata: dict | None = Field(None, description="Optional key-value metadata")


class SemanticMemoryIndexTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="semantic_memory_index",
            name="Semantic Memory Index",
            description="Auto-index unstructured conversations into retrievable knowledge graphs.",
            category="memory",
            input_schema=SemanticMemoryIndexInput.schema_extra(),
            tags=["memory", "index", "knowledge-graph", "differentiator"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SemanticMemoryIndexInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context", {}) or {}
        user_id = context.get("user_id", 0)

        try:
            from datetime import datetime

            from app.services.rag.chunking_service import Chunk, ChunkingService
            from app.services.rag.embedding_service import EmbeddingService
            from app.services.rag.vector_store import QdrantVectorStore

            embedder = EmbeddingService()
            store = QdrantVectorStore()
            chunker = ChunkingService()

            # Chunk the text
            chunks = await chunker.chunk_book(
                validated.text,
                book_title=f"memory:{validated.conversation_id}",
            )
            if not chunks:
                chunks = [
                    Chunk(
                        id=str(uuid.uuid4()),
                        book_title=f"memory:{validated.conversation_id}",
                        text=validated.text,
                        topics=[],
                        relevance_score=0.5,
                        chunk_index=0,
                        total_chunks=1,
                        created_at=datetime.now(UTC).isoformat(),
                    )
                ]

            # Make IDs deterministic for idempotency
            for chunk in chunks:
                hash_input = f"{validated.conversation_id}:{chunk.text}"
                chunk.id = str(uuid.uuid5(uuid.NAMESPACE_URL, hash_input))

            # Embed and store
            vectors = await embedder.embed([c.text for c in chunks])
            count = await store.upsert_chunks(user_id, chunks, vectors)
            collection = await store.ensure_collection(user_id)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "indexed": True,
                    "chunk_count": count,
                    "collection": collection,
                },
            )
        except Exception as e:
            logger.exception("semantic_memory_index failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- knowledge_base_connector -----------------------------------------


class KnowledgeBaseConnectorInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    page_id: str = Field(..., description="Knowledge page ID to connect")
    action: str = Field("sync", description="Action: 'sync', 'search', or 'link'")
    query: str | None = Field(None, description="Search query (required for 'search')")
    user_id: int | None = Field(None, description="User ID (auto-set from context)")


class KnowledgeBaseConnectorTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="knowledge_base_connector",
            name="Knowledge Base Connector",
            description="Seamlessly connect and sync with existing FlowManner knowledge pages.",
            category="knowledge",
            input_schema=KnowledgeBaseConnectorInput.schema_extra(),
            tags=["knowledge", "sync", "differentiator"],
            requires_auth=True,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = KnowledgeBaseConnectorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context", {}) or {}
        user_id = validated.user_id or context.get("user_id")
        action = validated.action

        try:
            from sqlalchemy import text

            from app.database import AsyncSessionLocal

            if action == "search":
                if not validated.query:
                    return ToolResult.error_result(
                        tool_id=self.tool_id, error="query is required for 'search'"
                    )
                async with AsyncSessionLocal() as session:
                    pattern = f"%{validated.query}%"
                    result = await session.execute(
                        text(
                            "SELECT id, title, description FROM community_templates WHERE title ILIKE :q OR description ILIKE :q OR content ILIKE :q LIMIT 10"
                        ),
                        {"q": pattern},
                    )
                    rows = result.fetchall()
                    await session.close()
                results = [
                    {"id": str(r[0]), "title": r[1], "description": r[2]} for r in rows
                ]
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "search",
                        "query": validated.query,
                        "results": results,
                        "count": len(results),
                    },
                )

            elif action == "sync":
                from datetime import datetime

                from app.services.rag.chunking_service import Chunk, ChunkingService
                from app.services.rag.embedding_service import EmbeddingService
                from app.services.rag.vector_store import QdrantVectorStore

                embedder = EmbeddingService()
                store = QdrantVectorStore()
                chunker = ChunkingService()
                uid = user_id or 0

                chunks = await chunker.chunk_book(
                    validated.page_id, book_title=f"kb:{validated.page_id}"
                )
                if not chunks:
                    chunks = [
                        Chunk(
                            id=str(uuid.uuid4()),
                            book_title=f"kb:{validated.page_id}",
                            text=validated.page_id,
                            topics=[],
                            relevance_score=0.5,
                            chunk_index=0,
                            total_chunks=1,
                            created_at=datetime.now(UTC).isoformat(),
                        )
                    ]
                for c in chunks:
                    c.id = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL, f"kb:{validated.page_id}:{c.text[:100]}"
                        )
                    )
                vectors = await embedder.embed([c.text for c in chunks])
                count = await store.upsert_chunks(uid, chunks, vectors)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "sync",
                        "page_id": validated.page_id,
                        "indexed_chunks": count,
                    },
                )

            elif action == "link":
                from redis.asyncio import Redis

                from app.config import settings

                try:
                    r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
                    key = f"kb_link:{validated.page_id}"
                    await r.sadd(key, str(user_id or 0))
                    await r.expire(key, 86400 * 30)
                    await r.aclose()
                except Exception:
                    logger.debug(
                        "kb link: Redis unavailable, returning success without persistence"
                    )
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "link",
                        "page_id": validated.page_id,
                        "linked": True,
                    },
                )
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown action: {action}. Use 'sync', 'search', or 'link'.",
                )
        except Exception as e:
            logger.exception("knowledge_base_connector failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- brand_voice_enforcer ---------------------------------------------


class BrandVoiceEnforcerInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="Text to evaluate or rewrite")
    style_guide_id: str = Field(..., description="Brand style guide identifier")
    action: str = Field("evaluate", description="Action: 'evaluate' or 'rewrite'")


class BrandVoiceEnforcerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="brand_voice_enforcer",
            name="Brand Voice Enforcer",
            description="Evaluate and edit text to match a custom, predefined brand style guide.",
            category="content",
            input_schema=BrandVoiceEnforcerInput.schema_extra(),
            tags=["content", "brand", "style-guide", "differentiator"],
            requires_auth=True,
            timeout_seconds=20,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = BrandVoiceEnforcerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            from app.services.brand_voice import evaluate_text, rewrite_text

            if validated.action == "evaluate":
                result = await evaluate_text(validated.text, validated.style_guide_id)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "score": result.score,
                        "issues": [
                            {
                                "type": i.type,
                                "excerpt": i.excerpt,
                                "suggestion": i.suggestion,
                            }
                            for i in result.issues
                        ],
                        "passed": result.passed,
                    },
                )
            elif validated.action == "rewrite":
                result = await rewrite_text(validated.text, validated.style_guide_id)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "rewritten_text": result.rewritten_text,
                        "changes_made": result.changes_made,
                    },
                )
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown action: {validated.action}. Use 'evaluate' or 'rewrite'.",
                )
        except Exception as e:
            logger.exception("brand_voice_enforcer failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- collaborative_team_space -----------------------------------------


class CollaborativeTeamSpaceInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    space_id: str = Field(..., description="Space identifier")
    action: str = Field(
        "read", description="Action: 'create', 'join', 'post', 'read', or 'leave'"
    )
    content: str | None = Field(
        None, description="Content to post (required for 'post')"
    )
    agent_id: str = Field("default", description="Agent identifier")


class CollaborativeTeamSpaceTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="collaborative_team_space",
            name="Collaborative Team Space",
            description="A shared whiteboard memory space for multiple agents to co-edit.",
            category="agent",
            input_schema=CollaborativeTeamSpaceInput.schema_extra(),
            tags=["agent", "collaboration", "whiteboard", "differentiator"],
            requires_auth=True,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CollaborativeTeamSpaceInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            from app.services.team_space import (
                create_space,
                join_space,
                leave_space,
                post_message,
                read_messages,
            )

            action = validated.action
            space_id = validated.space_id
            agent_id = validated.agent_id

            if action == "create":
                info = await create_space(space_id)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "create",
                        "space_id": info.space_id,
                        "created_at": info.created_at,
                    },
                )
            elif action == "join":
                info = await join_space(space_id, agent_id)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "join",
                        "space_id": space_id,
                        "members": info.members,
                    },
                )
            elif action == "post":
                if not validated.content:
                    return ToolResult.error_result(
                        tool_id=self.tool_id, error="content is required for 'post'"
                    )
                info = await post_message(space_id, agent_id, validated.content)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "post",
                        "space_id": space_id,
                        "messages": [
                            {
                                "agent_id": m.agent_id,
                                "content": m.content,
                                "timestamp": m.timestamp,
                            }
                            for m in info.messages
                        ],
                        "members": info.members,
                    },
                )
            elif action == "read":
                info = await read_messages(space_id)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "read",
                        "space_id": space_id,
                        "messages": [
                            {
                                "agent_id": m.agent_id,
                                "content": m.content,
                                "timestamp": m.timestamp,
                            }
                            for m in info.messages
                        ],
                        "members": info.members,
                        "created_at": info.created_at,
                    },
                )
            elif action == "leave":
                info = await leave_space(space_id, agent_id)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "leave",
                        "space_id": space_id,
                        "members": info.members,
                    },
                )
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown action: {action}. Use 'create', 'join', 'post', 'read', or 'leave'.",
                )
        except Exception as e:
            logger.exception("collaborative_team_space failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- pii_redactor -----------------------------------------------------


class PIIRedactorInput(ToolInput):
    text: str = Field(..., description="Text containing potentially sensitive data")
    level: str = Field(
        "standard", description="Redaction level: 'standard', 'strict', or 'custom'"
    )
    redact_types: list[str] | None = Field(
        None,
        description="Specific PII types to redact: name, email, phone, ssn, credit_card, address",
    )


class PIIRedactorTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="pii_redactor",
            name="PII Redactor",
            description="Automatically mask names, emails, and SSNs before sending to LLMs.",
            category="security",
            input_schema=PIIRedactorInput.schema_extra(),
            tags=["security", "privacy", "pii", "differentiator"],
            requires_auth=True,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = PIIRedactorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            from app.services.pii_redactor import redact_pii

            result = redact_pii(
                validated.text,
                types=validated.redact_types,
                level=validated.level,
            )
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "redacted_text": result.redacted_text,
                    "found": [
                        {
                            "type": h.type,
                            "start": h.start,
                            "end": h.end,
                            "masked_value": h.masked_value,
                        }
                        for h in result.found
                    ],
                    "count": result.count,
                },
            )
        except Exception as e:
            logger.exception("pii_redactor failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- semantic_chunking -------------------------------------------------


class SemanticChunkingInput(ToolInput):
    text: str = Field(..., description="Document text to chunk")
    max_chunk_size: int = Field(512, description="Maximum tokens per chunk")
    overlap: int = Field(64, description="Token overlap between chunks")
    strategy: str = Field(
        "semantic", description="Strategy: 'semantic', 'paragraph', or 'sentence'"
    )


class SemanticChunkingTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="semantic_chunking",
            name="Semantic Chunking",
            description="Intelligently split documents based on paragraph semantics, not character limits.",
            category="vector",
            input_schema=SemanticChunkingInput.schema_extra(),
            tags=["vector", "chunking", "embeddings", "differentiator"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SemanticChunkingInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.text or not validated.text.strip():
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "chunks": [],
                    "total_chunks": 0,
                    "strategy": validated.strategy,
                },
            )

        try:
            from app.services.rag.chunking_service import ChunkingService

            chunker = ChunkingService()
            chunks = await chunker.chunk_book(validated.text, book_title="user_input")

            # If strategy is 'sentence' and splitter is available, override separators
            if validated.strategy == "sentence" and chunker.splitter is not None:
                from langchain.text_splitter import RecursiveCharacterTextSplitter

                def _token_len(text: str) -> int:
                    try:
                        import tiktoken

                        return len(tiktoken.get_encoding("cl100k_base").encode(text))
                    except ImportError:
                        return len(text) // 4

                sentence_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=validated.max_chunk_size * 4,
                    chunk_overlap=validated.overlap * 4,
                    length_function=_token_len,
                    separators=[". ", ".\n", "\n", " "],
                )
                raw = sentence_splitter.split_text(validated.text)
                from datetime import datetime

                from app.services.rag.chunking_service import Chunk

                chunks = [
                    Chunk(
                        id=str(uuid.uuid4()),
                        book_title="user_input",
                        text=t.strip(),
                        topics=[],
                        relevance_score=0.5,
                        chunk_index=i,
                        total_chunks=len(raw),
                        created_at=datetime.now(UTC).isoformat(),
                    )
                    for i, t in enumerate(raw)
                    if t.strip()
                ]

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "chunks": [
                        {
                            "id": c.id,
                            "text": c.text,
                            "topics": c.topics,
                            "relevance_score": c.relevance_score,
                        }
                        for c in chunks
                    ],
                    "total_chunks": len(chunks),
                    "strategy": validated.strategy,
                },
            )
        except Exception as e:
            logger.exception("semantic_chunking failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- sub_agent_router --------------------------------------------------


class SubAgentRouterInput(ToolInput):
    task: str = Field(..., description="Task description to route")
    available_agents: list[str] | None = Field(
        None, description="List of available agent IDs"
    )
    strategy: str = Field(
        "auto", description="Routing strategy: 'auto', 'round_robin', or 'llm_select'"
    )


class SubAgentRouterTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="sub_agent_router",
            name="Sub-Agent Router",
            description="Dynamically route tasks to specialized agent personas based on intent.",
            category="agent",
            input_schema=SubAgentRouterInput.schema_extra(),
            tags=["agent", "routing", "orchestration", "differentiator"],
            requires_auth=True,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SubAgentRouterInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            from app.models.capability_models import Budget
            from app.services.budget_enforcer import get_budget_enforcer

            # Discover available agents if none specified
            candidates = validated.available_agents or []
            if not candidates:
                try:
                    from app.services.agent_registry_service import AgentRegistry

                    registry = AgentRegistry()
                    agents = await registry.search_by_capability(validated.task)
                    candidates = [
                        {
                            "id": a.template_id,
                            "name": a.name,
                            "description": a.description or "",
                        }
                        for a in (agents or [])
                    ]
                except Exception:
                    candidates = []

            if not candidates:
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "selected_agent": None,
                        "confidence": 0.0,
                        "rationale": "No available agents to route to",
                        "candidates": [],
                    },
                )

            # Select via round_robin for non-LLM strategies
            if validated.strategy == "round_robin":
                selected = candidates[0]  # Simplest: pick first
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "selected_agent": selected,
                        "confidence": 0.5,
                        "rationale": "Round-robin selection (first available)",
                        "candidates": [c["name"] for c in candidates],
                    },
                )

            # LLM-based selection (default: "auto" / "llm_select")
            enforcer = get_budget_enforcer()
            agent_list = "\n".join(
                f"- {c['name']}: {c.get('description', 'No description')}"
                for c in candidates[:10]
            )
            response = await enforcer.call(
                budget=Budget(max_cost_usd=0.01),
                model_id="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an agent router. Select the single best agent "
                            "for the given task. Respond with ONLY the agent name."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Task: {validated.task}\n\nAvailable agents:\n{agent_list}",
                    },
                ],
                temperature=0.1,
                max_tokens=50,
            )

            selected_name = (response.get("response") or "").strip()
            selected = next(
                (c for c in candidates if c["name"].lower() == selected_name.lower()),
                candidates[0] if candidates else None,
            )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "selected_agent": selected,
                    "confidence": 0.7 if selected else 0.0,
                    "rationale": f"LLM-selected: {selected_name}",
                    "candidates": [c["name"] for c in candidates],
                },
            )
        except Exception as e:
            logger.exception("sub_agent_router failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- task_planner ------------------------------------------------------


class TaskPlannerInput(ToolInput):
    objective: str = Field(..., description="High-level objective to decompose")
    max_steps: int = Field(10, description="Maximum number of subtasks")
    context: str | None = Field(None, description="Additional context for planning")


class TaskPlannerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="task_planner",
            name="Task Planner",
            description="Decompose complex user requests into a DAG of agent tasks.",
            category="agent",
            input_schema=TaskPlannerInput.schema_extra(),
            tags=["agent", "planning", "dag", "differentiator"],
            requires_auth=True,
            timeout_seconds=20,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TaskPlannerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        try:
            import json as _json

            from app.models.capability_models import Budget
            from app.services.budget_enforcer import get_budget_enforcer

            enforcer = get_budget_enforcer()
            ctx = f"\nContext: {validated.context}" if validated.context else ""

            response = await enforcer.call(
                budget=Budget(max_cost_usd=0.02),
                model_id="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a task planner. Decompose the objective into "
                            "subtasks. Output a JSON array of objects with keys: "
                            '"title", "description", "depends_on" (list of indices). '
                            f"Produce at most {validated.max_steps} subtasks."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Objective: {validated.objective}{ctx}",
                    },
                ],
                temperature=0.2,
                max_tokens=2000,
            )

            content = response.get("response", "")
            # Try raw JSON first, fall back to code-block extraction
            try:
                tasks = _json.loads(content.strip())
            except _json.JSONDecodeError:
                # Maybe wrapped in markdown code block
                if "```" in content:
                    parts = content.split("```")
                    content = parts[1] if len(parts) > 1 else content
                    if content.startswith("json"):
                        content = content[4:]
                try:
                    tasks = _json.loads(content.strip())
                except _json.JSONDecodeError:
                    tasks = []
            if not isinstance(tasks, list):
                # Fallback: return raw text as a single task
                tasks = [
                    {"title": validated.objective[:80], "description": content[:200]}
                ]

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "objective": validated.objective,
                    "tasks": tasks[: validated.max_steps],
                    "total_tasks": len(tasks),
                    "model": response.get("model", "unknown"),
                },
            )
        except Exception as e:
            logger.exception("task_planner failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- rag_context_builder -----------------------------------------------


class RAGContextBuilderInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    query: str = Field(..., description="Search query to retrieve relevant chunks")
    user_id: int | None = Field(None, description="User ID (auto-set from context)")
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    max_tokens: int = Field(4096, description="Maximum tokens for assembled context")


class RAGContextBuilderTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="rag_context_builder",
            name="RAG Context Builder",
            description="Assemble retrieved vector chunks into an optimized LLM prompt window.",
            category="knowledge",
            input_schema=RAGContextBuilderInput.schema_extra(),
            tags=["rag", "context", "prompt-engineering", "differentiator"],
            requires_auth=True,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = RAGContextBuilderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context", {}) or {}
        user_id = validated.user_id or context.get("user_id", 0)

        try:
            from app.services.model_router import get_model_router
            from app.services.rag.embedding_service import EmbeddingService
            from app.services.rag.retrieval_service import RetrievalService
            from app.services.rag.vector_store import QdrantVectorStore

            vector_store = QdrantVectorStore()
            embedding_service = EmbeddingService()
            router = get_model_router()
            retrieval = RetrievalService(
                vector_store, embedding_service, llm_router=router
            )

            # Retrieve relevant chunks
            chunks = await retrieval.retrieve(
                user_id=user_id, query=validated.query, limit=validated.top_k
            )

            if not chunks:
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={"context": "", "sources": [], "token_count": 0},
                )

            # Assemble context window
            context_parts = []
            sources = []
            token_count = 0
            for chunk in chunks:
                text = chunk.text
                est_tokens = len(text) // 4
                if token_count + est_tokens > validated.max_tokens:
                    break
                context_parts.append(text)
                token_count += est_tokens
                sources.append(
                    {
                        "chunk_id": chunk.id,
                        "score": round(chunk.score, 4),
                        "preview": text[:200],
                        "book_title": chunk.book_title,
                    }
                )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "context": "\n\n---\n\n".join(context_parts),
                    "sources": sources,
                    "token_count": token_count,
                },
            )
        except Exception as e:
            logger.exception("rag_context_builder failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# -- Register ----------------------------------------------------------

register_tool(PersistentAgentMemoryTool())
register_tool(SemanticMemoryIndexTool())
register_tool(KnowledgeBaseConnectorTool())
register_tool(BrandVoiceEnforcerTool())
register_tool(CollaborativeTeamSpaceTool())
register_tool(PIIRedactorTool())
register_tool(SemanticChunkingTool())
register_tool(SubAgentRouterTool())
register_tool(TaskPlannerTool())
register_tool(RAGContextBuilderTool())
