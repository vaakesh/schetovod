from sqlalchemy import CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.db_types import (
    BigInt,
    DateTimeTz,
    Money,
    price_tag_origin_enum,
    price_tag_unit_enum,
)
from core.enums import PriceTagOrigin, PriceTagUnit


class PriceTag(Base):
    """a shelf tag once printed or imported, offered again when the same goods need a tag"""

    __tablename__ = "price_tags"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    width_mm: Mapped[int] = mapped_column(
        nullable=False,
    )
    height_mm: Mapped[int] = mapped_column(
        nullable=False,
    )
    unit: Mapped[PriceTagUnit] = mapped_column(
        price_tag_unit_enum,
        nullable=False,
    )
    # the weight or volume in the header, e.g. «1 кг», None when the header shows only the unit
    pack: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    # may keep line breaks and no-break spaces, they shape the printed text
    name: Mapped[str] = mapped_column(
        nullable=False,
    )
    subtitle: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    # None prints an empty price block for a price written by hand
    price: Mapped[Money | None] = mapped_column(
        CheckConstraint(
            sqltext="price >= 0",
            name="price",
        ),
        nullable=True,
    )
    origin: Mapped[PriceTagOrigin] = mapped_column(
        price_tag_origin_enum,
        nullable=False,
    )
    origin_name: Mapped[str] = mapped_column(
        nullable=False,
    )
    # every printed field without case and spacing differences, one row per distinct tag
    dedup_key: Mapped[str] = mapped_column(
        nullable=False,
        unique=True,
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # the four tag sizes the shop prints and cuts
        CheckConstraint(
            sqltext=(
                "(width_mm, height_mm) IN ((40, 50), (50, 80), (60, 70), (70, 100))"
            ),
            name="size",
        ),
    )
