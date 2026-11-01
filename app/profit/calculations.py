from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from core.enums import ExpenseBasis
from invoices.repository import DayPurchases
from profit.models import OperatingExpense
from profit.schemas import ExpenseCharge, ProfitMargin, ProfitMonth
from traffic.analytics import DayTakings

# the first real stocktake, the ledger before it holds test records
COUNTED_ON = date(
    year=2026,
    month=10,
    day=25,
)
MARGIN_WINDOW_DAYS = 90
KOPECK = Decimal(
    value="0.01",
)
TENTH = Decimal(
    value="0.1",
)
ZERO = Decimal(
    value=0,
)
HUNDRED = Decimal(
    value=100,
)
MONTHS_IN_YEAR = 12


@dataclass
class Margin:
    cost: Decimal
    retail: Decimal
    date_from: date
    date_to: date

    @property
    def share(self) -> Decimal:
        return 1 - self.cost / self.retail

    def out(self) -> ProfitMargin:
        return ProfitMargin(
            percent=(self.share * HUNDRED).quantize(
                exp=TENTH,
            ),
            cost=self.cost,
            retail=self.retail,
            date_from=self.date_from,
            date_to=self.date_to,
        )


@dataclass
class MonthTakings:
    work_days: int
    revenue: Decimal
    card: Decimal


def month_start(day: date) -> date:
    return day.replace(
        day=1,
    )


def month_end(day: date) -> date:
    return day.replace(
        day=monthrange(
            year=day.year,
            month=day.month,
        )[1],
    )


def window_margin(
    purchases: Sequence[DayPurchases],
    date_from: date,
    date_to: date,
) -> Margin | None:
    """by the money that went through, so the goods bought often weigh more"""
    days = [purchase for purchase in purchases if date_from <= purchase.day <= date_to]
    retail = sum(
        (purchase.retail for purchase in days),
        start=ZERO,
    )
    if not retail:
        return None
    return Margin(
        cost=sum(
            (purchase.cost for purchase in days),
            start=ZERO,
        ),
        retail=retail,
        date_from=date_from,
        date_to=date_to,
    )


def margin_on(
    purchases: Sequence[DayPurchases],
    on: date,
) -> Margin | None:
    """the last days up to the date, the invoices before the first count are left out"""
    return window_margin(
        purchases=purchases,
        date_from=max(
            COUNTED_ON,
            on
            - timedelta(
                days=MARGIN_WINDOW_DAYS - 1,
            ),
        ),
        date_to=on,
    )


def first_margin(
    purchases: Sequence[DayPurchases],
) -> Margin | None:
    """stands in for the months without invoices"""
    return window_margin(
        purchases=purchases,
        date_from=COUNTED_ON,
        date_to=COUNTED_ON
        + timedelta(
            days=MARGIN_WINDOW_DAYS - 1,
        ),
    )


def in_force(
    expenses: Sequence[OperatingExpense],
    month: date,
) -> list[OperatingExpense]:
    return [
        expense
        for expense in expenses
        if expense.starts_on <= month
        and (expense.ends_on is None or month < expense.ends_on)
    ]


def charge(
    expense: OperatingExpense,
    takings: MonthTakings,
    fixed_share: Decimal,
) -> Decimal:
    match expense.basis:
        case ExpenseBasis.MONTH:
            total = expense.amount * fixed_share
        case ExpenseBasis.YEAR:
            total = expense.amount / MONTHS_IN_YEAR * fixed_share
        case ExpenseBasis.WORK_DAY:
            total = expense.amount * takings.work_days
        case ExpenseBasis.REVENUE_PERCENT:
            total = takings.revenue * expense.amount / HUNDRED
        case ExpenseBasis.CARD_PERCENT:
            total = takings.card * expense.amount / HUNDRED
    return total.quantize(
        exp=KOPECK,
    )


def month_takings(
    days: Sequence[DayTakings],
    date_from: date,
    date_to: date,
) -> MonthTakings:
    inside = [day for day in days if date_from <= day.day <= date_to]
    return MonthTakings(
        # a day of refunds alone is not a working day
        work_days=sum(1 for day in inside if day.revenue > 0),
        revenue=sum(
            (day.revenue for day in inside),
            start=ZERO,
        ),
        card=sum(
            (day.card for day in inside),
            start=ZERO,
        ),
    )


def profit_month(
    month: date,
    last_day: date,
    takings: MonthTakings,
    expenses: Sequence[OperatingExpense],
    margin: Margin | None,
    margin_estimated: bool,
    stock_difference: Decimal,
    write_offs: Decimal,
) -> ProfitMonth:
    """the sums of the stock are at retail prices, the profit moves by their cost only"""
    whole_month = month_end(
        day=month,
    )
    charges = [
        ExpenseCharge(
            name=expense.name,
            total=charge(
                expense=expense,
                takings=takings,
                fixed_share=Decimal(
                    value=last_day.day,
                )
                / whole_month.day,
            ),
        )
        for expense in in_force(
            expenses=expenses,
            month=month,
        )
    ]
    total = sum(
        (line.total for line in charges),
        start=ZERO,
    )
    gross = None
    stock_cost = None
    write_offs_cost = None
    profit = None
    percent = None
    if margin is not None:
        percent = (margin.share * HUNDRED).quantize(
            exp=TENTH,
        )
        gross = (takings.revenue * margin.share).quantize(
            exp=KOPECK,
        )
        cost_share = 1 - margin.share
        stock_cost = (stock_difference * cost_share).quantize(
            exp=KOPECK,
        )
        write_offs_cost = (write_offs * cost_share).quantize(
            exp=KOPECK,
        )
        profit = gross + stock_cost - total
    return ProfitMonth(
        month=month,
        in_progress=last_day < whole_month,
        work_days=takings.work_days,
        revenue=takings.revenue,
        card=takings.card,
        margin=percent,
        margin_estimated=margin_estimated,
        gross=gross,
        stock_difference=stock_cost,
        write_offs=write_offs_cost,
        charges=charges,
        expenses=total,
        profit=profit,
    )


def average_profit(
    months: Sequence[ProfitMonth],
) -> Decimal | None:
    finished = [
        month.profit
        for month in months
        if not month.in_progress and month.profit is not None
    ]
    if not finished:
        return None
    return (
        sum(
            finished,
            start=ZERO,
        )
        / len(
            finished,
        )
    ).quantize(
        exp=KOPECK,
    )


def break_even_day(
    takings: MonthTakings,
    expenses: Sequence[OperatingExpense],
    margin: Margin | None,
) -> Decimal | None:
    """the takings of a day where the margin left after the percents pays the fixed costs"""
    if margin is None or not takings.work_days or not takings.revenue:
        return None
    fixed = ZERO
    per_day = ZERO
    percents = ZERO
    for expense in expenses:
        match expense.basis:
            case ExpenseBasis.MONTH:
                fixed += expense.amount
            case ExpenseBasis.YEAR:
                fixed += expense.amount / MONTHS_IN_YEAR
            case ExpenseBasis.WORK_DAY:
                per_day += expense.amount
            case ExpenseBasis.REVENUE_PERCENT:
                percents += expense.amount / HUNDRED
            case ExpenseBasis.CARD_PERCENT:
                percents += expense.amount / HUNDRED * takings.card / takings.revenue
    earned = margin.share - percents
    if earned <= 0:
        return None
    return ((fixed / takings.work_days + per_day) / earned).quantize(
        exp=KOPECK,
    )
