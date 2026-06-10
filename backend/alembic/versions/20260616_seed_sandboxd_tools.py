"""Seed sandboxd tools into tools_catalog.

Inserts the 5 sandboxd agent tools so they survive fresh DB deploys.
Idempotent: uses ON CONFLICT (slug) DO NOTHING.

Revision ID: seed_sandboxd_tools
Revises: mission_sandboxes_001
Create Date: 2026-06-16
"""

import json
from uuid import uuid4

from sqlalchemy import text as sa_text

from alembic import op

# revision identifiers, used by Alembic.
revision = "seed_sandboxd_tools"
down_revision = "mission_sandboxes_001"
branch_labels = None
depends_on = None

SANDBOXD_TOOLS = [
    {
        "slug": "sandboxd_exec",
        "name": "Sandboxd Exec",
        "description": "Execute Python, Node, Bash, or Go code in an isolated Docker container via sandboxd.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.sandboxd_exec.SandboxdExecTool",
        "tags": ["sandbox", "code", "execution", "docker"],
        "timeout_seconds": 90,
    },
    {
        "slug": "sandboxd_file_read",
        "name": "Sandboxd File Read",
        "description": "Read a file from the sandbox workspace.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.sandboxd_file_read.SandboxdFileReadTool",
        "tags": ["sandbox", "file", "read"],
        "timeout_seconds": 30,
    },
    {
        "slug": "sandboxd_file_write",
        "name": "Sandboxd File Write",
        "description": "Write a file to the sandbox workspace.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.sandboxd_file_write.SandboxdFileWriteTool",
        "tags": ["sandbox", "file", "write"],
        "timeout_seconds": 30,
    },
    {
        "slug": "sandboxd_file_list",
        "name": "Sandboxd File List",
        "description": "List files in the sandbox workspace.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.sandboxd_file_list.SandboxdFileListTool",
        "tags": ["sandbox", "file", "list"],
        "timeout_seconds": 30,
    },
    {
        "slug": "sandboxd_preview",
        "name": "Sandboxd Preview",
        "description": "Get the live preview URL for a sandbox.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.sandboxd_preview.SandboxdPreviewTool",
        "tags": ["sandbox", "preview", "url"],
        "timeout_seconds": 30,
    },
    {
        "slug": "sandboxd_serve",
        "name": "Sandboxd Serve",
        "description": "Start a dev server inside the sandbox and return the preview URL.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.sandboxd_serve.SandboxdServeTool",
        "tags": ["sandbox", "serve", "preview", "server"],
        "timeout_seconds": 45,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for tool in SANDBOXD_TOOLS:
        tool_id = str(uuid4())
        conn.execute(
            sa_text(
                """
                INSERT INTO tools_catalog (
                    id, slug, name, description, category, tool_type,
                    handler_ref, tags, source, version,
                    enabled, visibility, requires_auth, timeout_seconds, tier,
                    created_at, updated_at
                ) VALUES (
                    :id, :slug, :name, :description, :category, 'builtin',
                    :handler_ref, CAST(:tags AS jsonb), 'alembic_seed', 1,
                    true, 'public', true, :timeout_seconds, 1,
                    now(), now()
                )
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {
                "id": tool_id,
                "slug": tool["slug"],
                "name": tool["name"],
                "description": tool["description"],
                "category": tool["category"],
                "handler_ref": tool["handler_ref"],
                "tags": json.dumps(tool["tags"]),
                "timeout_seconds": tool["timeout_seconds"],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    slugs = [t["slug"] for t in SANDBOXD_TOOLS]
    conn.execute(
        sa_text("DELETE FROM tools_catalog WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
