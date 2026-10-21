"""the ledger keeps the cash in the till next to the stock

create date: 2026-10-17 15:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d1f4a8c3e2"
down_revision: str | Sequence[str] | None = "e5c2a8d4b7f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'invoice', 'sale', 'write_off', 'stocktake', 'revaluation'"
CASH_KINDS = "'cash_in', 'cash_out', 'cash_count'"

# short names, the naming convention in db.py adds the table and the suffix
CHECKS = {
    "cash_only": f"kind NOT IN ({CASH_KINDS}) OR amount = 0",
    "no_cash": (
        "kind NOT IN ('invoice', 'write_off', 'stocktake', 'revaluation') OR cash = 0"
    ),
    "sale_cash": "kind <> 'sale' OR (cash * amount <= 0 AND abs(cash) <= abs(amount))",
    "cash_in_sign": (
        "kind <> 'cash_in' "
        "OR (reverses_id IS NULL AND cash > 0) "
        "OR (reverses_id IS NOT NULL AND cash < 0)"
    ),
    "cash_out_sign": (
        "kind <> 'cash_out' "
        "OR (reverses_id IS NULL AND cash < 0) "
        "OR (reverses_id IS NOT NULL AND cash > 0)"
    ),
}


def upgrade() -> None:
    # the split of the earlier sales is unknown, they count as cashless,
    # the first cash count sets the real balance of the till
    op.add_column(
        table_name="ledger_entries",
        column=sa.Column(
            "cash",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=False,
            server_default="0",
        ),
    )
    op.drop_constraint(
        constraint_name="ledger_kind",
        table_name="ledger_entries",
        type_="check",
    )
    op.create_check_constraint(
        constraint_name="ledger_kind",
        table_name="ledger_entries",
        condition=f"kind IN ({KINDS}, {CASH_KINDS})",
    )
    for name, condition in CHECKS.items():
        op.create_check_constraint(
            constraint_name=name,
            table_name="ledger_entries",
            condition=condition,
        )


def downgrade() -> None:
    # reversals go first, they point to the entries they cancel
    op.execute(
        sqltext=(
            f"DELETE FROM ledger_entries WHERE kind IN ({CASH_KINDS}) AND reverses_id IS NOT NULL"
        ),
    )
    op.execute(
        sqltext=f"DELETE FROM ledger_entries WHERE kind IN ({CASH_KINDS})",
    )
    for name in CHECKS:
        op.drop_constraint(
            constraint_name=name,
            table_name="ledger_entries",
            type_="check",
        )
    op.drop_constraint(
        constraint_name="ledger_kind",
        table_name="ledger_entries",
        type_="check",
    )
    op.create_check_constraint(
        constraint_name="ledger_kind",
        table_name="ledger_entries",
        condition=f"kind IN ({KINDS})",
    )
    op.drop_column(
        table_name="ledger_entries",
        column_name="cash",
    )
