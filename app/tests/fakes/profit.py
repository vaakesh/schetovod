from profit.models import OperatingExpense
from tests.fakes.store import FakeStore


class FakeExpenses:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def add(
        self,
        expense: OperatingExpense,
    ) -> None:
        expense.id = (
            max(
                (row.id for row in self.store.expenses),
                default=0,
            )
            + 1
        )
        self.store.expenses.append(
            expense,
        )

    async def get(
        self,
        expense_id: int,
    ) -> OperatingExpense | None:
        return next(
            (row for row in self.store.expenses if row.id == expense_id),
            None,
        )

    async def delete(
        self,
        expense: OperatingExpense,
    ) -> None:
        self.store.expenses.remove(
            expense,
        )

    async def all(self) -> list[OperatingExpense]:
        return list(
            self.store.expenses,
        )
