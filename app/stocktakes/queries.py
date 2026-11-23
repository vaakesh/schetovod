from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on

from core.db import SessionDep
from stocktakes.models import Stocktake, StocktakeLine
from stocktakes.schemas import Document, Line, Suggestion, Summary, name_key


def line_amount():
    return func.coalesce(
        StocktakeLine.entered_amount,
        func.round(
            StocktakeLine.price * StocktakeLine.quantity,
            2,
        ),
    )


class StocktakeQueries:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(self, document_id: int, *, writing: bool) -> Stocktake:
        # a shared lock keeps the header and its lines at the same revision
        doc = await self.session.scalar(
            statement=select(
                Stocktake,
            )
            .where(
                Stocktake.id == document_id,
            )
            .with_for_update(
                read=not writing,
            ),
        )
        if doc is None:
            raise HTTPException(
                status_code=404,
                detail="Переучёт не найден",
            )
        return doc

    async def history(self) -> list[Summary]:
        result = await self.session.execute(
            statement=select(
                Stocktake.id,
                Stocktake.started_at,
                Stocktake.completed_at,
                Stocktake.version,
                func.count(
                    StocktakeLine.id,
                ).label(
                    name="line_count",
                ),
                func.coalesce(
                    func.sum(
                        line_amount(),
                    ),
                    0,
                ).label(
                    name="total",
                ),
            )
            .outerjoin(
                target=StocktakeLine,
            )
            .group_by(
                Stocktake.id,
            )
            .order_by(
                Stocktake.completed_at.desc().nulls_first(),
                Stocktake.id.desc(),
            ),
        )
        return [
            Summary.model_validate(
                obj=row,
            )
            for row in result.mappings()
        ]

    async def document(self, document_id: int, since: int | None) -> Document | None:
        doc = await self.get(
            document_id=document_id,
            writing=False,
        )
        if doc.version == since:
            return None
        result = await self.session.execute(
            statement=select(
                StocktakeLine.id,
                StocktakeLine.name,
                StocktakeLine.unit,
                StocktakeLine.price,
                StocktakeLine.quantity,
                StocktakeLine.version,
                line_amount().label(
                    name="amount",
                ),
            )
            .where(
                StocktakeLine.document_id == document_id,
            )
            .order_by(
                StocktakeLine.id.desc(),
            ),
        )
        lines = [
            Line.model_validate(
                obj=row,
            )
            for row in result.mappings()
        ]
        return Document(
            id=doc.id,
            started_at=doc.started_at,
            completed_at=doc.completed_at,
            version=doc.version,
            line_count=len(
                lines,
            ),
            total=sum(
                (line.amount for line in lines),
                start=Decimal(
                    value="0.00",
                ),
            ),
            lines=lines,
        )

    async def suggestions(self, document_id: int, query: str) -> list[Suggestion]:
        key = name_key(
            name=query,
        )
        current = StocktakeLine.document_id == document_id
        # an amount without a unit price keeps the last known price for the same unit
        historical_price = func.first_value(
            StocktakeLine.price,
        ).over(
            partition_by=[StocktakeLine.name_key, StocktakeLine.unit],
            order_by=[
                StocktakeLine.price.is_(
                    other=None,
                ),
                Stocktake.completed_at.desc().nulls_last(),
                Stocktake.id.desc(),
            ],
        )
        latest = (
            select(
                StocktakeLine.name_key,
                StocktakeLine.name,
                StocktakeLine.unit,
                case(
                    (current, StocktakeLine.price),
                    else_=historical_price,
                ).label(
                    name="price",
                ),
                case(
                    (current, StocktakeLine.id),
                ).label(
                    name="current_line_id",
                ),
                case(
                    (current, StocktakeLine.quantity),
                ).label(
                    name="current_quantity",
                ),
                case(
                    (current, line_amount()),
                ).label(
                    name="current_amount",
                ),
            )
            .join(
                target=Stocktake,
            )
            .where(
                or_(
                    current,
                    Stocktake.completed_at.is_not(
                        other=None,
                    ),
                ),
                StocktakeLine.name_key.contains(
                    other=key,
                    autoescape=True,
                ),
            )
            .ext(
                distinct_on(
                    StocktakeLine.name_key,
                ),
            )
            .order_by(
                StocktakeLine.name_key,
                current.desc(),
                Stocktake.completed_at.desc(),
                Stocktake.id.desc(),
            )
            .subquery()
        )
        result = await self.session.execute(
            statement=select(
                latest,
            )
            .order_by(
                (latest.c.name_key == key).desc(),
                latest.c.name_key,
            )
            .limit(
                limit=15,
            ),
        )
        return [
            Suggestion.model_validate(
                obj=row,
            )
            for row in result.mappings()
        ]


QueriesDep = Annotated[
    StocktakeQueries,
    Depends(
        dependency=StocktakeQueries,
    ),
]
