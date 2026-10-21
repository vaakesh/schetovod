"""products remember whether a shelf tag with the current retail price is hanging

create date: 2026-10-17 12:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5c2a8d4b7f1"
down_revision: str | Sequence[str] | None = "a7d3e5f1c2b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # nobody has marked a tag yet, every product starts without one
    op.add_column(
        table_name="products",
        column=sa.Column(
            "has_price_tag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        table_name="products",
        column_name="has_price_tag",
    )
