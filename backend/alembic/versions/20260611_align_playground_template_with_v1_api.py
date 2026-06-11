"""Align playground_sandboxes.template with sandboxd v1 API naming.

The sandboxd v1 API (POST /v1/sandboxes) enforces a `^[a-z0-9-]+$` regex
on template names. The default SANDBOXD_DEFAULT_TEMPLATE was originally
flipped to `python.img` in commit 4f88743, and migration
20260611_backfill_playground_template_python_img backfilled existing
rows to `python.img`. The dot in the name is not in the v1 allowed
charset, so every v1 sandbox-create call 400s and falls back to the
internal /sandbox endpoint (which does accept dots).

This migration flips both the code default and the existing rows from
`python.img` to `python-img` (hyphen, v1-compliant) so the v1 path
stops 400ing and the data is consistent.

Revision ID: align_playground_template_with_v1_api_001
Revises: backfill_playground_template_001
Create Date: 2026-06-11
"""

from sqlalchemy import text as sa_text

from alembic import op

# revision identifiers, used by Alembic.
revision = "align_playground_template_with_v1_api_001"
down_revision = "backfill_playground_template_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename template values from 'python.img' to 'python-img'."""
    conn = op.get_bind()
    result = conn.execute(
        sa_text(
            "UPDATE playground_sandboxes "
            "SET template = 'python-img' "
            "WHERE template = 'python.img'"
        )
    )
    print(
        f"[align_playground_template_with_v1_api_001] "
        f"Updated {result.rowcount} rows from 'python.img' to 'python-img'"
    )


def downgrade() -> None:
    """Revert rows from 'python-img' back to 'python.img'.

    Lossy: any rows that were created with 'python-img' after this
    migration (rather than backfilled from 'python.img') will also be
    reverted, which is incorrect. Operators wanting a true revert
    should restore from a pre-migration database backup.
    """
    conn = op.get_bind()
    result = conn.execute(
        sa_text(
            "UPDATE playground_sandboxes "
            "SET template = 'python.img' "
            "WHERE template = 'python-img'"
        )
    )
    print(
        f"[align_playground_template_with_v1_api_001] downgrade: "
        f"Reverted {result.rowcount} rows from 'python-img' to 'python.img'"
    )
