"""
Memory & Knowledge Tools — Entity Tracker.

entity_tracker → Automatically extract and track people, projects, and
    concepts across sessions. Extracts entities from text using heuristic
    NLP patterns and persists them with Redis caching and PostgreSQL
    for durable cross-session recall.
"""

from __future__ import annotations

import logging
import os
import re
import uuid

import redis
from pydantic import ConfigDict, Field
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentMemory
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Redis connection (lazy, matches project pattern) ──────────────────

_redis: redis.Redis | None = None
_redis_available: bool | None = None

REDIS_TTL = int(os.getenv("ENTITY_TRACKER_REDIS_TTL", "604800"))  # 7 days


def _get_redis() -> redis.Redis | None:
    """Lazy Redis connection with graceful fallback (project convention)."""
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is None:
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis = redis.from_url(redis_url, decode_responses=True)
            _redis.ping()
            _redis_available = True
        except Exception:
            logger.warning("Redis unavailable; falling back to PostgreSQL-only mode")
            _redis_available = False
            return None
    return _redis


# ── Entity types ──────────────────────────────────────────────────────

ENTITY_TYPES = {
    "person": "Individual person name",
    "project": "Project, initiative, or work stream",
    "concept": "Abstract concept, idea, or topic",
    "organization": "Company, team, or org unit",
    "location": "Physical or virtual location",
}


# ── Input ─────────────────────────────────────────────────────────────

class EntityTrackerInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(
        ...,
        description="Memory key/identifier (for 'extract' this is the source key; "
        "for 'track'/'lookup'/'delete' this is the entity name)",
    )
    value: str | None = Field(
        None,
        description="Text to extract entities from (required for 'extract' action)",
    )
    action: str = Field(
        "extract",
        description=(
            "Action: 'extract' (parse text for entities), "
            "'track' (manually add/update entity), "
            "'list' (list tracked entities), "
            "'lookup' (find entity contexts), or "
            "'delete' (remove tracked entity)"
        ),
    )
    entity_type: str = Field(
        "concept",
        description=f"Entity type for 'track' action: {', '.join(ENTITY_TYPES)}",
    )
    namespace: str = Field(
        "default",
        description="Namespace for isolation per user/session",
    )
    user_id: int | None = Field(
        None,
        description="User ID (auto-set from auth context if omitted)",
    )
    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Max results for list/lookup actions",
    )
    metadata: dict | None = Field(
        None,
        description="Optional key-value metadata for the entity",
    )


# ── Tool ──────────────────────────────────────────────────────────────

class EntityTrackerTool(BaseTool):
    """Automatically extract and track people, projects, and concepts.

    Extracts entities from unstructured text using heuristic NLP patterns
    (proper noun detection, project-name patterns, concept keywords) and
    persists them for cross-session recall and lookup.
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="entity_tracker",
            name="Entity Tracker",
            description=(
                "Automatically extract and track people, projects, and "
                "concepts across sessions. Extracts entities from text "
                "and persists them for cross-session recall."
            ),
            category="memory",
            input_schema=EntityTrackerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["memory", "entity", "extraction", "tracking", "differentiator"],
            requires_auth=True,
            timeout_seconds=20,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = EntityTrackerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        # Resolve user_id from auth context if not explicitly provided
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

        try:
            if action == "extract":
                return await self._extract(validated, user_id)
            elif action == "track":
                return await self._track(validated, user_id)
            elif action == "list":
                return await self._list_entities(validated, user_id)
            elif action == "lookup":
                return await self._lookup(validated, user_id)
            elif action == "delete":
                return await self._delete(validated, user_id)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: {action}. "
                        "Use 'extract', 'track', 'list', 'lookup', or 'delete'."
                    ),
                )
        except Exception as e:
            logger.exception("entity_tracker failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _redis_key(namespace: str, entity_name: str) -> str:
        return f"entity:{namespace}:{entity_name.lower()}"

    @staticmethod
    def _agent_id(namespace: str, entity_name: str) -> str:
        return f"{namespace}:entity:{entity_name.lower()}"

    async def _fetch_text(
        self,
        validated: EntityTrackerInput,
        user_id: int | None,
    ) -> tuple[str | None, str]:
        """Try to fetch text from stored context for the given key."""
        key = validated.key
        namespace = validated.namespace

        # Try Redis
        redis_client = _get_redis()
        if redis_client:
            for prefix in ("ctxwin", "crossagent", "memsum"):
                try:
                    rk = f"{prefix}:{namespace}:{key}"
                    value = redis_client.get(rk)
                    if value:
                        return value, f"redis:{prefix}"
                except Exception:
                    continue

        # Fall back to PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(namespace, key),
                        AgentMemory.user_id == (user_id or 0),
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalars().first()
                if row:
                    return row.content, f"postgresql:{row.content_type}"
        except Exception as e:
            logger.warning("PostgreSQL fetch failed: %s", e)

        return None, "not_found"

    # ── extract ──────────────────────────────────────────────────

    async def _extract(
        self,
        validated: EntityTrackerInput,
        user_id: int | None,
    ) -> ToolResult:
        """Parse text and extract entities (people, projects, concepts, etc.)."""
        # Resolve text: use direct value or fetch from store
        text = validated.value
        if text is None:
            fetched, source = await self._fetch_text(validated, user_id)
            if fetched is None:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"No text found for key='{validated.key}' "
                        f"in namespace='{validated.namespace}'. "
                        "Provide a 'value' or ensure the key exists."
                    ),
                )
            text = fetched

        entities = self._extract_entities(text)
        stats = {
            "text_length": len(text),
            "total_entities": len(entities),
            "by_type": {
                etype: len([e for e in entities if e["type"] == etype])
                for etype in ENTITY_TYPES
            },
        }

        # Persist extracted entities
        persisted = 0
        for entity in entities:
            saved = await self._save_entity(
                validated.namespace,
                entity["name"],
                entity["type"],
                entity.get("context", ""),
                user_id,
                {"source_key": validated.key, "extraction_method": "heuristic"},
            )
            if saved:
                persisted += 1

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "extract",
                "key": validated.key,
                "namespace": validated.namespace,
                "entities": entities,
                "persisted_count": persisted,
                **stats,
            },
        )

    # ── track ────────────────────────────────────────────────────

    async def _track(
        self,
        validated: EntityTrackerInput,
        user_id: int | None,
    ) -> ToolResult:
        """Manually add or update a tracked entity."""
        entity_name = validated.key.strip()
        if not entity_name:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Entity name (key) is required for 'track' action",
            )

        entity_type = validated.entity_type
        if entity_type not in ENTITY_TYPES:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    f"Unknown entity_type: '{entity_type}'. "
                    f"Use one of: {', '.join(ENTITY_TYPES)}"
                ),
            )

        # Use provided value as context/description, or create a stub
        context = validated.value or f"Tracked {entity_type}: {entity_name}"
        metadata = {
            "tracked_manually": True,
            **(validated.metadata or {}),
        }

        saved = await self._save_entity(
            validated.namespace, entity_name, entity_type,
            context, user_id, metadata,
        )

        result = {
            "action": "track",
            "entity_name": entity_name,
            "entity_type": entity_type,
            "namespace": validated.namespace,
        }
        if not saved:
            result["warning"] = "Entity was not persisted (storage unavailable)"

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result=result,
        )

    # ── list ─────────────────────────────────────────────────────

    async def _list_entities(
        self,
        validated: EntityTrackerInput,
        user_id: int | None,
    ) -> ToolResult:
        """List all tracked entities in a namespace."""
        namespace = validated.namespace

        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id.like(f"{namespace}:entity:%"),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "entity_tracker",
                    )
                    .order_by(AgentMemory.updated_at.desc())
                    .limit(validated.limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                entities = []
                for r in rows:
                    entity_name = (
                        r.agent_id.split(":entity:", 1)[1]
                        if ":entity:" in r.agent_id
                        else r.agent_id
                    )
                    meta = r.metadata_json or {}
                    entities.append({
                        "name": entity_name,
                        "type": meta.get("entity_type", "concept"),
                        "context": r.content,
                        "mention_count": meta.get("mention_count", 1),
                        "first_seen": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                        "last_seen": (
                            r.updated_at.isoformat() if r.updated_at else None
                        ),
                    })

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "list",
                        "namespace": namespace,
                        "count": len(entities),
                        "entities": entities,
                    },
                )
        except Exception as e:
            logger.exception("Entity list failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── lookup ───────────────────────────────────────────────────

    async def _lookup(
        self,
        validated: EntityTrackerInput,
        user_id: int | None,
    ) -> ToolResult:
        """Find all stored contexts where an entity was mentioned."""
        entity_name = validated.key.strip()
        if not entity_name:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Entity name (key) is required for 'lookup' action",
            )

        namespace = validated.namespace
        entity_lower = entity_name.lower()

        # Find the entity tracker entry first
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(namespace, entity_name),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "entity_tracker",
                    )
                    .limit(1)
                )
                result = await session.execute(stmt)
                entity_row = result.scalars().first()

                if entity_row is None:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(
                            f"No entity '{entity_name}' found "
                            f"in namespace='{namespace}'"
                        ),
                    )

                # Find all stored contexts that mention this entity
                stmt2 = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content.ilike(f"%{entity_lower}%"),
                        AgentMemory.content_type.in_(
                            ["context_window", "cross_agent_memory", "memory_summary"]
                        ),
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(validated.limit)
                )
                result2 = await session.execute(stmt2)
                mention_rows = result2.scalars().all()

                mentions = [
                    {
                        "id": r.id,
                        "content_type": r.content_type,
                        "snippet": _extract_snippet(r.content, entity_lower),
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                    for r in mention_rows
                ]

                meta = entity_row.metadata_json or {}

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "lookup",
                        "entity_name": entity_name,
                        "entity_type": meta.get("entity_type", "concept"),
                        "namespace": namespace,
                        "first_seen": (
                            entity_row.created_at.isoformat()
                            if entity_row.created_at else None
                        ),
                        "mention_count": len(mentions),
                        "mentions": mentions,
                    },
                )
        except Exception as e:
            logger.exception("Entity lookup failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── delete ───────────────────────────────────────────────────

    async def _delete(
        self,
        validated: EntityTrackerInput,
        user_id: int | None,
    ) -> ToolResult:
        """Remove a tracked entity."""
        entity_name = validated.key.strip()
        namespace = validated.namespace
        deleted_pg = False
        deleted_redis = False

        # PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentMemory).where(
                    AgentMemory.agent_id == self._agent_id(namespace, entity_name),
                    AgentMemory.user_id == (user_id or 0),
                    AgentMemory.content_type == "entity_tracker",
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    await session.delete(row)
                if rows:
                    await session.commit()
                    deleted_pg = True
                    logger.info(
                        "Deleted entity tracker entry: name=%s namespace=%s",
                        entity_name, namespace,
                    )
        except Exception as e:
            logger.error("PostgreSQL delete failed: %s", e)

        # Redis
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(namespace, entity_name)
                redis_client.delete(rk)
                deleted_redis = True
            except Exception as e:
                logger.warning("Redis delete failed (non-fatal): %s", e)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "delete",
                "entity_name": entity_name,
                "namespace": namespace,
                "deleted_from_postgresql": deleted_pg,
                "deleted_from_redis": deleted_redis,
            },
        )

    # ── entity persistence ───────────────────────────────────────

    async def _save_entity(
        self,
        namespace: str,
        entity_name: str,
        entity_type: str,
        context: str,
        user_id: int | None,
        extra_metadata: dict | None = None,
    ) -> bool:
        """Persist an entity to PostgreSQL and cache in Redis."""
        pg_stored = False
        redis_stored = False
        metadata = {
            "entity_type": entity_type,
            **(extra_metadata or {}),
        }

        # PostgreSQL — upsert: increment mention_count if already exists
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentMemory).where(
                    AgentMemory.agent_id == self._agent_id(namespace, entity_name),
                    AgentMemory.user_id == (user_id or 0),
                    AgentMemory.content_type == "entity_tracker",
                )
                result = await session.execute(stmt)
                existing = result.scalars().first()

                if existing:
                    # Update: increment mention count, merge metadata
                    existing.content = context or existing.content
                    existing_meta = existing.metadata_json or {}
                    existing_meta["mention_count"] = (
                        existing_meta.get("mention_count", 1) + 1
                    )
                    existing_meta.update(metadata)
                    existing.metadata_json = existing_meta
                else:
                    entry = AgentMemory(
                        id=str(uuid.uuid4()),
                        user_id=user_id or 0,
                        agent_id=self._agent_id(namespace, entity_name),
                        content=context,
                        content_type="entity_tracker",
                        metadata_json={**metadata, "mention_count": 1},
                    )
                    session.add(entry)

                await session.commit()
                pg_stored = True
        except Exception as e:
            logger.error("Failed to persist entity in PG: %s", e)

        # Redis cache
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(namespace, entity_name)
                redis_client.setex(rk, REDIS_TTL, context)
                redis_stored = True
            except Exception as e:
                logger.warning("Redis entity cache failed (non-fatal): %s", e)

        return pg_stored or redis_stored

    # ── entity extraction engine ─────────────────────────────────

    @staticmethod
    def _extract_entities(text: str) -> list[dict]:
        """Heuristic entity extraction: proper nouns, project patterns, concepts."""
        if not text:
            return []

        entities: list[dict] = []
        seen: set[str] = set()

        # ── Projects (before people — "Phoenix Project" is a project, not a person)
        # ── Projects: words near "project", "initiative", "sprint", "epic", "milestone"
        project_patterns = [
            r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,3})\s+(?i:project|initiative|sprint|epic|milestone)\b',
            r'\b(?i:project|initiative|sprint|epic|milestone)\s+["\u201C]?([A-Za-z0-9\s-]+)["\u201D]?\b',
            r'\b(?i:Project|Initiative)\s+([A-Z][a-zA-Z0-9]+)\b',
        ]
        for pattern in project_patterns:
            for match in re.finditer(pattern, text):
                proj = match.group(1).strip()
                if proj.lower() not in seen and len(proj) > 2:
                    seen.add(proj.lower())
                    seen.add(match.group(0).strip().lower())  # block person re-match
                    entities.append({
                        "name": proj,
                        "type": "project",
                        "context": _surrounding_text(
                            text, match.start(), match.end(),
                        ),
                    })

        # ── Organizations: "Corp", "Inc", "LLC", "Ltd", "Company", "Team"
        org_patterns = [
            r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,3})\s+(?i:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Company)\b',
            r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,2})\s+(?i:Team|Department|Division|Group)\b',
        ]
        for pattern in org_patterns:
            for match in re.finditer(pattern, text):
                org = match.group(1).strip()
                if org.lower() not in seen and len(org) > 2:
                    seen.add(org.lower())
                    seen.add(match.group(0).strip().lower())  # block person re-match
                    entities.append({
                        "name": org,
                        "type": "organization",
                        "context": _surrounding_text(
                            text, match.start(), match.end(),
                        ),
                    })

        # ── People (after projects/orgs — only unmatched capitalized pairs)
        # ── People: capitalized two-word names (Mr./Ms./Dr. prefix or typical patterns)
        person_pattern = re.compile(
            r"\b(?:Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
        )
        for match in person_pattern.finditer(text):
            name = match.group(0).strip()
            if name.lower() not in seen:
                seen.add(name.lower())
                entities.append({
                    "name": name,
                    "type": "person",
                    "context": _surrounding_text(text, match.start(), match.end()),
                })

        # Also catch "FirstName LastName" capitalized pairs not already matched
        for match in re.finditer(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", text):
            first, last = match.group(1), match.group(2)
            full = f"{first} {last}"
            if full.lower() not in seen:
                # Filter out common false positives (days, months, common words)
                if first not in _FALSE_POSITIVES and last not in _FALSE_POSITIVES:
                    seen.add(full.lower())
                    entities.append({
                        "name": full,
                        "type": "person",
                        "context": _surrounding_text(
                            text, match.start(), match.end(),
                        ),
                    })

        # ── Concepts: key nouns/phrases detected by frequency and context
        concept_keywords = [
            "architecture", "design", "deployment", "pipeline", "security",
            "performance", "scalability", "reliability", "monitoring",
            "authentication", "authorization", "database", "migration",
            "refactoring", "integration", "testing", "documentation",
            "strategy", "roadmap", "budget", "deadline", "dependency",
            "workflow", "automation", "optimization", "compliance",
        ]
        text_lower = text.lower()
        for keyword in concept_keywords:
            if keyword in text_lower and keyword not in seen:
                seen.add(keyword)
                # Find the surrounding phrase for context
                idx = text_lower.find(keyword)
                entities.append({
                    "name": keyword.title(),
                    "type": "concept",
                    "context": _surrounding_text(text, idx, idx + len(keyword)),
                })

        # ── Locations: "in City", "at Place", "based in X", "located in X"
        loc_pattern = re.compile(
            r'\b(?:in|at|from|based\sin|located\sin)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b'
        )
        for match in loc_pattern.finditer(text):
            loc = match.group(1).strip()
            if loc.lower() not in seen and loc.lower() not in _FALSE_POSITIVES:
                seen.add(loc.lower())
                entities.append({
                    "name": loc,
                    "type": "location",
                    "context": _surrounding_text(text, match.start(), match.end()),
                })

        # Deduplicate by name+type
        keyed: dict[str, dict] = {}
        for e in entities:
            k = f"{e['type']}:{e['name'].lower()}"
            if k in keyed:
                if len(e.get("context", "")) > len(keyed[k].get("context", "")):
                    keyed[k] = e
            else:
                keyed[k] = e

        return list(keyed.values())


# ── Shared helpers ────────────────────────────────────────────────────

# Words that are commonly capitalized but not names
_FALSE_POSITIVES: set[str] = {
    "The", "This", "That", "These", "Those", "There", "Here",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "Today", "Tomorrow", "Yesterday",
    "First", "Second", "Third", "Last", "Next", "Final",
    "After", "Before", "During", "While", "Since", "Until",
    "Because", "However", "Therefore", "Although", "Unless",
    "Would", "Could", "Should", "Might", "Shall", "Cannot",
    "Other", "Another", "Every", "Several", "Various",
    "About", "Above", "Across", "Against", "Along", "Among",
    "Around", "Behind", "Below", "Beneath", "Beside", "Between",
    "Beyond", "Inside", "Outside", "Under", "Within", "Without",
}


def _surrounding_text(text: str, start: int, end: int, window: int = 60) -> str:
    """Extract surrounding context around a match position."""
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    snippet = text[ctx_start:ctx_end].replace("\n", " ").strip()
    if ctx_start > 0:
        snippet = "…" + snippet
    if ctx_end < len(text):
        snippet = snippet + "…"
    return snippet


def _extract_snippet(text: str, query: str, window: int = 80) -> str:
    """Extract a snippet of text around a query match for mention display."""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:window * 2] + ("…" if len(text) > window * 2 else "")
    start = max(0, idx - window)
    end = min(len(text), idx + len(query) + window)
    snippet = text[start:end].replace("\n", " ")
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


# ── Register ──────────────────────────────────────────────────────────

register_tool(EntityTrackerTool())
