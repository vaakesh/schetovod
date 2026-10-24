from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from typing import Annotated

from fastapi import Depends

from core.enums import LedgerKind
from core.http import invalid
from invoices.repository import InvoiceRepositoryDep
from ledger.repository import LedgerRepositoryDep, LedgerRow
from ledger.service import entry_supplier_name, ledger_entry_out
from reports.schemas import (
    CashNote,
    LedgerReport,
    PeriodReport,
    ReportDay,
    ReportInvoice,
    SupplierDebt,
)


class ReportService:
    def __init__(
        self,
        ledger: LedgerRepositoryDep,
        invoices: InvoiceRepositoryDep,
    ) -> None:
        self.ledger = ledger
        self.invoices = invoices

    async def report(
        self,
        date_from: date,
        date_to: date,
    ) -> LedgerReport:
        if date_from > date_to:
            invalid(
                detail="Начало периода позже его конца",
            )
        sums = await self.ledger.sums_by_kind(
            date_from=date_from,
            date_to=date_to,
        )
        cash_sums = await self.ledger.cash_sums_by_kind(
            date_from=date_from,
            date_to=date_to,
        )
        zero = Decimal(
            value=0,
        )
        day_before = date_from - timedelta(
            days=1,
        )
        sales = sums.get(
            LedgerKind.SALE,
            zero,
        )
        sales_cash = cash_sums.get(
            LedgerKind.SALE,
            zero,
        )
        rows = await self.ledger.history(
            limit=None,
            offset=0,
            date_from=date_from,
            date_to=date_to,
            newest_first=False,
        )
        return LedgerReport(
            date_from=date_from,
            date_to=date_to,
            opening=await self.ledger.balance(
                on=day_before,
            ),
            invoices=sums.get(
                LedgerKind.INVOICE,
                zero,
            ),
            sales=sales,
            write_offs=sums.get(
                LedgerKind.WRITE_OFF,
                zero,
            ),
            stocktakes=sums.get(
                LedgerKind.STOCKTAKE,
                zero,
            ),
            revaluations=sums.get(
                LedgerKind.REVALUATION,
                zero,
            ),
            closing=await self.ledger.balance(
                on=date_to,
            ),
            cash_opening=await self.ledger.cash_balance(
                on=day_before,
            ),
            sales_cash=sales_cash,
            # the sales are negative, they take the stock out
            sales_card=-sales - sales_cash,
            cash_ins=cash_sums.get(
                LedgerKind.CASH_IN,
                zero,
            ),
            cash_outs=cash_sums.get(
                LedgerKind.CASH_OUT,
                zero,
            ),
            cash_counts=cash_sums.get(
                LedgerKind.CASH_COUNT,
                zero,
            ),
            cash_closing=await self.ledger.cash_balance(
                on=date_to,
            ),
            entries=[
                ledger_entry_out(
                    row=row,
                    short_names=True,
                )
                for row in rows
            ],
        )

    async def period_report(
        self,
        date_from: date,
        date_to: date,
    ) -> PeriodReport:
        """the period day by day with the invoices and what is owed for them"""
        if date_from > date_to:
            invalid(
                detail="Начало периода позже его конца",
            )
        day_before = date_from - timedelta(
            days=1,
        )
        rows = await self.ledger.history(
            limit=None,
            offset=0,
            date_from=date_from,
            date_to=date_to,
            newest_first=False,
        )
        invoice_ids = [
            row.entry.invoice_id for row in rows if row.entry.invoice_id is not None
        ]
        cost_totals = await self.invoices.cost_totals(
            invoice_ids=invoice_ids,
        )
        paid_totals = await self.invoices.paid_totals(
            invoice_ids=invoice_ids,
            on=date_to,
        )
        return PeriodReport(
            date_from=date_from,
            date_to=date_to,
            opening=await self.ledger.balance(
                on=day_before,
            ),
            cash_opening=await self.ledger.cash_balance(
                on=day_before,
            ),
            days=[
                _report_day(
                    day=day,
                    rows=list(
                        day_rows,
                    ),
                    cost_totals=cost_totals,
                    paid_totals=paid_totals,
                )
                for day, day_rows in groupby(
                    rows,
                    key=lambda row: row.entry.occurred_on,
                )
            ],
            paid_in_period=await self.invoices.paid_between(
                date_from=date_from,
                date_to=date_to,
            ),
            debts=[
                SupplierDebt(
                    supplier_name=debt.supplier_short_name or debt.supplier_name,
                    invoice_number=debt.invoice.invoice_number or "",
                    invoice_date=debt.invoice.invoice_date,
                    cost_total=debt.cost_total,
                    paid=debt.paid,
                    debt=debt.cost_total - debt.paid,
                )
                for debt in await self.invoices.debts(
                    on=date_to,
                )
            ],
        )


ReportServiceDep = Annotated[
    ReportService,
    Depends(
        dependency=ReportService,
    ),
]


def _report_day(
    day: date,
    rows: list[LedgerRow],
    cost_totals: dict[int, Decimal],
    paid_totals: dict[int, Decimal],
) -> ReportDay:
    """the entries of one day in the ledger order, a reversal cancels its entry in the sums"""
    zero = Decimal(
        value=0,
    )
    invoices: list[ReportInvoice] = []
    sales = zero
    sales_cash = zero
    cash_moves = zero
    cash_notes: list[CashNote] = []
    for row in rows:
        entry = row.entry
        if entry.kind == LedgerKind.INVOICE and entry.invoice_id is not None:
            invoices.append(
                ReportInvoice(
                    supplier_name=entry_supplier_name(
                        row=row,
                    )
                    or "",
                    invoice_number=row.invoice_number or "",
                    cost_total=cost_totals.get(
                        entry.invoice_id,
                        zero,
                    ),
                    retail_total=entry.amount,
                    paid=paid_totals.get(
                        entry.invoice_id,
                        zero,
                    ),
                ),
            )
        elif entry.kind == LedgerKind.SALE:
            # a sale takes the stock out, its amount is negative
            sales -= entry.amount
            sales_cash += entry.cash
        elif entry.kind in (
            LedgerKind.CASH_IN,
            LedgerKind.CASH_OUT,
            LedgerKind.CASH_COUNT,
        ):
            cash_moves += entry.cash
            if entry.reverses_id is None and row.reversed_by_id is None:
                cash_notes.append(
                    CashNote(
                        kind=entry.kind,
                        cash=entry.cash,
                        comment=entry.comment,
                    ),
                )
    last = rows[-1]
    return ReportDay(
        day=day,
        invoices=invoices,
        sales_cash=sales_cash,
        sales_card=sales - sales_cash,
        cash_moves=cash_moves,
        cash_notes=cash_notes,
        cash_after=last.cash_after,
        balance_after=last.balance_after,
    )
