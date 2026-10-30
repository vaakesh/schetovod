from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from core.schema_types import FormModel, InvoiceDate, OutputDate


class AqsiModel(BaseModel):
    """the fields of an aQsi response that are used, the rest is ignored"""

    model_config = ConfigDict(
        alias_generator=to_camel,
    )


class AqsiShiftRow(AqsiModel):
    id: UUID


class AqsiShiftPage(AqsiModel):
    rows: list[AqsiShiftRow]
    pages: int


# the sums of aQsi are in kopecks
class AqsiCounters(AqsiModel):
    total: int
    cash: int
    cashless: int
    prepayment: int
    credit: int
    consideration: int


class AqsiCorrectionCounters(AqsiModel):
    income: AqsiCounters
    income_refund: AqsiCounters
    expense: AqsiCounters
    expense_refund: AqsiCounters


class AqsiShiftCounters(AqsiModel):
    income: AqsiCounters
    income_refund: AqsiCounters
    expense: AqsiCounters
    expense_refund: AqsiCounters
    corrections: AqsiCorrectionCounters


class AqsiOpenedReport(AqsiModel):
    # a time without its zone can not be placed on a day of the shop
    date_time: AwareDatetime


class AqsiClosedReport(AqsiModel):
    shift_counters: AqsiShiftCounters


class AqsiShift(AqsiModel):
    id: UUID
    number: int
    shift_opened_report: AqsiOpenedReport | None = None
    shift_closed_report: AqsiClosedReport | None = None


class ShiftImportCreate(FormModel):
    date_from: InvoiceDate
    date_to: InvoiceDate


class ImportedShift(BaseModel):
    entry_id: int
    shift_number: int
    occurred_on: OutputDate
    cash: Decimal
    card: Decimal


class SkippedShift(BaseModel):
    shift_number: int
    occurred_on: OutputDate | None
    reason: str


class ShiftImportResult(BaseModel):
    imported: list[ImportedShift]
    skipped: list[SkippedShift]
