from datetime import date

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    corrections: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text(
            text="'{}'::jsonb",
        ),
    )

    supplier: Mapped[Supplier | None] = relationship(
        back_populates="invoices",
        lazy="raise",
    )
    items: Mapped[list[InvoiceItem]] = relationship(
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


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    occurred_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
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
    # signed
    amount: Mapped[Money] = mapped_column(
        nullable=False,
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
    invoice: Mapped[Invoice | None] = relationship(
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
    )
