from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.db_types import BigInt, DateTimeTz, Money, Quantity, stocktake_unit_enum
from core.enums import StocktakeUnit


class Stocktake(Base):
    __tablename__ = "stocktakes"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    started_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    completed_at: Mapped[DateTimeTz | None] = mapped_column(
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        server_default="1",
    )

    __table_args__ = (
        # every open document has the same indexed value
        Index(
            "stocktakes_open_key",
            completed_at.is_(
                other=None,
            ),
            unique=True,
            postgresql_where=completed_at.is_(
                other=None,
            ),
        ),
    )


class StocktakeLine(Base):
    __tablename__ = "stocktake_lines"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    document_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="stocktakes.id",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        nullable=False,
    )
    name_key: Mapped[str] = mapped_column(
        nullable=False,
    )
    unit: Mapped[StocktakeUnit] = mapped_column(
        stocktake_unit_enum,
        nullable=False,
    )
    price: Mapped[Money | None] = mapped_column(
        CheckConstraint(
            sqltext="price >= 0",
            name="price",
        ),
        nullable=True,
    )
    quantity: Mapped[Quantity | None] = mapped_column(
        CheckConstraint(
            sqltext="quantity >= 0",
            name="quantity",
        ),
        nullable=True,
    )
    entered_amount: Mapped[Money | None] = mapped_column(
        CheckConstraint(
            sqltext="entered_amount >= 0",
            name="entered_amount",
        ),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        server_default="1",
    )

    __table_args__ = (
        # a name can occur once in each document
        UniqueConstraint(
            "document_id",
            "name_key",
        ),
        # pieces are indivisible
        CheckConstraint(
            sqltext="unit <> 'шт' OR quantity = trunc(quantity)",
            name="whole_pieces",
        ),
        # a counted quantity needs a unit price, a directly entered amount stands on its own
        CheckConstraint(
            sqltext="(quantity IS NOT NULL AND price IS NOT NULL AND entered_amount IS NULL) "
            "OR (quantity IS NULL AND entered_amount IS NOT NULL)",
            name="measurement",
        ),
    )


class StocktakeRequest(Base):
    """acknowledgements survive subsequent edits and deletion of a line"""

    __tablename__ = "stocktake_requests"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    document_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="stocktakes.id",
        ),
        nullable=False,
    )
    signature: Mapped[str] = mapped_column(
        nullable=False,
    )
    line_id: Mapped[BigInt | None] = mapped_column(
        nullable=True,
    )
