import asyncio
from sqlalchemy import text


async def check():
    from app.database import async_engine

    async with async_engine.connect() as conn:
        for table in [
            "orchestration_tasks",
            "community_templates",
            "ai_agents",
            "agent_teams",
        ]:
            r = await conn.execute(
                text(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name='{table}' ORDER BY ordinal_position"
                )
            )
            cols = [row[0] for row in r.fetchall()]
            print(f"{table}: {cols}")


asyncio.run(check())
