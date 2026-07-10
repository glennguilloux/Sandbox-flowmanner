# mypy: disable-error-code=attr-defined
"""Q3 — create the dedicated `skills` table (C3 correction).

Skills are NOT stored in ``memory_entries`` (which has no governance
columns) nor in ``personal_memory_claims`` (subject-predicate-object
claims). They are a distinct, structured registry of reusable procedural
knowledge distilled by the background reviewer.

NOTE on location: this migration lives in the ACTIVE alembic tree
(``backend/alembic/versions/``, resolved by ``alembic.ini``
``script_location = %(here)s/alembic``). An earlier draft mistakenly
targeted ``backend/app/migrations/versions/`` which alembic never reads,
so it would never have been applied. This file chains from the real head
``20260710_e42_source_priority``.

Revision ID: 20260710_q3_skills
Revises:     20260710_e42_source_priority
Create Date: 2026-07-10 13:00:00

Forward + reversible: ``downgrade()`` drops the table entirely.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260710_q3_skills"
down_revision = "20260710_e42_source_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("frontmatter", postgresql.JSONB, nullable=True),
        sa.Column("trust_tier", sa.String(50), nullable=False, server_default="unverified"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("provenance", sa.String(50), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_skills_workspace_id", "skills", ["workspace_id"])
    op.create_index("ix_skills_user_id", "skills", ["user_id"])
    op.create_index("ix_skills_agent_id", "skills", ["agent_id"])
    # A skill name is unique WITHIN a workspace (class-level names).
    op.create_index(
        "ix_skills_workspace_name",
        "skills",
        ["workspace_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_skills_workspace_name", table_name="skills")
    op.drop_index("ix_skills_agent_id", table_name="skills")
    op.drop_index("ix_skills_user_id", table_name="skills")
    op.drop_index("ix_skills_workspace_id", table_name="skills")
    op.drop_table("skills")
