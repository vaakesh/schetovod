"""orders to the suppliers, one draft cart and the confirmed history

create date: 2026-10-26 12:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8c1d3a6e2b4"
down_revision: str | Sequence[str] | None = "d7a4c2e9f8b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "confirmed",
                name="order_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(
                timezone=True,
            ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(
                timezone=True,
            ),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            sqltext="(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="confirmed_at",
        ),
        sa.PrimaryKeyConstraint(
            "id",
        ),
    )
    op.create_index(
        index_name="orders_status_key",
        table_name="orders",
        columns=[
            "status",
        ],
        unique=True,
        postgresql_where=sa.text(
            text="status = 'draft'",
        ),
    )
    op.create_table(
        "order_items",
        sa.Column(
            "id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            nullable=False,
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
            "unit",
            sa.String(),
            nullable=True,
        ),
        sa.Column(
            "cost_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(
                timezone=True,
            ),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            columns=[
                "order_id",
            ],
            refcolumns=[
                "orders.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            columns=[
                "product_id",
            ],
            refcolumns=[
                "products.id",
            ],
        ),
        sa.PrimaryKeyConstraint(
            "id",
        ),
        sa.UniqueConstraint(
            "order_id",
            "product_id",
        ),
    )
    op.create_index(
        index_name="order_items_order_id_idx",
        table_name="order_items",
        columns=[
            "order_id",
        ],
    )
    op.create_index(
        index_name="order_items_product_id_idx",
        table_name="order_items",
        columns=[
            "product_id",
        ],
    )


def downgrade() -> None:
    op.drop_table(
        table_name="order_items",
    )
    op.drop_table(
        table_name="orders",
    )
