"""payments to the supplier for confirmed invoices, an invoice may be paid in parts

create date: 2026-10-17 18:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e3b7a1d5f2"
down_revision: str | Sequence[str] | None = "b6d1f4a8c3e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoice_payments",
        sa.Column(
            "id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "paid_on",
            sa.Date(),
            server_default=sa.func.current_date(),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            sa.CheckConstraint(
                sqltext="amount > 0",
                name="amount",
            ),
            nullable=False,
        ),
        sa.Column(
            "comment",
            sa.String(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True,
            ),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            columns=[
                "invoice_id",
            ],
            refcolumns=[
                "invoices.id",
            ],
        ),
        sa.PrimaryKeyConstraint(
            "id",
        ),
    )
    op.create_index(
        index_name="invoice_payments_invoice_id_idx",
        table_name="invoice_payments",
        columns=[
            "invoice_id",
        ],
    )


def downgrade() -> None:
    op.drop_table(
        table_name="invoice_payments",
    )
