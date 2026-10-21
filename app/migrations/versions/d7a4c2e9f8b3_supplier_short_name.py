"""suppliers get an optional short name for the reports

create date: 2026-10-17 18:00:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a4c2e9f8b3"
down_revision: str | Sequence[str] | None = "c9e3b7a1d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # without it the reports print the full name, as before
    op.add_column(
        table_name="suppliers",
        column=sa.Column(
            "short_name",
            sa.String(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        table_name="suppliers",
        column_name="short_name",
    )
