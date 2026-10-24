from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.config import today
from core.db import Base
from core.db_types import (
    BigInt,
    DateTimeTz,
    Money,
    Quantity,
    invoice_status_enum,
    ledger_kind_enum,
)
from core.enums import InvoiceStatus, LedgerKind

if TYPE_CHECKING:
    from invoices.models import Invoice
    from products.models import Product


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    # the day it happened, reports are built by it, within a day entries go by id
    occurred_on: Mapped[date] = mapped_column(
        nullable=False,
        default=today,
        server_default=func.current_date(),
        index=True,
    )
    # when it was entered
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    kind: Mapped[LedgerKind] = mapped_column(
        ledger_kind_enum,
        nullable=False,
    )
    # signed, the stock at retail prices
    amount: Mapped[Money] = mapped_column(
        nullable=False,
    )
    # signed, the cash in the till, zero for an entry that does not touch it
    cash: Mapped[Money] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    comment: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    invoice_id: Mapped[BigInt | None] = mapped_column(
        nullable=True,
        unique=True,
    )
    # copied from the invoice, only a confirmed invoice can be posted
    invoice_status: Mapped[InvoiceStatus | None] = mapped_column(
        invoice_status_enum,
        CheckConstraint(
            sqltext=f"invoice_status = '{InvoiceStatus.CONFIRMED}'",
            name="invoice_status_confirmed",
        ),
        nullable=True,
    )
    # a reversal cancels the entry it points to, an entry is reversed at most once
    reverses_id: Mapped[BigInt | None] = mapped_column(
        ForeignKey(
            column="ledger_entries.id",
        ),
        nullable=True,
        unique=True,
    )

    invoice: Mapped[Invoice | None] = relationship(
        lazy="raise",
    )
    reverses: Mapped[LedgerEntry | None] = relationship(
        remote_side=[
            id,
        ],
        lazy="raise",
    )

    __table_args__ = (
        # also blocks declining an invoice that is already posted
        ForeignKeyConstraint(
            columns=[
                "invoice_id",
                "invoice_status",
            ],
            refcolumns=[
                "invoices.id",
                "invoices.status",
            ],
        ),
        # an invoice entry always points to an invoice, other kinds never do
        CheckConstraint(
            sqltext=f"(kind = '{LedgerKind.INVOICE}') = (invoice_id IS NOT NULL)",
            name="invoice_id",
        ),
        CheckConstraint(
            sqltext="(invoice_id IS NULL) = (invoice_status IS NULL)",
            name="invoice_status_present",
        ),
        # an invoice brings stock in and is never reversed, its invoice can not be unposted
        CheckConstraint(
            sqltext=f"kind <> '{LedgerKind.INVOICE}' OR (amount >= 0 AND reverses_id IS NULL)",
            name="invoice_amount",
        ),
        # a sale or a write-off takes stock out, only its reversal brings it back
        CheckConstraint(
            sqltext=(
                f"kind NOT IN ('{LedgerKind.SALE}', '{LedgerKind.WRITE_OFF}') "
                "OR (reverses_id IS NULL AND amount < 0) "
                "OR (reverses_id IS NOT NULL AND amount > 0)"
            ),
            name="outflow_sign",
        ),
        # a revaluation changes the price of something, the sign depends on the direction
        CheckConstraint(
            sqltext=f"kind <> '{LedgerKind.REVALUATION}' OR amount <> 0",
            name="revaluation_amount",
        ),
        # the till operations move money only, the stock stays
        CheckConstraint(
            sqltext=(
                f"kind NOT IN ('{LedgerKind.CASH_IN}', '{LedgerKind.CASH_OUT}', "
                f"'{LedgerKind.CASH_COUNT}') OR amount = 0"
            ),
            name="cash_only",
        ),
        # only a sale and the till operations touch the till
        CheckConstraint(
            sqltext=(
                f"kind NOT IN ('{LedgerKind.INVOICE}', '{LedgerKind.WRITE_OFF}', "
                f"'{LedgerKind.STOCKTAKE}', '{LedgerKind.REVALUATION}') OR cash = 0"
            ),
            name="no_cash",
        ),
        # the cash part of a sale goes into the till and is at most the whole sale,
        # the reversal flips both signs
        CheckConstraint(
            sqltext=(
                f"kind <> '{LedgerKind.SALE}' OR (cash * amount <= 0 AND abs(cash) <= abs(amount))"
            ),
            name="sale_cash",
        ),
        CheckConstraint(
            sqltext=(
                f"kind <> '{LedgerKind.CASH_IN}' "
                "OR (reverses_id IS NULL AND cash > 0) "
                "OR (reverses_id IS NOT NULL AND cash < 0)"
            ),
            name="cash_in_sign",
        ),
        CheckConstraint(
            sqltext=(
                f"kind <> '{LedgerKind.CASH_OUT}' "
                "OR (reverses_id IS NULL AND cash < 0) "
                "OR (reverses_id IS NOT NULL AND cash > 0)"
            ),
            name="cash_out_sign",
        ),
    )


class RevaluationItem(Base):
    """a product whose stock on the shelf got a new price"""

    __tablename__ = "revaluation_items"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    ledger_entry_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="ledger_entries.id",
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
    # the invoice line that brought the new price, None for a revaluation by hand
    invoice_item_id: Mapped[BigInt | None] = mapped_column(
        ForeignKey(
            column="invoice_items.id",
        ),
        nullable=True,
    )
    # counted on the shelf, the old stock only
    quantity: Mapped[Quantity] = mapped_column(
        CheckConstraint(
            sqltext="quantity > 0",
            name="quantity",
        ),
        nullable=False,
    )
    old_price: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="old_price >= 0 AND old_price = trunc(old_price)",
            name="old_price",
        ),
        nullable=False,
    )
    new_price: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="new_price >= 0 AND new_price = trunc(new_price)",
            name="new_price",
        ),
        nullable=False,
    )

    ledger_entry: Mapped[LedgerEntry] = relationship(
        lazy="raise",
    )
    product: Mapped[Product] = relationship(
        lazy="raise",
    )

    __table_args__ = (
        # an unchanged price has nothing to revalue
        CheckConstraint(
            sqltext="old_price <> new_price",
            name="price_changed",
        ),
    )
