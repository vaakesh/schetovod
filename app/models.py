from datetime import date

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import today
from db import Base
from db_types import (
    BigInt,
    DateTimeTz,
    Money,
    Percent,
    Quantity,
    invoice_status_enum,
    ledger_kind_enum,
)
from enums import InvoiceStatus, LedgerKind


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


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    supplier_id: Mapped[BigInt | None] = mapped_column(
        ForeignKey(
            column="suppliers.id",
        ),
        nullable=True,
        index=True,
    )
    # as printed, may contain letters and leading zeros
    invoice_number: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    # date of the document, not of the upload
    invoice_date: Mapped[date | None] = mapped_column(
        nullable=True,
    )
    # starts as a draft until the user confirms or declines it
    status: Mapped[InvoiceStatus] = mapped_column(
        invoice_status_enum,
        nullable=False,
        default=InvoiceStatus.DRAFT,
        server_default=InvoiceStatus.DRAFT,
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    # raw model response as is, including incomplete draft lines
    extracted: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    # the draft form as the user saved it last, None until the first save,
    # then the form is built from the extraction and the current catalog
    form: Mapped[dict | None] = mapped_column(
        # None is stored as SQL NULL, not as a JSON null
        JSONB(
            none_as_null=True,
        ),
        nullable=True,
    )

    supplier: Mapped[Supplier | None] = relationship(
        back_populates="invoices",
        lazy="raise",
    )
    items: Mapped[list[InvoiceItem]] = relationship(
        back_populates="invoice",
        lazy="raise",
    )
    payments: Mapped[list[InvoicePayment]] = relationship(
        back_populates="invoice",
        lazy="raise",
    )

    __table_args__ = (
        # confirmed invoices need an identity, drafts and declined uploads may be incomplete
        CheckConstraint(
            sqltext=(
                f"status <> '{InvoiceStatus.CONFIRMED}' OR "
                "(supplier_id IS NOT NULL AND invoice_number IS NOT NULL "
                "AND invoice_date IS NOT NULL)"
            ),
            name="confirmed_fields",
        ),
        # target for the composite foreign key from invoice_items
        UniqueConstraint(
            "id",
            "supplier_id",
        ),
        # target for the composite foreign key from ledger_entries
        UniqueConstraint(
            "id",
            "status",
        ),
        # only confirmed invoices are unique, a declined one may be uploaded again
        Index(
            "invoices_supplier_id_invoice_number_invoice_date_key",
            "supplier_id",
            "invoice_number",
            "invoice_date",
            unique=True,
            postgresql_where=text(
                text=f"status = '{InvoiceStatus.CONFIRMED}'",
            ),
        ),
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    invoice_id: Mapped[BigInt] = mapped_column(
        nullable=False,
    )
    product_id: Mapped[BigInt] = mapped_column(
        nullable=False,
        index=True,
    )
    # copied from the invoice, the product must belong to the same supplier
    supplier_id: Mapped[BigInt] = mapped_column(
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(
        CheckConstraint(
            sqltext="line_no > 0",
            name="line_no",
        ),
        nullable=False,
    )
    # as printed on this invoice
    name: Mapped[str] = mapped_column(
        nullable=False,
    )
    quantity: Mapped[Quantity] = mapped_column(
        CheckConstraint(
            sqltext="quantity > 0",
            name="quantity",
        ),
        nullable=False,
    )
    unit: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    vat_percent: Mapped[Percent | None] = mapped_column(
        CheckConstraint(
            sqltext="vat_percent BETWEEN 0 AND 100",
            name="vat_percent",
        ),
        nullable=True,
    )
    # unit price without VAT, missing when the invoice shows only prices with VAT
    base_price: Mapped[Money | None] = mapped_column(
        CheckConstraint(
            sqltext="base_price >= 0",
            name="base_price",
        ),
        nullable=True,
    )
    # unit price actually paid, with VAT if any
    cost_price: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="cost_price >= 0",
            name="cost_price",
        ),
        nullable=False,
    )
    # line total actually paid, kept separately from the rounded unit price
    cost_price_total: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="cost_price_total >= 0",
            name="cost_price_total",
        ),
        nullable=False,
    )
    # as of posting
    markup_pct: Mapped[Percent] = mapped_column(
        CheckConstraint(
            sqltext="markup_pct BETWEEN 0 AND 999.99",
            name="markup_pct",
        ),
        nullable=False,
    )
    # unit price with markup, whole rubles
    retail_price: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="retail_price >= 0 AND retail_price = trunc(retail_price)",
            name="retail_price",
        ),
        nullable=False,
    )

    invoice: Mapped[Invoice] = relationship(
        back_populates="items",
        lazy="raise",
    )
    # shares supplier_id with the invoice relationship on purpose,
    # if they disagree the composite foreign keys reject the row
    product: Mapped[Product] = relationship(
        lazy="raise",
        overlaps="invoice,items",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            columns=[
                "invoice_id",
                "supplier_id",
            ],
            refcolumns=[
                "invoices.id",
                "invoices.supplier_id",
            ],
        ),
        # the product belongs to the invoice supplier
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
        # also serves lookups of invoice lines by invoice_id
        UniqueConstraint(
            "invoice_id",
            "line_no",
        ),
    )


class InvoicePayment(Base):
    """money paid to the supplier for a confirmed invoice, the till is not touched"""

    __tablename__ = "invoice_payments"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    invoice_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="invoices.id",
        ),
        nullable=False,
        index=True,
    )
    paid_on: Mapped[date] = mapped_column(
        nullable=False,
        default=today,
        server_default=func.current_date(),
    )
    amount: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="amount > 0",
            name="amount",
        ),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    invoice: Mapped[Invoice] = relationship(
        back_populates="payments",
        lazy="raise",
    )


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
