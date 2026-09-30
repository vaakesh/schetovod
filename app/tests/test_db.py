import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from db import DATABASE_CONNECTION_MESSAGE, get_engine, get_session
from main import app


class DatabaseConnectionApiTests(unittest.TestCase):
    def test_connection_failures_return_service_unavailable(self) -> None:
        errors = (
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
        )
        engine = AsyncMock(
            spec=AsyncEngine,
        )
        app.dependency_overrides[get_engine] = lambda: engine
        self.addCleanup(
            app.dependency_overrides.clear,
        )

        for error in errors:
            with self.subTest(
                error=type(
                    error,
                ).__name__,
            ):
                session = AsyncMock(
                    spec=AsyncSession,
                )
                session.__aenter__.return_value = session
                session.connection.side_effect = error

                with (
                    patch(
                        target="db.AsyncSession",
                        return_value=session,
                    ),
                    TestClient(
                        app=app,
                    ) as client,
                ):
                    response = client.get(
                        url="/invoice",
                    )

                self.assertEqual(
                    first=response.status_code,
                    second=503,
                )
                self.assertEqual(
                    first=response.json(),
                    second={"detail": DATABASE_CONNECTION_MESSAGE},
                )
                session.execute.assert_not_awaited()
                session.__aexit__.assert_awaited_once()


class DatabaseSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_connection_yields_session(self) -> None:
        session = AsyncMock(
            spec=AsyncSession,
        )
        session.__aenter__.return_value = session
        engine = AsyncMock(
            spec=AsyncEngine,
        )

        with patch(
            target="db.AsyncSession",
            return_value=session,
        ):
            dependency = get_session(
                engine=engine,
            )
            try:
                self.assertIs(
                    expr1=await anext(
                        dependency,
                    ),
                    expr2=session,
                )
                session.connection.assert_awaited_once()
            finally:
                await dependency.aclose()

        session.__aexit__.assert_awaited_once()

    async def test_query_errors_are_not_reported_as_connection_failures(self) -> None:
        session = AsyncMock(
            spec=AsyncSession,
        )
        session.__aenter__.return_value = session
        session.__aexit__.return_value = False
        error = IntegrityError(
            statement="INSERT INTO supplier",
            params=None,
            orig=Exception(
                "duplicate key value violates unique constraint",
            ),
        )
        engine = AsyncMock(
            spec=AsyncEngine,
        )

        with patch(
            target="db.AsyncSession",
            return_value=session,
        ):
            dependency = get_session(
                engine=engine,
            )
            await anext(
                dependency,
            )
            with self.assertRaises(
                expected_exception=IntegrityError,
            ):
                await dependency.athrow(
                    error,
                )

        session.__aexit__.assert_awaited_once()
