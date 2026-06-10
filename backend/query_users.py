import asyncio

from sqlalchemy import text

from app.database import AsyncSessionLocal


async def q():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT id, email, role FROM users LIMIT 5"))
        rows = r.fetchall()
        for row in rows:
            print(f"id={row[0]} email={row[1]} role={row[2]}")


asyncio.run(q())
