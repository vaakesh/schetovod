from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from taskiq import SmartRetryMiddleware
from taskiq.schedule_sources import LabelScheduleSource

from aqsi.client import AqsiClient
from core.broker import ATTEMPTS, broker, delayed_tasks, scheduler
from core.config import settings
from core.enums import ReceiptKind
from tests.fakes import FakeReceipts, FakeStore
from traffic.models import Receipt
from traffic.repository import ReceiptRepository
from traffic.schemas import ReceiptImportResult
from traffic.service import TrafficService, months_of
from traffic.tasks import import_receipts

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


def saved(
    processed_at: datetime,
) -> Receipt:
    return Receipt(
        aqsi_id=uuid4(),
        shift_id=uuid4(),
        processed_at=processed_at,
        kind=ReceiptKind.SALE,
        total=Decimal(
            value=100,
        ),
        cash=Decimal(
            value=100,
        ),
        card=Decimal(
            value=0,
        ),
        positions=1,
    )


class FakeAqsi:
    """the list of receipts, two of them on a page"""

    def __init__(self) -> None:
        self.receipts: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.failure: int | None = None
        # the failure starts with this period, the ones before it answer
        self.failing_from: str = ""
        self.body: bytes | None = None

    def handle(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.requests.append(
            request,
        )
        if (
            self.failure is not None
            and request.url.params["filtered.processedAtTzFrom"] >= self.failing_from
        ):
            return httpx.Response(
                status_code=self.failure,
            )
        if self.body is not None:
            return httpx.Response(
                status_code=200,
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

    def periods(self) -> list[tuple[str, str]]:
        return [
            (
                request.url.params["filtered.processedAtTzFrom"],
                request.url.params["filtered.processedAtTzTo"],
            )
            for request in self.requests
            if request.url.params["page"] == "1"
        ]


class TestReceiptImport:
    @pytest.fixture(
        autouse=True,
    )
    def setup(
        self,
        store: FakeStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.store = store
        self.aqsi = FakeAqsi()
        monkeypatch.setattr(
            target=settings,
            name="aqsi_api_integration",
            value=KEY,
        )

    async def load(self) -> ReceiptImportResult:
        return await TrafficService(
            aqsi=AqsiClient(
                transport=httpx.MockTransport(
                    handler=self.aqsi.handle,
                ),
            ),
            receipts=cast(
                ReceiptRepository,
                FakeReceipts(
                    store=self.store,
                ),
            ),
        ).load_new()

    def result(
        self,
        received: int,
        loaded: int,
        present: int,
    ) -> ReceiptImportResult:
        return ReceiptImportResult(
            received=received,
            loaded=loaded,
            present=present,
        )

    async def test_a_receipt_is_saved_in_rubles(self) -> None:
        source = receipt()
        self.aqsi.receipts = [
            source,
        ]
        # one month and a single answer, the same receipt is not read twice
        self.store.receipts = [
            saved(
                processed_at=datetime(
                    year=2026,
                    month=10,
                    day=15,
                    tzinfo=UTC,
                ),
            ),
        ]

        await self.load()

        row = self.store.receipts[1]
        assert str(row.aqsi_id) == source["id"]
        assert str(row.shift_id) == source["info"]["shiftId"]
        assert (row.shift_number, row.number) == (278, 2)
        assert row.kind == ReceiptKind.SALE
        assert row.total == Decimal(
            value="740.50",
        )
        assert row.cash == Decimal(
            value="0.50",
        )
        assert row.card == Decimal(
            value="740.00",
        )
        assert row.positions == 2
        assert row.processed_at == datetime(
            year=2026,
            month=10,
            day=14,
            hour=7,
            minute=11,
            tzinfo=UTC,
        )
        assert self.store.commits == 1

    async def test_an_empty_base_loads_as_far_back_as_the_forecast_looks(self) -> None:
        await self.load()

        assert self.aqsi.periods() == [
            ("2026-07-24T00:00:00+03:00", "2026-08-01T00:00:00+03:00"),
            ("2026-08-01T00:00:00+03:00", "2026-09-01T00:00:00+03:00"),
            ("2026-09-01T00:00:00+03:00", "2026-10-01T00:00:00+03:00"),
            ("2026-10-01T00:00:00+03:00", "2026-10-17T00:00:00+03:00"),
        ]

    async def test_loading_goes_on_from_a_week_before_the_last_receipt(self) -> None:
        self.store.receipts = [
            # the day of the shop, it is already the 13th in Moscow
            saved(
                processed_at=datetime(
                    year=2026,
                    month=10,
                    day=12,
                    hour=22,
                    tzinfo=UTC,
                ),
            ),
        ]

        await self.load()

        assert self.aqsi.periods() == [
            ("2026-10-06T00:00:00+03:00", "2026-10-17T00:00:00+03:00"),
        ]

    async def test_a_missed_week_leaves_no_gap(self) -> None:
        self.store.receipts = [
            saved(
                processed_at=datetime(
                    year=2026,
                    month=9,
                    day=10,
                    hour=12,
                    tzinfo=UTC,
                ),
            ),
        ]

        await self.load()

        assert self.aqsi.periods() == [
            ("2026-09-03T00:00:00+03:00", "2026-10-01T00:00:00+03:00"),
            ("2026-10-01T00:00:00+03:00", "2026-10-17T00:00:00+03:00"),
        ]

    async def test_the_key_goes_to_aqsi(self) -> None:
        await self.load()

        request = self.aqsi.requests[0]
        params = request.url.params
        assert request.url.path == "/pub/v4/Receipts"
        assert request.headers["x-client-key"] == f"Application {KEY}"
        assert params["filtered.variant"] == "receipt"
        assert params["sorted[0].id"] == "processedAtTz"
        assert params["sorted[0].desc"] == "false"

    async def test_every_page_of_the_list_is_read(self) -> None:
        self.store.receipts = [
            saved(
                processed_at=datetime(
                    year=2026,
                    month=10,
                    day=15,
                    tzinfo=UTC,
                ),
            ),
        ]
        self.aqsi.receipts = [receipt() for _ in range(5)]

        result = await self.load()

        assert result.loaded == 5
        assert len(self.aqsi.requests) == 3

    async def test_a_refund_is_kept_and_an_expense_is_not(self) -> None:
        self.store.receipts = [
            saved(
                processed_at=datetime(
                    year=2026,
                    month=10,
                    day=15,
                    tzinfo=UTC,
                ),
            ),
        ]
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

        result = await self.load()

        assert result == self.result(
            received=2,
            loaded=2,
            present=0,
        )
        assert [row.kind for row in self.store.receipts[1:]] == [
            ReceiptKind.SALE,
            ReceiptKind.REFUND,
        ]

    async def test_a_receipt_read_again_is_not_repeated(self) -> None:
        self.aqsi.receipts = [
            receipt(),
        ]
        self.store.receipts = [
            saved(
                processed_at=datetime(
                    year=2026,
                    month=10,
                    day=15,
                    tzinfo=UTC,
                ),
            ),
        ]
        await self.load()
        self.aqsi.receipts.append(
            receipt(),
        )

        result = await self.load()

        assert result == self.result(
            received=2,
            loaded=1,
            present=1,
        )
        assert len(self.store.receipts) == 3

    async def test_nothing_new_loads_nothing(self) -> None:
        self.store.receipts = [
            saved(
                processed_at=datetime(
                    year=2026,
                    month=10,
                    day=15,
                    tzinfo=UTC,
                ),
            ),
        ]

        assert await self.load() == self.result(
            received=0,
            loaded=0,
            present=0,
        )

    async def test_a_failure_keeps_the_months_before_it(self) -> None:
        self.aqsi.receipts = [
            receipt(
                date_time="2026-09-20T10:11:00.000+03:00",
            ),
        ]
        self.aqsi.failure = 500
        self.aqsi.failing_from = "2026-08-01"

        with pytest.raises(
            expected_exception=HTTPException,
        ):
            await self.load()

        assert len(self.store.receipts) == 1
        assert self.store.commits == 1

    async def test_the_next_attempt_goes_on_after_a_failure(self) -> None:
        self.aqsi.receipts = [
            receipt(
                date_time="2026-09-20T10:11:00.000+03:00",
            ),
        ]
        self.aqsi.failure = 500
        self.aqsi.failing_from = "2026-08-01"
        with pytest.raises(
            expected_exception=HTTPException,
        ):
            await self.load()
        self.aqsi.requests.clear()
        self.aqsi.failure = None

        await self.load()

        assert self.aqsi.periods()[0][0] == "2026-09-13T00:00:00+03:00"
        assert len(self.store.receipts) == 1

    @pytest.mark.parametrize(
        argnames=("code", "detail"),
        argvalues=[
            (401, "ключ не принят"),
            (500, "сервис ответил ошибкой 500"),
        ],
    )
    async def test_a_failure_of_aqsi_saves_nothing(
        self,
        code: int,
        detail: str,
    ) -> None:
        self.aqsi.failure = code

        with pytest.raises(
            expected_exception=HTTPException,
        ) as error:
            await self.load()

        assert error.value.detail == f"Не удалось получить данные из aQsi: {detail}"
        assert KEY not in error.value.detail
        assert self.store.receipts == []

    async def test_a_response_of_another_shape_saves_nothing(self) -> None:
        self.aqsi.body = b'{"rows": [{"id": "not-a-receipt"}], "pages": 1}'

        with pytest.raises(
            expected_exception=HTTPException,
        ):
            await self.load()

        assert self.store.receipts == []

    async def test_a_time_without_a_zone_is_not_accepted(self) -> None:
        self.aqsi.receipts = [
            receipt(
                date_time="2026-10-14T10:11:00",
            ),
        ]

        with pytest.raises(
            expected_exception=HTTPException,
        ):
            await self.load()

        assert self.store.receipts == []


class TestMonthsOf:
    def test_a_period_within_a_month_stays_whole(self) -> None:
        assert months_of(
            date_from=date(
                year=2026,
                month=10,
                day=3,
            ),
            date_to=date(
                year=2026,
                month=10,
                day=16,
            ),
        ) == [
            (
                date(
                    year=2026,
                    month=10,
                    day=3,
                ),
                date(
                    year=2026,
                    month=10,
                    day=16,
                ),
            ),
        ]

    def test_a_period_is_cut_over_a_short_month_and_a_new_year(self) -> None:
        months = months_of(
            date_from=date(
                year=2025,
                month=12,
                day=31,
            ),
            date_to=date(
                year=2026,
                month=3,
                day=1,
            ),
        )

        assert [(start.isoformat(), end.isoformat()) for start, end in months] == [
            ("2025-12-31", "2025-12-31"),
            ("2026-01-01", "2026-01-31"),
            ("2026-02-01", "2026-02-28"),
            ("2026-03-01", "2026-03-01"),
        ]


class TestSchedule:
    def test_the_task_runs_every_ten_minutes(self) -> None:
        assert import_receipts.labels["schedule"] == [
            {
                "cron": "*/10 * * * *",
                "cron_offset": "Europe/Moscow",
            },
        ]

    def test_a_failed_task_waits_for_the_next_run(self) -> None:
        assert import_receipts.labels["retry_on_error"] is False

    def test_a_delayed_attempt_goes_through_the_schedule_source(self) -> None:
        retry = cast(
            SmartRetryMiddleware,
            broker.middlewares[0],
        )

        assert retry.default_retry_count == ATTEMPTS
        # without a source the delay of a Redis broker is ignored
        assert retry.schedule_source is delayed_tasks

    def test_the_scheduler_reads_the_delayed_attempts(self) -> None:
        sources = scheduler.sources

        assert isinstance(
            sources[0],
            LabelScheduleSource,
        )
        assert sources[1] is delayed_tasks
