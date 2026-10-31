from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqsi.client import AqsiClient, aqsi_client
from core.config import settings
from tests.fakes import FakeStore
from tests.ledger.helpers import LedgerApi

KEY = "secret-aqsi-key"


def counters(
    cash: int = 0,
    cashless: int = 0,
    prepayment: int = 0,
) -> dict[str, int]:
    return {
        "total": cash + cashless + prepayment,
        "cash": cash,
        "cashless": cashless,
        "prepayment": prepayment,
        "credit": 0,
        "consideration": 0,
    }


def closed_report(
    income: dict[str, int] | None = None,
    refund: dict[str, int] | None = None,
    expense: dict[str, int] | None = None,
    correction: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "shiftCounters": {
            "income": income or counters(),
            "incomeRefund": refund or counters(),
            "expense": expense or counters(),
            "expenseRefund": counters(),
            "corrections": {
                "income": correction or counters(),
                "incomeRefund": counters(),
                "expense": counters(),
                "expenseRefund": counters(),
            },
        },
    }


def shift(
    number: int,
    closed: dict[str, Any] | None,
    opened_at: str | None = "2026-10-14T09:25:00.000+03:00",
) -> dict[str, Any]:
    return {
        "id": str(
            uuid4(),
        ),
        "number": number,
        "shiftOpenedReport": {"dateTime": opened_at} if opened_at else None,
        "shiftClosedReport": closed,
    }


class FakeAqsi:
    """the two methods of aQsi that are used, two shifts on a page"""

    def __init__(self) -> None:
        self.shifts: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.failure: int | None = None

    def handle(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.requests.append(
            request,
        )
        if self.failure is not None:
            return httpx.Response(
                status_code=self.failure,
            )
        if request.url.path == "/pub/v4/Shifts":
            page = int(
                request.url.params["page"],
            )
            size = 2
            rows = self.shifts[(page - 1) * size : page * size]
            return httpx.Response(
                status_code=200,
                json={
                    "rows": [
                        {"id": row["id"], "number": row["number"]} for row in rows
                    ],
                    "pages": max(
                        (len(self.shifts) + size - 1) // size,
                        1,
                    ),
                },
            )
        for row in self.shifts:
            if request.url.path == f"/pub/v4/Shifts/{row['id']}":
                return httpx.Response(
                    status_code=200,
                    json=row,
                )
        return httpx.Response(
            status_code=404,
        )


class TestShiftImport(LedgerApi):
    @pytest.fixture(
        autouse=True,
    )
    def setup_aqsi(
        self,
        test_app: FastAPI,
        store: FakeStore,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.aqsi = FakeAqsi()
        monkeypatch.setattr(
            target=settings,
            name="aqsi_api_integration",
            value=KEY,
        )
        test_app.dependency_overrides[aqsi_client] = lambda: AqsiClient(
            transport=httpx.MockTransport(
                handler=self.aqsi.handle,
            ),
        )

    def load(
        self,
        date_from: str = "01-10-2026",
        date_to: str = "16-10-2026",
        expected: int = 200,
    ) -> dict[str, Any]:
        return self.post(
            url="/ledger/import-shifts",
            payload={
                "date_from": date_from,
                "date_to": date_to,
            },
            expected=expected,
        )

    def test_a_closed_shift_becomes_a_sale(self) -> None:
        self.aqsi.shifts = [
            shift(
                number=284,
                closed=closed_report(
                    income=counters(
                        cash=462900,
                        cashless=2797400,
                    ),
                ),
            ),
        ]

        result = self.load()

        assert result["imported"] == [
            {
                "entry_id": self.store.entries[0].id,
                "shift_number": 284,
                "occurred_on": "14-10-2026",
                "cash": "4629.00",
                "card": "27974.00",
            },
        ]
        assert result["skipped"] == []
        entry = self.store.entries[0]
        assert (str(entry.amount), str(entry.cash), entry.comment) == (
            "-32603.00",
            "4629.00",
            "Смена aQsi №284",
        )
        assert entry.aqsi_shift_id == UUID(
            hex=self.aqsi.shifts[0]["id"],
        )
        assert self.store.locks == 1
        assert self.store.commits == 1

    def test_the_key_and_the_days_of_the_shop_go_to_aqsi(self) -> None:
        self.load(
            date_from="14-10-2026",
            date_to="14-10-2026",
        )

        request = self.aqsi.requests[0]
        assert request.headers["x-client-key"] == f"Application {KEY}"
        # the last day is included, the upper bound of aQsi is not
        assert (
            request.url.params["filtered.startDateFrom"] == "2026-10-14T00:00:00+03:00"
        )
        assert request.url.params["filtered.startDateTo"] == "2026-10-15T00:00:00+03:00"

    def test_every_page_of_the_list_is_read(self) -> None:
        self.aqsi.shifts = [
            shift(
                number=number,
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            )
            for number in (1, 2, 3, 4, 5)
        ]

        result = self.load()

        assert [row["shift_number"] for row in result["imported"]] == [1, 2, 3, 4, 5]

    def test_a_shift_over_midnight_stays_on_its_opening_day(self) -> None:
        self.aqsi.shifts = [
            shift(
                number=277,
                # the shift of the 14th in Moscow, written in UTC
                opened_at="2026-10-13T21:30:00.000Z",
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            ),
        ]

        assert self.load()["imported"][0]["occurred_on"] == "14-10-2026"

    def test_refunds_are_taken_off_the_takings(self) -> None:
        self.aqsi.shifts = [
            shift(
                number=1,
                closed=closed_report(
                    income=counters(
                        cash=100000,
                        cashless=50000,
                    ),
                    refund=counters(
                        cash=10000,
                        cashless=5000,
                    ),
                ),
            ),
        ]

        row = self.load()["imported"][0]

        assert (row["cash"], row["card"]) == ("900.00", "450.00")

    def test_a_loaded_shift_is_not_entered_twice(self) -> None:
        self.aqsi.shifts = [
            shift(
                number=1,
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            ),
        ]
        self.load()

        result = self.load()

        assert result["imported"] == []
        assert [row["reason"] for row in result["skipped"]] == ["смена уже загружена"]
        assert len(self.store.entries) == 1

    def test_a_manual_sale_of_the_same_day_does_not_stop_it(self) -> None:
        self.sale(
            amount="500.00",
            cash="500.00",
            shift=-2,
        )
        self.aqsi.shifts = [
            shift(
                number=1,
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            ),
        ]

        assert len(self.load()["imported"]) == 1
        assert len(self.store.entries) == 2

    def test_an_empty_shift_is_left_out_silently(self) -> None:
        self.aqsi.shifts = [
            shift(
                number=275,
                closed=closed_report(),
            ),
        ]

        assert self.load() == {"imported": [], "skipped": []}

    @pytest.mark.parametrize(
        argnames=("closed", "reason"),
        argvalues=[
            (None, "смена ещё не закрыта"),
            (
                closed_report(
                    income=counters(
                        cash=10000,
                        prepayment=500,
                    ),
                ),
                "есть расход, коррекция или оплата кроме наличных и безнала, занесите вручную",
            ),
            (
                closed_report(
                    income=counters(
                        cash=10000,
                    ),
                    expense=counters(
                        cash=500,
                    ),
                ),
                "есть расход, коррекция или оплата кроме наличных и безнала, занесите вручную",
            ),
            (
                closed_report(
                    income=counters(
                        cash=10000,
                    ),
                    correction=counters(
                        cash=500,
                    ),
                ),
                "есть расход, коррекция или оплата кроме наличных и безнала, занесите вручную",
            ),
            (
                closed_report(
                    income=counters(
                        cash=10000,
                    ),
                    refund=counters(
                        cash=20000,
                    ),
                ),
                "возвраты больше продаж, занесите вручную",
            ),
            (
                closed_report(
                    income=counters(
                        cash=10000,
                        cashless=20000,
                    ),
                    refund=counters(
                        cash=15000,
                    ),
                ),
                "возвраты больше продаж, занесите вручную",
            ),
        ],
    )
    def test_a_shift_that_is_not_a_plain_sale_is_skipped(
        self,
        closed: dict[str, Any] | None,
        reason: str,
    ) -> None:
        self.aqsi.shifts = [
            shift(
                number=1,
                closed=closed,
            ),
            shift(
                number=2,
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            ),
        ]

        result = self.load()

        assert [row["shift_number"] for row in result["imported"]] == [2]
        assert result["skipped"] == [
            {
                "shift_number": 1,
                "occurred_on": "14-10-2026",
                "reason": reason,
            },
        ]

    def test_a_shift_of_a_closed_period_is_skipped(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-1,
        )
        self.post(
            url="/ledger/stocktake",
            payload={
                "occurred_on": "15-10-2026",
                "counted": "1000.00",
                "comment": None,
            },
        )
        self.aqsi.shifts = [
            shift(
                number=1,
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            ),
            shift(
                number=2,
                opened_at="2026-10-15T09:25:00.000+03:00",
                closed=closed_report(
                    income=counters(
                        cash=10000,
                    ),
                ),
            ),
        ]

        result = self.load()

        assert [row["shift_number"] for row in result["imported"]] == [2]
        assert result["skipped"] == [
            {
                "shift_number": 1,
                "occurred_on": "14-10-2026",
                "reason": "Период закрыт переучётом от 15-10-2026",
            },
        ]

    def test_a_reversed_period_order_is_refused(self) -> None:
        self.load(
            date_from="16-10-2026",
            date_to="01-10-2026",
            expected=422,
        )

        assert self.aqsi.requests == []

    @pytest.mark.parametrize(
        argnames=("failure", "detail"),
        argvalues=[
            (401, "ключ не принят"),
            (500, "сервис ответил ошибкой 500"),
        ],
    )
    def test_a_refusal_of_aqsi_names_no_key(
        self,
        failure: int,
        detail: str,
    ) -> None:
        self.aqsi.failure = failure

        response = self.client.post(
            url="/ledger/import-shifts",
            json={
                "date_from": "01-10-2026",
                "date_to": "16-10-2026",
            },
        )

        assert response.status_code == 502
        assert (
            response.json()["detail"] == f"Не удалось получить данные из aQsi: {detail}"
        )
        assert KEY not in response.text
        assert self.store.entries == []

    def test_a_response_of_another_shape_enters_nothing(self) -> None:
        self.aqsi.shifts = [
            {
                **shift(
                    number=1,
                    closed=closed_report(),
                ),
                "shiftClosedReport": {"shiftCounters": {}},
            },
        ]

        self.load(
            expected=502,
        )

        assert self.store.entries == []

    def test_a_missing_key_is_named(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            target=settings,
            name="aqsi_api_integration",
            value="",
        )

        detail = self.load(
            expected=502,
        )["detail"]

        assert "AQSI_API_INTEGRATION" in detail
        assert self.aqsi.requests == []
