from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from core.enums import ExpenseBasis
from core.schema_types import FormModel, InvoiceDate, Money, OutputDate, Text


class ExpenseForm(FormModel):
    name: Text
    # the form sends the plain value, a strict model expects an enum member
    basis: Annotated[
        ExpenseBasis,
        Field(
            strict=False,
        ),
    ]
    amount: Money
    # the first day of the month the rate starts from
    starts_on: InvoiceDate


class ExpenseOut(BaseModel):
    id: int
    name: str
    basis: ExpenseBasis
    amount: Decimal
    starts_on: OutputDate


class ExpenseCharge(BaseModel):
    name: str
    total: Decimal


class ProfitMonth(BaseModel):
    # the first day of the month
    month: OutputDate
    # the month goes on, its fixed costs are taken for the days gone by
    in_progress: bool
    work_days: int
    revenue: Decimal
    card: Decimal
    # percent of the revenue, null without a single invoice to count it by
    margin: Decimal | None
    # the invoices of the month are missing, the nearest known margin stands in
    margin_estimated: bool
    gross: Decimal | None
    # the result of the stocktakes at cost, a shortage is negative
    stock_difference: Decimal | None
    # at cost, for information only, they do not lower the profit
    write_offs: Decimal | None
    charges: list[ExpenseCharge]
    expenses: Decimal
    profit: Decimal | None


class ProfitMargin(BaseModel):
    # percent of the retail prices
    percent: Decimal
    cost: Decimal
    retail: Decimal
    date_from: OutputDate
    date_to: OutputDate


class ProfitReport(BaseModel):
    last_receipt_at: datetime | None
    # newest first
    months: list[ProfitMonth]
    # by the finished months
    average_profit: Decimal | None
    # the takings of a working day that cover all the costs
    break_even_day: Decimal | None
    margin: ProfitMargin | None
    # the rates in force
    expenses: list[ExpenseOut]
