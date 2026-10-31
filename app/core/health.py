from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from core.db import DATABASE_CONNECTION_ERRORS, SessionDep

router = APIRouter()


@router.get(
    path="/health",
)
async def health(session: SessionDep) -> dict[str, str]:
    try:
        await session.execute(
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
