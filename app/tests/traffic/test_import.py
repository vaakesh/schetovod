from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqsi.client import AqsiClient, aqsi_client
from core.config import settings
from core.enums import ReceiptKind
from tests.fakes import FakeStore

KEY = "secret-aqsi-key"
PAGE_SIZE = 2


def receipt(
    date_time: str = "2026-10-14T10:11:00.000+03:00",
    type_id: int = 1,
    total: int = 74050,
    cash: int = 50,
    cashless: int = 74000,
    positions: int = 2,
) -> dict[str, Any]:
    return {
        "id": str(
            uuid4(),
        ),
        "variant": "receipt",
        "info": {
            "shiftId": str(
                uuid4(),
            ),
            "shiftNumber": 278,
            "number": 2,
            "dateTime": date_time,
            "typeId": type_id,
            "sum": total,
            "amounts": {
                "cash": cash,
                "cashless": cashless,
                "prepayment": 0,
                "credit": 0,
                "consideration": 0,
            },
        },
        "positions": [{"id": str(index)} for index in range(positions)],
    }


class FakeAqsi:
    """the list of receipts, two of them on a page"""

    def __init__(self) -> None:
        self.receipts: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.failure: int | None = None
        self.status = 200
        self.body: bytes | None = None

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
        if self.body is not None:
            return httpx.Response(
                status_code=self.status,
                content=self.body,
            )
        page = int(
            request.url.params["page"],
        )
        return httpx.Response(
            status_code=200,
            json={
                "rows": self.receipts[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
                "pages": max(
                    (len(self.receipts) + PAGE_SIZE - 1) // PAGE_SIZE,
                    1,
                ),
            },
        )


class TestReceiptImport:
    @pytest.fixture(
        autouse=True,
    )
    def setup(
        self,
        test_app: FastAPI,
        store: FakeStore,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.client = client
        self.store = store
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
        date_from: str = "14-10-2026",
        date_to: str = "14-10-2026",
    ) -> Any:
        return self.client.post(
            url="/traffic/import",
            json={
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    def test_a_receipt_is_saved_in_rubles(self) -> None:
        source = receipt()
        self.aqsi.receipts = [
            source,
        ]

        response = self.load()

        assert response.status_code == 200
        assert response.json() == {"received": 1, "loaded": 1, "present": 0}
        saved = self.store.receipts[0]
        assert str(saved.aqsi_id) == source["id"]
        assert str(saved.shift_id) == source["info"]["shiftId"]
        assert (saved.shift_number, saved.number) == (278, 2)
        assert saved.kind == ReceiptKind.SALE
        assert saved.total == Decimal(
            value="740.50",
        )
        assert saved.cash == Decimal(
            value="0.50",
        )
        assert saved.card == Decimal(
            value="740.00",
        )
        assert saved.positions == 2
        assert saved.processed_at == datetime(
            year=2026,
            month=10,
            day=14,
            hour=7,
            minute=11,
            tzinfo=UTC,
        )
        assert self.store.commits == 1

    def test_the_key_and_the_days_of_the_shop_go_to_aqsi(self) -> None:
        self.load()

        request = self.aqsi.requests[0]
        params = request.url.params
        assert request.url.path == "/pub/v4/Receipts"
        assert request.headers["x-client-key"] == f"Application {KEY}"
        # the last day is included, the upper bound of aQsi is not
        assert params["filtered.processedAtTzFrom"] == "2026-10-14T00:00:00+03:00"
        assert params["filtered.processedAtTzTo"] == "2026-10-15T00:00:00+03:00"
        assert params["filtered.variant"] == "receipt"
        assert params["sorted[0].id"] == "processedAtTz"
        assert params["sorted[0].desc"] == "false"

    def test_every_page_of_the_list_is_read(self) -> None:
        self.aqsi.receipts = [receipt() for _ in range(5)]

        result = self.load().json()

        assert result["loaded"] == 5
        assert len(self.aqsi.requests) == 3

    def test_a_refund_is_kept_and_an_expense_is_not(self) -> None:
        self.aqsi.receipts = [
            receipt(
                type_id=1,
            ),
            receipt(
                type_id=2,
            ),
            receipt(
                type_id=3,
            ),
            receipt(
                type_id=4,
            ),
        ]

        result = self.load().json()

        assert result == {"received": 2, "loaded": 2, "present": 0}
        assert [saved.kind for saved in self.store.receipts] == [
            ReceiptKind.SALE,
            ReceiptKind.REFUND,
        ]

    def test_a_period_loaded_again_adds_only_the_new_receipts(self) -> None:
        self.aqsi.receipts = [
            receipt(),
        ]
        self.load()
        self.aqsi.receipts.append(
            receipt(),
        )

        result = self.load().json()

        assert result == {"received": 2, "loaded": 1, "present": 1}
        assert len(self.store.receipts) == 2

    def test_an_empty_period_loads_nothing(self) -> None:
        assert self.load().json() == {"received": 0, "loaded": 0, "present": 0}

    def test_the_start_can_not_be_after_the_end(self) -> None:
        response = self.load(
            date_from="15-10-2026",
            date_to="14-10-2026",
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Начало периода позже конца"
        assert self.aqsi.requests == []

    @pytest.mark.parametrize(
        argnames=("code", "detail"),
        argvalues=[
            (401, "ключ не принят"),
            (500, "сервис ответил ошибкой 500"),
        ],
    )
    def test_a_failure_of_aqsi_saves_nothing(
        self,
        code: int,
        detail: str,
    ) -> None:
        self.aqsi.failure = code

        response = self.load()

        assert response.status_code == 502
        assert (
            response.json()["detail"] == f"Не удалось получить данные из aQsi: {detail}"
        )
        assert KEY not in response.text
        assert self.store.receipts == []

    def test_the_reason_of_a_refusal_reaches_the_user(self) -> None:
        self.aqsi.status = 400
        self.aqsi.body = '{"message": "Начальная дата слишком ранняя"}'.encode()

        response = self.load()

        assert response.status_code == 502
        assert response.json()["detail"] == (
            "Не удалось получить данные из aQsi: Начальная дата слишком ранняя"
        )

    def test_a_refusal_without_a_reason_shows_its_code(self) -> None:
        self.aqsi.status = 400
        self.aqsi.body = b"oops"

        response = self.load()

        assert response.json()["detail"] == (
            "Не удалось получить данные из aQsi: сервис ответил ошибкой 400"
        )

    def test_a_response_of_another_shape_saves_nothing(self) -> None:
        self.aqsi.body = b'{"rows": [{"id": "not-a-receipt"}], "pages": 1}'

        response = self.load()

        assert response.status_code == 502
        assert self.store.receipts == []

    def test_a_time_without_a_zone_is_not_accepted(self) -> None:
        self.aqsi.receipts = [
            receipt(
                date_time="2026-10-14T10:11:00",
            ),
        ]

        assert self.load().status_code == 502
        assert self.store.receipts == []
