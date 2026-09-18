"""ledger entries get a date instead of a moment and can be reversed

create date: 2026-09-18 14:45:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a1c9d27b58"
down_revision: str | Sequence[str] | None = "d2b85f0c7a14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        index_name="ledger_entries_occurred_at_idx",
        table_name="ledger_entries",
    )
    # the default goes first, the old one can not be cast along with the column
    op.alter_column(
        table_name="ledger_entries",
        column_name="occurred_at",
        server_default=None,
    )
    op.alter_column(
        table_name="ledger_entries",
        column_name="occurred_at",
        type_=sa.Date(),
        # the day of the shop, the server keeps time in utc
        postgresql_using="(occurred_at AT TIME ZONE 'Europe/Moscow')::date",
    )
    op.alter_column(
        table_name="ledger_entries",
        column_name="occurred_at",
        new_column_name="occurred_on",
        server_default=sa.text(
            text="CURRENT_DATE",
        ),
    )
    op.create_index(
        index_name="ledger_entries_occurred_on_idx",
        table_name="ledger_entries",
        columns=[
            "occurred_on",
        ],
    )
    op.add_column(
        table_name="ledger_entries",
        column=sa.Column(
            "reverses_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        constraint_name="ledger_entries_reverses_id_fkey",
        source_table="ledger_entries",
        referent_table="ledger_entries",
        local_cols=[
            "reverses_id",
        ],
        remote_cols=[
            "id",
        ],
    )
    op.create_unique_constraint(
        constraint_name="ledger_entries_reverses_id_key",
        table_name="ledger_entries",
        columns=[
            "reverses_id",
        ],
    )
    # short names, the naming convention in db.py adds the table and the suffix
    op.create_check_constraint(
        constraint_name="invoice_amount",
        table_name="ledger_entries",
        condition="kind <> 'invoice' OR (amount >= 0 AND reverses_id IS NULL)",
    )
    op.create_check_constraint(
        constraint_name="outflow_sign",
        table_name="ledger_entries",
        condition=(
            "kind NOT IN ('sale', 'write_off') "
            "OR (reverses_id IS NULL AND amount < 0) "
            "OR (reverses_id IS NOT NULL AND amount > 0)"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        constraint_name="outflow_sign",
        table_name="ledger_entries",
        type_="check",
    )
    op.drop_constraint(
        constraint_name="invoice_amount",
        table_name="ledger_entries",
        type_="check",
    )
    op.drop_column(
        table_name="ledger_entries",
        column_name="reverses_id",
    )
    op.drop_index(
        index_name="ledger_entries_occurred_on_idx",
        table_name="ledger_entries",
    )
    op.alter_column(
        table_name="ledger_entries",
        column_name="occurred_on",
        server_default=None,
    )
    op.alter_column(
        table_name="ledger_entries",
        column_name="occurred_on",
        type_=sa.DateTime(
            timezone=True,
        ),
        postgresql_using="occurred_on::timestamp AT TIME ZONE 'Europe/Moscow'",
    )
    op.alter_column(
        table_name="ledger_entries",
        column_name="occurred_on",
        new_column_name="occurred_at",
        server_default=sa.text(
            text="now()",
        ),
    )
    op.create_index(
        index_name="ledger_entries_occurred_at_idx",
        table_name="ledger_entries",
        columns=[
            "occurred_at",
        ],
    )
