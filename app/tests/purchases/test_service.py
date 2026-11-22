from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, create_autospec

import pytest
from fastapi import HTTPException

from purchases.repository import HistoryRow, PurchaseRepository, SummaryRow, UnitWindow
from purchases.schemas import Period, PriceTrendStatus, Sort
from purchases.service import PurchaseService

AS_OF = date(
    year=2026,
    month=10,
    day=16,
)


def delivery_day(*, days_ago: int) -> date:
    return AS_OF - timedelta(
        days=days_ago,
    )


def summary_row(
    *,
    product_id: int = 1,
    name: str = "Молоко",
    deliveries: int = 1,
    spend: str = "100.00",
    last_ago: int = 0,
    recent_days: tuple[int, ...] = (),
    units: list[UnitWindow] | None = None,
) -> SummaryRow:
    return SummaryRow(
        product_id=product_id,
        name=name,
        supplier_id=7,
        supplier_name="Ферма",
        deliveries=deliveries,
        lifetime_deliveries=deliveries,
        spend=Decimal(
            value=spend,
        ),
        last_on=delivery_day(
            days_ago=last_ago,
        ),
        recent_days=[
            delivery_day(
                days_ago=offset,
            )
            for offset in recent_days
        ],
        units=units or [],
    )


def unit_window(
    *,
    unit: str | None = "шт",
    current_cost: str = "100.00",
    current_quantity: str = "1",
    current_deliveries: int = 1,
    previous_cost: str = "100.00",
    previous_quantity: str = "1",
    previous_deliveries: int = 1,
) -> UnitWindow:
    return UnitWindow(
        unit=unit,
        current_cost=Decimal(
            value=current_cost,
        ),
        current_quantity=Decimal(
            value=current_quantity,
        ),
        current_deliveries=current_deliveries,
        previous_cost=Decimal(
            value=previous_cost,
        ),
        previous_quantity=Decimal(
            value=previous_quantity,
        ),
        previous_deliveries=previous_deliveries,
    )


@pytest.fixture
def repository() -> Mock:
    return create_autospec(
        spec=PurchaseRepository,
        instance=True,
        spec_set=True,
    )


@pytest.fixture
def service(repository: Mock) -> PurchaseService:
    return PurchaseService(
        repository=repository,
    )


class TestSummary:
    @pytest.mark.parametrize(
        ("period", "since", "search", "expected_search"),
        [
            (Period.DAYS_30, "2026-09-17", "Молоко", "Молоко"),
            (Period.DAYS_60, "2026-08-18", "", None),
            (Period.DAYS_90, "2026-07-19", " Молоко ", "Молоко"),
            (Period.ALL, None, "   ", None),
        ],
    )
    async def test_uses_inclusive_dates_and_passes_search_filters(
        self,
        service: PurchaseService,
        repository: Mock,
        period: Period,
        since: str | None,
        search: str,
        expected_search: str | None,
    ) -> None:
        repository.summaries.return_value = []
        expected_since = (
            date.fromisoformat(
                since,
            )
            if since is not None
            else None
        )

        report = await service.summary(
            period=period,
            sort=Sort.FREQUENCY,
            search=search,
            supplier_id=7,
        )

        assert report.as_of == AS_OF
        assert report.period == period
        assert report.items == []
        repository.summaries.assert_awaited_once_with(
            as_of=AS_OF,
            since=expected_since,
            search=expected_search,
            supplier_id=7,
        )

    @pytest.mark.parametrize(
        ("sort", "expected_ids"),
        [
            (Sort.FREQUENCY, [3, 1, 2]),
            (Sort.SPEND, [1, 2, 3]),
            (Sort.LAST_DELIVERY, [4, 1, 2, 3]),
        ],
    )
    async def test_orders_by_metric_with_stable_product_ties(
        self,
        service: PurchaseService,
        repository: Mock,
        sort: Sort,
        expected_ids: list[int],
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                product_id=2,
                name="Абрикосы",
                deliveries=2,
            ),
            summary_row(
                product_id=4,
                name="Огурцы",
                deliveries=0,
                spend="0.00",
                last_ago=65,
            ),
            summary_row(
                product_id=3,
                name="Яблоки",
                deliveries=3,
                spend="30.00",
            ),
            summary_row(
                product_id=1,
                name="абрикосы",
                deliveries=2,
            ),
        ]

        report = await service.summary(
            period=Period.DAYS_30,
            sort=sort,
            search=None,
            supplier_id=None,
        )

        assert [item.product_id for item in report.items] == expected_ids

    @pytest.mark.parametrize(
        ("recent_days", "usual_interval", "overdue"),
        [
            ((10, 14, 16, 20, 25, 40), 4, True),
            ((6, 10, 14, 18), 4, False),
            ((12, 16, 20), None, False),
        ],
    )
    async def test_marks_overdue_from_recent_delivery_gaps(
        self,
        service: PurchaseService,
        repository: Mock,
        recent_days: tuple[int, ...],
        usual_interval: int | None,
        overdue: bool,
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                last_ago=recent_days[0],
                recent_days=recent_days,
            ),
        ]

        report = await service.summary(
            period=Period.DAYS_90,
            sort=Sort.FREQUENCY,
            search=None,
            supplier_id=None,
        )

        item = report.items[0]
        assert item.days_since == recent_days[0]
        assert item.usual_interval_days == usual_interval
        assert item.overdue is overdue

    @pytest.mark.parametrize(
        ("cost", "previous_cost", "expected"),
        [
            ("105.00", "100.00", "rapid_growth"),
            ("1049.99", "1000.00", "rapid_growth"),
            ("104.99", "100.00", "rising"),
            ("102.00", "100.00", "stable"),
            ("98.00", "100.00", "stable"),
            ("97.99", "100.00", "falling"),
        ],
    )
    async def test_classifies_changes_at_thresholds(
        self,
        service: PurchaseService,
        repository: Mock,
        cost: str,
        previous_cost: str,
        expected: PriceTrendStatus,
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                units=[
                    unit_window(
                        current_cost=cost,
                        previous_cost=previous_cost,
                    ),
                ],
            ),
        ]

        report = await service.summary(
            period=Period.ALL,
            sort=Sort.FREQUENCY,
            search=None,
            supplier_id=None,
        )

        assert report.items[0].price_trend.status == expected

    async def test_compares_quantity_weighted_prices_before_rounding_averages(
        self,
        service: PurchaseService,
        repository: Mock,
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                units=[
                    unit_window(
                        current_cost="26.24",
                        current_quantity="3",
                        current_deliveries=2,
                        previous_cost="50.00",
                        previous_quantity="6",
                        previous_deliveries=3,
                    ),
                ],
            ),
        ]

        report = await service.summary(
            period=Period.DAYS_30,
            sort=Sort.SPEND,
            search=None,
            supplier_id=None,
        )

        assert report.items[0].price_trend.model_dump(
            mode="json",
        ) == {
            "unit": "шт",
            "current_average": "8.75",
            "previous_average": "8.33",
            "current_deliveries": 2,
            "previous_deliveries": 3,
            "change_pct": "4.96",
            "status": "rising",
        }

    @pytest.mark.parametrize(
        "units",
        [(None,), ("шт", "кг"), ("шт", None)],
    )
    async def test_suppresses_price_comparison_for_unknown_or_mixed_units(
        self,
        service: PurchaseService,
        repository: Mock,
        units: tuple[str | None, ...],
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                units=[
                    unit_window(
                        unit=unit,
                    )
                    for unit in units
                ],
            ),
        ]

        report = await service.summary(
            period=Period.DAYS_90,
            sort=Sort.FREQUENCY,
            search=None,
            supplier_id=None,
        )

        assert report.items[0].price_trend.model_dump() == {
            "unit": None,
            "current_average": None,
            "previous_average": None,
            "current_deliveries": None,
            "previous_deliveries": None,
            "change_pct": None,
            "status": "insufficient",
        }

    async def test_reports_available_average_without_a_previous_period(
        self,
        service: PurchaseService,
        repository: Mock,
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                units=[
                    unit_window(
                        current_cost="20.01",
                        current_quantity="2",
                        previous_cost="0",
                        previous_quantity="0",
                        previous_deliveries=0,
                    ),
                ],
            ),
        ]

        report = await service.summary(
            period=Period.DAYS_30,
            sort=Sort.FREQUENCY,
            search=None,
            supplier_id=None,
        )

        assert report.items[0].price_trend.model_dump(
            mode="json",
        ) == {
            "unit": "шт",
            "current_average": "10.01",
            "previous_average": None,
            "current_deliveries": 1,
            "previous_deliveries": 0,
            "change_pct": None,
            "status": "insufficient",
        }


class TestHistory:
    async def test_returns_posted_invoice_line_values(
        self,
        service: PurchaseService,
        repository: Mock,
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                product_id=9,
                spend="26.24",
            ),
        ]
        repository.history.return_value = [
            HistoryRow(
                occurred_on=AS_OF,
                invoice_id=42,
                invoice_number="П-42",
                line_no=2,
                unit="шт.",
                quantity=Decimal(
                    value="3.000",
                ),
                cost_price=Decimal(
                    value="8.75",
                ),
                cost_price_total=Decimal(
                    value="26.24",
                ),
                retail_price=Decimal(
                    value="12.00",
                ),
            ),
        ]

        history = await service.history(
            product_id=9,
            period=Period.ALL,
        )

        assert history.as_of == AS_OF
        assert history.period == Period.ALL
        assert history.product.product_id == 9
        assert history.lines[0].model_dump(
            mode="json",
        ) == {
            "occurred_on": "16-10-2026",
            "invoice_id": 42,
            "invoice_number": "П-42",
            "line_no": 2,
            "unit": "шт.",
            "quantity": "3.000",
            "cost_price": "8.75",
            "cost_price_total": "26.24",
            "retail_price": "12.00",
        }
        repository.history.assert_awaited_once_with(
            as_of=AS_OF,
            since=None,
            product_id=9,
        )

    async def test_returns_empty_period_for_a_previously_delivered_product(
        self,
        service: PurchaseService,
        repository: Mock,
    ) -> None:
        repository.summaries.return_value = [
            summary_row(
                product_id=9,
                deliveries=0,
                spend="0.00",
                last_ago=92,
            ),
        ]
        repository.history.return_value = []

        history = await service.history(
            product_id=9,
            period=Period.DAYS_30,
        )

        assert history.product.product_id == 9
        assert history.product.days_since == 92
        assert history.product.deliveries == 0
        assert history.lines == []

    async def test_returns_404_for_product_without_deliveries(
        self,
        service: PurchaseService,
        repository: Mock,
    ) -> None:
        repository.summaries.return_value = []

        with pytest.raises(
            expected_exception=HTTPException,
        ) as error:
            await service.history(
                product_id=9,
                period=Period.DAYS_90,
            )

        assert error.value.status_code == 404
        assert error.value.detail == "Поставки товара не найдены"
        repository.history.assert_not_awaited()
