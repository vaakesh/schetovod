from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.config import now
from core.enums import OrderStatus
from invoices.calculations import to_kopecks
from orders.models import Order, OrderItem
from orders.repository import OrderRepositoryDep
from orders.schemas import (
    OrderItemSet,
    OrderLine,
    OrderList,
    OrderListItem,
    OrderOut,
)
from products.repository import ProductRepositoryDep, ProductRow
from suppliers.models import Supplier
from suppliers.repository import SupplierRepositoryDep


class OrderService:
    def __init__(
        self,
        orders: OrderRepositoryDep,
        products: ProductRepositoryDep,
        suppliers: SupplierRepositoryDep,
    ) -> None:
        self.orders = orders
        self.products = products
        self.suppliers = suppliers

    async def draft(self) -> OrderOut | None:
        order = await self.orders.draft(
            lock=False,
        )
        if order is None:
            return None
        return await self._out(
            order=order,
        )

    async def set_item(
        self,
        product_id: int,
        payload: OrderItemSet,
    ) -> OrderOut:
        """the first product starts the cart, a product already there gets the new quantity"""
        product = await self.products.get(
            product_id=product_id,
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Товар не найден",
            )
        order = await self.orders.draft(
            lock=True,
        )
        if order is None:
            order = await self.orders.create(
                order=Order(
                    status=OrderStatus.DRAFT,
                    confirmed_at=None,
                    items=[],
                ),
            )
        item = _find_item(
            order=order,
            product_id=product_id,
        )
        if item is None:
            order.items.append(
                OrderItem(
                    product_id=product_id,
                    quantity=payload.quantity,
                    unit=None,
                    cost_price=None,
                ),
            )
        else:
            item.quantity = payload.quantity
        await self.orders.commit()
        return await self._out(
            order=order,
        )

    async def remove_item(
        self,
        product_id: int,
    ) -> OrderOut | None:
        """the cart without its last line is deleted, there is no empty draft"""
        order = await self.orders.draft(
            lock=True,
        )
        item = (
            _find_item(
                order=order,
                product_id=product_id,
            )
            if order is not None
            else None
        )
        if order is None or item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Товара нет в заказе",
            )
        order.items.remove(
            item,
        )
        if not order.items:
            await self.orders.delete(
                order=order,
            )
            await self.orders.commit()
            return None
        await self.orders.commit()
        return await self._out(
            order=order,
        )

    async def clear(self) -> None:
        order = await self.orders.draft(
            lock=True,
        )
        if order is not None:
            await self.orders.delete(
                order=order,
            )
            await self.orders.commit()

    async def confirm(self) -> OrderOut:
        """the lines keep the unit and the cost price they were ordered with"""
        order = await self.orders.draft(
            lock=True,
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Заказ пуст, подтверждать нечего",
            )
        rows = await self.products.rows(
            product_ids=[item.product_id for item in order.items],
        )
        for item in order.items:
            last_item = rows[item.product_id].last_item
            item.unit = last_item.unit if last_item else None
            item.cost_price = last_item.cost_price if last_item else None
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = now()
        await self.orders.commit()
        return await self._out(
            order=order,
        )

    async def get(
        self,
        order_id: int,
    ) -> OrderOut:
        order = await self.orders.get(
            order_id=order_id,
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Заказ не найден",
            )
        return await self._out(
            order=order,
        )

    async def list_orders(
        self,
        limit: int,
        offset: int,
    ) -> OrderList:
        # one more than asked tells whether there is another page
        orders = await self.orders.list_confirmed(
            limit=limit + 1,
            offset=offset,
        )
        items = []
        for order in orders[:limit]:
            out = await self._out(
                order=order,
            )
            if out.confirmed_at is None:
                raise RuntimeError(
                    "a confirmed order has a confirmation time",
                )
            items.append(
                OrderListItem(
                    id=out.id,
                    confirmed_at=out.confirmed_at,
                    lines=len(
                        out.lines,
                    ),
                    # the lines are sorted by supplier, each name once
                    supplier_names=list(
                        dict.fromkeys(
                            (line.supplier_name for line in out.lines),
                        ),
                    ),
                    total=out.total,
                ),
            )
        return OrderList(
            items=items,
            has_more=len(orders) > limit,
        )

    async def _out(
        self,
        order: Order,
    ) -> OrderOut:
        rows = await self.products.rows(
            product_ids=[item.product_id for item in order.items],
        )
        suppliers = {
            supplier.id: supplier for supplier in await self.suppliers.list_all()
        }
        lines = sorted(
            (
                order_line(
                    item=item,
                    row=rows[item.product_id],
                    supplier=suppliers[rows[item.product_id].product.supplier_id],
                    draft=order.status == OrderStatus.DRAFT,
                )
                for item in order.items
            ),
            key=lambda line: (
                line.supplier_name.casefold(),
                line.supplier_id,
                line.name.casefold(),
                line.product_id,
            ),
        )
        return OrderOut(
            id=order.id,
            status=order.status,
            confirmed_at=order.confirmed_at,
            lines=lines,
            total=sum(
                (line.cost_total for line in lines if line.cost_total is not None),
                start=Decimal(
                    value=0,
                ),
            ),
            has_unpriced=any(line.cost_total is None for line in lines),
        )


OrderServiceDep = Annotated[
    OrderService,
    Depends(
        dependency=OrderService,
    ),
]


def _find_item(
    order: Order,
    product_id: int,
) -> OrderItem | None:
    return next(
        (item for item in order.items if item.product_id == product_id),
        None,
    )


def order_line(
    item: OrderItem,
    row: ProductRow,
    supplier: Supplier,
    draft: bool,
) -> OrderLine:
    """a draft follows the last posted line, a confirmed order keeps its own copy"""
    if draft:
        unit = row.last_item.unit if row.last_item else None
        cost_price = row.last_item.cost_price if row.last_item else None
    else:
        unit = item.unit
        cost_price = item.cost_price
    return OrderLine(
        product_id=row.product.id,
        name=row.product.name,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        quantity=item.quantity,
        unit=unit,
        cost_price=cost_price,
        cost_total=to_kopecks(
            value=item.quantity * cost_price if cost_price is not None else None,
        ),
    )
