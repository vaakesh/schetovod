from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from core.schema_types import OutputDate


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


class ForecastValue(BaseModel):
    expected: float
    low: float
    high: float


class HourForecast(BaseModel):
    hour: int
    receipts: ForecastValue
    revenue: ForecastValue
    # null while the hour is not over, a part of an hour looks like a fall
    fact_receipts: int | None
    fact_revenue: Decimal | None


class DayFact(BaseModel):
    # the hours before it are over, null when the whole day is
    until_hour: int | None
    receipts: int
    revenue: Decimal
    # the same hours of the past days, a plan for the whole day would be out of reach
    plan_receipts: ForecastValue
    plan_revenue: ForecastValue


class DayForecast(BaseModel):
    day: OutputDate
    weekday: int
    # the number of past days the forecast stands on, no sums without them
    based_on: int
    receipts: ForecastValue | None
    revenue: ForecastValue | None
    hours: list[HourForecast]
    # null for a day to come and for a past day without sales
    fact: DayFact | None


class ForecastScore(BaseModel):
    # percent, 100 is a forecast without a single miss
    accuracy: float
    # percent, above zero means the forecast was too low
    bias: float


class ForecastAccuracy(BaseModel):
    # the finished days with sales, today and the days off are left out
    days: int
    receipts: ForecastScore | None
    revenue: ForecastScore | None


class TrafficForecast(BaseModel):
    date_from: OutputDate
    # today at most, it is forecast by the days before it alone
    date_to: OutputDate
    # by date, from the fifth week of the period, a period up to today goes a week on
    days: list[DayForecast]
    accuracy: ForecastAccuracy | None


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
