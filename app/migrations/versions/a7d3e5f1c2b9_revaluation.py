"""products keep the shelf price, a revaluation entry reprices the stock on the shelf

create date: 2026-09-30 13:30:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e5f1c2b9"
down_revision: str | Sequence[str] | None = "f3a1c9d27b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'invoice', 'sale', 'write_off', 'stocktake'"


def upgrade() -> None:
    # the enum column is as long as its longest value, revaluation does not fit
    op.alter_column(
        table_name="ledger_entries",
        column_name="kind",
        type_=sa.String(
            length=11,
        ),
    )
    # short names, the naming convention in db.py adds the table and the suffix
    op.drop_constraint(
        constraint_name="ledger_kind",
        table_name="ledger_entries",
        type_="check",
    )
    op.create_check_constraint(
        constraint_name="ledger_kind",
        table_name="ledger_entries",
        condition=f"kind IN ({KINDS}, 'revaluation')",
    )
    op.create_check_constraint(
        constraint_name="revaluation_amount",
        table_name="ledger_entries",
        condition="kind <> 'revaluation' OR amount <> 0",
    )

    op.add_column(
        table_name="products",
        column=sa.Column(
            "retail_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),
    )
    # a product is created with its first posted line, the newest line has the shelf price
    op.execute(
        sqltext="""
        UPDATE products
        SET retail_price = items.retail_price
        FROM invoice_items AS items
        WHERE items.id = (
            SELECT max(id) FROM invoice_items WHERE product_id = products.id
        )
        """,
    )
    op.alter_column(
        table_name="products",
        column_name="retail_price",
        nullable=False,
    )
    op.create_check_constraint(
        constraint_name="retail_price",
        table_name="products",
        condition="retail_price >= 0 AND retail_price = trunc(retail_price)",
    )

    op.create_table(
        "revaluation_items",
        sa.Column(
            "id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "ledger_entry_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "invoice_item_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "quantity",
            sa.Numeric(
                precision=12,
                scale=3,
            ),
            sa.CheckConstraint(
                sqltext="quantity > 0",
                name="quantity",
            ),
            nullable=False,
        ),
        sa.Column(
            "old_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            sa.CheckConstraint(
                sqltext="old_price >= 0 AND old_price = trunc(old_price)",
                name="old_price",
            ),
            nullable=False,
        ),
        sa.Column(
            "new_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            sa.CheckConstraint(
                sqltext="new_price >= 0 AND new_price = trunc(new_price)",
                name="new_price",
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            sqltext="old_price <> new_price",
            name="price_changed",
        ),
        sa.ForeignKeyConstraint(
            columns=[
                "ledger_entry_id",
            ],
            refcolumns=[
                "ledger_entries.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            columns=[
                "product_id",
            ],
            refcolumns=[
                "products.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            columns=[
                "invoice_item_id",
            ],
            refcolumns=[
                "invoice_items.id",
            ],
        ),
        sa.PrimaryKeyConstraint(
            "id",
        ),
    )
    op.create_index(
        index_name="revaluation_items_ledger_entry_id_idx",
        table_name="revaluation_items",
        columns=[
            "ledger_entry_id",
        ],
    )
    op.create_index(
        index_name="revaluation_items_product_id_idx",
        table_name="revaluation_items",
        columns=[
            "product_id",
        ],
    )


def downgrade() -> None:
    op.drop_table(
        table_name="revaluation_items",
    )
    op.drop_column(
        table_name="products",
        column_name="retail_price",
    )
    op.execute(
        sqltext="DELETE FROM ledger_entries WHERE kind = 'revaluation'",
    )
    op.drop_constraint(
        constraint_name="revaluation_amount",
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
    op.alter_column(
        table_name="ledger_entries",
        column_name="kind",
        type_=sa.String(
            length=9,
        ),
    )
