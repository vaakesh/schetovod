from collections.abc import Collection
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from config import today
from enums import InvoiceSort, InvoiceStatus, LedgerKind
from models import (
    Invoice,
    InvoiceItem,
    InvoicePayment,
    LedgerEntry,
    Product,
    ProductAlias,
    RevaluationItem,
    Supplier,
)
from pricing import normalize_name
from repositories import (
    CatalogRow,
    DebtRow,
    InvoiceRow,
    LedgerRow,
    ProductRow,
)

INN = "7701234560"
ZERO = Decimal(
    value=0,
)


def invoice_payload() -> dict[str, Any]:
    return {
        "supplier": {"name": "ООО «Поставщик»", "inn": INN},
        "invoice_number": "00042/А",
        "invoice_date": "12-08-2026",
        "items": [
            {
                "line_no": "1",
                "name": "Сахар-песок 1 кг",
                "quantity": "2.500",
                "unit": "кг",
                "base_price": "50.00",
                "base_price_total": "125.00",
                "cost_price": "50.00",
                "cost_price_total": "125.00",
                "vat_percent": None,
            },
            {
                "line_no": "2",
                "name": "Соль",
                "quantity": "1",
                "unit": "шт",
                "base_price": None,
                "base_price_total": "30.00",
                "cost_price": None,
                "cost_price_total": None,
                "vat_percent": None,
            },
        ],
        "totals": {"base_total": "155.00", "cost_total": None},
    }


def _debt(row: InvoiceRow) -> Decimal | None:
    return None if row.cost_total is None else row.cost_total - row.paid


class FakeStore:
    """the database for one test, the fake repositories share it"""

    def __init__(self) -> None:
        self.invoices: dict[int, Invoice] = {}
        self.suppliers: dict[int, Supplier] = {}
        self.products: dict[int, Product] = {}
        self.aliases: list[ProductAlias] = []
        self.items: list[InvoiceItem] = []
        self.payments: list[InvoicePayment] = []
        self.entries: list[LedgerEntry] = []
        self.revaluations: list[RevaluationItem] = []
        self.commits = 0
        self.locks = 0
        # the order of the ledger locks and the draft reads
        self.events: list[str] = []
        self.last_id = 0

    def new_id(self) -> int:
        self.last_id += 1
        return self.last_id

    def add_supplier(
        self,
        name: str,
        inn: str | None,
    ) -> Supplier:
        supplier = Supplier(
            id=self.new_id(),
            name=name,
            short_name=None,
            inn=inn,
        )
        self.suppliers[supplier.id] = supplier
        return supplier

    def add_product(
        self,
        supplier: Supplier,
        name: str,
        markup_pct: str,
        retail_price: str,
    ) -> Product:
        product = Product(
            id=self.new_id(),
            supplier_id=supplier.id,
            name=name,
            markup_pct=Decimal(
                value=markup_pct,
            ),
            retail_price=Decimal(
                value=retail_price,
            ),
            # the database default, a fake product is never inserted
            has_price_tag=False,
        )
        self.products[product.id] = product
        self.aliases.append(
            ProductAlias(
                id=self.new_id(),
                product_id=product.id,
                supplier_id=supplier.id,
                alias_normalized=normalize_name(
                    name=name,
                ),
                alias_raw=name,
            ),
        )
        return product


class FakeInvoices:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def create(
        self,
        invoice: Invoice,
    ) -> Invoice:
        invoice.id = self.store.new_id()
        # the server default is applied on insert, there is none here
        invoice.created_at = datetime.now(
            tz=UTC,
        )
        self.store.invoices[invoice.id] = invoice
        return invoice

    async def get_draft(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        self.store.events.append(
            "get_draft",
        )
        invoice = self.store.invoices.get(
            invoice_id,
        )
        if invoice is None or invoice.status != InvoiceStatus.DRAFT:
            return None
        return invoice

    async def find_confirmed(
        self,
        supplier_id: int,
        invoice_number: str,
        invoice_date: date,
    ) -> Invoice | None:
        for invoice in self.store.invoices.values():
            if (
                invoice.status == InvoiceStatus.CONFIRMED
                and invoice.supplier_id == supplier_id
                and invoice.invoice_number == invoice_number
                and invoice.invoice_date == invoice_date
            ):
                return invoice
        return None

    async def search(
        self,
        status: InvoiceStatus | None,
        unpaid: bool,
        query: str | None,
        sort: InvoiceSort,
        limit: int,
        offset: int,
    ) -> list[InvoiceRow]:
        rows = []
        for invoice in sorted(
            self.store.invoices.values(),
            key=lambda invoice: -invoice.id,
        ):
            supplier = None
            if invoice.supplier_id is not None:
                supplier = self.store.suppliers.get(
                    invoice.supplier_id,
                )
            name = supplier.name if supplier else invoice.extracted["supplier"]["name"]
            if status is not None and invoice.status != status:
                continue
            texts = (name or "", invoice.invoice_number or "")
            if query and not any(
                (query.lower() in text.lower() for text in texts),
            ):
                continue
            entry = await FakeLedger(
                store=self.store,
            ).get_for_invoice(
                invoice_id=invoice.id,
            )
            lines = (
                invoice.form["lines"] if invoice.form else invoice.extracted["items"]
            )
            cost_totals = await self.cost_totals(
                invoice_ids=[
                    invoice.id,
                ],
            )
            paid_totals = await self.paid_totals(
                invoice_ids=[
                    invoice.id,
                ],
                on=None,
            )
            rows.append(
                InvoiceRow(
                    invoice=invoice,
                    supplier_name=name,
                    retail_total=entry.amount if entry else None,
                    lines=len(
                        lines,
                    ),
                    cost_total=(
                        cost_totals.get(
                            invoice.id,
                            ZERO,
                        )
                        if invoice.status == InvoiceStatus.CONFIRMED
                        else None
                    ),
                    paid=paid_totals.get(
                        invoice.id,
                        ZERO,
                    ),
                ),
            )
        if unpaid:
            rows = [row for row in rows if (_debt(row=row) or 0) > 0]
        if sort == InvoiceSort.DEBT:
            # stable, the newest first stays within an equal debt, no debt goes last
            rows.sort(
                key=lambda row: (
                    _debt(row=row) is None,
                    -(_debt(row=row) or 0),
                ),
            )
        return rows[offset : offset + limit]

    async def get_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        invoice = self.store.invoices.get(
            invoice_id,
        )
        if (
            invoice is None
            or invoice.status != InvoiceStatus.CONFIRMED
            or invoice.supplier_id is None
        ):
            return None
        # what selectinload brings in the real repository
        invoice.supplier = self.store.suppliers[invoice.supplier_id]
        items = [item for item in self.store.items if item.invoice_id == invoice.id]
        for item in items:
            item.product = self.store.products[item.product_id]
        invoice.items = items
        return invoice

    async def lock_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        invoice = self.store.invoices.get(
            invoice_id,
        )
        if invoice is None or invoice.status != InvoiceStatus.CONFIRMED:
            return None
        return invoice

    async def cost_totals(
        self,
        invoice_ids: Collection[int],
    ) -> dict[int, Decimal]:
        totals: dict[int, Decimal] = {}
        for item in self.store.items:
            if item.invoice_id in invoice_ids:
                totals[item.invoice_id] = (
                    totals.get(
                        item.invoice_id,
                        ZERO,
                    )
                    + item.cost_price_total
                )
        return totals

    async def paid_totals(
        self,
        invoice_ids: Collection[int],
        on: date | None,
    ) -> dict[int, Decimal]:
        totals: dict[int, Decimal] = {}
        for payment in self.store.payments:
            if payment.invoice_id in invoice_ids and (
                on is None or payment.paid_on <= on
            ):
                totals[payment.invoice_id] = (
                    totals.get(
                        payment.invoice_id,
                        ZERO,
                    )
                    + payment.amount
                )
        return totals

    async def paid_between(
        self,
        date_from: date,
        date_to: date,
    ) -> Decimal:
        return sum(
            (
                payment.amount
                for payment in self.store.payments
                if date_from <= payment.paid_on <= date_to
            ),
            start=ZERO,
        )

    async def debts(
        self,
        on: date,
    ) -> list[DebtRow]:
        rows = []
        for entry in self.store.entries:
            if entry.invoice_id is None or entry.occurred_on > on:
                continue
            invoice = self.store.invoices[entry.invoice_id]
            if invoice.supplier_id is None:
                continue
            cost_total = (
                await self.cost_totals(
                    invoice_ids=[
                        invoice.id,
                    ],
                )
            ).get(
                invoice.id,
                ZERO,
            )
            paid = (
                await self.paid_totals(
                    invoice_ids=[
                        invoice.id,
                    ],
                    on=on,
                )
            ).get(
                invoice.id,
                ZERO,
            )
            if cost_total > paid:
                rows.append(
                    DebtRow(
                        invoice=invoice,
                        supplier_name=self.store.suppliers[invoice.supplier_id].name,
                        supplier_short_name=self.store.suppliers[
                            invoice.supplier_id
                        ].short_name,
                        cost_total=cost_total,
                        paid=paid,
                    ),
                )
        rows.sort(
            key=lambda row: (row.invoice.invoice_date, row.invoice.id),
        )
        return rows

    async def payments_of(
        self,
        invoice_id: int,
    ) -> list[InvoicePayment]:
        return sorted(
            (
                payment
                for payment in self.store.payments
                if payment.invoice_id == invoice_id
            ),
            key=lambda payment: (payment.paid_on, payment.id),
        )

    async def get_payment(
        self,
        invoice_id: int,
        payment_id: int,
    ) -> InvoicePayment | None:
        for payment in self.store.payments:
            if payment.id == payment_id and payment.invoice_id == invoice_id:
                return payment
        return None

    async def add_payment(
        self,
        payment: InvoicePayment,
    ) -> InvoicePayment:
        payment.id = self.store.new_id()
        self.store.payments.append(
            payment,
        )
        return payment

    async def delete_payment(
        self,
        payment: InvoicePayment,
    ) -> None:
        self.store.payments.remove(
            payment,
        )

    async def flush(self) -> None:
        pass

    async def add_items(
        self,
        items: list[InvoiceItem],
    ) -> None:
        for item in items:
            item.id = self.store.new_id()
        self.store.items += items

    async def commit(self) -> None:
        self.store.commits += 1


class FakeSuppliers:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def get(
        self,
        supplier_id: int,
    ) -> Supplier | None:
        return self.store.suppliers.get(
            supplier_id,
        )

    async def get_by_inn(
        self,
        inn: str,
    ) -> Supplier | None:
        for supplier in self.store.suppliers.values():
            if supplier.inn == inn:
                return supplier
        return None

    async def search_by_name(
        self,
        name: str,
        only_without_inn: bool,
        limit: int,
    ) -> list[Supplier]:
        return [
            supplier
            for supplier in self.store.suppliers.values()
            if name.lower() in supplier.name.lower()
            and not (only_without_inn and supplier.inn is not None)
        ][:limit]

    async def search(
        self,
        query: str | None,
        limit: int,
    ) -> list[Supplier]:
        found = [
            supplier
            for supplier in self.store.suppliers.values()
            if not query
            or query.lower() in supplier.name.lower()
            or (
                query.isdigit()
                and supplier.inn is not None
                and supplier.inn.startswith(
                    query,
                )
            )
        ]
        found.sort(
            key=lambda supplier: (supplier.name, supplier.id),
        )
        return found[:limit]

    async def list_all(self) -> list[Supplier]:
        return sorted(
            self.store.suppliers.values(),
            key=lambda supplier: (supplier.name, supplier.id),
        )

    async def rank_by_aliases(
        self,
        aliases: Collection[str],
        only_without_inn: bool,
        limit: int,
    ) -> list[tuple[Supplier, int]]:
        ranked = []
        for supplier in self.store.suppliers.values():
            if only_without_inn and supplier.inn is not None:
                continue
            matched = {
                alias.alias_normalized
                for alias in self.store.aliases
                if alias.supplier_id == supplier.id
                and alias.alias_normalized in aliases
            }
            if matched:
                ranked.append(
                    (
                        supplier,
                        len(
                            matched,
                        ),
                    ),
                )
        ranked.sort(
            key=lambda row: -row[1],
        )
        return ranked[:limit]

    async def create(
        self,
        supplier: Supplier,
    ) -> Supplier:
        supplier.id = self.store.new_id()
        self.store.suppliers[supplier.id] = supplier
        return supplier


class FakeProducts:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def get(
        self,
        product_id: int,
    ) -> Product | None:
        return self.store.products.get(
            product_id,
        )

    async def create(
        self,
        product: Product,
    ) -> Product:
        product.id = self.store.new_id()
        self.store.products[product.id] = product
        return product

    async def add_alias(
        self,
        alias: ProductAlias,
    ) -> ProductAlias:
        alias.id = self.store.new_id()
        self.store.aliases.append(
            alias,
        )
        return alias

    async def find_by_aliases(
        self,
        supplier_id: int,
        aliases: Collection[str],
    ) -> dict[str, Product]:
        return {
            alias.alias_normalized: self.store.products[alias.product_id]
            for alias in self.store.aliases
            if alias.supplier_id == supplier_id and alias.alias_normalized in aliases
        }

    async def aliases_of(
        self,
        supplier_id: int,
    ) -> list[tuple[str, Product]]:
        return [
            (alias.alias_normalized, self.store.products[alias.product_id])
            for alias in self.store.aliases
            if alias.supplier_id == supplier_id
        ]

    async def search(
        self,
        supplier_id: int,
        query: str | None,
        key: str | None,
        limit: int,
    ) -> list[ProductRow]:
        found = [
            product
            for product in self.store.products.values()
            if product.supplier_id == supplier_id
            and (
                not query
                or query.lower() in product.name.lower()
                or any(
                    key is not None and key in alias.alias_normalized
                    for alias in self.store.aliases
                    if alias.product_id == product.id
                )
            )
        ]
        found.sort(
            key=lambda product: (product.name, product.id),
        )
        return [
            ProductRow(
                product=product,
                # items are appended as invoices are posted, the last one is the newest
                last_item=next(
                    (
                        item
                        for item in reversed(
                            self.store.items,
                        )
                        if item.product_id == product.id
                    ),
                    None,
                ),
            )
            for product in found[:limit]
        ]

    async def last_cost_prices(
        self,
        product_ids: Collection[int],
    ) -> dict[int, Decimal]:
        costs: dict[int, Decimal] = {}
        # items are appended as invoices are posted, the last one wins
        for item in self.store.items:
            if item.product_id in product_ids:
                costs[item.product_id] = item.cost_price
        return costs

    async def catalog(self) -> list[CatalogRow]:
        products = sorted(
            self.store.products.values(),
            key=lambda product: (product.name, product.id),
        )
        return [
            CatalogRow(
                product=product,
                last_item=next(
                    (
                        item
                        for item in reversed(
                            self.store.items,
                        )
                        if item.product_id == product.id
                    ),
                    None,
                ),
                aliases=[
                    alias
                    for alias in self.store.aliases
                    if alias.product_id == product.id
                ],
            )
            for product in products
        ]


class FakeLedger:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def lock(self) -> None:
        self.store.locks += 1
        self.store.events.append(
            "lock",
        )

    async def create(
        self,
        entry: LedgerEntry,
    ) -> LedgerEntry:
        entry.id = self.store.new_id()
        # the column defaults are applied on flush, there is none here
        if entry.occurred_on is None:
            entry.occurred_on = today()
        if entry.cash is None:
            entry.cash = Decimal(
                value=0,
            )
        self.store.entries.append(
            entry,
        )
        return entry

    async def add_revaluation_items(
        self,
        items: list[RevaluationItem],
    ) -> None:
        for item in items:
            item.id = self.store.new_id()
        self.store.revaluations += items

    async def revaluation_items_of(
        self,
        entry_id: int,
    ) -> list[RevaluationItem]:
        items = [
            item for item in self.store.revaluations if item.ledger_entry_id == entry_id
        ]
        # what selectinload brings in the real repository
        for item in items:
            item.product = self.store.products[item.product_id]
        return items

    async def sums_by_kind(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        return self.sums(
            field="amount",
            date_from=date_from,
            date_to=date_to,
        )

    async def cash_sums_by_kind(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        return self.sums(
            field="cash",
            date_from=date_from,
            date_to=date_to,
        )

    def sums(
        self,
        field: str,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        sums: dict[LedgerKind, Decimal] = {}
        for entry in self.store.entries:
            if date_from <= entry.occurred_on <= date_to:
                sums[entry.kind] = sums.get(
                    entry.kind,
                    Decimal(
                        value=0,
                    ),
                ) + getattr(
                    entry,
                    field,
                )
        return sums

    async def get(
        self,
        entry_id: int,
    ) -> LedgerEntry | None:
        for entry in self.store.entries:
            if entry.id == entry_id:
                return entry
        return None

    async def get_for_invoice(
        self,
        invoice_id: int,
    ) -> LedgerEntry | None:
        for entry in self.store.entries:
            if entry.invoice_id == invoice_id:
                return entry
        return None

    async def balance(
        self,
        on: date | None = None,
    ) -> Decimal:
        return self.total(
            field="amount",
            on=on,
        )

    async def cash_balance(
        self,
        on: date | None = None,
    ) -> Decimal:
        return self.total(
            field="cash",
            on=on,
        )

    def total(
        self,
        field: str,
        on: date | None,
    ) -> Decimal:
        return sum(
            (
                getattr(
                    entry,
                    field,
                )
                for entry in self.store.entries
                if on is None or entry.occurred_on <= on
            ),
            start=Decimal(
                value=0,
            ),
        )

    async def is_reversed(
        self,
        entry_id: int,
    ) -> bool:
        return any(
            (entry.reverses_id == entry_id for entry in self.store.entries),
        )

    def in_force(
        self,
        entry: LedgerEntry,
        kind: LedgerKind,
    ) -> bool:
        return (
            entry.kind == kind
            and entry.reverses_id is None
            and not any(
                (other.reverses_id == entry.id for other in self.store.entries),
            )
        )

    async def last_count_on(
        self,
        kind: LedgerKind,
    ) -> date | None:
        dates = [
            entry.occurred_on
            for entry in self.store.entries
            if self.in_force(
                entry=entry,
                kind=kind,
            )
        ]
        return max(
            dates,
            default=None,
        )

    async def has_count_after(
        self,
        entry: LedgerEntry,
        kind: LedgerKind,
    ) -> bool:
        return any(
            self.in_force(
                entry=other,
                kind=kind,
            )
            and (other.occurred_on, other.id) > (entry.occurred_on, entry.id)
            for other in self.store.entries
        )

    async def history(
        self,
        limit: int | None,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        newest_first: bool = True,
    ) -> list[LedgerRow]:
        ordered = sorted(
            self.store.entries,
            key=lambda entry: (entry.occurred_on, entry.id),
        )
        rows = []
        balance = Decimal(
            value=0,
        )
        cash = Decimal(
            value=0,
        )
        for entry in ordered:
            balance += entry.amount
            cash += entry.cash
            invoice = None
            if entry.invoice_id is not None:
                invoice = self.store.invoices.get(
                    entry.invoice_id,
                )
            supplier = None
            if invoice is not None and invoice.supplier_id is not None:
                supplier = self.store.suppliers.get(
                    invoice.supplier_id,
                )
            reversals = [
                other.id
                for other in self.store.entries
                if other.reverses_id == entry.id
            ]
            rows.append(
                LedgerRow(
                    entry=entry,
                    balance_after=balance,
                    cash_after=cash,
                    reversed_by_id=reversals[0] if reversals else None,
                    invoice_number=invoice.invoice_number if invoice else None,
                    supplier_name=supplier.name if supplier else None,
                    supplier_short_name=supplier.short_name if supplier else None,
                ),
            )
        rows = [
            row
            for row in rows
            if (date_from is None or row.entry.occurred_on >= date_from)
            and (date_to is None or row.entry.occurred_on <= date_to)
        ]
        if newest_first:
            rows.reverse()
        return rows[offset : None if limit is None else offset + limit]
