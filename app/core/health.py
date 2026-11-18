from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from core.db import DATABASE_CONNECTION_ERRORS, get_gastronom_engine, get_meat_engine

router = APIRouter()


@router.get(
    path="/health",
)
async def health(
    gastronom: Annotated[
        AsyncEngine,
        Depends(
            dependency=get_gastronom_engine,
        ),
    ],
    meat: Annotated[
        AsyncEngine,
        Depends(
            dependency=get_meat_engine,
        ),
    ],
) -> dict[str, str]:
    try:
        for engine in (gastronom, meat):
            async with engine.connect() as connection:
                await connection.execute(
                    statement=select(
                        1,
                    ),
                )
    except DATABASE_CONNECTION_ERRORS as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных недоступна",
        ) from error
    return {"status": "ok"}
