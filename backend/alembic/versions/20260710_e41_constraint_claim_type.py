"""Epic 4.1a — add 'constraint' to PersonalMemoryClaim.claim_type

Extends the ``ck_personal_memory_claim_claim_type_valid`` CHECK constraint
to admit the new ``constraint`` claim type (negative / standing prohibitions
such as "never run rm -rf on prod"). This is the durable home for the
over-hardening guardrails enforced at tool dispatch (Epic 4.1b) and
surfaced to the reviewer as a don't-capture list (Epic 4.2).

CHECK constraints cannot be ALTERed in-place, so we drop the existing
constraint and recreate it with the widened value set. The model tuple
``ALL_CLAIM_TYPES`` in ``app/models/personal_memory_models.py`` and the
``ClaimType`` enum in ``app/schemas/personal_memory.py`` ship in the same
commit (AGENTS.md ritual rule 6: migration + model change together).

Revision ID: 20260710_e41_constraint_claim_type
Revises: 20260709_e33_memory_entry_deleted_at
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260710_e41_constraint_claim_type"
down_revision: str | Sequence[str] | None = "20260709_e33_memory_entry_deleted_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALL_CLAIM_TYPES: tuple[str, ...] = (
    "fact",
    "preference",
    "observation",
    "sensitive",
    "constraint",
)


def upgrade() -> None:
    # Recreate the claim_type CHECK constraint with the widened value set.
    op.drop_constraint(
        "ck_personal_memory_claim_claim_type_valid",
        table_name="personal_memory_claims",
        type_="check",
    )
    op.create_check_constraint(
        "ck_personal_memory_claim_claim_type_valid",
        "personal_memory_claims",
        sa.text(f"claim_type IN {_ALL_CLAIM_TYPES}"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_personal_memory_claim_claim_type_valid",
        table_name="personal_memory_claims",
        type_="check",
    )
    op.create_check_constraint(
        "ck_personal_memory_claim_claim_type_valid",
        "personal_memory_claims",
        sa.text("claim_type IN ('fact', 'preference', 'observation', 'sensitive')"),
    )
