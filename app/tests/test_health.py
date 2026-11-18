from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from core.db import get_gastronom_engine, get_meat_engine


@pytest.fixture
def databases(test_app: FastAPI) -> tuple[AsyncMock, AsyncMock]:
    def make_engine() -> tuple[AsyncMock, AsyncMock]:
        engine = AsyncMock(
            spec=AsyncEngine,
        )
        connection = AsyncMock(
            spec=AsyncConnection,
        )
        engine.connect.return_value.__aenter__.return_value = connection
        return engine, connection

    gastronom_engine, gastronom = make_engine()
    meat_engine, meat = make_engine()

    test_app.dependency_overrides[get_gastronom_engine] = lambda: gastronom_engine
    test_app.dependency_overrides[get_meat_engine] = lambda: meat_engine
    return gastronom, meat


class TestHealth:
    def test_returns_ok_without_authentication(
        self, anonymous_client: TestClient, databases: tuple[AsyncMock, AsyncMock]
    ) -> None:
        response = anonymous_client.get(
            url="/health",
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        gastronom, meat = databases
        gastronom.execute.assert_awaited_once()
        meat.execute.assert_awaited_once()

    @pytest.mark.parametrize(
        argnames="failed_database",
        argvalues=[0, 1],
        ids=["gastronom", "meat"],
    )
    def test_returns_503_when_database_query_fails(
        self,
        anonymous_client: TestClient,
        databases: tuple[AsyncMock, AsyncMock],
        failed_database: int,
    ) -> None:
        databases[failed_database].execute.side_effect = OSError()

        response = anonymous_client.get(
            url="/health",
        )

        assert response.status_code == 503
        assert response.json() == {"detail": "База данных недоступна"}
