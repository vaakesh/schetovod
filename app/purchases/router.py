from typing import Annotated

from fastapi import APIRouter, Path, Query

from purchases.schemas import (
    Period,
    PurchaseHistory,
    PurchaseOverview,
    PurchaseReport,
    Sort,
)
from purchases.service import PurchaseServiceDep

router = APIRouter()
MAX_BIGINT_ID = 2**63 - 1


@router.get(
    path="/purchases",
    response_model=PurchaseReport,
)
async def purchase_report(
    service: PurchaseServiceDep,
    period: Period = Period.DAYS_30,
    sort: Sort = Sort.FREQUENCY,
    search: Annotated[
        str | None,
        Query(
            pattern=r"^[^\x00]*$",
        ),
    ] = None,
    supplier_id: Annotated[
        int | None,
        Query(
            gt=0,
            le=MAX_BIGINT_ID,
        ),
    ] = None,
) -> PurchaseReport:
    return await service.summary(
        period=period,
        sort=sort,
        search=search,
        supplier_id=supplier_id,
    )


@router.get(
    path="/purchases/overview",
    response_model=PurchaseOverview,
)
async def purchase_overview(
    service: PurchaseServiceDep,
    period: Period = Period.DAYS_30,
    supplier_id: Annotated[
        int | None,
        Query(
            gt=0,
            le=MAX_BIGINT_ID,
        ),
    ] = None,
) -> PurchaseOverview:
    return await service.overview(
        period=period,
        supplier_id=supplier_id,
    )


@router.get(
    path="/purchases/{product_id}",
    response_model=PurchaseHistory,
)
async def purchase_history(
    service: PurchaseServiceDep,
    product_id: Annotated[
        int,
        Path(
            gt=0,
            le=MAX_BIGINT_ID,
        ),
    ],
    period: Period = Period.DAYS_30,
) -> PurchaseHistory:
    return await service.history(
        product_id=product_id,
        period=period,
    )
