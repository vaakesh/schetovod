from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.config import today
from core.http import invalid
from invoices.models import InvoicePayment
from invoices.queries import InvoiceQueryServiceDep
from invoices.repository import InvoiceRepositoryDep
from invoices.schemas import PaymentCreate, PostedInvoice


class InvoicePaymentService:
    def __init__(
        self,
        invoices: InvoiceRepositoryDep,
        queries: InvoiceQueryServiceDep,
    ) -> None:
        self.invoices = invoices
        self.queries = queries

    async def add_payment(
        self,
        invoice_id: int,
        payload: PaymentCreate,
    ) -> PostedInvoice:
        """a part or the rest of what is owed to the supplier, the till is not touched"""
        invoice = await self.invoices.lock_confirmed(
            invoice_id=invoice_id,
        )
        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проведённая накладная не найдена",
            )
        if payload.paid_on > today():
            invalid(
                detail="Дата оплаты не может быть в будущем",
            )
        cost_totals = await self.invoices.cost_totals(
            invoice_ids=[
                invoice.id,
            ],
        )
        paid_totals = await self.invoices.paid_totals(
            invoice_ids=[
                invoice.id,
            ],
            on=None,
        )
        zero = Decimal(
            value=0,
        )
        debt = cost_totals.get(
            invoice.id,
            zero,
        ) - paid_totals.get(
            invoice.id,
            zero,
        )
        if payload.amount > debt:
            invalid(
                detail=f"Оплата больше долга по накладной, осталось {debt} ₽",
            )
        await self.invoices.add_payment(
            payment=InvoicePayment(
                invoice_id=invoice.id,
                paid_on=payload.paid_on,
                amount=payload.amount,
                comment=payload.comment,
            ),
        )
        await self.invoices.commit()
        return await self.queries.get_posted(
            invoice_id=invoice.id,
        )

    async def delete_payment(
        self,
        invoice_id: int,
        payment_id: int,
    ) -> PostedInvoice:
        """a payment entered by mistake, nothing else depends on it"""
        payment = await self.invoices.get_payment(
            invoice_id=invoice_id,
            payment_id=payment_id,
        )
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Оплата не найдена",
            )
        await self.invoices.delete_payment(
            payment=payment,
        )
        await self.invoices.commit()
        return await self.queries.get_posted(
            invoice_id=invoice_id,
        )


InvoicePaymentServiceDep = Annotated[
    InvoicePaymentService,
    Depends(
        dependency=InvoicePaymentService,
    ),
]
