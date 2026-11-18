from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from auth.cookies import ACCESS_COOKIE
from auth.models import UserSession
from auth.security import create_access_token
from core import db
from suppliers.models import Supplier
from tests.fakes import signed_in_user


@pytest.fixture
def store_sessions(
    test_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> tuple[AsyncMock, AsyncMock, Mock]:
    gastronom_engine = Mock(
        spec=AsyncEngine,
    )
    meat_engine = Mock(
        spec=AsyncEngine,
    )
    gastronom = AsyncMock(
        spec=AsyncSession,
    )
    gastronom.__aenter__.return_value = gastronom
    gastronom.scalar.return_value = UserSession(
        user=signed_in_user(),
    )
    meat = AsyncMock(
        spec=AsyncSession,
    )
    meat.__aenter__.return_value = meat
    sessions = {gastronom_engine: gastronom, meat_engine: meat}
    session_factory = Mock(
        side_effect=lambda bind, expire_on_commit: sessions[bind],
    )
    test_app.dependency_overrides[db.get_gastronom_engine] = lambda: gastronom_engine
    monkeypatch.setattr(
        target=db,
        name="get_meat_engine",
        value=lambda: meat_engine,
    )
    monkeypatch.setattr(
        target=db,
        name="AsyncSession",
        value=session_factory,
    )
    return gastronom, meat, session_factory


@pytest.fixture
def signed_in_client(test_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(
        app=test_app,
        base_url="https://testserver",
    ) as client:
        client.cookies.set(
            name=ACCESS_COOKIE,
            value=create_access_token(
                user_id=1,
                session_id=1,
            ),
        )
        yield client


class TestStoreDatabase:
    @pytest.mark.parametrize(
        argnames=("path", "name", "session_count"),
        argvalues=[
            ("/supplier", "Поставщик гастронома", 1),
            ("/stores/gastronom/supplier", "Поставщик гастронома", 1),
            ("/stores/meat/supplier", "Поставщик мясного", 2),
        ],
    )
    def test_reads_suppliers_from_selected_database_and_authenticates_in_gastronom(
        self,
        signed_in_client: TestClient,
        store_sessions: tuple[AsyncMock, AsyncMock, Mock],
        path: str,
        name: str,
        session_count: int,
    ) -> None:
        gastronom, meat, session_factory = store_sessions
        gastronom.scalars.return_value = [
            Supplier(
                id=1,
                name="Поставщик гастронома",
            ),
        ]
        meat.scalars.return_value = [
            Supplier(
                id=1,
                name="Поставщик мясного",
            ),
        ]

        response = signed_in_client.get(
            url=path,
            params={"store": "meat"},
        )

        assert response.status_code == 200
        assert response.json() == [
            {"id": 1, "name": name, "short_name": None, "inn": None},
        ]
        assert session_factory.call_count == session_count
        gastronom.scalar.assert_awaited_once()
        meat.scalar.assert_not_awaited()

    def test_meat_write_changes_only_meat_supplier(
        self,
        signed_in_client: TestClient,
        store_sessions: tuple[AsyncMock, AsyncMock, Mock],
    ) -> None:
        gastronom, meat, _ = store_sessions
        gastronom.get.return_value = Supplier(
            id=1,
            name="Поставщик гастронома",
        )
        meat.get.return_value = Supplier(
            id=1,
            name="Поставщик мясного",
        )

        response = signed_in_client.put(
            url="/stores/meat/supplier/1",
            json={"name": "Новый поставщик мясного", "short_name": None, "inn": None},
        )

        assert response.status_code == 200
        assert response.json() == {
            "id": 1,
            "name": "Новый поставщик мясного",
            "short_name": None,
            "inn": None,
        }
        meat.commit.assert_awaited_once()
        gastronom.get.assert_not_awaited()
        gastronom.commit.assert_not_awaited()


class TestStoreRoutes:
    def test_unknown_store_returns_404(self, anonymous_client: TestClient) -> None:
        response = anonymous_client.get(
            url="/stores/unknown/supplier",
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Магазин не найден"}

    @pytest.mark.parametrize(
        argnames=("method", "path"),
        argvalues=[
            ("GET", "/orders"),
            ("GET", "/order/draft"),
            ("GET", "/profit"),
            ("GET", "/traffic/report"),
            ("GET", "/traffic/forecast"),
            ("POST", "/ledger/import-shifts"),
        ],
    )
    def test_gastronom_only_routes_return_404_in_meat(
        self, client: TestClient, method: str, path: str
    ) -> None:
        response = client.request(
            method=method,
            url=f"/stores/meat{path}",
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}

    @pytest.mark.parametrize(
        argnames="store",
        argvalues=["gastronom", "meat"],
    )
    def test_both_stores_require_authentication(
        self, anonymous_client: TestClient, store: str
    ) -> None:
        response = anonymous_client.get(
            url=f"/stores/{store}/supplier",
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Требуется вход"}
