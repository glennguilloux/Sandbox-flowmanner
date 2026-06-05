"""
Full-Text Search Service

PostgreSQL full-text search across missions, agents, and knowledge.
Uses tsvector columns with GIN indexes for fast text search.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SearchService:
    """Full-text search across Flowmanner entities."""

    async def search(
        self,
        db: AsyncSession,
        query: str,
        entity_types: list[str] | None = None,
        user_id: int | None = None,
        limit: int = 20,
    ) -> dict:
        """
        Search across missions, agents, and knowledge.

        Returns: {
            "results": [...],
            "total": int,
            "query": str
        }
        """
        if not query or len(query.strip()) < 2:
            return {"results": [], "total": 0, "query": query}

        # Clean and format query for tsquery
        tsquery = self._to_tsquery(query)
        results = []

        types_to_search = entity_types or ["missions", "agents", "knowledge"]

        for entity_type in types_to_search:
            if entity_type == "missions":
                results.extend(await self._search_missions(db, tsquery, user_id, limit))
            elif entity_type == "agents":
                results.extend(await self._search_agents(db, tsquery, user_id, limit))
            elif entity_type == "knowledge":
                results.extend(await self._search_knowledge(db, tsquery, user_id, limit))

        # Sort by relevance score
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        results = results[:limit]

        return {
            "results": results,
            "total": len(results),
            "query": query,
        }

    async def _search_missions(
        self, db: AsyncSession, tsquery: str, user_id: int | None, limit: int
    ) -> list[dict]:
        """Search missions using full-text search."""
        try:
            # Check if tsvector column exists
            check = await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'missions' AND column_name = 'search_vector'"
            ))
            has_tsvector = check.scalar() is not None

            if has_tsvector:
                # Use indexed full-text search
                query = text("""
                    SELECT id, title, description, status, created_at,
                           ts_rank(search_vector, to_tsquery('english', :tsquery)) as score
                    FROM missions
                    WHERE search_vector @@ to_tsquery('english', :tsquery)
                    ORDER BY score DESC
                    LIMIT :limit
                """)
                result = await db.execute(query, {"tsquery": tsquery, "limit": limit})
            else:
                # Fallback to LIKE search
                query = text("""
                    SELECT id, title, description, status, created_at, 0.5 as score
                    FROM missions
                    WHERE title ILIKE :pattern OR description ILIKE :pattern
                    ORDER BY created_at DESC
                    LIMIT :limit
                """)
                pattern = f"%{tsquery.replace(' & ', '%')}%"
                result = await db.execute(query, {"pattern": pattern, "limit": limit})

            rows = result.fetchall()
            return [
                {
                    "type": "mission",
                    "id": row.id,
                    "title": row.title,
                    "description": (row.description or "")[:200],
                    "status": row.status,
                    "created_at": str(row.created_at) if row.created_at else None,
                    "score": float(row.score),
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Mission search failed: {e}")
            return []

    async def _search_agents(
        self, db: AsyncSession, tsquery: str, user_id: int | None, limit: int
    ) -> list[dict]:
        """Search agents using full-text search."""
        try:
            query = text("""
                SELECT id, name, description, category, created_at, 0.5 as score
                FROM agents
                WHERE name ILIKE :pattern OR description ILIKE :pattern
                ORDER BY created_at DESC
                LIMIT :limit
            """)
            pattern = f"%{tsquery.replace(' & ', '%')}%"
            result = await db.execute(query, {"pattern": pattern, "limit": limit})

            rows = result.fetchall()
            return [
                {
                    "type": "agent",
                    "id": row.id,
                    "title": row.name,
                    "description": (row.description or "")[:200],
                    "category": row.category,
                    "created_at": str(row.created_at) if row.created_at else None,
                    "score": float(row.score),
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Agent search failed: {e}")
            return []

    async def _search_knowledge(
        self, db: AsyncSession, tsquery: str, user_id: int | None, limit: int
    ) -> list[dict]:
        """Search knowledge/memories using full-text search."""
        try:
            query = text("""
                SELECT id, content, session_id, created_at, 0.5 as score
                FROM memories
                WHERE content ILIKE :pattern
                ORDER BY created_at DESC
                LIMIT :limit
            """)
            pattern = f"%{tsquery.replace(' & ', '%')}%"
            result = await db.execute(query, {"pattern": pattern, "limit": limit})

            rows = result.fetchall()
            return [
                {
                    "type": "knowledge",
                    "id": row.id,
                    "title": (row.content or "")[:100],
                    "description": (row.content or "")[:200],
                    "session_id": row.session_id,
                    "created_at": str(row.created_at) if row.created_at else None,
                    "score": float(row.score),
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Knowledge search failed: {e}")
            return []

    def _to_tsquery(self, query: str) -> str:
        """Convert user query to tsquery format."""
        # Remove special characters, split on spaces, join with &
        words = query.strip().split()
        # Escape tsquery special chars
        cleaned = []
        for word in words:
            w = word.strip().replace("'", "").replace(":", "").replace("!", "")
            if w and len(w) > 1:
                cleaned.append(w)
        return " & ".join(cleaned) if cleaned else query.strip()

    async def get_suggestions(
        self, db: AsyncSession, query: str, limit: int = 5
    ) -> list[str]:
        """Get search suggestions based on partial input."""
        if not query or len(query.strip()) < 2:
            return []

        try:
            pattern = f"%{query}%"
            # Get recent matching titles
            missions = await db.execute(text(
                "SELECT DISTINCT title FROM missions WHERE title ILIKE :p LIMIT :l"
            ), {"p": pattern, "l": limit})

            return [row.title for row in missions.fetchall()]
        except Exception as e:
            logger.warning(f"Suggestions failed: {e}")
            return []


_search_service: SearchService | None = None


def get_search_service() -> SearchService:
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
