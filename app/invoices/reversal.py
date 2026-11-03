from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.enums import InvoiceStatus, LedgerKind
from core.http import conflict
from invoices.extraction import InvoiceExtraction
from invoices.forms import posted_form
from invoices.models import Invoice
from invoices.repository import InvoiceRepository, InvoiceRepositoryDep
from invoices.schemas import ReversedInvoice
from ledger.models import LedgerEntry
from ledger.repository import LedgerRepository, LedgerRepositoryDep
from ledger.service import reverse_entry


async def reverse_block(
    invoices: InvoiceRepository,
    ledger: LedgerRepository,
    invoice: Invoice,
    entry: LedgerEntry,
) -> str | None:
    """why the posting of the invoice can not be cancelled now"""
    if invoice.status == InvoiceStatus.REVERSED:
        return "Накладная уже сторнирована"
    # the stock counted after the invoice already holds its goods
    if await ledger.has_count_after(
        entry=entry,
        kind=LedgerKind.STOCKTAKE,
    ):
        return "После накладной был переучёт, сторнировать её уже нельзя"
    paid = sum(
        (
            payment.amount
            for payment in await invoices.payments_of(
                invoice_id=invoice.id,
            )
        ),
        start=Decimal(
            value=0,
        ),
    )
    # a draft has no payments, so they would have nowhere to go
    if paid > 0:
        return f"По накладной есть оплаты на {paid:.2f} ₽, сначала удалите их"
    return None


class InvoiceReversalService:
    def __init__(
        self,
        invoices: InvoiceRepositoryDep,
        ledger: LedgerRepositoryDep,
    ) -> None:
        self.invoices = invoices
        self.ledger = ledger

    async def reverse_invoice(
        self,
        invoice_id: int,
        copy_to_draft: bool,
    ) -> ReversedInvoice:
        """cancels the inflow and the revaluation of the invoice, the catalog stays as it is"""
        await self.ledger.lock()
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
        blocked = await reverse_block(
            invoices=self.invoices,
            ledger=self.ledger,
            invoice=invoice,
            entry=entry,
        )
        if blocked is not None:
            conflict(
                detail=blocked,
            )
        # the old stock goes back to the shelf price it had before the invoice
        for revaluation in await self.ledger.revaluations_of_invoice(
            invoice_id=invoice.id,
        ):
            if await self.ledger.is_reversed(
                entry_id=revaluation.id,
            ):
                continue
            await reverse_entry(
                ledger=self.ledger,
                entry=revaluation,
            )

        # the foreign key carries the status over to the posting in the database
        invoice.status = InvoiceStatus.REVERSED
        entry.invoice_status = InvoiceStatus.REVERSED
        await self.invoices.flush()
        reversal = await reverse_entry(
            ledger=self.ledger,
            entry=entry,
        )

        draft_id = None
        if copy_to_draft:
            extraction = InvoiceExtraction.model_validate(
                obj=invoice.extracted,
            )
            draft = await self.invoices.create(
                invoice=Invoice(
                    supplier_id=invoice.supplier_id,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    status=InvoiceStatus.DRAFT,
                    extracted=invoice.extracted,
                    form=posted_form(
                        invoice=invoice,
                        extraction=extraction,
                    ).model_dump(
                        mode="json",
                    ),
                ),
            )
            draft_id = draft.id
        balance = await self.ledger.balance()
        await self.invoices.commit()
        return ReversedInvoice(
            id=invoice.id,
            reversal_entry_id=reversal.id,
            draft_id=draft_id,
            balance=balance,
        )


InvoiceReversalServiceDep = Annotated[
    InvoiceReversalService,
    Depends(
        dependency=InvoiceReversalService,
    ),
]
