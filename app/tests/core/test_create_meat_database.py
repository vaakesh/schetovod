from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from migrations import create_meat_database


class TestCreateMeatDatabase:
    async def test_rejects_existing_custom_template_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connection = AsyncMock(
            spec=AsyncConnection,
        )
        connection.scalar.return_value = True
        context = MagicMock()
        context.__aenter__.return_value = connection
        engine = AsyncMock(
            spec=AsyncEngine,
        )
        engine.connect.return_value = context
        monkeypatch.setattr(
            target=create_meat_database,
            name="create_async_engine",
            value=Mock(
                return_value=engine,
            ),
        )

        with pytest.raises(
            expected_exception=ValueError,
            match="POSTGRES_MEAT_DB не может указывать на шаблон базы PostgreSQL",
        ):
            await create_meat_database.create_meat_database()

        connection.exec_driver_sql.assert_not_awaited()
        engine.dispose.assert_awaited_once()
