from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import quantiles

from traffic.schemas import (
    DayForecast,
    DayLoad,
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
# days ahead, every one of them is forecast on its own
HORIZON = 7
# the same weekdays a forecast stands on and how far back they are looked for
BASE_DAYS = 8
BASE_WEEKS = 12
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
    values: list[int],
) -> tuple[float, float, float]:
    """the lower quartile, the median and the upper quartile"""
    if (
        len(
            values,
        )
        == 1
    ):
        only = float(
            values[0],
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


def forecast_day(
    day: date,
    rows: list[HourRow],
) -> DayForecast:
    """the median of the latest same weekdays, a one-off rush does not move it"""
    sales: dict[date, dict[int, int]] = defaultdict(dict)
    for row in rows:
        if row.day.weekday() == day.weekday() and row.sales > 0:
            sales[row.day][row.hour] = row.sales
    base = sorted(
        sales,
        reverse=True,
    )[:BASE_DAYS]
    if not base:
        return DayForecast(
            day=day,
            weekday=day.weekday(),
            based_on=0,
            receipts=None,
            low=None,
            high=None,
            hours=[],
        )
    low, middle, high = spread(
        values=[
            sum(
                sales[past].values(),
            )
            for past in base
        ],
    )
    hours: list[HourForecast] = []
    for hour in hour_span(
        hours={hour for past in base for hour in sales[past]},
    ):
        hour_low, hour_middle, hour_high = spread(
            values=[
                sales[past].get(
                    hour,
                    0,
                )
                for past in base
            ],
        )
        hours.append(
            HourForecast(
                hour=hour,
                receipts=hour_middle,
                low=hour_low,
                high=hour_high,
            ),
        )
    return DayForecast(
        day=day,
        weekday=day.weekday(),
        based_on=len(
            base,
        ),
        receipts=middle,
        low=low,
        high=high,
        hours=hours,
    )


def forecast(
    rows: list[HourRow],
    today: date,
) -> list[DayForecast]:
    return [
        forecast_day(
            day=today
            + timedelta(
                days=ahead,
            ),
            rows=rows,
        )
        for ahead in range(
            1,
            HORIZON + 1,
        )
    ]
