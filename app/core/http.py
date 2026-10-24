from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import HTTPException, Query, status

from core.schema_types import InvoiceDate

PageLimit = Annotated[
    int,
    Query(
        ge=1,
        le=200,
    ),
]
PageOffset = Annotated[
    int,
    Query(
        ge=0,
    ),
]
ReportDate = Annotated[
    InvoiceDate,
    Query(),
]


def conflict(detail: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def invalid(detail: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detail,
    )
