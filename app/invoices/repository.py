from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import ScalarSelect, case, func, or_, select
from sqlalchemy.orm import selectinload

from core.db import SessionDep
from core.enums import InvoiceSort, InvoiceStatus
from invoices.models import Invoice, InvoiceItem, InvoicePayment
from ledger.models import LedgerEntry
from suppliers.models import Supplier


@dataclass
class InvoiceRow:
    invoice: Invoice
    # the chosen supplier, or the name the model read while there is none
    supplier_name: str | None
    # None until the invoice is confirmed
    retail_total: Decimal | None
    lines: int
    # owed to the supplier, None until the invoice is confirmed
    cost_total: Decimal | None
    paid: Decimal


@dataclass
class DebtRow:
    invoice: Invoice
    supplier_name: str
    supplier_short_name: str | None
    cost_total: Decimal
    paid: Decimal


class InvoiceRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def create(
        self,
        invoice: Invoice,
    ) -> Invoice:
        self.session.add(
            instance=invoice,
        )
        await self.session.flush()
        return invoice

    async def get_draft(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        # the row lock keeps a save or a decline from overwriting a draft confirmed meanwhile,
        # after the wait the status is checked again and a confirmed invoice is not found
        return await self.session.scalar(
            statement=select(
                Invoice,
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.status == InvoiceStatus.DRAFT,
            )
            .with_for_update(),
        )

    async def find_confirmed(
        self,
        supplier_id: int,
        invoice_number: str,
        invoice_date: date,
    ) -> Invoice | None:
        return await self.session.scalar(
            statement=select(
                Invoice,
            ).where(
                Invoice.supplier_id == supplier_id,
                Invoice.invoice_number == invoice_number,
                Invoice.invoice_date == invoice_date,
                Invoice.status == InvoiceStatus.CONFIRMED,
            ),
        )

    async def search(
        self,
        status: InvoiceStatus | None,
        unpaid: bool,
        query: str | None,
        sort: InvoiceSort,
        limit: int,
        offset: int,
    ) -> list[InvoiceRow]:
        """the supplier is searched by name and the invoice by number,
        unpaid leaves the confirmed invoices with a debt"""
        # a draft without a chosen supplier shows the name the model read
        supplier_name = func.coalesce(
            Supplier.name,
            Invoice.extracted["supplier"]["name"].astext,
        )
        lines = func.jsonb_array_length(
            func.coalesce(
                Invoice.form["lines"],
                Invoice.extracted["items"],
            ),
        )
        cost_total = _cost_total()
        paid = _paid_total(
            on=None,
        )
        # only a confirmed invoice owes anything
        debt = case(
            (
                Invoice.status == InvoiceStatus.CONFIRMED,
                cost_total - paid,
            ),
            else_=None,
        )
        order = (
            Invoice.created_at.desc(),
            Invoice.id.desc(),
        )
        if sort == InvoiceSort.DEBT:
            order = (
                debt.desc().nulls_last(),
                *order,
            )
        statement = (
            select(
                Invoice,
                supplier_name,
                LedgerEntry.amount,
                lines,
                cost_total,
                paid,
            )
            .outerjoin(
                target=Supplier,
                onclause=Supplier.id == Invoice.supplier_id,
            )
            .outerjoin(
                target=LedgerEntry,
                onclause=LedgerEntry.invoice_id == Invoice.id,
            )
            .order_by(
                *order,
            )
            .limit(
                limit=limit,
            )
            .offset(
                offset=offset,
            )
        )
        if unpaid:
            statement = statement.where(
                debt > 0,
            )
        if status is not None:
            statement = statement.where(
                Invoice.status == status,
            )
        if query:
            statement = statement.where(
                or_(
                    supplier_name.icontains(
                        other=query,
                        autoescape=True,
                    ),
                    Invoice.invoice_number.icontains(
                        other=query,
                        autoescape=True,
                    ),
                ),
            )
        result = await self.session.execute(
            statement=statement,
        )
        return [
            InvoiceRow(
                invoice=invoice,
                supplier_name=name,
                retail_total=amount,
                lines=count,
                # a draft has no lines yet, its sum would be the sum of nothing
                cost_total=cost if invoice.status == InvoiceStatus.CONFIRMED else None,
                paid=paid,
            )
            for invoice, name, amount, count, cost, paid in result.tuples()
        ]

    async def get_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        """with the supplier and the lines with their products"""
        return await self.session.scalar(
            statement=select(
                Invoice,
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.status == InvoiceStatus.CONFIRMED,
            )
            .options(
                selectinload(
                    Invoice.supplier,
                ),
                selectinload(
                    Invoice.items,
                ).selectinload(
                    InvoiceItem.product,
                ),
            ),
        )

    async def lock_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        """the row lock keeps two payments from overpaying the invoice together"""
        return await self.session.scalar(
            statement=select(
                Invoice,
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.status == InvoiceStatus.CONFIRMED,
            )
            .with_for_update(),
        )

    async def cost_totals(
        self,
        invoice_ids: Collection[int],
    ) -> dict[int, Decimal]:
        """owed to the supplier for each invoice, the sum of its lines"""
        result = await self.session.execute(
            statement=select(
                InvoiceItem.invoice_id,
                func.sum(
                    InvoiceItem.cost_price_total,
                ),
            )
            .where(
                InvoiceItem.invoice_id.in_(
                    other=invoice_ids,
                ),
            )
            .group_by(
                InvoiceItem.invoice_id,
            ),
        )
        return {invoice_id: total for invoice_id, total in result.tuples()}

    async def paid_totals(
        self,
        invoice_ids: Collection[int],
        on: date | None,
    ) -> dict[int, Decimal]:
        """paid for each invoice up to the end of the day, an unpaid one is missing"""
        statement = (
            select(
                InvoicePayment.invoice_id,
                func.sum(
                    InvoicePayment.amount,
                ),
            )
            .where(
                InvoicePayment.invoice_id.in_(
                    other=invoice_ids,
                ),
            )
            .group_by(
                InvoicePayment.invoice_id,
            )
        )
        if on is not None:
            statement = statement.where(
                InvoicePayment.paid_on <= on,
            )
        result = await self.session.execute(
            statement=statement,
        )
        return {invoice_id: total for invoice_id, total in result.tuples()}

    async def paid_between(
        self,
        date_from: date,
        date_to: date,
    ) -> Decimal:
        """paid to the suppliers on the days, for any invoices"""
        total = await self.session.scalar(
            statement=select(
                func.coalesce(
                    func.sum(
                        InvoicePayment.amount,
                    ),
                    0,
                ),
            ).where(
                InvoicePayment.paid_on >= date_from,
                InvoicePayment.paid_on <= date_to,
            ),
        )
        return Decimal(
            value=total or 0,
        )

    async def debts(
        self,
        on: date,
    ) -> list[DebtRow]:
        """invoices posted by the end of the day and not paid in full by then, the oldest first"""
        cost_total = _cost_total()
        paid = _paid_total(
            on=on,
        )
        result = await self.session.execute(
            statement=select(
                Invoice,
                Supplier.name,
                Supplier.short_name,
                cost_total,
                paid,
            )
            .join(
                target=Supplier,
                onclause=Supplier.id == Invoice.supplier_id,
            )
            .join(
                target=LedgerEntry,
                onclause=LedgerEntry.invoice_id == Invoice.id,
            )
            .where(
                LedgerEntry.occurred_on <= on,
                cost_total > paid,
            )
            .order_by(
                Invoice.invoice_date,
                Invoice.id,
            ),
        )
        return [
            DebtRow(
                invoice=invoice,
                supplier_name=name,
                supplier_short_name=short_name,
                cost_total=cost,
                paid=paid_sum,
            )
            for invoice, name, short_name, cost, paid_sum in result.tuples()
        ]

    async def payments_of(
        self,
        invoice_id: int,
    ) -> list[InvoicePayment]:
        result = await self.session.scalars(
            statement=select(
                InvoicePayment,
            )
            .where(
                InvoicePayment.invoice_id == invoice_id,
            )
            .order_by(
                InvoicePayment.paid_on,
                InvoicePayment.id,
            ),
        )
        return list(
            result,
        )

    async def get_payment(
        self,
        invoice_id: int,
        payment_id: int,
    ) -> InvoicePayment | None:
        return await self.session.scalar(
            statement=select(
                InvoicePayment,
            ).where(
                InvoicePayment.id == payment_id,
                InvoicePayment.invoice_id == invoice_id,
            ),
        )

    async def add_payment(
        self,
        payment: InvoicePayment,
    ) -> InvoicePayment:
        self.session.add(
            instance=payment,
        )
        await self.session.flush()
        return payment

    async def delete_payment(
        self,
        payment: InvoicePayment,
    ) -> None:
        await self.session.delete(
            instance=payment,
        )
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def add_items(
        self,
        items: list[InvoiceItem],
    ) -> None:
        self.session.add_all(
            instances=items,
        )
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()


def _cost_total() -> ScalarSelect[Decimal]:
    """owed to the supplier for the invoice of the outer query, zero without lines"""
    return (
        select(
            func.coalesce(
                func.sum(
                    InvoiceItem.cost_price_total,
                ),
                0,
            ),
        )
        .where(
            InvoiceItem.invoice_id == Invoice.id,
        )
        .scalar_subquery()
    )


def _paid_total(on: date | None) -> ScalarSelect[Decimal]:
    """paid for the invoice of the outer query up to the end of the day, or ever"""
    statement = select(
        func.coalesce(
            func.sum(
                InvoicePayment.amount,
            ),
            0,
        ),
    ).where(
        InvoicePayment.invoice_id == Invoice.id,
    )
    if on is not None:
        statement = statement.where(
            InvoicePayment.paid_on <= on,
        )
    return statement.scalar_subquery()


InvoiceRepositoryDep = Annotated[
    InvoiceRepository,
    Depends(
        dependency=InvoiceRepository,
    ),
]
