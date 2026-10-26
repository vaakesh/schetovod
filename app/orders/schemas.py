from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from core.enums import OrderStatus
from core.schema_types import FormModel, Quantity


class OrderItemSet(FormModel):
    # the whole quantity, not an addition to the one already in the cart
    quantity: Quantity


class OrderLine(BaseModel):
    product_id: int
    name: str
    supplier_id: int
    supplier_name: str
    quantity: Decimal
    # a draft shows the last posted line, a confirmed order the one it was confirmed with,
    # None while the product was never posted
    unit: str | None
    cost_price: Decimal | None
    cost_total: Decimal | None


class OrderOut(BaseModel):
    id: int
    status: OrderStatus
    # None while the order is a draft
    confirmed_at: datetime | None
    # by supplier, then by name
    lines: list[OrderLine]
    # the lines with a cost price only
    total: Decimal
    # some lines have no cost price, the total is short of them
    has_unpriced: bool


class OrderListItem(BaseModel):
    id: int
    confirmed_at: datetime
    lines: int
    supplier_names: list[str]
    total: Decimal


class OrderList(BaseModel):
    items: list[OrderListItem]
    has_more: bool
