"""allow retail prices in kopecks

Revision ID: a765726bb3b0
Revises: 896f50caf3f4
Create Date: 2026-11-26 21:44:58.870243

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a765726bb3b0"
down_revision: str | Sequence[str] | None = "896f50caf3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRICE_COLUMNS = (
    ("products", "retail_price"),
    ("invoice_items", "retail_price"),
    ("revaluation_items", "old_price"),
    ("revaluation_items", "new_price"),
)


def replace_price_checks(*, whole_rubles: bool) -> None:
    for table, column in PRICE_COLUMNS:
        condition = f"{column} >= 0"
        if whole_rubles:
            condition += f" AND {column} = trunc({column})"
        op.drop_constraint(
            constraint_name=column,
            table_name=table,
            type_="check",
        )
        op.create_check_constraint(
            constraint_name=column,
            table_name=table,
            condition=condition,
        )


def upgrade() -> None:
    replace_price_checks(
        whole_rubles=False,
    )


def downgrade() -> None:
    # existing fractional prices make the transaction fail without changing any amounts
    replace_price_checks(
        whole_rubles=True,
    )
