from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.enums import LedgerKind
from core.http import invalid
from ledger.models import LedgerEntry, RevaluationItem
from ledger.repository import LedgerRepository, LedgerRepositoryDep
from ledger.rules import check_date
from ledger.schemas import LedgerPosted, RevaluationCreate, RevaluationLineOut
from ledger.service import LedgerServiceDep
from products.models import Product
from products.pricing import reprice, revaluation_amount
from products.repository import ProductRepositoryDep


class RevaluationService:
    def __init__(
        self,
        ledger: LedgerRepositoryDep,
        products: ProductRepositoryDep,
        operations: LedgerServiceDep,
    ) -> None:
        self.ledger = ledger
        self.products = products
        self.operations = operations

    async def add_revaluation(
        self,
        payload: RevaluationCreate,
    ) -> LedgerPosted:
        """the stock of the products on the shelf takes the new prices, the markups stay"""
        await self.ledger.lock()
        await check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=False,
        )
        items: list[RevaluationItem] = []
        products: list[Product] = []
        for line in payload.lines:
            product = await self.products.get(
                product_id=line.product_id,
            )
            if product is None:
                invalid(
                    detail=f"Товара с id {line.product_id} нет",
                )
            if product in products:
                invalid(
                    detail=f"Товар «{product.name}» указан дважды",
                )
            new_price = Decimal(
                value=line.new_price,
            )
            if new_price == product.retail_price:
                invalid(
                    detail=f"Цена товара «{product.name}» уже {line.new_price} ₽",
                )
            products.append(
                product,
            )
            items.append(
                RevaluationItem(
                    product_id=product.id,
                    invoice_item_id=None,
                    quantity=line.quantity,
                    old_price=product.retail_price,
                    new_price=new_price,
                ),
            )
        return await self.operations.finish(
            entry=await post_revaluation(
                ledger=self.ledger,
                occurred_on=payload.occurred_on,
                comment=payload.comment,
                items=items,
                products=products,
            ),
        )

    async def revaluation_lines(
        self,
        entry_id: int,
    ) -> list[RevaluationLineOut]:
        """the products of a revaluation, a reversal shows the lines it cancels"""
        entry = await self.ledger.get(
            entry_id=entry_id,
        )
        if entry is None or entry.kind != LedgerKind.REVALUATION:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Переоценка не найдена",
            )
        items = await self.ledger.revaluation_items_of(
            entry_id=entry.reverses_id or entry.id,
        )
        # a reversal takes every line back
        sign = -1 if entry.reverses_id is not None else 1
        return [
            RevaluationLineOut(
                product_id=item.product_id,
                product_name=item.product.name,
                quantity=item.quantity,
                old_price=item.old_price,
                new_price=item.new_price,
                amount=sign
                * revaluation_amount(
                    quantity=item.quantity,
                    old_price=item.old_price,
                    new_price=item.new_price,
                ),
            )
            for item in items
        ]


RevaluationServiceDep = Annotated[
    RevaluationService,
    Depends(
        dependency=RevaluationService,
    ),
]


async def post_revaluation(
    ledger: LedgerRepository,
    occurred_on: date,
    comment: str | None,
    items: list[RevaluationItem],
    products: list[Product],
) -> LedgerEntry:
    """the entry for the items, the products take the new prices"""
    amount = sum(
        (
            revaluation_amount(
                quantity=item.quantity,
                old_price=item.old_price,
                new_price=item.new_price,
            )
            for item in items
        ),
        start=Decimal(
            value=0,
        ),
    )
    if not amount:
        invalid(
            detail="Переоценка выходит меньше копейки, проверьте количество",
        )
    entry = await ledger.create(
        entry=LedgerEntry(
            kind=LedgerKind.REVALUATION,
            occurred_on=occurred_on,
            amount=amount,
            comment=comment,
        ),
    )
    for item, product in zip(
        items,
        products,
        strict=True,
    ):
        item.ledger_entry_id = entry.id
        reprice(
            product=product,
            price=item.new_price,
        )
    await ledger.add_revaluation_items(
        items=items,
    )
    return entry
