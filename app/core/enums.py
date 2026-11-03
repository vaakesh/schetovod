from enum import StrEnum


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    # a confirmed invoice cancelled by a reversal in the ledger, it stays for the history
    REVERSED = "reversed"


class OrderStatus(StrEnum):
    # the one cart being filled, until the user confirms it
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class InvoiceSort(StrEnum):
    # the newest uploads first
    NEWEST = "newest"
    # the biggest debt first, the invoices without one at the end
    DEBT = "debt"


class ReceiptKind(StrEnum):
    SALE = "sale"
    REFUND = "refund"


class ExpenseBasis(StrEnum):
    # the amount is rubles for a month or for a year
    MONTH = "month"
    YEAR = "year"
    # rubles for every day with sales
    WORK_DAY = "work_day"
    # the amount is a percent of the takings
    REVENUE_PERCENT = "revenue_percent"
    CARD_PERCENT = "card_percent"


class LedgerKind(StrEnum):
    INVOICE = "invoice"
    SALE = "sale"
    WRITE_OFF = "write_off"
    STOCK_IN = "stock_in"
    STOCKTAKE = "stocktake"
    REVALUATION = "revaluation"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    CASH_COUNT = "cash_count"
