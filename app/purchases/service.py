from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from statistics import median
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.config import today
from purchases.repository import PurchaseRepositoryDep, SummaryRow, UnitWindow
from purchases.schemas import (
    Period,
    PriceTrend,
    PriceTrendStatus,
    ProductSummary,
    PurchaseHistory,
    PurchaseLine,
    PurchaseOverview,
    PurchaseReport,
    Sort,
)

_TWO_PLACES = Decimal(
    value="0.01",
)
_PERIOD_DAYS = {
    Period.DAYS_30: 30,
    Period.DAYS_60: 60,
    Period.DAYS_90: 90,
}


def _since(*, as_of: date, period: Period) -> date | None:
    if period == Period.ALL:
        return None
    return as_of - timedelta(
        days=_PERIOD_DAYS[period] - 1,
    )


def _trend_status(*, change_pct: Decimal | None) -> PriceTrendStatus:
    if change_pct is None:
        return "insufficient"
    if change_pct >= 5:
        return "rapid_growth"
    if -2 <= change_pct <= 2:
        return "stable"
    return "rising" if change_pct > 0 else "falling"


def _price_trend(*, units: list[UnitWindow]) -> PriceTrend:
    if (
        len(
            units,
        )
        != 1
        or not units[0].unit
    ):
        return PriceTrend(
            unit=None,
            current_average=None,
            previous_average=None,
            current_deliveries=None,
            previous_deliveries=None,
            change_pct=None,
            status="insufficient",
        )

    window = units[0]
    current_average = (
        window.current_cost / window.current_quantity
        if window.current_quantity
        else None
    )
    previous_average = (
        window.previous_cost / window.previous_quantity
        if window.previous_quantity
        else None
    )
    change_pct = None
    if (
        current_average is not None
        and previous_average is not None
        and previous_average > 0
    ):
        change_pct = (
            (current_average - previous_average) * 100 / previous_average
        ).quantize(
            exp=_TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )
    return PriceTrend(
        unit=window.unit,
        current_average=current_average.quantize(
            exp=_TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )
        if current_average is not None
        else None,
        previous_average=previous_average.quantize(
            exp=_TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )
        if previous_average is not None
        else None,
        current_deliveries=window.current_deliveries,
        previous_deliveries=window.previous_deliveries,
        change_pct=change_pct,
        status=_trend_status(
            change_pct=change_pct,
        ),
    )


def _product_summary(*, row: SummaryRow, as_of: date) -> ProductSummary:
    gaps = [
        Decimal(
            value=(newer - older).days,
        )
        for newer, older in pairwise(
            row.recent_days,
        )
    ]
    interval = (
        median(
            data=gaps,
        )
        if len(
            gaps,
        )
        >= 3
        else None
    )
    days_since = (as_of - row.last_on).days
    return ProductSummary(
        product_id=row.product_id,
        name=row.name,
        supplier_id=row.supplier_id,
        supplier_name=row.supplier_name,
        deliveries=row.deliveries,
        lifetime_deliveries=row.lifetime_deliveries,
        spend=row.spend,
        last_on=row.last_on,
        days_since=days_since,
        usual_interval_days=interval,
        overdue=interval is not None and days_since > interval * 3 / 2,
        price_trend=_price_trend(
            units=row.units,
        ),
    )


class PurchaseService:
    def __init__(self, repository: PurchaseRepositoryDep) -> None:
        self.repository = repository

    async def overview(
        self,
        *,
        period: Period,
        supplier_id: int | None,
    ) -> PurchaseOverview:
        as_of = today()
        return await self.repository.overview(
            as_of=as_of,
            since=_since(
                as_of=as_of,
                period=period,
            ),
            supplier_id=supplier_id,
        )

    async def summary(
        self,
        *,
        period: Period,
        sort: Sort,
        search: str | None,
        supplier_id: int | None,
    ) -> PurchaseReport:
        as_of = today()
        rows = await self.repository.summaries(
            as_of=as_of,
            since=_since(
                as_of=as_of,
                period=period,
            ),
            search=(search or "").strip() or None,
            supplier_id=supplier_id,
        )
        if sort == Sort.LAST_DELIVERY:
            rows.sort(
                key=lambda row: (row.last_on, row.name.casefold(), row.product_id),
            )
        else:
            rows = [row for row in rows if row.deliveries > 0]
            rows.sort(
                key=lambda row: (
                    -row.spend if sort == Sort.SPEND else -row.deliveries,
                    row.name.casefold(),
                    row.product_id,
                ),
            )
        return PurchaseReport(
            as_of=as_of,
            period=period,
            items=[
                _product_summary(
                    row=row,
                    as_of=as_of,
                )
                for row in rows
            ],
        )

    async def history(self, *, product_id: int, period: Period) -> PurchaseHistory:
        as_of = today()
        since = _since(
            as_of=as_of,
            period=period,
        )
        rows = await self.repository.summaries(
            as_of=as_of,
            since=since,
            search=None,
            supplier_id=None,
            product_id=product_id,
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Поставки товара не найдены",
            )
        lines = await self.repository.history(
            as_of=as_of,
            since=since,
            product_id=product_id,
        )
        return PurchaseHistory(
            as_of=as_of,
            period=period,
            product=_product_summary(
                row=rows[0],
                as_of=as_of,
            ),
            lines=[
                PurchaseLine.model_validate(
                    obj=line,
                    from_attributes=True,
                )
                for line in lines
            ],
        )


PurchaseServiceDep = Annotated[
    PurchaseService,
    Depends(
        dependency=PurchaseService,
    ),
]
