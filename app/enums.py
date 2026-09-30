from enum import StrEnum


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class LedgerKind(StrEnum):
    INVOICE = "invoice"
    SALE = "sale"
    WRITE_OFF = "write_off"
    STOCKTAKE = "stocktake"
    REVALUATION = "revaluation"
