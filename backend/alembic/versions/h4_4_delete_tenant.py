"""H4 Phase 4 — Delete Tenant model, rename workspace_id columns, drop tenant FK.

Revision: h4_4_delete_tenant
Down revision: h4_1_workspace_billing

Operations:
1. Drop tenant_invitations table
2. Drop tenant_members table
3. Drop users.tenant_id FK constraint + column
4. Rename custom_roles.tenant_id → custom_roles.workspace_id
5. Rename role_delegations.tenant_id → role_delegations.workspace_id
6. Rename user_tenants.tenant_id → user_tenants.workspace_id
7. Rename user_custom_roles.tenant_id → user_custom_roles.workspace_id
8. Drop tenants table
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h4_4_delete_tenant"
down_revision: Union[str, None] = "h4_1_workspace_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop dependent tables first (they reference tenants.id)
    op.drop_table("tenant_invitations")
    op.drop_table("tenant_members")

    # 2. Drop users.tenant_id FK and column
    # Drop FK by column name (Alembic can resolve this for most dialects)
    with op.batch_alter_table("users") as batch_op:
        try:
            batch_op.drop_constraint("users_ibfk_tenant", type_="foreignkey")
        except Exception:
            pass
    op.drop_column("users", "tenant_id")

    # 3. Rename columns: tenant_id → workspace_id
    op.alter_column("custom_roles", "tenant_id", new_column_name="workspace_id")
    op.alter_column("role_delegations", "tenant_id", new_column_name="workspace_id")
    op.alter_column("user_tenants", "tenant_id", new_column_name="workspace_id")
    op.alter_column("user_custom_roles", "tenant_id", new_column_name="workspace_id")

    # 4. Drop the tenants table itself
    op.drop_table("tenants")


def downgrade() -> None:
    # Reverse: re-create tenants, rename columns back, restore users.tenant_id
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("subscription_tier_id", sa.Integer(), nullable=True),
        sa.Column("max_members", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "max_missions_per_day", sa.Integer(), nullable=False, server_default="100"
        ),
        sa.Column("billing_customer_id", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # Rename columns back: workspace_id → tenant_id
    op.alter_column("custom_roles", "workspace_id", new_column_name="tenant_id")
    op.alter_column("role_delegations", "workspace_id", new_column_name="tenant_id")
    op.alter_column("user_tenants", "workspace_id", new_column_name="tenant_id")
    op.alter_column("user_custom_roles", "workspace_id", new_column_name="tenant_id")

    # Restore users.tenant_id
    op.add_column("users", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "users_ibfk_tenant", "users", "tenants", ["tenant_id"], ["id"]
    )

    # Re-create dependent tables
    op.create_table(
        "tenant_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column(
            "can_create_missions", sa.Boolean(), nullable=False, server_default="1"
        ),
        sa.Column(
            "can_manage_members", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("can_view_billing", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("invited_by", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
