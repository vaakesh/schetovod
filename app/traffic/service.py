from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends

from aqsi.client import AqsiClientDep
from aqsi.schemas import AqsiReceipt
from core.config import settings, today
from core.enums import ReceiptKind
from core.http import invalid
from traffic import analytics
from traffic.models import Receipt
from traffic.repository import ReceiptRepositoryDep
from traffic.schemas import ReceiptImportResult, TrafficReport

# the receipt types of aQsi that a customer stands behind
KINDS = {
    1: ReceiptKind.SALE,
    2: ReceiptKind.REFUND,
}
KOPECKS = 100
# a till without a network sends its receipts late, they land before the last one
OVERLAP_DAYS = 7


def rubles(
    kopecks: int,
) -> Decimal:
    return (
        Decimal(
            value=kopecks,
        )
        / KOPECKS
    )


def receipt_row(
    receipt: AqsiReceipt,
) -> Receipt:
    return Receipt(
        aqsi_id=receipt.id,
        shift_id=receipt.info.shift_id,
        shift_number=receipt.info.shift_number,
        number=receipt.info.number,
        processed_at=receipt.info.date_time,
        kind=KINDS[receipt.info.type_id],
        total=rubles(
            kopecks=receipt.info.sum,
        ),
        cash=rubles(
            kopecks=receipt.info.amounts.cash,
        ),
        card=rubles(
            kopecks=receipt.info.amounts.cashless,
        ),
        positions=len(
            receipt.positions,
        ),
    )


def months_of(
    date_from: date,
    date_to: date,
) -> list[tuple[date, date]]:
    """the period cut by calendar months, the first and the last may be partial"""
    months: list[tuple[date, date]] = []
    start = date_from
    while start <= date_to:
        next_month = (
            start.replace(
                day=28,
            )
            + timedelta(
                days=4,
            )
        ).replace(
            day=1,
        )
        months.append(
            (
                start,
                min(
                    next_month
                    - timedelta(
                        days=1,
                    ),
                    date_to,
                ),
            ),
        )
        start = next_month
    return months


class TrafficService:
    def __init__(
        self,
        aqsi: AqsiClientDep,
        receipts: ReceiptRepositoryDep,
    ) -> None:
        self.aqsi = aqsi
        self.receipts = receipts

    async def load_new(self) -> ReceiptImportResult:
        """
        goes on from the last saved receipt, so a run that was missed or failed
        leaves no gap, and the receipts read twice are dropped by aqsi_id
        """
        received = 0
        loaded = 0
        for date_from, date_to in months_of(
            date_from=await self._load_from(),
            date_to=today(),
        ):
            receipts = [
                receipt_row(
                    receipt=receipt,
                )
                for receipt in await self.aqsi.receipts(
                    date_from=date_from,
                    date_to=date_to,
                )
                if receipt.info.type_id in KINDS
            ]
            loaded += await self.receipts.add_new(
                receipts=receipts,
            )
            # the months before a failure stay, the next attempt starts after them
            await self.receipts.commit()
            received += len(
                receipts,
            )
        return ReceiptImportResult(
            received=received,
            loaded=loaded,
            present=received - loaded,
        )

    async def _load_from(self) -> date:
        last_receipt_at = await self.receipts.last_receipt_at()
        if last_receipt_at is None:
            # the forecast looks this far back
            return today() - timedelta(
                weeks=analytics.BASE_WEEKS,
            )
        return last_receipt_at.astimezone(
            tz=ZoneInfo(
                key=settings.timezone,
            ),
        ).date() - timedelta(
            days=OVERLAP_DAYS,
        )

    async def report(
        self,
        date_from: date,
        date_to: date,
    ) -> TrafficReport:
        if date_from > date_to:
            invalid(
                detail="Начало периода позже конца",
            )
        current = today()
        # today is not over, a part of a day would pull every average down
        yesterday = current - timedelta(
            days=1,
        )
        date_to = min(
            date_to,
            yesterday,
        )
        base_from = current - timedelta(
            weeks=analytics.BASE_WEEKS,
        )
        rows = await self.receipts.hourly(
            date_from=min(
                date_from,
                base_from,
            ),
            date_to=yesterday,
        )
        period = [row for row in rows if date_from <= row.day <= date_to]
        return TrafficReport(
            date_from=date_from,
            date_to=date_to,
            last_receipt_at=await self.receipts.last_receipt_at(),
            summary=analytics.summary(
                rows=period,
            ),
            by_hour=analytics.by_hour(
                rows=period,
            ),
            by_weekday=analytics.by_weekday(
                rows=period,
            ),
            heatmap=analytics.heatmap(
                rows=period,
            ),
            daily=analytics.daily(
                rows=period,
            ),
            forecast=analytics.forecast(
                rows=[row for row in rows if row.day >= base_from],
                today=current,
            ),
        )


TrafficServiceDep = Annotated[
    TrafficService,
    Depends(
        dependency=TrafficService,
    ),
]
