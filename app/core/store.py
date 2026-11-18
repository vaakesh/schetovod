from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status


class Store(StrEnum):
    GASTRONOM = "gastronom"
    MEAT = "meat"


async def get_store(request: Request) -> Store:
    name = request.path_params.get(
        "store",
        Store.GASTRONOM,
    )
    try:
        return Store(
            name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Магазин не найден",
        ) from error


StoreDep = Annotated[
    Store,
    Depends(
        dependency=get_store,
    ),
]
