"""replace invoice corrections with the draft form

create date: 2026-09-08 15:10:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2b85f0c7a14"
down_revision: str | Sequence[str] | None = "c4e7a91d3f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column(
        table_name="invoices",
        column_name="corrections",
    )
    op.add_column(
        table_name="invoices",
        column=sa.Column(
            "form",
            postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        table_name="invoices",
        column_name="form",
    )
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
