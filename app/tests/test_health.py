from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.db import get_session


@pytest.fixture
def database(test_app: FastAPI) -> Iterator[AsyncMock]:
    session = AsyncMock()

    async def connection() -> AsyncMock:
        return session

    test_app.dependency_overrides[get_session] = connection
    try:
        yield session
    finally:
        test_app.dependency_overrides.pop(
            get_session,
            None,
        )


class TestHealth:
    def test_returns_ok_without_authentication(
        self, anonymous_client: TestClient, database: AsyncMock
    ) -> None:
        response = anonymous_client.get(
            url="/health",
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_returns_503_when_database_query_fails(
        self, anonymous_client: TestClient, database: AsyncMock
    ) -> None:
        database.execute.side_effect = OSError()

        response = anonymous_client.get(
            url="/health",
        )

        assert response.status_code == 503
        assert response.json() == {"detail": "База данных недоступна"}
