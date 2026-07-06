from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Async engine - all params driven by app/config.py settings
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    echo=settings.DB_ECHO,
    connect_args={
        "server_settings": {
            "statement_timeout": str(settings.DATABASE_STATEMENT_TIMEOUT_MS),
            "idle_in_transaction_session_timeout": str(settings.DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS),
        },
        "timeout": settings.DATABASE_CONNECT_TIMEOUT,
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields an async session WITHOUT implicit commit.

    Command handlers own their own transaction boundaries via
    ``CommandHandlerBase.wrap_command()``.  Query handlers never commit.
    """
    async with AsyncSessionLocal() as session:
        yield session


# Legacy — kept for backwards compatibility with v1 endpoints and AuthCookieMiddleware
async def get_db():
    """FastAPI dependency that yields an async database session.

    Auto-commits on success.  Prefer ``get_db_session`` for new code.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias for backwards compatibility
SessionLocal = AsyncSessionLocal


# ── Task 2.8: fresh_session() wrapper ───────────────────────────
# Consolidates the AsyncSessionLocal() pattern used in fire-and-forget
# contexts (chat_service.py, task workers, etc.).  The wrapper owns its
# transaction: commit on success, rollback on exception.  The caller
# does NOT own this transaction — fresh_session is the boundary.
from contextlib import asynccontextmanager as _asynccontextmanager


@_asynccontextmanager
async def fresh_session():
    """Open a short-lived AsyncSession that commits on success, rolls back on exception.

    Use this for writes that must NOT hold a transaction open across a long-running
    operation (LLM stream, tool execution).  The caller does NOT own this transaction —
    fresh_session does.

    fresh_session() owns its transaction (fresh AsyncSession), so the AGENTS.md §3
    "no commit in sub-modules" rule does not apply — the wrapper is the transaction
    boundary, not a sub-module of the caller.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
