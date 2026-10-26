from core.enums import OrderStatus
from orders.models import Order
from tests.fakes.store import FakeStore


class FakeOrders:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def draft(
        self,
        lock: bool,
    ) -> Order | None:
        return next(
            (
                order
                for order in self.store.orders.values()
                if order.status == OrderStatus.DRAFT
            ),
            None,
        )

    async def get(
        self,
        order_id: int,
    ) -> Order | None:
        return self.store.orders.get(
            order_id,
        )

    async def create(
        self,
        order: Order,
    ) -> Order:
        order.id = self.store.new_id()
        self.store.orders[order.id] = order
        return order

    async def delete(
        self,
        order: Order,
    ) -> None:
        del self.store.orders[order.id]

    async def list_confirmed(
        self,
        limit: int,
        offset: int,
    ) -> list[Order]:
        confirmed = sorted(
            (
                order
                for order in self.store.orders.values()
                if order.status == OrderStatus.CONFIRMED
            ),
            key=lambda order: (order.confirmed_at, order.id),
            reverse=True,
        )
        return confirmed[offset : offset + limit]

    async def commit(self) -> None:
        self.store.commits += 1
