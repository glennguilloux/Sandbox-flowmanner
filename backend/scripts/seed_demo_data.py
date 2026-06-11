#!/usr/bin/env python3
"""Seed demo data for Flowmanner development.

Creates demo users, missions, agents, and chat conversations.
Only runs when ENABLE_DEMO_MODE=true in the environment.
Idempotent: safe to run multiple times (uses upsert logic).

Usage:
    # From host:
    docker compose exec backend python scripts/seed_demo_data.py

    # Or via make:
    make db-seed-demo
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal, engine
from app.models import (
    Agent,
    ChatMessage,
    ChatThread,
    Mission,
    MissionLog,
    MissionTask,
    User,
    Workspace,
    WorkspaceMember,
)

# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

DEMO_USERS = [
    {
        "email": "demo@flowmanner.com",
        "username": "demo_user",
        "full_name": "Demo User",
        "hashed_password": "$2b$12$LJ3m4ys3Lk0TSwHjmz0VOeUtEfV0rFTUsBgAKMBZo0TSAGMX0GRei",  # "demo1234"
        "role": "pro",
        "is_active": True,
        "is_admin": False,
        "onboarding_completed": True,
        "onboarding_completed_at": datetime.now(UTC),
        "login_count": 42,
    },
    {
        "email": "alice@flowmanner.com",
        "username": "alice_dev",
        "full_name": "Alice Developer",
        "hashed_password": "$2b$12$LJ3m4ys3Lk0TSwHjmz0VOeUtEfV0rFTUsBgAKMBZo0TSAGMX0GRei",
        "role": "free",
        "is_active": True,
        "is_admin": False,
        "onboarding_completed": True,
        "onboarding_completed_at": datetime.now(UTC),
        "login_count": 15,
    },
    {
        "email": "admin@flowmanner.com",
        "username": "admin",
        "full_name": "Flowmanner Admin",
        "hashed_password": "$2b$12$LJ3m4ys3Lk0TSwHjmz0VOeUtEfV0rFTUsBgAKMBZo0TSAGMX0GRei",
        "role": "admin",
        "is_active": True,
        "is_admin": True,
        "onboarding_completed": True,
        "onboarding_completed_at": datetime.now(UTC),
        "login_count": 120,
    },
]

MISSION_TEMPLATES: list[dict[str, Any]] = [
    {
        "title": "Generate REST API for User Management",
        "description": "Create a complete REST API with CRUD endpoints for user management, including authentication middleware and input validation.",
        "mission_type": "code_generation",
        "status": "completed",
        "priority": "high",
        "plan": {
            "steps": [
                "Analyze existing schema",
                "Generate CRUD endpoints",
                "Add auth middleware",
                "Write validation",
                "Generate OpenAPI spec",
            ],
            "estimated_tokens": 4500,
        },
        "results": {
            "files_created": 6,
            "endpoints": [
                "GET /users",
                "POST /users",
                "GET /users/:id",
                "PUT /users/:id",
                "DELETE /users/:id",
            ],
            "tests_passed": 12,
        },
        "tokens_used": 4230,
        "actual_cost": 0.0085,
        "feedback_score": 5,
    },
    {
        "title": "Refactor Database Connection Pool",
        "description": "Optimize the SQLAlchemy connection pool configuration to handle higher concurrency and reduce connection timeouts.",
        "mission_type": "refactoring",
        "status": "completed",
        "priority": "high",
        "plan": {
            "steps": [
                "Audit current pool settings",
                "Benchmark under load",
                "Adjust pool_size and max_overflow",
                "Add pool_pre_ping",
                "Verify with load test",
            ],
            "estimated_tokens": 3000,
        },
        "results": {
            "pool_size_before": 5,
            "pool_size_after": 10,
            "timeout_reduction_ms": 45,
            "throughput_increase_pct": 35,
        },
        "tokens_used": 2870,
        "actual_cost": 0.0057,
        "feedback_score": 4,
    },
    {
        "title": "Write Unit Tests for Auth Module",
        "description": "Comprehensive pytest suite covering JWT generation, token refresh, password hashing, and role-based access control.",
        "mission_type": "testing",
        "status": "completed",
        "priority": "medium",
        "plan": {
            "steps": [
                "Identify test scenarios",
                "Write JWT tests",
                "Write password tests",
                "Write RBAC tests",
                "Measure coverage",
            ],
            "estimated_tokens": 3500,
        },
        "results": {
            "tests_written": 24,
            "coverage_pct": 92,
            "edge_cases_found": 3,
        },
        "tokens_used": 3410,
        "actual_cost": 0.0068,
        "feedback_score": 5,
    },
    {
        "title": "Design Microservices Architecture",
        "description": "Analyze the monolithic backend and propose a migration path to microservices, including service boundaries and communication patterns.",
        "mission_type": "architecture",
        "status": "completed",
        "priority": "high",
        "plan": {
            "steps": [
                "Map current module dependencies",
                "Identify bounded contexts",
                "Define service boundaries",
                "Design API gateway pattern",
                "Plan migration phases",
            ],
            "estimated_tokens": 6000,
        },
        "results": {
            "services_identified": 5,
            "migration_phases": 3,
            "estimated_duration_weeks": 12,
        },
        "tokens_used": 5820,
        "actual_cost": 0.0116,
        "feedback_score": 4,
    },
    {
        "title": "Create Docker Compose for Local Dev",
        "description": "Set up docker-compose.yml with all required services (PostgreSQL, Redis, Qdrant) for local development with hot reload.",
        "mission_type": "devops",
        "status": "completed",
        "priority": "medium",
        "plan": {
            "steps": [
                "List required services",
                "Write compose file",
                "Configure volumes",
                "Add health checks",
                "Document usage",
            ],
            "estimated_tokens": 2500,
        },
        "results": {
            "services_configured": 4,
            "health_checks_added": 4,
            "documentation_written": True,
        },
        "tokens_used": 2340,
        "actual_cost": 0.0047,
        "feedback_score": 5,
    },
    {
        "title": "Implement Rate Limiting Middleware",
        "description": "Add sliding-window rate limiting to FastAPI using Redis as the backing store, with configurable limits per endpoint.",
        "mission_type": "code_generation",
        "status": "completed",
        "priority": "high",
        "plan": {
            "steps": [
                "Design sliding-window algorithm",
                "Implement Redis-backed limiter",
                "Create FastAPI middleware",
                "Add per-endpoint config",
                "Write integration tests",
            ],
            "estimated_tokens": 3800,
        },
        "results": {
            "middleware_created": True,
            "endpoints_protected": 15,
            "test_scenarios": 8,
        },
        "tokens_used": 3650,
        "actual_cost": 0.0073,
        "feedback_score": 4,
    },
    {
        "title": "Build Analytics Dashboard Backend",
        "description": "Create API endpoints for the analytics dashboard: usage metrics, token consumption, cost breakdowns, and trend data.",
        "mission_type": "code_generation",
        "status": "completed",
        "priority": "medium",
        "plan": {
            "steps": [
                "Define metric schemas",
                "Build aggregation queries",
                "Create REST endpoints",
                "Add caching layer",
                "Test with sample data",
            ],
            "estimated_tokens": 4200,
        },
        "results": {
            "endpoints_created": 8,
            "metrics_implemented": 12,
            "cache_hit_target_pct": 85,
        },
        "tokens_used": 4050,
        "actual_cost": 0.0081,
        "feedback_score": 3,
    },
    {
        "title": "Set Up OpenTelemetry Tracing",
        "description": "Integrate OpenTelemetry for distributed tracing across FastAPI, SQLAlchemy, and external HTTP calls with Jaeger export.",
        "mission_type": "devops",
        "status": "completed",
        "priority": "medium",
        "plan": {
            "steps": [
                "Install OTel packages",
                "Configure TracerProvider",
                "Instrument FastAPI",
                "Instrument SQLAlchemy",
                "Export to Jaeger",
            ],
            "estimated_tokens": 3200,
        },
        "results": {
            "instruments_added": 4,
            "jaeger_connected": True,
            "sample_traces": 50,
        },
        "tokens_used": 3100,
        "actual_cost": 0.0062,
        "feedback_score": 5,
    },
    {
        "title": "Migrate to Pydantic v2",
        "description": "Upgrade all Pydantic models from v1 to v2 syntax, including Config migration, validator changes, and model_serializer updates.",
        "mission_type": "refactoring",
        "status": "in_progress",
        "priority": "high",
        "plan": {
            "steps": [
                "Audit v1 patterns",
                "Migrate Config to model_config",
                "Update validators",
                "Fix .dict() to .model_dump()",
                "Run full test suite",
            ],
            "estimated_tokens": 5000,
        },
        "results": None,
        "tokens_used": 2100,
        "actual_cost": 0.0042,
        "feedback_score": None,
    },
    {
        "title": "Write API Integration Tests",
        "description": "End-to-end integration tests for the main API flows: user registration, mission creation, agent execution, and chat messaging.",
        "mission_type": "testing",
        "status": "pending",
        "priority": "medium",
        "plan": {
            "steps": [
                "Set up test database",
                "Write registration flow tests",
                "Write mission lifecycle tests",
                "Write agent execution tests",
                "Write chat flow tests",
            ],
            "estimated_tokens": 4500,
        },
        "results": None,
        "tokens_used": None,
        "actual_cost": None,
        "feedback_score": None,
    },
]

DEMO_AGENTS = [
    {
        "name": "Code Architect",
        "description": "Specialized in system design and code architecture. Analyzes dependencies, identifies patterns, and proposes clean architectures.",
        "system_prompt": "You are a senior software architect. Analyze codebases for architectural patterns, dependency issues, and design improvements. Provide concrete, actionable recommendations with code examples.",
        "model_preference": "deepseek/deepseek-v4-flash",
    },
    {
        "name": "Test Engineer",
        "description": "Writes comprehensive test suites including unit, integration, and e2e tests. Focuses on edge cases and coverage.",
        "system_prompt": "You are a QA engineer specializing in automated testing. Write thorough test suites using pytest, vitest, and Playwright. Always consider edge cases, error paths, and boundary conditions.",
        "model_preference": "deepseek/deepseek-v4-flash",
    },
    {
        "name": "DevOps Specialist",
        "description": "Handles infrastructure, CI/CD pipelines, Docker configurations, and deployment automation.",
        "system_prompt": "You are a DevOps engineer expert in Docker, Kubernetes, GitHub Actions, and infrastructure as code. Focus on reliability, security, and automation. Provide production-ready configurations.",
        "model_preference": "deepseek/deepseek-v4-flash",
    },
    {
        "name": "Security Auditor",
        "description": "Performs security audits, identifies vulnerabilities, and ensures compliance with OWASP guidelines.",
        "system_prompt": "You are a security engineer. Audit code for OWASP Top 10 vulnerabilities, insecure configurations, and data exposure risks. Provide severity ratings and remediation steps.",
        "model_preference": "deepseek/deepseek-v4-flash",
    },
    {
        "name": "Documentation Writer",
        "description": "Creates clear, structured documentation including API docs, READMEs, and architecture guides.",
        "system_prompt": "You are a technical writer. Create clear, concise documentation that developers actually want to read. Use examples, diagrams (in mermaid syntax), and maintain consistent formatting.",
        "model_preference": "deepseek/deepseek-v4-flash",
    },
]

CHAT_CONVERSATIONS: list[dict[str, Any]] = [
    {
        "title": "How to set up the dev environment?",
        "messages": [
            {
                "role": "user",
                "content": "How do I set up the local development environment for Flowmanner?",
            },
            {
                "role": "assistant",
                "content": "Here's how to set up the Flowmanner dev environment:\n\n"
                "1. **Clone the repository** and navigate to the project root\n"
                "2. **Copy `.env.example` to `.env`** and fill in your API keys\n"
                "3. **Run `make dev`** to start all services with hot reload\n"
                "4. **Run migrations**: `make db-upgrade`\n"
                "5. **Access the API docs** at `http://localhost:8000/docs`\n\n"
                "The dev environment includes PostgreSQL, Redis, Qdrant, and Jaeger for tracing. "
                "Backend code changes are hot-reloaded automatically.",
            },
        ],
    },
    {
        "title": "Best practices for mission creation",
        "messages": [
            {
                "role": "user",
                "content": "What are the best practices for creating effective missions?",
            },
            {
                "role": "assistant",
                "content": "Here are key best practices for mission creation:\n\n"
                "**1. Be specific in your description**\n"
                "- Include file paths, function names, and expected behavior\n"
                "- Mention constraints (performance, security, compatibility)\n\n"
                "**2. Break complex tasks into sub-missions**\n"
                "- Use the decomposition feature for tasks with 5+ steps\n"
                "- Each sub-mission should have a clear, verifiable outcome\n\n"
                "**3. Provide context files**\n"
                "- Attach relevant source files so the AI understands existing patterns\n"
                "- Include test files to show expected behavior\n\n"
                "**4. Choose the right model**\n"
                "- Use local models (Qwen) for simple, fast tasks\n"
                "- Use cloud models (DeepSeek) for complex reasoning\n\n"
                "**5. Review and iterate**\n"
                "- Check the generated plan before execution\n"
                "- Provide feedback scores to improve future results",
            },
        ],
    },
    {
        "title": "Understanding the agent system",
        "messages": [
            {
                "role": "user",
                "content": "Can you explain how the agent system works in Flowmanner?",
            },
            {
                "role": "assistant",
                "content": "The Flowmanner agent system works in layers:\n\n"
                "**Agent Registry**\n"
                "- Agents are registered with a name, system prompt, and model preference\n"
                "- Each agent specializes in a specific domain (code, testing, DevOps, etc.)\n\n"
                "**Mission Execution**\n"
                "1. You create a mission describing what you need\n"
                "2. The system selects the best agent based on the task type\n"
                "3. The agent generates a plan with ordered steps\n"
                "4. Each step is executed, producing output\n"
                "5. Results are collected and returned\n\n"
                "**Model Routing**\n"
                "- Missions can specify a model preference (BYOK or built-in)\n"
                "- The ModelRouter selects the best available model\n"
                "- Local models (llama.cpp) are preferred for cost efficiency\n\n"
                "**Feedback Loop**\n"
                "- Your feedback scores train the system to pick better agents\n"
                "- Failed missions trigger improvement suggestions",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    return datetime.now(UTC)


def ago(minutes: int) -> datetime:
    return now_utc() - timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------


async def seed_users(session) -> dict[str, int]:
    """Insert demo users, return mapping of username -> user.id."""
    user_ids: dict[str, int] = {}

    for data in DEMO_USERS:
        stmt = (
            pg_insert(User)
            .values(**data)
            .on_conflict_do_update(
                index_elements=[User.email],
                set_={
                    "full_name": data["full_name"],
                    "role": data["role"],
                    "login_count": data["login_count"],
                },
            )
            .returning(User.id, User.username)
        )
        result = await session.execute(stmt)
        row = result.one()
        user_ids[row.username] = row.id

    await session.flush()
    return user_ids


async def seed_workspace(session, user_ids: dict[str, int]) -> str:
    """Create a demo workspace owned by the demo user."""
    demo_id = user_ids["demo_user"]
    ws_id = str(uuid4())

    stmt = (
        pg_insert(Workspace)
        .values(
            id=ws_id,
            name="Demo Workspace",
            slug="demo-workspace",
            owner_id=demo_id,
            plan="pro",
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[Workspace.slug],
            set_={"name": "Demo Workspace", "plan": "pro"},
        )
        .returning(Workspace.id)
    )
    result = await session.execute(stmt)
    ws_id = result.scalar_one()

    # Add members
    for username, uid in user_ids.items():
        role = "owner" if username == "demo_user" else "member"
        member_stmt = (
            pg_insert(WorkspaceMember)
            .values(
                workspace_id=ws_id,
                user_id=uid,
                role=role,
                is_active=True,
            )
            .on_conflict_do_nothing()
        )
        await session.execute(member_stmt)

    await session.flush()
    return ws_id


async def seed_missions(session, user_ids: dict[str, int]) -> list[str]:
    """Insert demo missions with tasks and logs."""
    demo_id = user_ids["demo_user"]
    mission_ids: list[str] = []

    for i, tmpl in enumerate(MISSION_TEMPLATES):
        mission_id = str(uuid4())
        created_at = ago(60 * 24 - i * 120)  # stagger by 2 hours

        mission_data = {
            "id": mission_id,
            "user_id": demo_id,
            "title": tmpl["title"],
            "description": tmpl["description"],
            "mission_type": tmpl["mission_type"],
            "status": tmpl["status"],
            "priority": tmpl["priority"],
            "plan": tmpl["plan"],
            "results": tmpl["results"],
            "tokens_used": tmpl["tokens_used"],
            "actual_cost": tmpl["actual_cost"],
            "feedback_score": tmpl["feedback_score"],
            "created_at": created_at,
            "updated_at": created_at,
        }

        if tmpl["status"] == "completed":
            mission_data["started_at"] = created_at + timedelta(seconds=5)
            mission_data["completed_at"] = created_at + timedelta(minutes=2)
        elif tmpl["status"] == "in_progress":
            mission_data["started_at"] = created_at + timedelta(seconds=5)

        stmt = (
            pg_insert(Mission)
            .values(**mission_data)
            .on_conflict_do_update(
                index_elements=[Mission.id],
                set_={
                    "title": tmpl["title"],
                    "status": tmpl["status"],
                    "results": tmpl["results"],
                    "tokens_used": tmpl["tokens_used"],
                },
            )
        )
        await session.execute(stmt)

        # Add sample tasks for completed missions
        if tmpl["status"] == "completed" and tmpl.get("plan", {}).get("steps"):
            for j, step in enumerate(tmpl["plan"]["steps"]):
                task_id = str(uuid4())
                task_data = {
                    "id": task_id,
                    "mission_id": mission_id,
                    "title": step,
                    "description": f"Step {j + 1}: {step}",
                    "task_type": "llm_generation",
                    "order_index": j,
                    "status": "completed",
                    "started_at": created_at + timedelta(seconds=5 + j * 10),
                    "completed_at": created_at + timedelta(seconds=15 + j * 10),
                    "tokens_used": (tmpl["tokens_used"] or 0) // max(len(tmpl["plan"]["steps"]), 1),
                }
                task_stmt = pg_insert(MissionTask).values(**task_data).on_conflict_do_nothing()
                await session.execute(task_stmt)

        # Add a mission log
        log_data = {
            "id": str(uuid4()),
            "mission_id": mission_id,
            "level": "info",
            "message": f"Mission '{tmpl['title']}' created with status: {tmpl['status']}",
            "data": {"source": "seed_demo_data"},
            "timestamp": created_at,
        }
        log_stmt = pg_insert(MissionLog).values(**log_data).on_conflict_do_nothing()
        await session.execute(log_stmt)

        mission_ids.append(mission_id)

    await session.flush()
    return mission_ids


async def seed_agents(session, user_ids: dict[str, int]) -> list[str]:
    """Insert demo agents."""
    demo_id = str(user_ids["demo_user"])
    agent_ids: list[str] = []

    for tmpl in DEMO_AGENTS:
        agent_id = str(uuid4())
        stmt = (
            pg_insert(Agent)
            .values(
                id=agent_id,
                name=tmpl["name"],
                owner_id=demo_id,
                description=tmpl["description"],
                system_prompt=tmpl["system_prompt"],
                model_preference=tmpl["model_preference"],
            )
            .on_conflict_do_update(
                index_elements=[Agent.id],
                set_={
                    "name": tmpl["name"],
                    "description": tmpl["description"],
                    "system_prompt": tmpl["system_prompt"],
                },
            )
        )
        await session.execute(stmt)
        agent_ids.append(agent_id)

    await session.flush()
    return agent_ids


async def seed_chats(session, user_ids: dict[str, int]) -> None:
    """Insert demo chat threads with messages."""
    demo_id = user_ids["demo_user"]

    for conv in CHAT_CONVERSATIONS:
        # Check if thread with this title already exists
        existing = await session.execute(
            select(ChatThread.id).where(
                ChatThread.user_id == demo_id,
                ChatThread.title == conv["title"],
            )
        )
        existing_id = existing.scalar_one_or_none()

        if existing_id:
            thread_id = existing_id
        else:
            thread = ChatThread(
                user_id=demo_id,
                username="demo_user",
                title=conv["title"],
                message_count=len(conv["messages"]),
            )
            session.add(thread)
            await session.flush()
            thread_id = thread.id

        # Insert messages (skip if thread already has messages)
        msg_count = await session.execute(select(ChatMessage.id).where(ChatMessage.thread_id == thread_id).limit(1))
        if msg_count.scalar_one_or_none() is not None:
            continue

        for j, msg in enumerate(conv["messages"]):
            message = ChatMessage(
                thread_id=thread_id,
                user_id=demo_id,
                role=msg["role"],
                content=msg["content"],
                created_at=ago(30 * 24 - j * 5),
            )
            session.add(message)

    await session.flush()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    # Gate: only run if ENABLE_DEMO_MODE is set
    if os.environ.get("ENABLE_DEMO_MODE", "").lower() not in ("true", "1", "yes"):
        print("SKIP: ENABLE_DEMO_MODE is not set to true. No demo data created.")
        print("Set ENABLE_DEMO_MODE=true in your .env to enable demo seeding.")
        return

    print("=" * 60)
    print("Flowmanner Demo Data Seeder")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        try:
            print("\n[1/5] Seeding users...")
            user_ids = await seed_users(session)
            print(f"      Created/updated {len(user_ids)} users: {list(user_ids.keys())}")

            print("\n[2/5] Seeding workspace...")
            ws_id = await seed_workspace(session, user_ids)
            print(f"      Workspace: {ws_id}")

            print("\n[3/5] Seeding missions...")
            mission_ids = await seed_missions(session, user_ids)
            print(f"      Created/updated {len(mission_ids)} missions")

            print("\n[4/5] Seeding agents...")
            agent_ids = await seed_agents(session, user_ids)
            print(f"      Created/updated {len(agent_ids)} agents")

            print("\n[5/5] Seeding chat conversations...")
            await seed_chats(session, user_ids)
            print(f"      Created/updated {len(CHAT_CONVERSATIONS)} conversations")

            await session.commit()

            print("\n" + "=" * 60)
            print("Demo data seeded successfully!")
            print("=" * 60)
            print(f"\nDemo credentials:")
            print(f"  Email:    demo@flowmanner.com")
            print(f"  Password: demo1234")
            print(f"\nAdmin credentials:")
            print(f"  Email:    admin@flowmanner.com")
            print(f"  Password: demo1234")

        except Exception as e:
            await session.rollback()
            print(f"\nERROR: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
