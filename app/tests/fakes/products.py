from collections.abc import Collection
from decimal import Decimal

from core.enums import InvoiceStatus
from invoices.models import InvoiceItem
from products.models import Product, ProductAlias
from products.repository import CatalogRow, ProductRow
from tests.fakes.store import FakeStore


class FakeProducts:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def get(
        self,
        product_id: int,
    ) -> Product | None:
        return self.store.products.get(
            product_id,
        )

    async def create(
        self,
        product: Product,
    ) -> Product:
        product.id = self.store.new_id()
        self.store.products[product.id] = product
        return product

    async def add_alias(
        self,
        alias: ProductAlias,
    ) -> ProductAlias:
        alias.id = self.store.new_id()
        self.store.aliases.append(
            alias,
        )
        return alias

    async def find_by_aliases(
        self,
        supplier_id: int,
        aliases: Collection[str],
    ) -> dict[str, Product]:
        return {
            alias.alias_normalized: self.store.products[alias.product_id]
            for alias in self.store.aliases
            if alias.supplier_id == supplier_id and alias.alias_normalized in aliases
        }

    async def aliases_of(
        self,
        supplier_id: int,
    ) -> list[tuple[str, Product]]:
        return [
            (alias.alias_normalized, self.store.products[alias.product_id])
            for alias in self.store.aliases
            if alias.supplier_id == supplier_id
        ]

    async def search(
        self,
        supplier_id: int,
        query: str | None,
        key: str | None,
        limit: int,
    ) -> list[ProductRow]:
        found = [
            product
            for product in self.store.products.values()
            if product.supplier_id == supplier_id
            and (
                not query
                or query.lower() in product.name.lower()
                or any(
                    key is not None and key in alias.alias_normalized
                    for alias in self.store.aliases
                    if alias.product_id == product.id
                )
            )
        ]
        found.sort(
            key=lambda product: (product.name, product.id),
        )
        return [
            ProductRow(
                product=product,
                last_item=self.last_item(
                    product_id=product.id,
                ),
            )
            for product in found[:limit]
        ]

    def last_item(
        self,
        product_id: int,
    ) -> InvoiceItem | None:
        """items are appended as invoices are posted, the last confirmed one is the newest"""
        for item in reversed(
            self.store.items,
        ):
            invoice = self.store.invoices.get(
                item.invoice_id,
            )
            if item.product_id == product_id and (
                invoice is None or invoice.status == InvoiceStatus.CONFIRMED
            ):
                return item
        return None

    async def last_cost_prices(
        self,
        product_ids: Collection[int],
    ) -> dict[int, Decimal]:
        costs: dict[int, Decimal] = {}
        for product_id in product_ids:
            item = self.last_item(
                product_id=product_id,
            )
            if item is not None:
                costs[product_id] = item.cost_price
        return costs

    async def rows(
        self,
        product_ids: Collection[int],
    ) -> dict[int, ProductRow]:
        return {
            product.id: ProductRow(
                product=product,
                last_item=self.last_item(
                    product_id=product.id,
                ),
            )
            for product in self.store.products.values()
            if product.id in product_ids
        }

    async def catalog(self) -> list[CatalogRow]:
        products = sorted(
            self.store.products.values(),
            key=lambda product: (product.name, product.id),
        )
        return [
            CatalogRow(
                product=product,
                last_item=self.last_item(
                    product_id=product.id,
                ),
                aliases=[
                    alias
                    for alias in self.store.aliases
                    if alias.product_id == product.id
                ],
            )
            for product in products
        ]
