"""a sale can be loaded from a shift of the aQsi cash register

create date: 2026-10-31 12:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f6c8e1d470"
down_revision: str | Sequence[str] | None = "f8c1d3a6e2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        table_name="ledger_entries",
        column=sa.Column(
            "aqsi_shift_id",
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        constraint_name="ledger_entries_aqsi_shift_id_key",
        table_name="ledger_entries",
        columns=[
            "aqsi_shift_id",
        ],
    )
    # a short name, the naming convention in db.py adds the table and the suffix
    op.create_check_constraint(
        constraint_name="aqsi_shift_sale",
        table_name="ledger_entries",
        condition="kind = 'sale' OR aqsi_shift_id IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        constraint_name="aqsi_shift_sale",
        table_name="ledger_entries",
        type_="check",
    )
    op.drop_constraint(
        constraint_name="ledger_entries_aqsi_shift_id_key",
        table_name="ledger_entries",
        type_="unique",
    )
    op.drop_column(
        table_name="ledger_entries",
        column_name="aqsi_shift_id",
    )
