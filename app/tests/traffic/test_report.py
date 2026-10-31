from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from core.enums import ReceiptKind
from tests.fakes import FakeStore
from traffic.models import Receipt


class TestTrafficReport:
    @pytest.fixture(
        autouse=True,
    )
    def setup(
        self,
        store: FakeStore,
        client: TestClient,
    ) -> None:
        self.client = client
        self.store = store

    def add(
        self,
        at: datetime,
        kind: ReceiptKind = ReceiptKind.SALE,
    ) -> None:
        self.store.receipts.append(
            Receipt(
                aqsi_id=uuid4(),
                shift_id=uuid4(),
                processed_at=at,
                kind=kind,
                total=Decimal(
                    value="100.00",
                ),
                cash=Decimal(
                    value="100.00",
                ),
                card=Decimal(
                    value=0,
                ),
                positions=1,
            ),
        )

    def report(
        self,
        date_from: str = "01-10-2026",
        date_to: str = "16-10-2026",
    ) -> dict[str, Any]:
        response = self.client.get(
            url="/traffic/report",
            params={
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        assert response.status_code == 200
        return response.json()

    def test_an_empty_table_gives_an_empty_report(self) -> None:
        report = self.report()

        assert report["last_receipt_at"] is None
        assert report["summary"]["receipts"] == 0
        assert report["by_hour"] == []
        assert [day["based_on"] for day in report["forecast"]] == [0] * 7

    def test_today_is_left_out_of_the_period(self) -> None:
        # the fixed clock stands on 16-10-2026
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=15,
                hour=9,
                tzinfo=UTC,
            ),
        )
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=16,
                hour=9,
                tzinfo=UTC,
            ),
        )

        report = self.report()

        assert report["date_to"] == "15-10-2026"
        assert report["summary"]["receipts"] == 1
        assert report["daily"][0]["day"] == "15-10-2026"
        # the last receipt still shows how far the loading went
        assert report["last_receipt_at"].startswith("2026-10-16")

    def test_a_late_receipt_falls_on_the_day_and_hour_of_the_shop(self) -> None:
        # 01:30 on the 15th in Moscow
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=14,
                hour=22,
                minute=30,
                tzinfo=UTC,
            ),
        )

        report = self.report()

        assert report["daily"][0]["day"] == "15-10-2026"
        assert report["by_hour"][0]["hour"] == 1

    def test_the_forecast_does_not_depend_on_the_period(self) -> None:
        # thursday, the same weekday as the 22nd
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=15,
                hour=9,
                tzinfo=UTC,
            ),
        )

        report = self.report(
            date_from="01-09-2026",
            date_to="02-09-2026",
        )

        assert report["summary"]["receipts"] == 0
        thursday = report["forecast"][5]
        assert thursday["day"] == "22-10-2026"
        assert (thursday["based_on"], thursday["receipts"]) == (1, 1.0)

    def test_the_start_can_not_be_after_the_end(self) -> None:
        response = self.client.get(
            url="/traffic/report",
            params={
                "date_from": "02-10-2026",
                "date_to": "01-10-2026",
            },
        )

        assert response.status_code == 422
