from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema, DropSchema

from auth.models import User, UserSession
from core.config import settings
from core.db import Base, get_gastronom_engine
from stocktakes import events, service
from stocktakes.models import Stocktake, StocktakeLine, StocktakeRequest


@pytest.fixture
async def stocktake_engine(
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    schema = f"count_test_{uuid4().hex}"
    # PostgreSQL notification channels are shared across schemas
    monkeypatch.setattr(
        target=events,
        name="CHANNEL",
        value=schema,
    )
    monkeypatch.setattr(
        target=service,
        name="CHANNEL",
        value=schema,
    )
    engine = create_async_engine(
        url=settings.database_url,
        connect_args={"server_settings": {"search_path": schema}},
        # the websocket test client runs in a separate event loop
        poolclass=NullPool,
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                statement=CreateSchema(
                    name=schema,
                ),
            )
            await connection.run_sync(
                fn=Base.metadata.create_all,
                tables=[
                    Base.metadata.tables[model.__tablename__]
                    for model in (
                        User,
                        UserSession,
                        Stocktake,
                        StocktakeLine,
                        StocktakeRequest,
                    )
                ],
            )
        test_app.dependency_overrides[get_gastronom_engine] = lambda: engine
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                statement=DropSchema(
                    name=schema,
                    cascade=True,
                    if_exists=True,
                ),
            )
        await engine.dispose()
