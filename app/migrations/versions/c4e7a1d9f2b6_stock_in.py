"""a stock inflow by hand, the opposite of a write-off

create date: 2026-11-01 12:00:00+03:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4e7a1d9f2b6"
down_revision: str | Sequence[str] | None = "ec86aad8688e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = (
    "'invoice', 'sale', 'write_off', 'stocktake', 'revaluation', "
    "'cash_in', 'cash_out', 'cash_count'"
)
OLD_NO_CASH = "'invoice', 'write_off', 'stocktake', 'revaluation'"


def replace_checks(
    kinds: str,
    no_cash: str,
) -> None:
    """short names, the naming convention in db.py adds the table and the suffix"""
    for name, condition in (
        ("ledger_kind", f"kind IN ({kinds})"),
        ("no_cash", f"kind NOT IN ({no_cash}) OR cash = 0"),
    ):
        op.drop_constraint(
            constraint_name=name,
            table_name="ledger_entries",
            type_="check",
        )
        op.create_check_constraint(
            constraint_name=name,
            table_name="ledger_entries",
            condition=condition,
        )


def upgrade() -> None:
    replace_checks(
        kinds=f"{OLD_KINDS}, 'stock_in'",
        no_cash=f"{OLD_NO_CASH}, 'stock_in'",
    )
    op.create_check_constraint(
        constraint_name="stock_in_sign",
        table_name="ledger_entries",
        condition=(
            "kind <> 'stock_in' "
            "OR (reverses_id IS NULL AND amount > 0) "
            "OR (reverses_id IS NOT NULL AND amount < 0)"
        ),
    )


def downgrade() -> None:
    # reversals go first, they point to the entries they cancel
    op.execute(
        sqltext="DELETE FROM ledger_entries WHERE kind = 'stock_in' AND reverses_id IS NOT NULL",
    )
    op.execute(
        sqltext="DELETE FROM ledger_entries WHERE kind = 'stock_in'",
    )
    op.drop_constraint(
        constraint_name="stock_in_sign",
        table_name="ledger_entries",
        type_="check",
    )
    replace_checks(
        kinds=OLD_KINDS,
        no_cash=OLD_NO_CASH,
    )
