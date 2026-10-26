from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.db_types import (
    BigInt,
    DateTimeTz,
    Money,
    Quantity,
    order_status_enum,
)
from core.enums import OrderStatus

if TYPE_CHECKING:
    from products.models import Product


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    # the cart stays a draft until the user confirms it, a confirmed order never changes
    status: Mapped[OrderStatus] = mapped_column(
        order_status_enum,
        nullable=False,
        default=OrderStatus.DRAFT,
        server_default=OrderStatus.DRAFT,
    )
    confirmed_at: Mapped[DateTimeTz | None] = mapped_column(
        nullable=True,
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

    # a line taken out of the list is deleted, a deleted order takes its lines along
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # a confirmed order knows when, a draft was not confirmed yet
        CheckConstraint(
            sqltext=f"(status = '{OrderStatus.CONFIRMED}') = (confirmed_at IS NOT NULL)",
            name="confirmed_at",
        ),
        # there is one cart, a second draft would split it
        Index(
            "orders_status_key",
            "status",
            unique=True,
            postgresql_where=text(
                text=f"status = '{OrderStatus.DRAFT}'",
            ),
        ),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    order_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="orders.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    product_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="products.id",
        ),
        nullable=False,
        index=True,
    )
    # pieces or kilograms, in the unit of the last invoice
    quantity: Mapped[Quantity] = mapped_column(
        CheckConstraint(
            sqltext="quantity > 0",
            name="quantity",
        ),
        nullable=False,
    )
    # copied from the last posted line on confirmation, a draft shows the current ones
    unit: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    cost_price: Mapped[Money | None] = mapped_column(
        nullable=True,
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

    order: Mapped[Order] = relationship(
        back_populates="items",
        lazy="raise",
    )
    product: Mapped[Product] = relationship(
        lazy="raise",
    )

    __table_args__ = (
        # a product is ordered on one line, adding it again changes the quantity
        UniqueConstraint(
            "order_id",
            "product_id",
        ),
    )
