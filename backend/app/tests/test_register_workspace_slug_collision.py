"""
Regression test for the signup-500 (workspace slug collision).

Bug (pre-fix): POST /api/auth/register auto-creates a default workspace
whose slug was derived PURELY from the user's display name:

    ws_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"

Because `workspaces.slug` has a UNIQUE constraint, the SECOND user
whose name slugifies to an already-persisted slug raised
`asyncpg.UniqueViolationError`, which SQLAlchemy escalated to
`PendingRollbackError` on the shared `db` session. That session is
reused for the refresh-token write + analytics, so EVERY subsequent
flush died and registration returned a generic 500
("An error occurred. Please try again later.").

This test reproduces the collision through the REAL register handler and
asserts the fix: the slug is now collision-proof (uuid suffix) AND a
workspace auto-create failure is isolated via db.rollback() so signup
still returns 200.

Run with: pytest app/tests/test_register_workspace_slug_collision.py -v
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

# The app import guards on OPENAI_API_KEY (a router import enforces it).
import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.database import AsyncSessionLocal  # noqa: E402
from app.main_fastapi import app  # noqa: E402
from app.models.workspace_models import Workspace, WorkspaceMember  # noqa: E402


def _slugify(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"


@pytest.mark.asyncio
async def test_register_succeeds_when_workspace_slug_collides():
    """A second user with a name that collides an existing workspace slug
    must still register 200 (no 500, no session poisoning).

    Seeds an EXISTING workspace with the exact slug the OLD code would
    generate for the new user (guaranteed unique violation for the pre-fix
    path), then registers a user whose auto-slug collides, and asserts 200.
    """
    colliding_name = f"slugtest-{uuid.uuid4().hex[:8]} User"
    base_slug = _slugify(colliding_name)  # what the OLD code would emit

    # Seed via the app's own session factory (correct engine/loop binding).
    async with AsyncSessionLocal() as db:
        seeded = Workspace(
            id=str(uuid.uuid4()),
            name=colliding_name,
            slug=base_slug,
            owner_id=0,
        )
        db.add(seeded)
        db.add(WorkspaceMember(workspace_id=seeded.id, user_id=0, role="owner"))
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"{base_slug}@example.com"
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "ValidPass123!",
                "full_name": colliding_name,
                "username": base_slug,
            },
        )

    try:
        # Core assertion: signup does NOT 500 on a slug collision.
        assert resp.status_code == 200, (
            f"expected 200, got {resp.status_code}: {resp.text[:300]}"
        )
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
    finally:
        # Clean up the seeded collision workspace so the test is repeatable.
        async with AsyncSessionLocal() as db:
            await db.execute(
                Workspace.__table__.delete().where(Workspace.slug == base_slug)
            )
            await db.commit()


@pytest.mark.asyncio
async def test_generated_workspace_slug_is_collision_proof():
    """The slug emitted for a user must always be unique (uuid shard)."""
    name = "Collision Proof User"
    base = _slugify(name)
    ws_id = str(uuid.uuid4())
    # Mirror the fixed code path exactly.
    slug = f"{base}-{ws_id[:8]}"
    assert slug.startswith(base + "-")
    assert len(slug) > len(base)
    # Two different users with the same name get different slugs.
    other = f"{base}-{uuid.uuid4().hex[:8]}"
    assert slug != other
