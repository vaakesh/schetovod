from decimal import Decimal

from pydantic import (
    BaseModel,
)

from core.enums import LedgerKind
from core.schema_types import OutputDate
from ledger.schemas import LedgerEntryOut


class LedgerReport(BaseModel):
    date_from: OutputDate
    date_to: OutputDate
    # stock at retail prices at the end of the day before the period
    opening: Decimal
    # signed stock sums of the period by kind, a reversal counts with the kind it cancels
    invoices: Decimal
    sales: Decimal
    write_offs: Decimal
    stocktakes: Decimal
    revaluations: Decimal
    # stock at retail prices at the end of the last day
    closing: Decimal
    # cash in the till at the end of the day before the period
    cash_opening: Decimal
    # the sales split into what went into the till and what went to the bank account
    sales_cash: Decimal
    sales_card: Decimal
    # signed cash sums of the period by kind
    cash_ins: Decimal
    cash_outs: Decimal
    cash_counts: Decimal
    # cash in the till at the end of the last day
    cash_closing: Decimal
    # in the ledger order
    entries: list[LedgerEntryOut]


class ReportInvoice(BaseModel):
    supplier_name: str
    invoice_number: str
    # owed to the supplier
    cost_total: Decimal
    # the inflow at retail prices
    retail_total: Decimal
    # paid by the end of the period
    paid: Decimal


class CashNote(BaseModel):
    kind: LedgerKind
    # signed, positive brings cash into the till
    cash: Decimal
    comment: str | None


class ReportDay(BaseModel):
    day: OutputDate
    invoices: list[ReportInvoice]
    sales_cash: Decimal
    sales_card: Decimal
    # signed, the cash ins, the cash outs and the cash counts of the day
    cash_moves: Decimal
    # what each of them was, the reversed ones and the reversals are left out
    cash_notes: list[CashNote]
    # the balances at the end of the day
    cash_after: Decimal
    balance_after: Decimal


class SupplierDebt(BaseModel):
    supplier_name: str
    invoice_number: str
    # a confirmed invoice always has it
    invoice_date: OutputDate | None
    cost_total: Decimal
    paid: Decimal
    debt: Decimal


class PeriodReport(BaseModel):
    """the period day by day, for the printed report"""

    date_from: OutputDate
    date_to: OutputDate
    # the balances at the end of the day before the period
    opening: Decimal
    cash_opening: Decimal
    # only the days with entries
    days: list[ReportDay]
    # paid to the suppliers on the days of the period, for any invoices
    paid_in_period: Decimal
    # unpaid at the end of the period
    debts: list[SupplierDebt]
