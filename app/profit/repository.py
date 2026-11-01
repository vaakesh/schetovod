from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from core.db import SessionDep
from profit.models import OperatingExpense


class ExpenseRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def add(
        self,
        expense: OperatingExpense,
    ) -> None:
        self.session.add(
            instance=expense,
        )
        await self.session.flush()

    async def get(
        self,
        expense_id: int,
    ) -> OperatingExpense | None:
        return await self.session.get(
            entity=OperatingExpense,
            ident=expense_id,
            with_for_update=True,
        )

    async def delete(
        self,
        expense: OperatingExpense,
    ) -> None:
        await self.session.delete(
            instance=expense,
        )
        await self.session.flush()

    async def all(self) -> list[OperatingExpense]:
        """every rate there ever was, the oldest first"""
        result = await self.session.scalars(
            statement=select(
                OperatingExpense,
            ).order_by(
                OperatingExpense.id,
            ),
        )
        return list(
            result.all(),
        )


ExpenseRepositoryDep = Annotated[
    ExpenseRepository,
    Depends(
        dependency=ExpenseRepository,
    ),
]
