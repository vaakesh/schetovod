from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

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
def get_engine() -> AsyncEngine:
    # one engine with a connection pool per process
    return create_async_engine(
        url=settings.database_url,
    )


async def get_session(
    engine: Annotated[
        AsyncEngine,
        Depends(
            dependency=get_engine,
        ),
    ],
) -> AsyncIterator[AsyncSession]:
    # a new session per request, closed after the response
    async with AsyncSession(
        bind=engine,
        expire_on_commit=False,
    ) as session:
        yield session


SessionDep = Annotated[
    AsyncSession,
    Depends(
        dependency=get_session,
    ),
]
