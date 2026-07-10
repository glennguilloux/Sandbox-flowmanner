"""Epic 2.3 E23-A — add ``source_priority`` to PersonalMemoryClaim.

Stores a denormalized integer precedence (derived from ``source_type`` via
the ``SOURCE_PRIORITY`` map) on every claim so ``recall()`` can ORDER BY it at
the SQL layer. Q1/Q2/Q5 ranking all depend on SQL-level ordering, so this is a
stored column (not a read-time derivation).

Precedence (higher = stronger authority):
    user_explicit (4) > conversation (3) > mission (2) > program_learning (1)
Any source_type not in the map defaults to 0 (lowest), so the seed UPDATE is
total and never drops a row.

Migration + model change ship together (AGENTS.md ritual rule 6). The model
column default is ``source_priority_for(source_type)``; existing rows are
backfilled here. The column is NOT NULL with server_default 0 so the
constraint holds for any future write that omits the value.

Revision ID: 20260710_e42_source_priority
Revises: 20260710_e41_constraint_claim_type
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260710_e42_source_priority"
down_revision: Union[str, Sequence[str], None] = "20260710_e41_constraint_claim_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "personal_memory_claims"
_COLUMN = "source_priority"

# source_type -> priority, matching app/models/personal_memory_models.SOURCE_PRIORITY.
_SOURCE_PRIORITY_CASE = sa.text(
    "CASE source_type "
    "WHEN 'user_explicit' THEN 4 "
    "WHEN 'conversation' THEN 3 "
    "WHEN 'mission' THEN 2 "
    "WHEN 'program_learning' THEN 1 "
    "ELSE 0 END"
)


def upgrade() -> None:
    # 1. Add the column NOT NULL, default 0 (server side) so the constraint
    #    is immediately satisfiable for every existing row.
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # 2. Pre-flight is implicit: column is NOT NULL with a sentinel default,
    #    so there are no NULLs to clean up — no DELETE, no sentinel UPDATE of
    #    real data needed. Backfill priority from source_type for all rows.
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET {_COLUMN} = {_SOURCE_PRIORITY_CASE}"
        )
    )

    # 3. Drop the server default now that rows are populated — application
    #    writes set source_priority explicitly via source_priority_for().
    op.alter_column(
        _TABLE,
        _COLUMN,
        server_default=None,
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # 4. Index for the recall() ORDER BY source_priority (and direct lookups).
    op.create_index(
        f"ix_{_TABLE}_source_priority",
        _TABLE,
        [_COLUMN],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        f"ix_{_TABLE}_source_priority", table_name=_TABLE
    )
    op.drop_column(_TABLE, _COLUMN)
