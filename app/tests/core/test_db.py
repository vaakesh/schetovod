from collections.abc import Iterator
from contextlib import aclosing
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from core import db
from core.db import get_engine, get_session


@pytest.fixture
def engine() -> AsyncMock:
    return AsyncMock(
        spec=AsyncEngine,
    )


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    session = AsyncMock(
        spec=AsyncSession,
    )
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    monkeypatch.setattr(
        target=db,
        name="AsyncSession",
        value=lambda **kwargs: session,
    )
    return session


@pytest.fixture
def database_client(test_app: FastAPI, engine: AsyncMock) -> Iterator[TestClient]:
    test_app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(
        app=test_app,
    ) as client:
        yield client


class TestDatabaseConnection:
    @pytest.mark.parametrize(
        argnames="error",
        argvalues=[
            ConnectionRefusedError(),
            TimeoutError(),
            SQLAlchemyTimeoutError(),
            DBAPIError(
                statement=None,
                params=None,
                orig=Exception(
                    "password authentication failed for user schetovod",
                ),
            ),
        ],
        ids=["refused", "timeout", "pool-timeout", "authentication"],
    )
    def test_returns_503_when_connection_fails(
        self,
        database_client: TestClient,
        session: AsyncMock,
        error: Exception,
    ) -> None:
        session.connection.side_effect = error

        response = database_client.get(
            url="/invoice",
        )

        assert response.status_code == 503
        assert response.json() == {
            "detail": (
                "Не удалось подключиться к базе данных. "
                "Проверьте настройки PostgreSQL в .env и доступность сервера базы данных."
            ),
        }
        session.execute.assert_not_awaited()
        session.__aexit__.assert_awaited_once()


class TestGetSession:
    async def test_yields_session_when_connection_succeeds(
        self,
        engine: AsyncMock,
        session: AsyncMock,
    ) -> None:
        async with aclosing(
            thing=get_session(
                engine=engine,
            ),
        ) as dependency:
            result = await anext(
                dependency,
            )

            assert result is session
            session.connection.assert_awaited_once()

        session.__aexit__.assert_awaited_once()

    async def test_propagates_query_errors_without_reporting_connection_failure(
        self,
        engine: AsyncMock,
        session: AsyncMock,
    ) -> None:
        error = IntegrityError(
            statement="INSERT INTO supplier",
            params=None,
            orig=Exception(
                "duplicate key value violates unique constraint",
            ),
        )

        async with aclosing(
            thing=get_session(
                engine=engine,
            ),
        ) as dependency:
            await anext(
                dependency,
            )
            with pytest.raises(
                expected_exception=IntegrityError,
            ) as raised:
                await dependency.athrow(
                    error,
                )

        assert raised.value is error
        session.__aexit__.assert_awaited_once()
