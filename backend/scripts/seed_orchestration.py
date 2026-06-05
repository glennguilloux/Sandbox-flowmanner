"""Seed orchestration and community data into REAL database tables."""

import asyncio
import json
import uuid
from app.database import AsyncSessionLocal
from sqlalchemy import text

AGENTS = [
    {
        "name": "Research Analyst",
        "description": "Deep research and analysis agent with web scraping capabilities",
        "role": "SPECIALIST",
        "caps": {"tools": ["web_search", "data_analysis", "report_generation"]},
        "cfg": {"system_prompt": "You are a research analyst."},
    },
    {
        "name": "Support Agent",
        "description": "Customer support specialist with knowledge base access",
        "role": "WORKER",
        "caps": {"tools": ["knowledge_base", "ticket_system", "email"]},
        "cfg": {"system_prompt": "You are a helpful support agent."},
    },
    {
        "name": "Code Assistant",
        "description": "Software development assistant for code review and generation",
        "role": "WORKER",
        "caps": {"tools": ["code_execution", "github", "documentation"]},
        "cfg": {"system_prompt": "You are a senior developer."},
    },
    {
        "name": "Data Processor",
        "description": "Automated data pipeline and ETL specialist",
        "role": "WORKER",
        "caps": {"tools": ["database", "file_processing", "api_client"]},
        "cfg": {"system_prompt": "You process and transform data."},
    },
]

TEAMS = [
    {
        "name": "Research Team",
        "description": "Cross-functional research and analysis team",
        "members": [0, 2],
    },
    {
        "name": "DevOps Team",
        "description": "Development and operations automation team",
        "members": [2, 3],
    },
]

TASK_DATA = [
    ("Analyze Q4 market data", "PENDING"),
    ("Resolve ticket #1234", "IN_PROGRESS"),
    ("Review PR #567", "COMPLETED"),
    ("Process daily ETL", "COMPLETED"),
    ("Generate monthly report", "FAILED"),
    ("Setup CI pipeline", "CANCELLED"),
    ("Data quality audit", "COMPLETED"),
]

TEMPLATES = [
    {
        "title": "Customer Support Bot",
        "description": "Customer support agent with knowledge base integration",
        "category": "support",
        "tags": ["support", "automation"],
        "rating": 4.8,
        "rc": 12,
        "fc": 34,
        "uc": 156,
        "featured": True,
    },
    {
        "title": "Research Analyst",
        "description": "Deep research agent with web search and analysis",
        "category": "research",
        "tags": ["research", "analysis"],
        "rating": 4.5,
        "rc": 8,
        "fc": 21,
        "uc": 89,
        "featured": True,
    },
    {
        "title": "Code Review Assistant",
        "description": "Automated code review with security scanning",
        "category": "engineering",
        "tags": ["code-review", "security"],
        "rating": 4.3,
        "rc": 6,
        "fc": 15,
        "uc": 67,
        "featured": False,
    },
    {
        "title": "Lead Qualifier",
        "description": "Sales lead qualification and scoring agent",
        "category": "sales",
        "tags": ["sales", "crm"],
        "rating": 4.0,
        "rc": 4,
        "fc": 8,
        "uc": 45,
        "featured": False,
    },
    {
        "title": "Meeting Summarizer",
        "description": "Meeting transcription and action item extraction",
        "category": "productivity",
        "tags": ["meetings", "productivity"],
        "rating": 4.7,
        "rc": 10,
        "fc": 28,
        "uc": 134,
        "featured": True,
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT id FROM users LIMIT 1"))
        user_row = r.fetchone()
        if not user_row:
            print("ERROR: No users found")
            return
        uid = int(user_row[0])
        print(f"Using user_id: {uid}")

        # Seed agents
        agent_ids = []
        for a in AGENTS:
            aid = str(uuid.uuid4())
            agent_ids.append(aid)
            exists = await db.execute(
                text(
                    "SELECT COUNT(*) FROM orchestration_agents WHERE name=:n AND user_id=:u"
                ),
                {"n": a["name"], "u": uid},
            )
            if exists.scalar() > 0:
                print(f"  Skip agent: {a['name']}")
                continue
            await db.execute(
                text(
                    "INSERT INTO orchestration_agents (id, name, description, role, status, capabilities, config, user_id, created_at, updated_at) VALUES (:id, :name, :desc, :role, 'IDLE', :caps, :cfg, :uid, NOW(), NOW())"
                ),
                {
                    "id": aid,
                    "name": a["name"],
                    "desc": a["description"],
                    "role": a["role"],
                    "caps": json.dumps(a["caps"]),
                    "cfg": json.dumps(a["cfg"]),
                    "uid": uid,
                },
            )
            print(f"  Created agent: {a['name']}")

        # Get DB agent IDs
        r = await db.execute(
            text(
                "SELECT id FROM orchestration_agents WHERE user_id=:u ORDER BY created_at DESC"
            ),
            {"u": uid},
        )
        db_ids = [str(row[0]) for row in r.fetchall()]

        # Seed teams
        for t in TEAMS:
            tid = str(uuid.uuid4())
            member_ids = [db_ids[i] for i in t["members"] if i < len(db_ids)]
            members_json = json.dumps([{"id": m, "role": "member"} for m in member_ids])
            exists = await db.execute(
                text(
                    "SELECT COUNT(*) FROM orchestration_teams WHERE name=:n AND user_id=:u"
                ),
                {"n": t["name"], "u": uid},
            )
            if exists.scalar() > 0:
                print(f"  Skip team: {t['name']}")
                continue
            await db.execute(
                text(
                    "INSERT INTO orchestration_teams (id, name, description, members, status, user_id, created_at, updated_at) VALUES (:id, :name, :desc, :members, 'ACTIVE', :uid, NOW(), NOW())"
                ),
                {
                    "id": tid,
                    "name": t["name"],
                    "desc": t["description"],
                    "members": members_json,
                    "uid": uid,
                },
            )
            print(f"  Created team: {t['name']}")

        # Seed tasks
        for i, (name, status) in enumerate(TASK_DATA):
            tid = str(uuid.uuid4())
            agent_id = db_ids[i % len(db_ids)] if db_ids else None
            inp = json.dumps({"query": f"Input for {name}"})
            exists = await db.execute(
                text(
                    "SELECT COUNT(*) FROM orchestration_tasks WHERE name=:n AND user_id=:u"
                ),
                {"n": name, "u": uid},
            )
            if exists.scalar() > 0:
                print(f"  Skip task: {name}")
                continue
            await db.execute(
                text(
                    "INSERT INTO orchestration_tasks (id, name, description, assigned_agent_id, status, input, user_id, created_at) VALUES (:id, :name, :desc, :aid, :status, :inp, :uid, NOW())"
                ),
                {
                    "id": tid,
                    "name": name,
                    "desc": f"Task: {name}",
                    "aid": agent_id,
                    "status": status,
                    "inp": inp,
                    "uid": uid,
                },
            )
            print(f"  Created task: {name} [{status}]")

        # Create community_templates table
        await db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS community_templates (id VARCHAR(36) NOT NULL PRIMARY KEY, title VARCHAR(255) NOT NULL, description TEXT NOT NULL, author_id VARCHAR(36) NOT NULL, author_name VARCHAR(100) NOT NULL, category VARCHAR(50) NOT NULL, tags TEXT, content TEXT, rating FLOAT DEFAULT 0.0, rating_count INTEGER DEFAULT 0, fork_count INTEGER DEFAULT 0, use_count INTEGER DEFAULT 0, is_featured BOOLEAN DEFAULT false, created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), updated_at TIMESTAMP WITH TIME ZONE DEFAULT now())"
            )
        )
        print("  Ensured community_templates table")

        # Seed templates
        for t in TEMPLATES:
            tid = str(uuid.uuid4())
            exists = await db.execute(
                text("SELECT COUNT(*) FROM community_templates WHERE title=:t"),
                {"t": t["title"]},
            )
            if exists.scalar() > 0:
                print(f"  Skip template: {t['title']}")
                continue
            await db.execute(
                text(
                    "INSERT INTO community_templates (id, title, description, author_id, author_name, category, tags, content, rating, rating_count, fork_count, use_count, is_featured, created_at, updated_at) VALUES (:id, :title, :desc, :aid, 'Admin', :cat, :tags, :content, :rating, :rc, :fc, :uc, :featured, NOW(), NOW())"
                ),
                {
                    "id": tid,
                    "title": t["title"],
                    "desc": t["description"],
                    "aid": str(uid),
                    "cat": t["category"],
                    "tags": json.dumps(t["tags"]),
                    "content": json.dumps({"prompt": t["title"]}),
                    "rating": t["rating"],
                    "rc": t["rc"],
                    "fc": t["fc"],
                    "uc": t["uc"],
                    "featured": t["featured"],
                },
            )
            print(f"  Created template: {t['title']}")

        await db.commit()
        print("\nSeed complete!")
        for tbl in [
            "orchestration_agents",
            "orchestration_teams",
            "orchestration_tasks",
            "community_templates",
        ]:
            r = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl}: {r.scalar()} rows")


if __name__ == "__main__":
    asyncio.run(seed())
