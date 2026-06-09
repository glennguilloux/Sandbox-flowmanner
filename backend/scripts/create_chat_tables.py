"""Create chat tables: chat_threads, chat_messages, chat_files.

Run once:
    python -m scripts.create_chat_tables
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import engine


TABLES_SQL = """
CREATE TABLE IF NOT EXISTS chat_threads (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(255),
    agent_id VARCHAR(36),
    model_preference VARCHAR(100),
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_chat_threads_user_id ON chat_threads(user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id VARCHAR(36) PRIMARY KEY,
    thread_id VARCHAR(36) NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_thread_id ON chat_messages(thread_id);

CREATE TABLE IF NOT EXISTS chat_files (
    id VARCHAR(36) PRIMARY KEY,
    thread_id VARCHAR(36) NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_chat_files_thread_id ON chat_files(thread_id);
"""


async def main():
    async with engine.begin() as conn:
        for statement in TABLES_SQL.strip().split(";"):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))
    print("Chat tables created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
