from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.db_types import (
    BigInt,
    DateTimeTz,
    Money,
    Percent,
)

if TYPE_CHECKING:
    from suppliers.models import Supplier


class Product(Base):
    __tablename__ = "products"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    supplier_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="suppliers.id",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        nullable=False,
    )
    markup_pct: Mapped[Percent] = mapped_column(
        CheckConstraint(
            sqltext="markup_pct BETWEEN 0 AND 999.99",
            name="markup_pct",
        ),
        nullable=False,
    )
    # the price on the shelf, whole rubles, the old price of a revaluation
    retail_price: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="retail_price >= 0 AND retail_price = trunc(retail_price)",
            name="retail_price",
        ),
        nullable=False,
    )
    # a shelf tag with the current retail price is hanging, any new price resets it
    has_price_tag: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=false(),
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

    supplier: Mapped[Supplier] = relationship(
        back_populates="products",
        lazy="raise",
    )
    aliases: Mapped[list[ProductAlias]] = relationship(
        back_populates="product",
        lazy="raise",
    )

    __table_args__ = (
        # target for composite foreign keys that tie rows to the product supplier
        UniqueConstraint(
            "id",
            "supplier_id",
        ),
    )


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    product_id: Mapped[BigInt] = mapped_column(
        nullable=False,
    )
    # copied from the product, needed for the unique key
    supplier_id: Mapped[BigInt] = mapped_column(
        nullable=False,
    )
    alias_normalized: Mapped[str] = mapped_column(
        nullable=False,
    )
    alias_raw: Mapped[str] = mapped_column(
        nullable=False,
    )

    product: Mapped[Product] = relationship(
        back_populates="aliases",
        lazy="raise",
    )

    __table_args__ = (
        # the alias belongs to the same supplier as its product
        ForeignKeyConstraint(
            columns=[
                "product_id",
                "supplier_id",
            ],
            refcolumns=[
                "products.id",
                "products.supplier_id",
            ],
        ),
        # a name is unique within a supplier, different suppliers may share it
        UniqueConstraint(
            "supplier_id",
            "alias_normalized",
        ),
    )
