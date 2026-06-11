"""Phase 4: playground sandboxes table

Revision ID: phase4_playground
Revises: seed_sandbox_dag_blueprint
Create Date: 2026-06-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "phase4_playground"
down_revision = "seed_sandbox_dag_blueprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playground_sandboxes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sandbox_id", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_token", sa.String(128), nullable=False, unique=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="creating"),
        sa.Column("template", sa.String(64), nullable=False, server_default="react-standard"),
        sa.Column("project_id", sa.String(128), nullable=True),
        sa.Column("is_persistent", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anonymous_ip", sa.String(45), nullable=True),
    )
    op.create_index("ix_playground_sandboxes_sandbox_id", "playground_sandboxes", ["sandbox_id"])
    op.create_index("ix_playground_sandboxes_session_token", "playground_sandboxes", ["session_token"])
    op.create_index("ix_playground_sandboxes_user_id", "playground_sandboxes", ["user_id"])
    op.create_index("ix_playground_sandboxes_workspace_id", "playground_sandboxes", ["workspace_id"])
    op.create_index("ix_playground_sandboxes_anonymous_ip", "playground_sandboxes", ["anonymous_ip"])
    op.create_index("ix_playground_status_expires", "playground_sandboxes", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_table("playground_sandboxes")
