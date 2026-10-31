from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.db_types import BigInt, DateTimeTz, Money, receipt_kind_enum
from core.enums import ReceiptKind


class Receipt(Base):
    """a receipt of the aQsi cash register, it never changes once it is printed"""

    __tablename__ = "receipts"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    # a period can be loaded again, the receipts already here are left as they are
    aqsi_id: Mapped[UUID] = mapped_column(
        unique=True,
        nullable=False,
    )
    shift_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    shift_number: Mapped[int | None] = mapped_column(
        nullable=True,
    )
    # the number within the shift
    number: Mapped[int | None] = mapped_column(
        nullable=True,
    )
    processed_at: Mapped[DateTimeTz] = mapped_column(
        index=True,
        nullable=False,
    )
    kind: Mapped[ReceiptKind] = mapped_column(
        receipt_kind_enum,
        nullable=False,
    )
    # holds the payments of any kind, cash and card are only the two usual ones
    total: Mapped[Money] = mapped_column(
        nullable=False,
    )
    cash: Mapped[Money] = mapped_column(
        nullable=False,
    )
    card: Mapped[Money] = mapped_column(
        nullable=False,
    )
    # the lines of the receipt, not the pieces sold
    positions: Mapped[int] = mapped_column(
        nullable=False,
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
