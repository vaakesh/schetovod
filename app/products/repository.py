from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from core.db import SessionDep
from invoices.models import InvoiceItem
from products.models import Product, ProductAlias


@dataclass
class ProductRow:
    product: Product
    # the last posted line of the product, None while it was never posted
    last_item: InvoiceItem | None


@dataclass
class CatalogRow(ProductRow):
    aliases: list[ProductAlias]


class ProductRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def get(
        self,
        product_id: int,
    ) -> Product | None:
        return await self.session.get(
            entity=Product,
            ident=product_id,
        )

    async def create(
        self,
        product: Product,
    ) -> Product:
        self.session.add(
            instance=product,
        )
        await self.session.flush()
        return product

    async def add_alias(
        self,
        alias: ProductAlias,
    ) -> ProductAlias:
        self.session.add(
            instance=alias,
        )
        await self.session.flush()
        return alias

    async def find_by_aliases(
        self,
        supplier_id: int,
        aliases: Collection[str],
    ) -> dict[str, Product]:
        """supplier products keyed by the normalized alias that matched"""
        if not aliases:
            return {}
        result = await self.session.execute(
            statement=select(
                ProductAlias.alias_normalized,
                Product,
            )
            .join(
                target=Product,
                onclause=ProductAlias.product,
            )
            .where(
                ProductAlias.supplier_id == supplier_id,
                ProductAlias.alias_normalized.in_(
                    other=aliases,
                ),
            ),
        )
        # dict() would take the result for a mapping because it has keys()
        return {alias: product for alias, product in result.tuples()}

    async def aliases_of(
        self,
        supplier_id: int,
    ) -> list[tuple[str, Product]]:
        """every spelling of every supplier product, to compare names in code"""
        result = await self.session.execute(
            statement=select(
                ProductAlias.alias_normalized,
                Product,
            )
            .join(
                target=Product,
                onclause=ProductAlias.product,
            )
            .where(
                ProductAlias.supplier_id == supplier_id,
            ),
        )
        return list(
            result.tuples(),
        )

    async def search(
        self,
        supplier_id: int,
        query: str | None,
        key: str | None,
        limit: int,
    ) -> list[ProductRow]:
        """supplier products by a part of the name or of any spelling, all of them without a query"""
        statement = (
            select_with_last_item()
            .where(
                Product.supplier_id == supplier_id,
            )
            .order_by(
                Product.name,
                Product.id,
            )
            .limit(
                limit=limit,
            )
        )
        if query:
            conditions = [
                Product.name.icontains(
                    other=query,
                    autoescape=True,
                ),
            ]
            if key:
                # another spelling, e.g. the one printed on an earlier invoice
                conditions.append(
                    exists().where(
                        ProductAlias.product_id == Product.id,
                        ProductAlias.alias_normalized.contains(
                            other=key,
                            autoescape=True,
                        ),
                    ),
                )
            statement = statement.where(
                or_(
                    *conditions,
                ),
            )
        result = await self.session.execute(
            statement=statement,
        )
        return [
            ProductRow(
                product=product,
                last_item=item,
            )
            for product, item in result.tuples()
        ]

    async def last_cost_prices(
        self,
        product_ids: Collection[int],
    ) -> dict[int, Decimal]:
        """the cost price of the last posted line of each product, never posted ones are left out"""
        if not product_ids:
            return {}
        result = await self.session.execute(
            statement=select_with_last_item().where(
                Product.id.in_(
                    other=product_ids,
                ),
            ),
        )
        return {
            product.id: item.cost_price
            for product, item in result.tuples()
            if item is not None
        }

    async def catalog(self) -> list[CatalogRow]:
        """every product of every supplier with all its spellings"""
        result = await self.session.execute(
            statement=select_with_last_item()
            .options(
                selectinload(
                    Product.aliases,
                ),
            )
            .order_by(
                Product.name,
                Product.id,
            ),
        )
        return [
            CatalogRow(
                product=product,
                last_item=item,
                aliases=list(
                    product.aliases,
                ),
            )
            for product, item in result.tuples()
        ]


def select_with_last_item() -> Select[Product, InvoiceItem]:
    """products with their last posted line, the line is None while a product was never posted"""
    # the newest line of every product, items exist only for confirmed invoices
    last_item_id = (
        select(
            func.max(
                InvoiceItem.id,
            ),
        )
        .where(
            InvoiceItem.product_id == Product.id,
        )
        .scalar_subquery()
    )
    last_item = aliased(
        InvoiceItem,
    )
    return select(
        Product,
        last_item,
    ).outerjoin(
        target=last_item,
        onclause=last_item.id == last_item_id,
    )


ProductRepositoryDep = Annotated[
    ProductRepository,
    Depends(
        dependency=ProductRepository,
    ),
]
