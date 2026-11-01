from datetime import date, timedelta
from decimal import Decimal

from traffic.analytics import (
    HourRow,
    by_hour,
    by_weekday,
    daily,
    forecast,
    forecast_day,
    heatmap,
    spread,
    summary,
)
from traffic.schemas import ForecastValue

# a monday
MONDAY = date(
    year=2026,
    month=10,
    day=5,
)


def row(
    day: date = MONDAY,
    hour: int = 10,
    sales: int = 1,
    revenue: str = "100.00",
) -> HourRow:
    return HourRow(
        day=day,
        hour=hour,
        sales=sales,
        revenue=Decimal(
            value=revenue,
        ),
    )


def weeks_ago(
    weeks: int,
) -> date:
    return MONDAY - timedelta(
        weeks=weeks,
    )


class TestAverages:
    def test_an_hour_is_averaged_over_the_working_days(self) -> None:
        rows = [
            row(
                hour=10,
                sales=4,
            ),
            row(
                day=MONDAY
                + timedelta(
                    days=1,
                ),
                hour=10,
                sales=2,
            ),
            # the day without sales in between is not a working day
            row(
                day=MONDAY
                + timedelta(
                    days=3,
                ),
                hour=11,
                sales=3,
                revenue="300.00",
            ),
        ]

        loads = by_hour(
            rows=rows,
        )

        assert [(load.hour, load.receipts) for load in loads] == [
            (10, 2.0),
            (11, 1.0),
        ]

    def test_a_quiet_hour_of_the_day_stays_on_the_axis(self) -> None:
        loads = by_hour(
            rows=[
                row(
                    hour=10,
                ),
                row(
                    hour=12,
                ),
            ],
        )

        assert [(load.hour, load.receipts) for load in loads] == [
            (10, 1.0),
            (11, 0.0),
            (12, 1.0),
        ]
        assert loads[1].average_check is None

    def test_a_refund_lowers_the_sum_and_not_the_customers(self) -> None:
        result = summary(
            rows=[
                row(
                    sales=2,
                    revenue="300.00",
                ),
                # only a refund in this hour
                row(
                    hour=11,
                    sales=0,
                    revenue="-100.00",
                ),
            ],
        )

        assert result.receipts == 2
        assert result.days == 1
        assert result.revenue == Decimal(
            value="200.00",
        )
        assert result.average_check == Decimal(
            value="100.00",
        )
        assert result.peak_hour == 10

    def test_a_day_with_only_a_refund_is_not_a_working_day(self) -> None:
        result = summary(
            rows=[
                row(
                    sales=0,
                    revenue="-100.00",
                ),
            ],
        )

        assert result.days == 0
        assert result.per_day is None
        assert result.average_check is None
        assert result.peak_hour is None

    def test_no_rows_give_an_empty_report(self) -> None:
        result = summary(
            rows=[],
        )

        assert (result.receipts, result.days, result.per_day) == (0, 0, None)
        assert (
            by_hour(
                rows=[],
            )
            == []
        )
        assert (
            heatmap(
                rows=[],
            )
            == []
        )
        assert (
            daily(
                rows=[],
            )
            == []
        )

    def test_a_weekday_is_averaged_over_its_own_days(self) -> None:
        loads = by_weekday(
            rows=[
                row(
                    sales=30,
                    revenue="3000.00",
                ),
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    sales=10,
                    revenue="1000.00",
                ),
                row(
                    day=MONDAY
                    + timedelta(
                        days=1,
                    ),
                    sales=5,
                    revenue="1000.00",
                ),
            ],
        )

        assert len(loads) == 7
        assert (loads[0].days, loads[0].receipts) == (2, 20.0)
        assert (loads[1].days, loads[1].receipts) == (1, 5.0)
        assert loads[1].average_check == Decimal(
            value="200.00",
        )
        assert (loads[2].days, loads[2].receipts, loads[2].average_check) == (
            0,
            0.0,
            None,
        )

    def test_the_heatmap_covers_the_same_hours_on_every_worked_weekday(self) -> None:
        cells = heatmap(
            rows=[
                row(
                    hour=10,
                    sales=2,
                ),
                row(
                    day=MONDAY
                    + timedelta(
                        days=1,
                    ),
                    hour=11,
                    sales=3,
                ),
            ],
        )

        assert [(cell.weekday, cell.hour, cell.receipts) for cell in cells] == [
            (0, 10, 2.0),
            (0, 11, 0.0),
            (1, 10, 0.0),
            (1, 11, 3.0),
        ]


class TestTrend:
    def test_the_trend_needs_a_few_days_and_looks_a_week_back(self) -> None:
        days = [
            MONDAY
            + timedelta(
                days=shift,
            )
            for shift in (0, 1, 2, 8)
        ]

        loads = daily(
            rows=[
                row(
                    day=day,
                    sales=sales,
                )
                for day, sales in zip(
                    days,
                    (10, 20, 30, 40),
                    strict=True,
                )
            ],
        )

        assert [load.trend for load in loads] == [
            None,
            None,
            20.0,
            # the days a week before it are out of the window
            None,
        ]


class TestSpread:
    def test_the_quartiles_are_interpolated(self) -> None:
        assert spread(
            values=[10, 20, 30, 40, 50],
        ) == (20.0, 30.0, 40.0)

    def test_one_value_has_no_spread(self) -> None:
        assert spread(
            values=[7],
        ) == (7.0, 7.0, 7.0)


class TestForecast:
    def test_only_the_same_weekday_counts(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    sales=10,
                ),
                row(
                    day=weeks_ago(
                        weeks=2,
                    ),
                    sales=20,
                ),
                row(
                    day=weeks_ago(
                        weeks=1,
                    )
                    + timedelta(
                        days=1,
                    ),
                    sales=500,
                ),
            ],
        )

        assert day.weekday == 0
        assert day.based_on == 2
        assert day.receipts == ForecastValue(
            expected=15.0,
            low=12.5,
            high=17.5,
        )

    def test_a_one_off_rush_does_not_move_the_median(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=weeks,
                    ),
                    sales=sales,
                )
                for weeks, sales in zip(
                    range(1, 6),
                    (10, 11, 12, 13, 400),
                    strict=True,
                )
            ],
        )

        assert day.receipts == ForecastValue(
            expected=12.0,
            low=11.0,
            high=13.0,
        )

    def test_every_same_weekday_of_the_rows_is_used(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=weeks,
                    ),
                    sales=100 if weeks > 8 else 10,
                )
                for weeks in range(1, 13)
            ],
        )

        assert day.based_on == 12
        assert day.receipts == ForecastValue(
            expected=10.0,
            low=10.0,
            high=100.0,
        )

    def test_the_revenue_is_forecast_by_day_and_by_hour(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    revenue="1000.00",
                ),
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    hour=11,
                    revenue="500.00",
                ),
                row(
                    day=weeks_ago(
                        weeks=2,
                    ),
                    revenue="2000.00",
                ),
            ],
        )

        assert day.revenue == ForecastValue(
            expected=1750.0,
            low=1625.0,
            high=1875.0,
        )
        assert [(hour.hour, hour.revenue.expected) for hour in day.hours] == [
            (10, 1500.0),
            (11, 250.0),
        ]

    def test_a_refund_lowers_the_revenue_and_not_the_customers(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    sales=2,
                    revenue="1000.00",
                ),
                # only a refund in this hour
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    hour=11,
                    sales=0,
                    revenue="-100.00",
                ),
            ],
        )

        assert day.receipts == ForecastValue(
            expected=2.0,
            low=2.0,
            high=2.0,
        )
        assert day.revenue == ForecastValue(
            expected=900.0,
            low=900.0,
            high=900.0,
        )
        assert [hour.hour for hour in day.hours] == [10]

    def test_a_day_with_only_a_refund_is_not_a_base_day(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    sales=0,
                    revenue="-100.00",
                ),
            ],
        )

        assert day.based_on == 0
        assert day.revenue is None

    def test_an_hour_missing_on_a_day_counts_as_a_quiet_one(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    hour=10,
                    sales=4,
                ),
                row(
                    day=weeks_ago(
                        weeks=1,
                    ),
                    hour=12,
                    sales=2,
                ),
                row(
                    day=weeks_ago(
                        weeks=2,
                    ),
                    hour=10,
                    sales=2,
                ),
            ],
        )

        assert [(hour.hour, hour.receipts.expected) for hour in day.hours] == [
            (10, 3.0),
            (11, 0.0),
            (12, 1.0),
        ]

    def test_a_weekday_without_a_past_has_no_numbers(self) -> None:
        day = forecast_day(
            day=MONDAY,
            rows=[],
        )

        assert day.based_on == 0
        assert (day.receipts, day.revenue) == (None, None)
        assert day.hours == []

    def test_today_and_a_week_after_it_are_forecast(self) -> None:
        days = forecast(
            rows=[],
            today=MONDAY,
        )

        assert [day.day for day in days] == [
            MONDAY
            + timedelta(
                days=shift,
            )
            for shift in range(8)
        ]
