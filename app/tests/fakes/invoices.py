from collections.abc import Collection
from datetime import UTC, date, datetime
from decimal import Decimal

from core.enums import InvoiceSort, InvoiceStatus
from invoices.models import Invoice, InvoiceItem, InvoicePayment
from invoices.repository import DebtRow, InvoiceRow
from tests.fakes.ledger import FakeLedger
from tests.fakes.store import ZERO, FakeStore


def _debt(row: InvoiceRow) -> Decimal | None:
    return None if row.cost_total is None else row.cost_total - row.paid


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
