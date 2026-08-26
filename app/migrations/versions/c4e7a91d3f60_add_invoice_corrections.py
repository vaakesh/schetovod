"""add invoice corrections

create date: 2026-08-26 13:20:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e7a91d3f60"
down_revision: str | Sequence[str] | None = "b8ca4f0d2e19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        table_name="invoices",
        column=sa.Column(
            "corrections",
            postgresql.JSONB(),
            server_default=sa.text(
                text="'{}'::jsonb",
            ),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        table_name="invoices",
        column_name="corrections",
    )
