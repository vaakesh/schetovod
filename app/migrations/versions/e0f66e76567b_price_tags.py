"""shelf tags printed or imported from the cenniki-v2 skill, offered again by name

create date: 2026-11-07 10:45:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e0f66e76567b"
down_revision: str | Sequence[str] | None = "e182dd92c1e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_tags",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("width_mm", sa.Integer(), nullable=False),
        sa.Column("height_mm", sa.Integer(), nullable=False),
        sa.Column(
            "unit",
            sa.Enum(
                "piece",
                "weight",
                name="price_tag_unit",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("pack", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subtitle", sa.String(), nullable=True),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "origin",
            sa.Enum(
                "maker",
                "country",
                name="price_tag_origin",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("origin_name", sa.String(), nullable=False),
        sa.Column("dedup_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price >= 0", name=op.f("price_tags_price_check")),
        sa.CheckConstraint(
            "(width_mm, height_mm) IN ((40, 50), (50, 80), (60, 70), (70, 100))",
            name=op.f("price_tags_size_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("price_tags_pkey")),
        sa.UniqueConstraint("dedup_key", name=op.f("price_tags_dedup_key_key")),
    )


def downgrade() -> None:
    op.drop_table("price_tags")
