"""operating expenses of the shop with the rates of the owner

create date: 2026-11-01 20:00:00+03:00
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "d7b2e4f1a9c3"
down_revision: str | Sequence[str] | None = "c4e7a1d9f2b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# the receipts go back to this month
FIRST_MONTH = date(
    year=2026,
    month=4,
    day=1,
)
EXPENSES = (
    ("Аренда", "month", "100000"),
    ("Свет", "month", "50000"),
    ("Патент", "year", "150000"),
    ("Зарплата за смену", "work_day", "3500"),
    ("Зарплата, процент от продаж", "revenue_percent", "2"),
    ("Эквайринг и комиссии банка", "card_percent", "3"),
)


def upgrade() -> None:
    table = op.create_table(
        "operating_expenses",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "basis",
            sa.Enum(
                "month",
                "year",
                "work_day",
                "revenue_percent",
                "card_percent",
                name="expense_basis",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name=op.f("operating_expenses_amount_check")),
        sa.CheckConstraint(
            "extract(day from starts_on) = 1",
            name=op.f("operating_expenses_starts_on_check"),
        ),
        sa.CheckConstraint(
            "extract(day from ends_on) = 1",
            name=op.f("operating_expenses_ends_on_check"),
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on > starts_on",
            name=op.f("operating_expenses_period_check"),
        ),
        sa.CheckConstraint(
            "basis NOT IN ('revenue_percent', 'card_percent') OR amount <= 100",
            name=op.f("operating_expenses_percent_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("operating_expenses_pkey")),
    )
    op.bulk_insert(
        table=table,
        rows=[
            {
                "name": name,
                "basis": basis,
                "amount": Decimal(
                    value=amount,
                ),
                "starts_on": FIRST_MONTH,
            }
            for name, basis, amount in EXPENSES
        ],
    )


def downgrade() -> None:
    op.drop_table("operating_expenses")
