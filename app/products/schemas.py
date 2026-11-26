from decimal import Decimal

from pydantic import BaseModel

from core.schema_types import (
    FormModel,
    InvoiceDate,
    PositiveShelfPrice,
    Quantity,
    ShelfPrice,
    Text,
)
from suppliers.schemas import SupplierSummary


class ProductSummary(BaseModel):
    id: int
    name: str
    markup_pct: Decimal
    # from the last posted line, None while the product was never posted
    unit: str | None
    vat_percent: Decimal | None
    cost_price: Decimal | None
    retail_price: Decimal | None


class CatalogAlias(BaseModel):
    id: int
    name: str


class CatalogProduct(ProductSummary):
    supplier_id: int
    # other names the product was printed with, the name itself is not repeated
    spellings: list[str]
    aliases: list[CatalogAlias]
    # a shelf tag with the current retail price is hanging
    has_price_tag: bool


class Catalog(BaseModel):
    # every supplier, including the ones without products yet
    suppliers: list[SupplierSummary]
    products: list[CatalogProduct]


class ProductRevaluation(FormModel):
    occurred_on: InvoiceDate
    # the old stock counted on the shelf
    quantity: Quantity
    comment: Text | None


class ProductEdit(FormModel):
    # the old name stays as another spelling of the product
    name: Text
    retail_price: PositiveShelfPrice
    # None when there is no old stock, the price then changes without a ledger entry
    revaluation: ProductRevaluation | None


class PriceTagMark(FormModel):
    has_price_tag: bool
    # the price the user saw, a tag hung for an older price is not the current one
    retail_price: ShelfPrice
