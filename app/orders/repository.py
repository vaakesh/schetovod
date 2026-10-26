from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.db import SessionDep
from core.enums import OrderStatus
from orders.models import Order


class OrderRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def draft(
        self,
        lock: bool,
    ) -> Order | None:
        """the cart with its lines, locked when it is about to change"""
        statement = (
            select(
                Order,
            )
            .where(
                Order.status == OrderStatus.DRAFT,
            )
            .options(
                selectinload(
                    Order.items,
                ),
            )
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(
            statement=statement,
        )

    async def get(
        self,
        order_id: int,
    ) -> Order | None:
        return await self.session.scalar(
            statement=select(
                Order,
            )
            .where(
                Order.id == order_id,
            )
            .options(
                selectinload(
                    Order.items,
                ),
            ),
        )

    async def create(
        self,
        order: Order,
    ) -> Order:
        self.session.add(
            instance=order,
        )
        await self.session.flush()
        return order

    async def delete(
        self,
        order: Order,
    ) -> None:
        await self.session.delete(
            instance=order,
        )

    async def list_confirmed(
        self,
        limit: int,
        offset: int,
    ) -> list[Order]:
        """the newest confirmed first, with their lines"""
        result = await self.session.scalars(
            statement=select(
                Order,
            )
            .where(
                Order.status == OrderStatus.CONFIRMED,
            )
            .options(
                selectinload(
                    Order.items,
                ),
            )
            .order_by(
                Order.confirmed_at.desc(),
                Order.id.desc(),
            )
            .limit(
                limit=limit,
            )
            .offset(
                offset=offset,
            ),
        )
        return list(
            result,
        )

    async def commit(self) -> None:
        await self.session.commit()


OrderRepositoryDep = Annotated[
    OrderRepository,
    Depends(
        dependency=OrderRepository,
    ),
]
