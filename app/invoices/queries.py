from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.enums import InvoiceSort, InvoiceStatus
from invoices.models import Invoice
from invoices.repository import InvoiceRepository, InvoiceRepositoryDep
from invoices.schemas import (
    InvoiceList,
    InvoiceListItem,
    PaymentOut,
    PostedInvoice,
    PostedLine,
)
from ledger.repository import LedgerRepositoryDep
from products.pricing import retail_price_total
from suppliers.service import supplier_summary


class InvoiceQueryService:
    def __init__(
        self,
        invoices: InvoiceRepositoryDep,
        ledger: LedgerRepositoryDep,
    ) -> None:
        self.invoices = invoices
        self.ledger = ledger

    async def list_invoices(
        self,
        status: InvoiceStatus | None,
        unpaid: bool,
        query: str | None,
        sort: InvoiceSort,
        limit: int,
        offset: int,
    ) -> InvoiceList:
        # one row more tells whether there is another page
        rows = await self.invoices.search(
            status=status,
            unpaid=unpaid,
            query=query,
            sort=sort,
            limit=limit + 1,
            offset=offset,
        )
        return InvoiceList(
            items=[
                InvoiceListItem(
                    id=row.invoice.id,
                    status=row.invoice.status,
                    invoice_number=row.invoice.invoice_number,
                    invoice_date=row.invoice.invoice_date,
                    supplier_name=row.supplier_name,
                    retail_total=row.retail_total,
                    debt=(
                        None if row.cost_total is None else row.cost_total - row.paid
                    ),
                    lines=row.lines,
                    created_at=row.invoice.created_at,
                )
                for row in rows[:limit]
            ],
            has_more=len(rows) > limit,
        )

    async def get_posted(
        self,
        invoice_id: int,
    ) -> PostedInvoice:
        invoice = await self.invoices.get_confirmed(
            invoice_id=invoice_id,
        )
        entry = await self.ledger.get_for_invoice(
            invoice_id=invoice_id,
        )
        if invoice is None or entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проведённая накладная не найдена",
            )
        supplier = invoice.supplier
        if (
            supplier is None
            or invoice.invoice_number is None
            or invoice.invoice_date is None
        ):
            raise RuntimeError(
                "a confirmed invoice has a supplier, a number and a date",
            )
        items = sorted(
            invoice.items,
            key=lambda item: item.id,
        )
        cost_total = sum(
            (item.cost_price_total for item in items),
            start=Decimal(
                value=0,
            ),
        )
        payments = await self.invoices.payments_of(
            invoice_id=invoice.id,
        )
        paid = sum(
            (payment.amount for payment in payments),
            start=Decimal(
                value=0,
            ),
        )
        return PostedInvoice(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            supplier=supplier_summary(
                supplier=supplier,
            ),
            lines=[
                PostedLine(
                    line_no=item.line_no,
                    name=item.name,
                    product_name=item.product.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    vat_percent=item.vat_percent,
                    base_price=item.base_price,
                    cost_price=item.cost_price,
                    cost_price_total=item.cost_price_total,
                    markup_pct=item.markup_pct,
                    retail_price=item.retail_price,
                    retail_price_total=retail_price_total(
                        retail_price=item.retail_price,
                        quantity=item.quantity,
                    ),
                )
                for item in items
            ],
            cost_total=cost_total,
            retail_total=entry.amount,
            ledger_entry_id=entry.id,
            paid=paid,
            debt=cost_total - paid,
            payments=[
                PaymentOut(
                    id=payment.id,
                    paid_on=payment.paid_on,
                    amount=payment.amount,
                    comment=payment.comment,
                )
                for payment in payments
            ],
        )


InvoiceQueryServiceDep = Annotated[
    InvoiceQueryService,
    Depends(
        dependency=InvoiceQueryService,
    ),
]


async def get_draft_invoice(
    invoices: InvoiceRepository,
    invoice_id: int,
) -> Invoice:
    draft_invoice = await invoices.get_draft(
        invoice_id=invoice_id,
    )
    if draft_invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Черновик накладной не найден",
        )
    return draft_invoice
