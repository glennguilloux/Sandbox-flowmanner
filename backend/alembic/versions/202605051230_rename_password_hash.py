"""rename password_hash to hashed_password

Revision ID: 202605051230
Revises: 
Create Date: 2026-05-05 12:30:00.000000

"""

from alembic import op

revision = "202605051230"
down_revision = None


def upgrade() -> None:
    # Rename password_hash column to hashed_password if it exists
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='users' AND column_name='password_hash') THEN
                ALTER TABLE users RENAME COLUMN password_hash TO hashed_password;
            END IF;
        END
        $$;
    """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='users' AND column_name='hashed_password') THEN
                ALTER TABLE users RENAME COLUMN hashed_password TO password_hash;
            END IF;
        END
        $$;
    """
    )
