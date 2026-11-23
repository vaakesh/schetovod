import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from auth.dependencies import get_current_user
from tests.fakes import signed_in_user

ROOT = "/stores/gastronom/stocktakes"


@pytest.fixture
async def api(
    test_app: FastAPI, stocktake_engine: AsyncEngine
) -> AsyncIterator[AsyncClient]:
    test_app.dependency_overrides[get_current_user] = signed_in_user
    async with AsyncClient(
        transport=ASGITransport(
            app=test_app,
        ),
        base_url="http://test",
    ) as client:
        yield client


def token(number: int) -> str:
    return str(
        UUID(
            int=number,
        ),
    )


def line(
    number: int,
    name: str = "Мёд",
    price: str = "15,50",
    quantity: str = "10",
    unit: str = "шт",
) -> dict[str, str]:
    return {
        "request_id": token(
            number=number,
        ),
        "name": name,
        "unit": unit,
        "price": price,
        "quantity": quantity,
    }


async def start(api: AsyncClient, number: int = 1) -> int:
    response = await api.post(
        url=f"{ROOT}/open",
        json={
            "request_id": token(
                number=number,
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["line_id"] is None
    return response.json()["document_id"]


async def finish(api: AsyncClient, doc: int, version: int) -> None:
    response = await api.post(
        url=f"{ROOT}/{doc}/complete",
        json={"version": version},
    )
    assert response.status_code == 204


class TestOpen:
    async def test_simultaneous_starts_and_lost_response_share_document(
        self,
        api: AsyncClient,
    ) -> None:
        ids = await asyncio.gather(
            start(
                api=api,
                number=1,
            ),
            start(
                api=api,
                number=2,
            ),
        )
        assert ids == [1, 1]
        await finish(
            api=api,
            doc=1,
            version=1,
        )

        assert (
            await start(
                api=api,
                number=2,
            )
            == 1
        )
        assert (
            await start(
                api=api,
                number=3,
            )
            == 2
        )


class TestLines:
    async def test_parallel_additions_round_each_line_before_summing(
        self, api: AsyncClient
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}"
        a, b = await asyncio.gather(
            api.post(
                url=f"{path}/lines",
                json=line(
                    number=2,
                    name="Молоко 1 л",
                    unit="кг",
                    price="0,50",
                    quantity="0,01",
                ),
            ),
            api.post(
                url=f"{path}/lines",
                json=line(
                    number=3,
                    name="Молоко 0,5 л",
                    unit="кг",
                    price="1",
                    quantity="0,005",
                ),
            ),
        )
        assert a.status_code == b.status_code == 200

        detail = await api.get(
            url=path,
        )
        history = await api.get(
            url=ROOT,
        )
        poll = await api.get(
            url=path,
            params={"since": 3},
        )

        assert detail.status_code == history.status_code == poll.status_code == 200
        assert poll.json() is None
        summary = detail.json()
        assert [
            item["amount"]
            for item in summary.pop(
                "lines",
            )
        ] == ["0.01", "0.01"]
        assert history.json() == [summary]
        assert summary == {
            "id": 1,
            "version": 3,
            "line_count": 2,
            "completed_at": None,
            "started_at": summary["started_at"],
            "total": "0.02",
        }

    async def test_duplicate_returns_winning_line_and_current_quantity(
        self, api: AsyncClient
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}"
        results = await asyncio.gather(
            api.post(
                url=f"{path}/lines",
                json=line(
                    number=2,
                    name="  МЁД   липовый  ",
                    quantity="0",
                ),
            ),
            api.post(
                url=f"{path}/lines",
                json=line(
                    number=3,
                    name="мед липовый",
                    quantity="0",
                    unit="кг",
                ),
            ),
        )
        saved, duplicate = sorted(
            results,
            key=lambda response: response.status_code,
        )
        assert saved.status_code == 200
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "duplicate"
        assert duplicate.json()["detail"]["line_id"] == saved.json()["line_id"]

        found = await api.get(
            url=f"{path}/suggestions",
            params={"q": "МёД  "},
        )
        assert found.status_code == 200
        assert (
            len(
                found.json(),
            )
            == 1
        )
        assert found.json()[0]["current_line_id"] == saved.json()["line_id"]
        assert found.json()[0]["current_quantity"] == "0.000"

    async def test_concurrent_edits_require_explicit_choice(
        self, api: AsyncClient
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}/lines"
        added = await api.post(
            url=path,
            json=line(
                number=2,
            ),
        )
        assert added.status_code == 200
        url = f"{path}/{added.json()['line_id']}"

        results = await asyncio.gather(
            api.put(
                url=url,
                json={
                    **line(
                        number=3,
                        quantity="13",
                    ),
                    "version": 1,
                },
            ),
            api.put(
                url=url,
                json={
                    **line(
                        number=4,
                        quantity="15",
                    ),
                    "version": 1,
                },
            ),
        )
        saved, conflict = sorted(
            results,
            key=lambda response: response.status_code,
        )
        assert saved.status_code == 200
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "line_changed"
        resolved = await api.put(
            url=url,
            json={
                **line(
                    number=5,
                    quantity="17",
                ),
                "version": 2,
            },
        )
        assert resolved.status_code == 200

    async def test_retries_after_delete_do_not_recreate_or_recount(
        self, api: AsyncClient
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}"
        create = line(
            number=2,
        )
        added = await api.post(
            url=f"{path}/lines",
            json=create,
        )
        assert added.status_code == 200
        url = f"{path}/lines/{added.json()['line_id']}"
        delete = {
            "request_id": token(
                number=3,
            ),
            "version": 1,
        }

        first = await api.request(
            method="DELETE",
            url=url,
            json=delete,
        )
        replay = await api.request(
            method="DELETE",
            url=url,
            json=delete,
        )
        delayed = await api.post(
            url=f"{path}/lines",
            json=create,
        )
        document = await api.get(
            url=path,
        )

        assert (
            first.status_code
            == replay.status_code
            == delayed.status_code
            == document.status_code
            == 200
        )
        assert first.json() == replay.json() == added.json() == delayed.json()
        assert document.json()["version"] == 3
        assert document.json()["lines"] == []

    @pytest.mark.parametrize(
        argnames=("unit", "quantity", "price"),
        argvalues=[
            ("шт", "1,1", "2"),
            ("кг", "1,0001", "2"),
            ("кг", "", "2"),
            ("кг", "-1", "2"),
            ("шт", "1", "1,999"),
        ],
    )
    async def test_rejects_invalid_measurement(
        self, api: AsyncClient, unit: str, quantity: str, price: str
    ) -> None:
        response = await api.post(
            url=f"{ROOT}/1/lines",
            json=line(
                number=2,
                unit=unit,
                quantity=quantity,
                price=price,
            ),
        )
        assert response.status_code == 422


class TestEnteredAmount:
    @pytest.mark.parametrize(
        argnames=("entered", "expected"),
        argvalues=[("0", "0.00"), ("167,89", "167.89")],
    )
    async def test_saves_exact_amount_without_price_or_quantity(
        self, api: AsyncClient, entered: str, expected: str
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}"
        payload = {
            "request_id": token(
                number=2,
            ),
            "name": "Сыр",
            "unit": "кг",
            "entered_amount": entered,
        }
        saved = await api.post(
            url=f"{path}/lines",
            json=payload,
        )
        replay = await api.post(
            url=f"{path}/lines",
            json=payload,
        )
        read = await api.get(
            url=path,
        )
        found = await api.get(
            url=f"{path}/suggestions",
            params={"q": "сыр"},
        )

        assert (
            saved.status_code
            == replay.status_code
            == read.status_code
            == found.status_code
            == 200
        )
        assert saved.json() == replay.json() == {"document_id": doc, "line_id": 1}
        assert read.json()["total"] == expected
        assert read.json()["lines"] == [
            {
                "id": 1,
                "name": "Сыр",
                "unit": "кг",
                "price": None,
                "quantity": None,
                "amount": expected,
                "version": 1,
            }
        ]
        assert found.json() == [
            {
                "name": "Сыр",
                "unit": "кг",
                "price": None,
                "current_quantity": None,
                "current_amount": expected,
                "current_line_id": 1,
            }
        ]

    async def test_switches_measurement_in_both_directions_and_recalculates_history(
        self, api: AsyncClient
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}/lines"
        saved = await api.post(
            url=path,
            json=line(
                number=2,
            ),
        )
        assert saved.status_code == 200
        url = f"{path}/{saved.json()['line_id']}"

        manual = await api.put(
            url=url,
            json={
                "request_id": token(
                    number=3,
                ),
                "name": "Мёд",
                "unit": "шт",
                "price": "11",
                "entered_amount": "27.82",
                "version": 1,
            },
        )
        history = await api.get(
            url=ROOT,
        )
        assert manual.status_code == history.status_code == 200
        assert history.json()[0]["total"] == "27.82"

        counted = await api.put(
            url=url,
            json={
                **line(
                    number=4,
                    price="2",
                    quantity="3",
                ),
                "version": 2,
            },
        )
        read = await api.get(
            url=f"{ROOT}/{doc}",
        )
        assert counted.status_code == read.status_code == 200
        assert read.json()["lines"][0]["quantity"] == "3.000"
        assert read.json()["total"] == "6.00"

    @pytest.mark.parametrize(
        argnames="measurement",
        argvalues=[
            {},
            {"quantity": "2"},
            {"price": "2", "quantity": "1", "entered_amount": "2"},
            {"entered_amount": "-1"},
            {"entered_amount": "1,005"},
            {"entered_amount": ""},
        ],
    )
    async def test_rejects_invalid_measurement(
        self, api: AsyncClient, measurement: dict[str, str]
    ) -> None:
        response = await api.post(
            url=f"{ROOT}/1/lines",
            json={
                "request_id": token(
                    number=2,
                ),
                "name": "Сыр",
                "unit": "кг",
                **measurement,
            },
        )
        assert response.status_code == 422


class TestComplete:
    async def test_concurrent_addition_cannot_silently_change_confirmed_total(
        self, api: AsyncClient
    ) -> None:
        doc = await start(
            api=api,
        )
        path = f"{ROOT}/{doc}"
        add, complete = await asyncio.gather(
            api.post(
                url=f"{path}/lines",
                json=line(
                    number=2,
                ),
            ),
            api.post(
                url=f"{path}/complete",
                json={"version": 1},
            ),
        )

        result = await api.get(
            url=path,
        )
        assert result.status_code == 200
        if add.status_code == 200:
            assert complete.status_code == 409
            assert complete.json()["detail"]["code"] == "document_changed"
            assert result.json()["completed_at"] is None
            assert result.json()["total"] == "155.00"
        else:
            assert add.status_code == 409
            assert add.json()["detail"]["code"] == "document_state"
            assert complete.status_code == 204
            assert result.json()["lines"] == []
            assert result.json()["completed_at"] is not None


class TestSuggestions:
    @pytest.mark.parametrize(
        argnames=("latest_unit", "expected_price"),
        argvalues=[("кг", "49.50"), ("шт", None)],
    )
    async def test_amount_only_entry_keeps_latest_unit_and_compatible_known_price(
        self, api: AsyncClient, latest_unit: str, expected_price: str | None
    ) -> None:
        first = await start(
            api=api,
        )
        priced = await api.post(
            url=f"{ROOT}/{first}/lines",
            json=line(
                number=2,
                price="49.50",
                unit="кг",
            ),
        )
        assert priced.status_code == 200
        await finish(
            api=api,
            doc=first,
            version=2,
        )
        second = await start(
            api=api,
            number=3,
        )
        manual = await api.post(
            url=f"{ROOT}/{second}/lines",
            json={
                "request_id": token(
                    number=4,
                ),
                "name": "Мёд",
                "unit": latest_unit,
                "entered_amount": "121.14",
            },
        )
        assert manual.status_code == 200
        await finish(
            api=api,
            doc=second,
            version=2,
        )
        current = await start(
            api=api,
            number=5,
        )

        found = await api.get(
            url=f"{ROOT}/{current}/suggestions",
            params={"q": "мед"},
        )

        assert found.status_code == 200
        assert found.json() == [
            {
                "name": "Мёд",
                "unit": latest_unit,
                "price": expected_price,
                "current_line_id": None,
                "current_quantity": None,
                "current_amount": None,
            }
        ]

    async def test_old_correction_changes_only_names_without_a_newer_count(
        self, api: AsyncClient
    ) -> None:
        old = await start(
            api=api,
        )
        honey = await api.post(
            url=f"{ROOT}/{old}/lines",
            json=line(
                number=2,
            ),
        )
        assert honey.status_code == 200
        await finish(
            api=api,
            doc=old,
            version=2,
        )
        newer = await start(
            api=api,
            number=3,
        )
        saved = await api.post(
            url=f"{ROOT}/{newer}/lines",
            json=line(
                number=4,
                price="75",
                unit="кг",
            ),
        )
        assert saved.status_code == 200
        await finish(
            api=api,
            doc=newer,
            version=2,
        )
        current = await start(
            api=api,
            number=5,
        )

        corrected = await api.put(
            url=f"{ROOT}/{old}/lines/{honey.json()['line_id']}?correction=true",
            json={
                **line(
                    number=6,
                    price="99",
                ),
                "version": 1,
            },
        )
        extra = await api.post(
            url=f"{ROOT}/{old}/lines?correction=true",
            json=line(
                number=7,
                name="Мёд лесной",
                price="50",
            ),
        )
        found = await api.get(
            url=f"{ROOT}/{current}/suggestions",
            params={"q": "МЕд"},
        )
        empty = await api.get(
            url=f"{ROOT}/{current}",
        )

        assert (
            corrected.status_code
            == extra.status_code
            == found.status_code
            == empty.status_code
            == 200
        )
        assert empty.json()["lines"] == []
        assert found.json() == [
            {
                "name": "Мёд",
                "price": "75.00",
                "unit": "кг",
                "current_line_id": None,
                "current_quantity": None,
                "current_amount": None,
            },
            {
                "name": "Мёд лесной",
                "price": "50.00",
                "unit": "шт",
                "current_line_id": None,
                "current_quantity": None,
                "current_amount": None,
            },
        ]
