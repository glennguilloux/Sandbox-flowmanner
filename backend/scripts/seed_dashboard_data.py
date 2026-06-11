"""Seed dashboard data for admin42 user (id=60)."""

import asyncio
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def table_exists(conn, table_name: str) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
        {"name": table_name},
    )
    return result.fetchone() is not None


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    user_id = 60

    async with engine.begin() as conn:
        user = await conn.execute(
            text("SELECT id, email, username FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
        user_row = user.fetchone()
        if not user_row:
            await conn.execute(
                text(
                    """INSERT INTO users (email, username, password_hash, full_name, is_active)
                     VALUES (:email, :username, :password, :name, true)"""
                ),
                {
                    "email": "admin42@example.com",
                    "username": "admin42",
                    "password": "placeholder",
                    "name": "Admin 42",
                },
            )
            print(f"  Created user admin42 (id={user_id})")
        else:
            print(f"  Using user: {user_row.username} ({user_row.email})")

        if await table_exists(conn, "missions"):
            existing = await conn.execute(
                text("SELECT COUNT(*) FROM missions WHERE user_id = :uid"),
                {"uid": user_id},
            )
            count = existing.scalar()
            if count == 0:
                missions = [
                    {
                        "title": "Daily News Digest",
                        "description": "Fetch top headlines and summarize",
                        "status": "pending",
                        "mission_type": "scheduled",
                    },
                    {
                        "title": "Code Review Bot",
                        "description": "Review pull requests for code quality",
                        "status": "pending",
                        "mission_type": "on_demand",
                    },
                    {
                        "title": "Weekly Analytics Report",
                        "description": "Generate weekly usage and performance report",
                        "status": "pending",
                        "mission_type": "scheduled",
                    },
                    {
                        "title": "Lead Qualification",
                        "description": "Score and qualify incoming leads",
                        "status": "pending",
                        "mission_type": "on_demand",
                    },
                ]
                for m in missions:
                    await conn.execute(
                        text(
                            """INSERT INTO missions (user_id, title, description, status, mission_type, created_at, updated_at)
                             VALUES (:uid, :title, :desc, :status, :type, NOW(), NOW())"""
                        ),
                        {
                            "uid": user_id,
                            "title": m["title"],
                            "desc": m["description"],
                            "status": m["status"],
                            "type": m["mission_type"],
                        },
                    )
                print(f"  Seeded {len(missions)} missions")
            else:
                print(f"  Missions already exist ({count})")
        else:
            print("  Table 'missions' does not exist - skipping")

        if await table_exists(conn, "workflow_runs"):
            existing = await conn.execute(
                text("SELECT COUNT(*) FROM workflow_runs WHERE user_id = :uid"),
                {"uid": user_id},
            )
            count = existing.scalar()
            if count == 0:
                runs = [
                    {
                        "workflow_name": "News Digest",
                        "status": "completed",
                        "duration_seconds": 12,
                    },
                    {
                        "workflow_name": "Code Review",
                        "status": "completed",
                        "duration_seconds": 9,
                    },
                    {
                        "workflow_name": "Analytics Report",
                        "status": "failed",
                        "duration_seconds": 3,
                    },
                    {
                        "workflow_name": "Lead Qualification",
                        "status": "completed",
                        "duration_seconds": 6,
                    },
                    {
                        "workflow_name": "News Digest",
                        "status": "completed",
                        "duration_seconds": 11,
                    },
                    {
                        "workflow_name": "Code Review",
                        "status": "failed",
                        "duration_seconds": 2,
                    },
                    {
                        "workflow_name": "Lead Qualification",
                        "status": "completed",
                        "duration_seconds": 6,
                    },
                ]
                for r in runs:
                    await conn.execute(
                        text(
                            """INSERT INTO workflow_runs (run_id, workflow_id, workflow_name, workflow_type, user_id, status, duration_seconds, started_at, completed_at)
                             VALUES (:run_id, :wf_id, :wf_name, :wf_type, :uid, :status, :dur, NOW(), NOW())"""
                        ),
                        {
                            "run_id": f"run_{uuid4().hex[:12]}",
                            "wf_id": f"wf_{uuid4().hex[:8]}",
                            "wf_name": r["workflow_name"],
                            "wf_type": "mission",
                            "uid": user_id,
                            "status": r["status"],
                            "dur": r["duration_seconds"],
                        },
                    )
                print(f"  Seeded {len(runs)} workflow runs")
            else:
                print(f"  Workflow runs already exist ({count})")
        else:
            print("  Table 'workflow_runs' does not exist - skipping")

        owner_id_str = str(user_id)

        if await table_exists(conn, "ai_agents"):
            existing = await conn.execute(
                text("SELECT COUNT(*) FROM ai_agents WHERE owner_id = :oid"),
                {"oid": owner_id_str},
            )
            count = existing.scalar()
            if count == 0:
                agents = [
                    {
                        "name": "News Fetcher",
                        "description": "Fetches and parses news articles",
                        "is_active": True,
                    },
                    {
                        "name": "Code Reviewer",
                        "description": "Analyzes code for quality issues",
                        "is_active": True,
                    },
                    {
                        "name": "Analytics Agent",
                        "description": "Generates usage reports",
                        "is_active": True,
                    },
                ]
                for a in agents:
                    await conn.execute(
                        text(
                            """INSERT INTO ai_agents (id, name, description, owner_id, is_active, created_at, updated_at)
                             VALUES (:id, :name, :desc, :oid, :active, NOW(), NOW())"""
                        ),
                        {
                            "id": str(uuid4()),
                            "name": a["name"],
                            "desc": a["description"],
                            "oid": owner_id_str,
                            "active": a["is_active"],
                        },
                    )
                print(f"  Seeded {len(agents)} AI agents")
            else:
                print(f"  AI agents already exist ({count})")
        else:
            print("  Table 'ai_agents' does not exist - skipping")

        if await table_exists(conn, "agent_teams"):
            existing = await conn.execute(
                text("SELECT COUNT(*) FROM agent_teams WHERE owner_id = :oid"),
                {"oid": owner_id_str},
            )
            count = existing.scalar()
            if count == 0:
                teams = [
                    {
                        "name": "Content Team",
                        "description": "Handles content generation workflows",
                        "agent_ids": '["news-fetcher"]',
                    },
                    {
                        "name": "Review Team",
                        "description": "Code review and QA",
                        "agent_ids": '["code-reviewer"]',
                    },
                ]
                for t in teams:
                    await conn.execute(
                        text(
                            """INSERT INTO agent_teams (id, name, description, owner_id, agent_ids, is_active, created_at, updated_at)
                             VALUES (:id, :name, :desc, :oid, :agent_ids, true, NOW(), NOW())"""
                        ),
                        {
                            "id": str(uuid4()),
                            "name": t["name"],
                            "desc": t["description"],
                            "oid": owner_id_str,
                            "agent_ids": t["agent_ids"],
                        },
                    )
                print(f"  Seeded {len(teams)} agent teams")
            else:
                print(f"  Agent teams already exist ({count})")
        else:
            print("  Table 'agent_teams' does not exist - skipping")

        if await table_exists(conn, "marketplace_listings"):
            existing = await conn.execute(
                text("SELECT COUNT(*) FROM marketplace_listings WHERE owner_id = :oid AND listing_type = :ltype"),
                {"oid": owner_id_str, "ltype": "template"},
            )
            count = existing.scalar()
            if count == 0:
                templates = [
                    {
                        "name": "Scrape & Summarize",
                        "description": "Scrape a webpage and generate a concise summary",
                        "category": "research",
                        "downloads": 142,
                    },
                    {
                        "name": "Auto-Reply Bot",
                        "description": "Automatically respond to common customer inquiries",
                        "category": "support",
                        "downloads": 89,
                    },
                    {
                        "name": "Lead Qualification",
                        "description": "Score and route incoming leads based on criteria",
                        "category": "sales",
                        "downloads": 67,
                    },
                    {
                        "name": "Code Review Assistant",
                        "description": "Review code for quality, security, and best practices",
                        "category": "engineering",
                        "downloads": 203,
                    },
                    {
                        "name": "Daily Digest",
                        "description": "Compile daily news and updates into a formatted report",
                        "category": "productivity",
                        "downloads": 115,
                    },
                ]
                for t in templates:
                    await conn.execute(
                        text(
                            """INSERT INTO marketplace_listings (id, name, description, owner_id, listing_type, category_id, download_count, is_published, rating, created_at, updated_at)
                             VALUES (:id, :name, :desc, :oid, 'template', :dl, true, 0.0, NOW(), NOW())"""
                        ),
                        {
                            "id": str(uuid4()),
                            "name": t["name"],
                            "desc": t["description"],
                            "oid": owner_id_str,
                            "dl": t["downloads"],
                        },
                    )
                print(f"  Seeded {len(templates)} community templates")
            else:
                print(f"  Community templates already exist ({count})")
        else:
            print("  Table 'marketplace_listings' does not exist - skipping")

    await engine.dispose()
    print("\nDashboard data seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
