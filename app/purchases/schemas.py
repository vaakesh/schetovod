from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from core.schema_types import OutputDate


class Period(StrEnum):
    DAYS_30 = "30d"
    DAYS_60 = "60d"
    DAYS_90 = "90d"
    ALL = "all"


class Sort(StrEnum):
    FREQUENCY = "frequency"
    LAST_DELIVERY = "last_delivery"
    SPEND = "spend"


PriceTrendStatus = Literal[
    "rapid_growth", "rising", "stable", "falling", "insufficient"
]


class PriceTrend(BaseModel):
    unit: str | None
    current_average: Decimal | None
    previous_average: Decimal | None
    current_deliveries: int | None
    previous_deliveries: int | None
    change_pct: Decimal | None
    status: PriceTrendStatus


class ProductSummary(BaseModel):
    product_id: int
    name: str
    supplier_id: int
    supplier_name: str
    deliveries: int
    lifetime_deliveries: int
    spend: Decimal
    last_on: OutputDate
    days_since: int
    usual_interval_days: Decimal | None
    overdue: bool
    price_trend: PriceTrend


class PurchaseReport(BaseModel):
    as_of: OutputDate
    period: Period
    items: list[ProductSummary]


class PurchaseOverview(BaseModel):
    spend: Decimal
    invoices: int


class PurchaseLine(BaseModel):
    occurred_on: OutputDate
    invoice_id: int
    invoice_number: str | None
    line_no: int
    unit: str | None
    quantity: Decimal
    cost_price: Decimal
    cost_price_total: Decimal
    retail_price: Decimal


class PurchaseHistory(BaseModel):
    as_of: OutputDate
    period: Period
    product: ProductSummary
    lines: list[PurchaseLine]
