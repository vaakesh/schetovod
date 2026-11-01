from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Date, Integer, case, cast, extract, func, select
from sqlalchemy.dialects.postgresql import insert

from aqsi.client import start_of_day
from core.config import settings
from core.db import SessionDep
from core.enums import ReceiptKind
from traffic.analytics import DayTakings, HourRow
from traffic.models import Receipt

# postgres takes a limited number of parameters in one statement
BATCH_SIZE = 1000


class ReceiptRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def add_new(
        self,
        receipts: Sequence[Receipt],
    ) -> int:
        """the number of receipts that were not here before"""
        added = 0
        for start in range(
            0,
            len(
                receipts,
            ),
            BATCH_SIZE,
        ):
            result = await self.session.scalars(
                statement=insert(
                    table=Receipt,
                )
                .values(
                    [
                        {
                            "aqsi_id": receipt.aqsi_id,
                            "shift_id": receipt.shift_id,
                            "shift_number": receipt.shift_number,
                            "number": receipt.number,
                            "processed_at": receipt.processed_at,
                            "kind": receipt.kind,
                            "total": receipt.total,
                            "cash": receipt.cash,
                            "card": receipt.card,
                            "positions": receipt.positions,
                        }
                        for receipt in receipts[start : start + BATCH_SIZE]
                    ],
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        Receipt.aqsi_id,
                    ],
                )
                .returning(
                    Receipt.id,
                ),
            )
            added += len(
                result.all(),
            )
        return added

    async def hourly(
        self,
        date_from: date,
        date_to: date,
    ) -> list[HourRow]:
        """the receipts by the days and hours of the shop, not of the server"""
        local = func.timezone(
            settings.timezone,
            Receipt.processed_at,
        )
        day = cast(
            expression=local,
            type_=Date,
        ).label(
            name="day",
        )
        hour = cast(
            expression=extract(
                field="hour",
                expr=local,
            ),
            type_=Integer,
        ).label(
            name="hour",
        )
        is_sale = Receipt.kind == ReceiptKind.SALE
        rows = await self.session.execute(
            statement=select(
                day,
                hour,
                func.count().filter(
                    is_sale,
                ),
                func.sum(
                    case(
                        (
                            is_sale,
                            Receipt.total,
                        ),
                        else_=-Receipt.total,
                    ),
                ),
            )
            .where(
                Receipt.processed_at
                >= start_of_day(
                    day=date_from,
                ),
                Receipt.processed_at
                < start_of_day(
                    day=date_to
                    + timedelta(
                        days=1,
                    ),
                ),
            )
            .group_by(
                day,
                hour,
            ),
        )
        return [
            HourRow(
                day=row_day,
                hour=row_hour,
                sales=sales,
                revenue=revenue,
            )
            for row_day, row_hour, sales, revenue in rows.tuples()
        ]

    async def daily_takings(self) -> list[DayTakings]:
        """every day of the shop with receipts, oldest first, the refunds are taken away"""
        day = cast(
            expression=func.timezone(
                settings.timezone,
                Receipt.processed_at,
            ),
            type_=Date,
        ).label(
            name="day",
        )
        is_sale = Receipt.kind == ReceiptKind.SALE
        rows = await self.session.execute(
            statement=select(
                day,
                func.sum(
                    case(
                        (
                            is_sale,
                            Receipt.total,
                        ),
                        else_=-Receipt.total,
                    ),
                ),
                func.sum(
                    case(
                        (
                            is_sale,
                            Receipt.card,
                        ),
                        else_=-Receipt.card,
                    ),
                ),
            )
            .group_by(
                day,
            )
            .order_by(
                day,
            ),
        )
        return [
            DayTakings(
                day=row_day,
                revenue=revenue,
                card=card,
            )
            for row_day, revenue, card in rows.tuples()
        ]

    async def last_receipt_at(self) -> datetime | None:
        return await self.session.scalar(
            statement=select(
                func.max(
                    Receipt.processed_at,
                ),
            ),
        )


ReceiptRepositoryDep = Annotated[
    ReceiptRepository,
    Depends(
        dependency=ReceiptRepository,
    ),
]
