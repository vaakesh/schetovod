"""add invoice drafts

create date: 2026-08-14 14:35:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8ca4f0d2e19"
down_revision: str | Sequence[str] | None = "24cd33985be4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        table_name="invoices",
        column_name="supplier_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        table_name="invoices",
        column_name="invoice_number",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        table_name="invoices",
        column_name="invoice_date",
        existing_type=sa.Date(),
        nullable=True,
    )
    op.alter_column(
        table_name="invoices",
        column_name="status",
        existing_type=sa.String(
            length=9,
        ),
        existing_nullable=False,
        server_default="draft",
    )
    for table_name, column_name in (
        ("invoices", "status"),
        ("ledger_entries", "invoice_status"),
    ):
        op.drop_constraint(
            constraint_name=op.f(
                name=f"{table_name}_invoice_status_check",
            ),
            table_name=table_name,
            type_="check",
        )
        op.create_check_constraint(
            constraint_name=op.f(
                name=f"{table_name}_invoice_status_check",
            ),
            table_name=table_name,
            condition=f"{column_name} IN ('draft', 'confirmed', 'declined')",
        )
    op.create_check_constraint(
        constraint_name=op.f(
            name="invoices_confirmed_fields_check",
        ),
        table_name="invoices",
        condition=(
            "status <> 'confirmed' OR "
            "(supplier_id IS NOT NULL AND invoice_number IS NOT NULL "
            "AND invoice_date IS NOT NULL)"
        ),
    )


def downgrade() -> None:
    op.alter_column(
        table_name="invoices",
        column_name="status",
        existing_type=sa.String(
            length=9,
        ),
        existing_nullable=False,
        server_default=None,
    )
    for table_name, column_name in (
        ("invoices", "status"),
        ("ledger_entries", "invoice_status"),
    ):
        op.drop_constraint(
            constraint_name=op.f(
                name=f"{table_name}_invoice_status_check",
            ),
            table_name=table_name,
            type_="check",
        )
        op.create_check_constraint(
            constraint_name=op.f(
                name=f"{table_name}_invoice_status_check",
            ),
            table_name=table_name,
            condition=f"{column_name} IN ('confirmed', 'declined')",
        )
    op.drop_constraint(
        constraint_name=op.f(
            name="invoices_confirmed_fields_check",
        ),
        table_name="invoices",
        type_="check",
    )
    op.alter_column(
        table_name="invoices",
        column_name="invoice_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.alter_column(
        table_name="invoices",
        column_name="invoice_number",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        table_name="invoices",
        column_name="supplier_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
