from fastapi import APIRouter, status

from core.http import PageLimit, PageOffset
from orders.schemas import OrderItemSet, OrderList, OrderOut
from orders.service import OrderServiceDep

router = APIRouter()


@router.get(
    path="/order/draft",
    response_model=OrderOut | None,
)
async def draft_order(
    service: OrderServiceDep,
) -> OrderOut | None:
    return await service.draft()


@router.put(
    path="/order/draft/items/{product_id}",
    response_model=OrderOut,
)
async def set_order_item(
    product_id: int,
    payload: OrderItemSet,
    service: OrderServiceDep,
) -> OrderOut:
    return await service.set_item(
        product_id=product_id,
        payload=payload,
    )


@router.delete(
    path="/order/draft/items/{product_id}",
    response_model=OrderOut | None,
)
async def remove_order_item(
    product_id: int,
    service: OrderServiceDep,
) -> OrderOut | None:
    return await service.remove_item(
        product_id=product_id,
    )


@router.delete(
    path="/order/draft",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_order(
    service: OrderServiceDep,
) -> None:
    await service.clear()


@router.post(
    path="/order/draft/confirm",
    response_model=OrderOut,
)
async def confirm_order(
    service: OrderServiceDep,
) -> OrderOut:
    return await service.confirm()


@router.get(
    path="/orders",
    response_model=OrderList,
)
async def list_orders(
    service: OrderServiceDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> OrderList:
    return await service.list_orders(
        limit=limit,
        offset=offset,
    )


@router.get(
    path="/order/{order_id}",
    response_model=OrderOut,
)
async def get_order(
    order_id: int,
    service: OrderServiceDep,
) -> OrderOut:
    return await service.get(
        order_id=order_id,
    )
