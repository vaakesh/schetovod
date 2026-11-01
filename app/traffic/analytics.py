from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import quantiles

from traffic.schemas import (
    DayFact,
    DayForecast,
    DayLoad,
    ForecastAccuracy,
    ForecastScore,
    ForecastValue,
    HeatCell,
    HourForecast,
    HourLoad,
    TrafficSummary,
    WeekdayLoad,
)

KOPECK = Decimal(
    value="0.01",
)
ZERO = Decimal(
    value=0,
)
WEEK = 7
# days after today, every one of them is forecast on its own
HORIZON = 7
# how far back the first import goes, a forecast period finds nothing older
BASE_WEEKS = 12
# the start of a period is only the base, the forecast begins after it
BASE_DAYS = 28
MIN_PERIOD_DAYS = BASE_DAYS + WEEK
TREND_DAYS = 7
TREND_MIN_DAYS = 3


@dataclass
class HourRow:
    """the receipts of one hour of one day of the shop"""

    day: date
    hour: int
    sales: int
    # the refunds are taken off
    revenue: Decimal


def average(
    value: float,
    count: int,
) -> float:
    return round(
        number=value / count,
        ndigits=1,
    )


def average_check(
    revenue: Decimal,
    sales: int,
) -> Decimal | None:
    if sales == 0:
        return None
    return (revenue / sales).quantize(
        exp=KOPECK,
    )


def working_days(
    rows: list[HourRow],
) -> set[date]:
    """a day without sales is a day off, or a day that was never loaded"""
    return {row.day for row in rows if row.sales > 0}


def hour_span(
    hours: set[int],
) -> list[int]:
    """the hours in a row, a quiet hour in the middle of the day is still an hour"""
    if not hours:
        return []
    return list(
        range(
            min(hours),
            max(hours) + 1,
        ),
    )


def sale_hours(
    rows: list[HourRow],
) -> list[int]:
    return hour_span(
        hours={row.hour for row in rows if row.sales > 0},
    )


def peak[Key](
    values: dict[Key, float],
) -> Key | None:
    """the first of the equal maximums, none when nothing was sold"""
    if (
        not values
        or max(
            values.values(),
        )
        == 0
    ):
        return None
    return max(
        values,
        key=lambda key: values[key],
    )


def by_hour(
    rows: list[HourRow],
) -> list[HourLoad]:
    days = len(
        working_days(
            rows=rows,
        ),
    )
    sales: dict[int, int] = defaultdict(int)
    revenue: dict[int, Decimal] = defaultdict(Decimal)
    for row in rows:
        sales[row.hour] += row.sales
        revenue[row.hour] += row.revenue
    return [
        HourLoad(
            hour=hour,
            receipts=average(
                value=sales[hour],
                count=days,
            ),
            average_check=average_check(
                revenue=revenue[hour],
                sales=sales[hour],
            ),
        )
        for hour in sale_hours(
            rows=rows,
        )
    ]


def weekday_days(
    rows: list[HourRow],
) -> dict[int, int]:
    days: dict[int, int] = defaultdict(int)
    for day in working_days(
        rows=rows,
    ):
        days[day.weekday()] += 1
    return days


def by_weekday(
    rows: list[HourRow],
) -> list[WeekdayLoad]:
    days = weekday_days(
        rows=rows,
    )
    sales: dict[int, int] = defaultdict(int)
    revenue: dict[int, Decimal] = defaultdict(Decimal)
    for row in rows:
        sales[row.day.weekday()] += row.sales
        revenue[row.day.weekday()] += row.revenue
    return [
        WeekdayLoad(
            weekday=weekday,
            days=days[weekday],
            receipts=average(
                value=sales[weekday],
                count=max(
                    days[weekday],
                    1,
                ),
            ),
            average_check=average_check(
                revenue=revenue[weekday],
                sales=sales[weekday],
            ),
        )
        for weekday in range(
            WEEK,
        )
    ]


def heatmap(
    rows: list[HourRow],
) -> list[HeatCell]:
    """only the weekdays that were worked, every one of them over the same hours"""
    days = weekday_days(
        rows=rows,
    )
    sales: dict[tuple[int, int], int] = defaultdict(int)
    for row in rows:
        sales[(row.day.weekday(), row.hour)] += row.sales
    hours = sale_hours(
        rows=rows,
    )
    return [
        HeatCell(
            weekday=weekday,
            hour=hour,
            receipts=average(
                value=sales[(weekday, hour)],
                count=days[weekday],
            ),
        )
        for weekday in sorted(days)
        for hour in hours
    ]


def daily(
    rows: list[HourRow],
) -> list[DayLoad]:
    """only the days with sales, a chart keeps the gaps by the dates"""
    sales: dict[date, int] = defaultdict(int)
    revenue: dict[date, Decimal] = defaultdict(Decimal)
    for row in rows:
        sales[row.day] += row.sales
        revenue[row.day] += row.revenue
    days = sorted(
        working_days(
            rows=rows,
        ),
    )
    result: list[DayLoad] = []
    for day in days:
        recent = [
            sales[other]
            for other in days
            if timedelta()
            <= day - other
            < timedelta(
                days=TREND_DAYS,
            )
        ]
        count = len(
            recent,
        )
        result.append(
            DayLoad(
                day=day,
                receipts=sales[day],
                revenue=revenue[day],
                trend=(
                    average(
                        value=sum(
                            recent,
                        ),
                        count=count,
                    )
                    if count >= TREND_MIN_DAYS
                    else None
                ),
            ),
        )
    return result


def summary(
    rows: list[HourRow],
) -> TrafficSummary:
    days = len(
        working_days(
            rows=rows,
        ),
    )
    sales = sum(row.sales for row in rows)
    revenue = sum(
        (row.revenue for row in rows),
        start=ZERO,
    )
    return TrafficSummary(
        receipts=sales,
        days=days,
        per_day=(
            average(
                value=sales,
                count=days,
            )
            if days > 0
            else None
        ),
        revenue=revenue,
        average_check=average_check(
            revenue=revenue,
            sales=sales,
        ),
        peak_hour=peak(
            values={
                load.hour: load.receipts
                for load in by_hour(
                    rows=rows,
                )
            },
        ),
        peak_weekday=peak(
            values={
                load.weekday: load.receipts
                for load in by_weekday(
                    rows=rows,
                )
            },
        ),
    )


def spread(
    values: list[float],
) -> tuple[float, float, float]:
    """the lower quartile, the median and the upper quartile"""
    if (
        len(
            values,
        )
        == 1
    ):
        only = round(
            number=values[0],
            ndigits=1,
        )
        return (
            only,
            only,
            only,
        )
    low, middle, high = quantiles(
        values,
        n=4,
        method="inclusive",
    )
    return (
        round(
            number=low,
            ndigits=1,
        ),
        round(
            number=middle,
            ndigits=1,
        ),
        round(
            number=high,
            ndigits=1,
        ),
    )


def forecast_value(
    values: list[float],
) -> ForecastValue:
    low, middle, high = spread(
        values=values,
    )
    return ForecastValue(
        expected=middle,
        low=low,
        high=high,
    )


def day_value(
    days: dict[date, dict[int, float]],
) -> ForecastValue:
    return forecast_value(
        values=[
            sum(
                hours.values(),
            )
            for hours in days.values()
        ],
    )


def hour_value(
    days: dict[date, dict[int, float]],
    hour: int,
) -> ForecastValue:
    """an hour missing on a day counts as a quiet one"""
    return forecast_value(
        values=[
            hours.get(
                hour,
                0,
            )
            for hours in days.values()
        ],
    )


def before_hour(
    days: dict[date, dict[int, float]],
    until_hour: int | None,
) -> dict[date, dict[int, float]]:
    if until_hour is None:
        return days
    return {
        day: {hour: value for hour, value in hours.items() if hour < until_hour}
        for day, hours in days.items()
    }


def hour_is_over(
    fact: DayFact | None,
    hour: int,
) -> bool:
    if fact is None:
        return False
    return fact.until_hour is None or hour < fact.until_hour


def forecast_day(
    day: date,
    rows: list[HourRow],
    actual: Sequence[HourRow] = (),
    until_hour: int | None = None,
) -> DayForecast:
    """
    the median of the same weekdays, a one-off rush does not move it,
    the rows are the past of the day, the actual ones are the day itself
    """
    weekday = [row for row in rows if row.day.weekday() == day.weekday()]
    base = working_days(
        rows=weekday,
    )
    if not base:
        return DayForecast(
            day=day,
            weekday=day.weekday(),
            based_on=0,
            receipts=None,
            revenue=None,
            hours=[],
            fact=None,
        )
    sales: dict[date, dict[int, float]] = defaultdict(dict)
    revenue: dict[date, dict[int, float]] = defaultdict(dict)
    for row in weekday:
        if row.day in base:
            sales[row.day][row.hour] = row.sales
            # a forecast is an estimate, not an amount of the books
            revenue[row.day][row.hour] = float(
                row.revenue,
            )
    done = [row for row in actual if until_hour is None or row.hour < until_hour]
    fact = None
    # today is measured from its first hour, a past day without sales was a day off
    if until_hour is not None or working_days(
        rows=done,
    ):
        fact = DayFact(
            until_hour=until_hour,
            receipts=sum(row.sales for row in done),
            revenue=sum(
                (row.revenue for row in done),
                start=ZERO,
            ),
            plan_receipts=day_value(
                days=before_hour(
                    days=sales,
                    until_hour=until_hour,
                ),
            ),
            plan_revenue=day_value(
                days=before_hour(
                    days=revenue,
                    until_hour=until_hour,
                ),
            ),
        )
    fact_sales = {row.hour: row.sales for row in done}
    fact_revenue = {row.hour: row.revenue for row in done}
    return DayForecast(
        day=day,
        weekday=day.weekday(),
        based_on=len(
            base,
        ),
        receipts=day_value(
            days=sales,
        ),
        revenue=day_value(
            days=revenue,
        ),
        hours=[
            HourForecast(
                hour=hour,
                receipts=hour_value(
                    days=sales,
                    hour=hour,
                ),
                revenue=hour_value(
                    days=revenue,
                    hour=hour,
                ),
                fact_receipts=(
                    fact_sales.get(
                        hour,
                        0,
                    )
                    if hour_is_over(
                        fact=fact,
                        hour=hour,
                    )
                    else None
                ),
                fact_revenue=(
                    fact_revenue.get(
                        hour,
                        ZERO,
                    )
                    if hour_is_over(
                        fact=fact,
                        hour=hour,
                    )
                    else None
                ),
            )
            # a sale at an unusual hour must not fall off the chart
            for hour in sale_hours(
                rows=[*weekday, *done],
            )
        ],
        fact=fact,
    )


def forecast(
    rows: list[HourRow],
    date_from: date,
    date_to: date,
    today: date,
    hour: int,
) -> list[DayForecast]:
    """every day stands on the days before it, it never sees itself or what came later"""
    first = date_from + timedelta(
        days=BASE_DAYS,
    )
    last = date_to
    if date_to == today:
        last += timedelta(
            days=HORIZON,
        )
    days = [
        first
        + timedelta(
            days=shift,
        )
        for shift in range(
            (last - first).days + 1,
        )
    ]
    return [
        forecast_day(
            day=day,
            rows=[
                row
                for row in rows
                if row.day
                < min(
                    day,
                    today,
                )
            ],
            actual=[row for row in rows if row.day == day],
            until_hour=hour if day == today else None,
        )
        for day in days
    ]


def score(
    facts: list[float],
    plans: list[float],
) -> ForecastScore | None:
    """the misses against the total, a quiet day does not weigh as much as a busy one"""
    total_fact = sum(
        facts,
    )
    total_plan = sum(
        plans,
    )
    if total_fact <= 0 or total_plan <= 0:
        return None
    misses = sum(
        abs(
            fact - plan,
        )
        for fact, plan in zip(
            facts,
            plans,
            strict=True,
        )
    )
    return ForecastScore(
        accuracy=round(
            number=max(
                100 - misses / total_fact * 100,
                0,
            ),
            ndigits=1,
        ),
        bias=round(
            number=(total_fact - total_plan) / total_plan * 100,
            ndigits=1,
        ),
    )


def accuracy(
    days: list[DayForecast],
    today: date,
) -> ForecastAccuracy | None:
    facts = [day.fact for day in days if day.fact is not None and day.day < today]
    if not facts:
        return None
    return ForecastAccuracy(
        days=len(
            facts,
        ),
        receipts=score(
            facts=[float(fact.receipts) for fact in facts],
            plans=[fact.plan_receipts.expected for fact in facts],
        ),
        revenue=score(
            facts=[float(fact.revenue) for fact in facts],
            plans=[fact.plan_revenue.expected for fact in facts],
        ),
    )
