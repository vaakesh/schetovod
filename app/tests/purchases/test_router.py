from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from purchases.schemas import (
    Period,
    PriceTrend,
    ProductSummary,
    PurchaseHistory,
    PurchaseLine,
    PurchaseOverview,
    PurchaseReport,
    Sort,
)
from purchases.service import PurchaseService

AS_OF = date(
    year=2026,
    month=10,
    day=16,
)
LAST_ON = date(
    year=2026,
    month=10,
    day=12,
)


@pytest.fixture
def purchase_service(test_app: FastAPI) -> AsyncMock:
    service = AsyncMock(
        spec=PurchaseService,
    )
    test_app.dependency_overrides[PurchaseService] = lambda: service
    return service


@pytest.fixture
def product_summary() -> tuple[ProductSummary, dict[str, object]]:
    product = ProductSummary(
        product_id=7,
        name="Молоко",
        supplier_id=3,
        supplier_name="Ферма",
        deliveries=4,
        lifetime_deliveries=5,
        spend=Decimal(
            value="480.00",
        ),
        last_on=LAST_ON,
        days_since=4,
        usual_interval_days=Decimal(
            value="3.5",
        ),
        overdue=False,
        price_trend=PriceTrend(
            unit="л",
            current_average=Decimal(
                value="120.00",
            ),
            previous_average=Decimal(
                value="100.00",
            ),
            current_deliveries=4,
            previous_deliveries=2,
            change_pct=Decimal(
                value="20.00",
            ),
            status="rapid_growth",
        ),
    )
    expected = {
        "product_id": 7,
        "name": "Молоко",
        "supplier_id": 3,
        "supplier_name": "Ферма",
        "deliveries": 4,
        "lifetime_deliveries": 5,
        "spend": "480.00",
        "last_on": "12-10-2026",
        "days_since": 4,
        "usual_interval_days": "3.5",
        "overdue": False,
        "price_trend": {
            "unit": "л",
            "current_average": "120.00",
            "previous_average": "100.00",
            "current_deliveries": 4,
            "previous_deliveries": 2,
            "change_pct": "20.00",
            "status": "rapid_growth",
        },
    }
    return product, expected


class TestPurchaseReport:
    def test_returns_empty_report_with_default_filters(
        self, client: TestClient, purchase_service: AsyncMock
    ) -> None:
        purchase_service.summary.return_value = PurchaseReport(
            as_of=AS_OF,
            period=Period.DAYS_30,
            items=[],
        )

        response = client.get(
            url="/purchases",
        )

        assert response.status_code == 200
        assert response.json() == {"as_of": "16-10-2026", "period": "30d", "items": []}
        purchase_service.summary.assert_awaited_once_with(
            period=Period.DAYS_30,
            sort=Sort.FREQUENCY,
            search=None,
            supplier_id=None,
        )

    def test_returns_filtered_report_at_the_gastronom_path(
        self,
        client: TestClient,
        purchase_service: AsyncMock,
        product_summary: tuple[ProductSummary, dict[str, object]],
    ) -> None:
        product, expected = product_summary
        purchase_service.summary.return_value = PurchaseReport(
            as_of=AS_OF,
            period=Period.DAYS_90,
            items=[product],
        )

        response = client.get(
            url="/stores/gastronom/purchases",
            params={
                "period": "90d",
                "sort": "spend",
                "search": "молоко",
                "supplier_id": 3,
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "as_of": "16-10-2026",
            "period": "90d",
            "items": [expected],
        }
        purchase_service.summary.assert_awaited_once_with(
            period=Period.DAYS_90,
            sort=Sort.SPEND,
            search="молоко",
            supplier_id=3,
        )

    @pytest.mark.parametrize(
        argnames=("name", "value", "error_type"),
        argvalues=[
            ("period", "7d", "enum"),
            ("sort", "price", "enum"),
            ("search", "milk\x00", "string_pattern_mismatch"),
            ("supplier_id", "0", "greater_than"),
            ("supplier_id", "9223372036854775808", "less_than_equal"),
            ("supplier_id", "abc", "int_parsing"),
        ],
    )
    def test_rejects_invalid_filters_before_querying(
        self,
        client: TestClient,
        purchase_service: AsyncMock,
        name: str,
        value: str,
        error_type: str,
    ) -> None:
        response = client.get(
            url="/purchases",
            params={name: value},
        )

        assert response.status_code == 422
        (error,) = response.json()["detail"]
        assert error["loc"] == ["query", name]
        assert error["type"] == error_type
        purchase_service.summary.assert_not_awaited()


class TestPurchaseOverview:
    def test_returns_period_totals_for_one_supplier(
        self, client: TestClient, purchase_service: AsyncMock
    ) -> None:
        purchase_service.overview.return_value = PurchaseOverview(
            invoices=3,
            spend=Decimal(
                value="830.15",
            ),
        )

        response = client.get(
            url="/stores/gastronom/purchases/overview",
            params={"period": "60d", "supplier_id": 7},
        )

        assert response.status_code == 200
        assert response.json() == {"invoices": 3, "spend": "830.15"}
        purchase_service.overview.assert_awaited_once_with(
            period=Period.DAYS_60,
            supplier_id=7,
        )


class TestPurchaseHistory:
    @pytest.mark.parametrize(
        argnames=("path", "params", "period"),
        argvalues=[
            ("/purchases/7", {}, Period.DAYS_30),
            ("/stores/gastronom/purchases/7", {"period": "all"}, Period.ALL),
        ],
    )
    def test_returns_product_history(
        self,
        client: TestClient,
        purchase_service: AsyncMock,
        product_summary: tuple[ProductSummary, dict[str, object]],
        path: str,
        params: dict[str, str],
        period: Period,
    ) -> None:
        product, expected = product_summary
        purchase_service.history.return_value = PurchaseHistory(
            as_of=AS_OF,
            period=period,
            product=product,
            lines=[
                PurchaseLine(
                    occurred_on=LAST_ON,
                    invoice_id=12,
                    invoice_number=None,
                    line_no=2,
                    unit=None,
                    quantity=Decimal(
                        value="2.500",
                    ),
                    cost_price=Decimal(
                        value="120.00",
                    ),
                    cost_price_total=Decimal(
                        value="300.00",
                    ),
                    retail_price=Decimal(
                        value="150.00",
                    ),
                ),
            ],
        )

        response = client.get(
            url=path,
            params=params,
        )

        assert response.status_code == 200
        assert response.json() == {
            "as_of": "16-10-2026",
            "period": period.value,
            "product": expected,
            "lines": [
                {
                    "occurred_on": "12-10-2026",
                    "invoice_id": 12,
                    "invoice_number": None,
                    "line_no": 2,
                    "unit": None,
                    "quantity": "2.500",
                    "cost_price": "120.00",
                    "cost_price_total": "300.00",
                    "retail_price": "150.00",
                },
            ],
        }
        purchase_service.history.assert_awaited_once_with(
            product_id=7,
            period=period,
        )

    def test_preserves_not_found_when_the_product_has_no_history(
        self, client: TestClient, purchase_service: AsyncMock
    ) -> None:
        purchase_service.history.side_effect = HTTPException(
            status_code=404,
            detail="Поставки товара не найдены",
        )

        response = client.get(
            url="/purchases/7",
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Поставки товара не найдены"}

    @pytest.mark.parametrize(
        argnames=("path", "location", "error_type"),
        argvalues=[
            ("/purchases/0", ["path", "product_id"], "greater_than"),
            (
                "/purchases/9223372036854775808",
                ["path", "product_id"],
                "less_than_equal",
            ),
            ("/purchases/abc", ["path", "product_id"], "int_parsing"),
            ("/purchases/7?period=7d", ["query", "period"], "enum"),
        ],
    )
    def test_rejects_invalid_history_parameters_before_querying(
        self,
        client: TestClient,
        purchase_service: AsyncMock,
        path: str,
        location: list[str],
        error_type: str,
    ) -> None:
        response = client.get(
            url=path,
        )

        assert response.status_code == 422
        (error,) = response.json()["detail"]
        assert error["loc"] == location
        assert error["type"] == error_type
        purchase_service.history.assert_not_awaited()


class TestPurchaseAccess:
    @pytest.mark.parametrize(
        argnames="path",
        argvalues=[
            "/purchases",
            "/purchases/overview",
            "/purchases/7",
            "/stores/gastronom/purchases",
            "/stores/gastronom/purchases/overview",
            "/stores/gastronom/purchases/7",
        ],
    )
    def test_requires_authentication(
        self, anonymous_client: TestClient, purchase_service: AsyncMock, path: str
    ) -> None:
        response = anonymous_client.get(
            url=path,
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Требуется вход"}
        purchase_service.summary.assert_not_awaited()
        purchase_service.history.assert_not_awaited()

    @pytest.mark.parametrize(
        argnames="path",
        argvalues=["/stores/meat/purchases", "/stores/meat/purchases/7"],
    )
    def test_routes_are_unavailable_in_meat(
        self, client: TestClient, purchase_service: AsyncMock, path: str
    ) -> None:
        response = client.get(
            url=path,
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
        purchase_service.summary.assert_not_awaited()
        purchase_service.history.assert_not_awaited()
