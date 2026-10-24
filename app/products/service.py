from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.http import conflict, invalid
from ledger.models import RevaluationItem
from ledger.repository import LedgerRepositoryDep
from ledger.revaluation import post_revaluation
from ledger.rules import check_date
from ledger.schemas import LedgerPosted
from ledger.service import LedgerServiceDep
from products.models import Product, ProductAlias
from products.pricing import normalize_name, reprice
from products.repository import ProductRepositoryDep, ProductRow
from products.schemas import (
    Catalog,
    CatalogProduct,
    PriceTagMark,
    ProductEdit,
    ProductSummary,
)
from suppliers.repository import SupplierRepositoryDep
from suppliers.service import supplier_summary


class ProductService:
    def __init__(
        self,
        suppliers: SupplierRepositoryDep,
        products: ProductRepositoryDep,
        ledger: LedgerRepositoryDep,
        operations: LedgerServiceDep,
    ) -> None:
        self.suppliers = suppliers
        self.products = products
        self.ledger = ledger
        self.operations = operations

    async def search_products(
        self,
        supplier_id: int,
        query: str | None,
        limit: int,
    ) -> list[ProductSummary]:
        supplier = await self.suppliers.get(
            supplier_id=supplier_id,
        )
        if supplier is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Продавец не найден",
            )
        rows = await self.products.search(
            supplier_id=supplier_id,
            query=query,
            key=normalize_name(
                name=query,
            )
            if query
            else None,
            limit=limit,
        )
        return [
            product_summary(
                row=row,
            )
            for row in rows
        ]

    async def catalog(self) -> Catalog:
        suppliers = await self.suppliers.list_all()
        rows = await self.products.catalog()
        products = []
        for row in rows:
            name_key = normalize_name(
                name=row.product.name,
            )
            products.append(
                CatalogProduct(
                    **product_summary(
                        row=row,
                    ).model_dump(),
                    supplier_id=row.product.supplier_id,
                    has_price_tag=row.product.has_price_tag,
                    spellings=[
                        alias.alias_raw
                        for alias in sorted(
                            row.aliases,
                            key=lambda alias: alias.id,
                        )
                        if alias.alias_normalized != name_key
                    ],
                ),
            )
        return Catalog(
            suppliers=[
                supplier_summary(
                    supplier=supplier,
                )
                for supplier in suppliers
            ],
            products=products,
        )

    async def edit_product(
        self,
        product_id: int,
        payload: ProductEdit,
    ) -> LedgerPosted | None:
        """a corrected name keeps the old one as a spelling, a new price revalues the old stock"""
        if payload.revaluation is not None:
            await self.ledger.lock()
            await check_date(
                ledger=self.ledger,
                on=payload.revaluation.occurred_on,
                stock=True,
                cash=False,
            )
        product = await self.products.get(
            product_id=product_id,
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Товар не найден",
            )
        new_price = Decimal(
            value=payload.retail_price,
        )
        if payload.revaluation is not None and new_price == product.retail_price:
            invalid(
                detail=f"Цена уже {payload.retail_price} ₽, переоценивать нечего",
            )
        name = payload.name.strip()
        if name != product.name:
            await self._rename(
                product=product,
                name=name,
            )
        if payload.revaluation is None:
            reprice(
                product=product,
                price=new_price,
            )
            await self.ledger.commit()
            return None
        return await self.operations.finish(
            entry=await post_revaluation(
                ledger=self.ledger,
                occurred_on=payload.revaluation.occurred_on,
                comment=payload.revaluation.comment,
                items=[
                    RevaluationItem(
                        product_id=product.id,
                        invoice_item_id=None,
                        quantity=payload.revaluation.quantity,
                        old_price=product.retail_price,
                        new_price=new_price,
                    ),
                ],
                products=[
                    product,
                ],
            ),
        )

    async def mark_price_tag(
        self,
        product_id: int,
        payload: PriceTagMark,
    ) -> None:
        product = await self.products.get(
            product_id=product_id,
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Товар не найден",
            )
        if product.retail_price != payload.retail_price:
            conflict(
                detail="Цена товара изменилась, обновите страницу",
            )
        product.has_price_tag = payload.has_price_tag
        await self.ledger.commit()

    async def _rename(
        self,
        product: Product,
        name: str,
    ) -> None:
        """both spellings find the product on the next invoices"""
        key = normalize_name(
            name=name,
        )
        # the old spelling first, a name differing only in case or quotes has the same key
        spellings = {
            normalize_name(
                name=product.name,
            ): product.name,
            key: name,
        }
        known = await self.products.find_by_aliases(
            supplier_id=product.supplier_id,
            aliases=spellings.keys(),
        )
        other = known.get(
            key,
        )
        if other is not None and other.id != product.id:
            conflict(
                detail=f"Название «{name}» уже у товара «{other.name}»",
            )
        for alias_key, spelling in spellings.items():
            if alias_key not in known:
                await self.products.add_alias(
                    alias=ProductAlias(
                        product_id=product.id,
                        supplier_id=product.supplier_id,
                        alias_normalized=alias_key,
                        alias_raw=spelling,
                    ),
                )
        product.name = name


ProductServiceDep = Annotated[
    ProductService,
    Depends(
        dependency=ProductService,
    ),
]


def product_summary(row: ProductRow) -> ProductSummary:
    return ProductSummary(
        id=row.product.id,
        name=row.product.name,
        markup_pct=row.product.markup_pct,
        unit=row.last_item.unit if row.last_item else None,
        vat_percent=row.last_item.vat_percent if row.last_item else None,
        cost_price=row.last_item.cost_price if row.last_item else None,
        # the shelf price, a revaluation may have changed it after the last invoice
        retail_price=row.product.retail_price,
    )
