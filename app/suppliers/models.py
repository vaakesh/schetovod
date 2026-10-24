from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.db_types import (
    BigInt,
    DateTimeTz,
)

if TYPE_CHECKING:
    from invoices.models import Invoice
    from products.models import Product


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    # as printed on the first invoice
    name: Mapped[str] = mapped_column(
        nullable=False,
    )
    # a short name for the reports, the full name is printed there without it
    short_name: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    # looked up by inn first, without it the user picks a supplier by name or adds one
    inn: Mapped[str | None] = mapped_column(
        # 10 digits for a company, 12 for a sole proprietor, the checksum is verified in code
        CheckConstraint(
            sqltext="inn ~ '^[0-9]{10}([0-9]{2})?$'",
            name="inn",
        ),
        nullable=True,
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

    products: Mapped[list[Product]] = relationship(
        back_populates="supplier",
        lazy="raise",
    )
    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="supplier",
        lazy="raise",
    )
