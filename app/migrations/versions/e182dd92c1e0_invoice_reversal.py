"""a confirmed invoice may be reversed while no stocktake came after it

create date: 2026-11-04 12:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e182dd92c1e0"
down_revision: str | Sequence[str] | None = "d7b2e4f1a9c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'draft', 'confirmed', 'declined'"
NEW_STATUSES = f"{OLD_STATUSES}, 'reversed'"


def replace_check(
    table_name: str,
    name: str,
    condition: str,
) -> None:
    """full names, the checks below were created with them"""
    op.drop_constraint(
        constraint_name=op.f(
            name=name,
        ),
        table_name=table_name,
        type_="check",
    )
    op.create_check_constraint(
        constraint_name=op.f(
            name=name,
        ),
        table_name=table_name,
        condition=condition,
    )


def replace_invoice_fkey(
    onupdate: str | None,
) -> None:
    op.drop_constraint(
        constraint_name=op.f(
            name="ledger_entries_invoice_id_invoice_status_fkey",
        ),
        table_name="ledger_entries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        constraint_name=op.f(
            name="ledger_entries_invoice_id_invoice_status_fkey",
        ),
        source_table="ledger_entries",
        referent_table="invoices",
        local_cols=[
            "invoice_id",
            "invoice_status",
        ],
        remote_cols=[
            "id",
            "status",
        ],
        onupdate=onupdate,
    )


def upgrade() -> None:
    for table_name, column_name in (
        ("invoices", "status"),
        ("ledger_entries", "invoice_status"),
    ):
        replace_check(
            table_name=table_name,
            name=f"{table_name}_invoice_status_check",
            condition=f"{column_name} IN ({NEW_STATUSES})",
        )
    replace_check(
        table_name="invoices",
        name="invoices_confirmed_fields_check",
        condition=(
            "status NOT IN ('confirmed', 'reversed') OR "
            "(supplier_id IS NOT NULL AND invoice_number IS NOT NULL "
            "AND invoice_date IS NOT NULL)"
        ),
    )
    replace_check(
        table_name="ledger_entries",
        name="ledger_entries_invoice_status_confirmed_check",
        condition="invoice_status IN ('confirmed', 'reversed')",
    )
    replace_check(
        table_name="ledger_entries",
        name="ledger_entries_invoice_amount_check",
        condition=(
            "kind <> 'invoice' "
            "OR (reverses_id IS NULL AND amount >= 0) "
            "OR (reverses_id IS NOT NULL AND amount <= 0)"
        ),
    )
    # the status of a reversed invoice is carried over to its entries
    replace_invoice_fkey(
        onupdate="CASCADE",
    )
    # the reversal points to the same invoice, so only the posting itself is unique
    op.drop_constraint(
        constraint_name=op.f(
            name="ledger_entries_invoice_id_key",
        ),
        table_name="ledger_entries",
        type_="unique",
    )
    op.create_index(
        index_name=op.f(
            name="ledger_entries_invoice_id_key",
        ),
        table_name="ledger_entries",
        columns=[
            "invoice_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            text="reverses_id IS NULL",
        ),
    )


def downgrade() -> None:
    # a reversed invoice has no place in the old schema, it is not dropped silently
    reversed_count = op.get_bind().scalar(
        sa.text(
            text="SELECT count(*) FROM invoices WHERE status = 'reversed'",
        ),
    )
    if reversed_count:
        raise RuntimeError(
            f"{reversed_count} reversed invoices are in the database, "
            "the downgrade would lose them",
        )
    op.drop_index(
        index_name=op.f(
            name="ledger_entries_invoice_id_key",
        ),
        table_name="ledger_entries",
    )
    op.create_unique_constraint(
        constraint_name=op.f(
            name="ledger_entries_invoice_id_key",
        ),
        table_name="ledger_entries",
        columns=[
            "invoice_id",
        ],
    )
    replace_invoice_fkey(
        onupdate=None,
    )
    replace_check(
        table_name="ledger_entries",
        name="ledger_entries_invoice_amount_check",
        condition="kind <> 'invoice' OR (amount >= 0 AND reverses_id IS NULL)",
    )
    replace_check(
        table_name="ledger_entries",
        name="ledger_entries_invoice_status_confirmed_check",
        condition="invoice_status = 'confirmed'",
    )
    replace_check(
        table_name="invoices",
        name="invoices_confirmed_fields_check",
        condition=(
            "status <> 'confirmed' OR "
            "(supplier_id IS NOT NULL AND invoice_number IS NOT NULL "
            "AND invoice_date IS NOT NULL)"
        ),
    )
    for table_name, column_name in (
        ("invoices", "status"),
        ("ledger_entries", "invoice_status"),
    ):
        replace_check(
            table_name=table_name,
            name=f"{table_name}_invoice_status_check",
            condition=f"{column_name} IN ({OLD_STATUSES})",
        )
