# mypy: disable-error-code=attr-defined
"""Add metadata (JSONB) column to personal_memory_claims.

Revision ID: 20260711_governance_poison_scan
Revises: 20260711_hitl_depth_decision
Create Date: 2026-07-11 18:30:00

t_9bb4df81: the retroactive poison-sweep must persist the FULL
severity/provenance verdict into ``personal_memory_claims.meta``. The model
previously had no ``meta`` column, so ``claim.meta = ...`` writes were a silent
no-op. This adds the (nullable) JSONB column the service now populates.
"""

from alembic import op
from alembic import context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260711_governance_poison_scan"
down_revision = "20260711_hitl_depth_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the live DB may already carry the ``metadata`` column
    # (added out-of-band during development) while alembic_version is still
    # stamped at this migration's down_revision. Only add it if missing so a
    # plain ``alembic upgrade head`` never crashes on a duplicate column.
    # NOTE: the existence check needs a live connection, which is absent in
    # offline mode (``alembic upgrade head --sql``). Skip the check there —
    # a render only needs the DDL, and idempotency is irrelevant to it.
    if not context.is_offline_mode():
        with op.get_context().autocommit_block():
            conn = op.get_bind()
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='personal_memory_claims' AND column_name='metadata'"
                )
            ).scalar()
        if exists:
            return
    op.add_column(
        "personal_memory_claims",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_personal_memory_claims_metadata",
        "personal_memory_claims",
        ["metadata"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    if not context.is_offline_mode():
        with op.get_context().autocommit_block():
            conn = op.get_bind()
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='personal_memory_claims' AND column_name='metadata'"
                )
            ).scalar()
        if not exists:
            return
    op.drop_index(
        "ix_personal_memory_claims_metadata",
        table_name="personal_memory_claims",
        postgresql_using="gin",
    )
    op.drop_column("personal_memory_claims", "metadata")
