from enum import StrEnum


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class InvoiceSort(StrEnum):
    # the newest uploads first
    NEWEST = "newest"
    # the biggest debt first, the invoices without one at the end
    DEBT = "debt"


class LedgerKind(StrEnum):
    INVOICE = "invoice"
    SALE = "sale"
    WRITE_OFF = "write_off"
    STOCKTAKE = "stocktake"
    REVALUATION = "revaluation"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    CASH_COUNT = "cash_count"
