from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from core.schema_types import FormModel, InvoiceDate, OutputDate


class ReceiptImportCreate(FormModel):
    date_from: InvoiceDate
    date_to: InvoiceDate


class ReceiptImportResult(BaseModel):
    # the sales and the refunds aQsi returned for the period
    received: int
    loaded: int
    present: int


class TrafficSummary(BaseModel):
    receipts: int
    # the days with at least one sale
    days: int
    per_day: float | None
    revenue: Decimal
    average_check: Decimal | None
    peak_hour: int | None
    peak_weekday: int | None


class HourLoad(BaseModel):
    hour: int
    receipts: float
    average_check: Decimal | None


class WeekdayLoad(BaseModel):
    # monday is 0
    weekday: int
    days: int
    receipts: float
    average_check: Decimal | None


class HeatCell(BaseModel):
    weekday: int
    hour: int
    receipts: float


class DayLoad(BaseModel):
    day: OutputDate
    receipts: int
    revenue: Decimal
    # the average of the last 7 calendar days, null while there are too few of them
    trend: float | None


class HourForecast(BaseModel):
    hour: int
    receipts: float
    low: float
    high: float


class DayForecast(BaseModel):
    day: OutputDate
    weekday: int
    # the number of past days the forecast stands on, no sums without them
    based_on: int
    receipts: float | None
    low: float | None
    high: float | None
    hours: list[HourForecast]


class TrafficReport(BaseModel):
    date_from: OutputDate
    # today is cut off, it is not over yet
    date_to: OutputDate
    last_receipt_at: datetime | None
    summary: TrafficSummary
    by_hour: list[HourLoad]
    by_weekday: list[WeekdayLoad]
    heatmap: list[HeatCell]
    daily: list[DayLoad]
    forecast: list[DayForecast]
