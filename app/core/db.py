from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import MetaData
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from core.store import Store, StoreDep

DATABASE_CONNECTION_MESSAGE = (
    "Не удалось подключиться к базе данных. "
    "Проверьте настройки PostgreSQL в .env и доступность сервера базы данных."
)
DATABASE_CONNECTION_ERRORS = (
    DBAPIError,
    SQLAlchemyTimeoutError,
    OSError,
    TimeoutError,
)

# postgres style names for constraints and indexes,
# a check constraint gets its short name from the model, e.g. "quantity"
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",
    "ck": "%(table_name)s_%(constraint_name)s_check",
}


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention=NAMING_CONVENTION,
    )


@cache
def get_gastronom_engine() -> AsyncEngine:
    return create_async_engine(
        url=settings.database_url,
    )


@cache
def get_meat_engine() -> AsyncEngine:
    return create_async_engine(
        url=settings.meat_database_url,
    )


@asynccontextmanager
async def open_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(
        bind=engine,
        expire_on_commit=False,
    ) as session:
        try:
            await session.connection()
        except DATABASE_CONNECTION_ERRORS as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=DATABASE_CONNECTION_MESSAGE,
            ) from error
        yield session


async def get_auth_session(
    engine: Annotated[
        AsyncEngine,
        Depends(
            dependency=get_gastronom_engine,
        ),
    ],
) -> AsyncGenerator[AsyncSession]:
    async with open_session(
        engine=engine,
    ) as session:
        yield session


AuthSessionDep = Annotated[
    AsyncSession,
    Depends(
        dependency=get_auth_session,
    ),
]


async def get_session(
    store: StoreDep,
    auth_session: AuthSessionDep,
) -> AsyncGenerator[AsyncSession]:
    if store is Store.GASTRONOM:
        yield auth_session
        return

    async with open_session(
        engine=get_meat_engine(),
    ) as session:
        yield session


SessionDep = Annotated[
    AsyncSession,
    Depends(
        dependency=get_session,
    ),
]
