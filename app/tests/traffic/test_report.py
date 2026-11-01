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

    def test_the_start_can_not_be_after_the_end(self) -> None:
        response = self.client.get(
            url="/traffic/report",
            params={
                "date_from": "02-10-2026",
                "date_to": "01-10-2026",
            },
        )

        assert response.status_code == 422

    def forecast(
        self,
        date_from: str = "01-09-2026",
        date_to: str = "16-10-2026",
    ) -> dict[str, Any]:
        response = self.client.get(
            url="/traffic/forecast",
            params={
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        assert response.status_code == 200
        return response.json()

    def test_the_forecast_begins_on_the_fifth_week_and_goes_a_week_on(self) -> None:
        forecast = self.forecast()

        # the fixed clock stands on 16-10-2026
        assert forecast["date_to"] == "16-10-2026"
        assert forecast["days"][0]["day"] == "29-09-2026"
        assert forecast["days"][-1]["day"] == "23-10-2026"
        assert forecast["accuracy"] is None

    def test_the_forecast_stands_on_the_chosen_period(self) -> None:
        # thursdays, the same weekday as the 22nd
        for month, day in ((9, 3), (10, 1)):
            self.add(
                at=datetime(
                    year=2026,
                    month=month,
                    day=day,
                    hour=9,
                    tzinfo=UTC,
                ),
            )

        whole = self.forecast()
        short = self.forecast(
            date_from="10-09-2026",
        )

        assert whole["days"][-2]["day"] == "22-10-2026"
        assert whole["days"][-2]["based_on"] == 2
        assert short["days"][-2]["based_on"] == 1

    def test_today_is_measured_up_to_the_last_finished_hour(self) -> None:
        # a friday, the same weekday as today
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=9,
                hour=7,
                tzinfo=UTC,
            ),
        )
        before = self.forecast()

        # the fixed clock stands on 12:00 in Moscow, this is 10:30 of today
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=16,
                hour=7,
                minute=30,
                tzinfo=UTC,
            ),
        )
        # this is 12:10, the hour is not over
        self.add(
            at=datetime(
                year=2026,
                month=10,
                day=16,
                hour=9,
                minute=10,
                tzinfo=UTC,
            ),
        )
        after = self.forecast()

        today = next(day for day in after["days"] if day["day"] == "16-10-2026")
        assert today["based_on"] == 1
        assert today["receipts"]["expected"] == 1.0
        assert today["fact"]["until_hour"] == 12
        assert today["fact"]["receipts"] == 1
        assert before["days"][17]["receipts"] == today["receipts"]

    def test_a_finished_day_goes_into_the_accuracy(self) -> None:
        for day in (2, 9):
            self.add(
                at=datetime(
                    year=2026,
                    month=10,
                    day=day,
                    hour=9,
                    tzinfo=UTC,
                ),
            )

        forecast = self.forecast(
            date_from="04-09-2026",
        )

        # the 2nd has no past friday to stand on, only the 9th is compared
        assert forecast["days"][0]["day"] == "02-10-2026"
        assert forecast["days"][0]["fact"] is None
        assert forecast["accuracy"]["days"] == 1

    def test_a_period_of_five_weeks_is_enough(self) -> None:
        response = self.client.get(
            url="/traffic/forecast",
            params={
                "date_from": "11-09-2026",
                "date_to": "15-10-2026",
            },
        )

        assert response.status_code == 200

    def test_a_shorter_forecast_period_is_refused(self) -> None:
        response = self.client.get(
            url="/traffic/forecast",
            params={
                "date_from": "12-09-2026",
                "date_to": "15-10-2026",
            },
        )

        assert response.status_code == 422

    def test_a_future_end_counts_only_up_to_today(self) -> None:
        response = self.client.get(
            url="/traffic/forecast",
            params={
                "date_from": "13-09-2026",
                "date_to": "31-12-2026",
            },
        )

        assert response.status_code == 422

    def test_the_forecast_start_can_not_be_after_the_end(self) -> None:
        response = self.client.get(
            url="/traffic/forecast",
            params={
                "date_from": "02-10-2026",
                "date_to": "01-10-2026",
            },
        )

        assert response.status_code == 422
