from decimal import Decimal
from typing import Any

from products.pricing import normalize_name

from invoices.models import Invoice, InvoiceItem, InvoicePayment
from ledger.models import LedgerEntry, RevaluationItem
from products.models import Product, ProductAlias
from suppliers.models import Supplier

INN = "7701234560"
ZERO = Decimal(
    value=0,
)


def invoice_payload() -> dict[str, Any]:
    return {
        "supplier": {"name": "ООО «Поставщик»", "inn": INN},
        "invoice_number": "00042/А",
        "invoice_date": "12-08-2026",
        "items": [
            {
                "line_no": "1",
                "name": "Сахар-песок 1 кг",
                "quantity": "2.500",
                "unit": "кг",
                "base_price": "50.00",
                "base_price_total": "125.00",
                "cost_price": "50.00",
                "cost_price_total": "125.00",
                "vat_percent": None,
            },
            {
                "line_no": "2",
                "name": "Соль",
                "quantity": "1",
                "unit": "шт",
                "base_price": None,
                "base_price_total": "30.00",
                "cost_price": None,
                "cost_price_total": None,
                "vat_percent": None,
            },
        ],
        "totals": {"base_total": "155.00", "cost_total": None},
    }


class FakeStore:
    """the database for one test, the fake repositories share it"""

    def __init__(self) -> None:
        self.invoices: dict[int, Invoice] = {}
        self.suppliers: dict[int, Supplier] = {}
        self.products: dict[int, Product] = {}
        self.aliases: list[ProductAlias] = []
        self.items: list[InvoiceItem] = []
        self.payments: list[InvoicePayment] = []
        self.entries: list[LedgerEntry] = []
        self.revaluations: list[RevaluationItem] = []
        self.commits = 0
        self.locks = 0
        # the order of the ledger locks and the draft reads
        self.events: list[str] = []
        self.last_id = 0

    def new_id(self) -> int:
        self.last_id += 1
        return self.last_id

    def add_supplier(
        self,
        name: str,
        inn: str | None,
    ) -> Supplier:
        supplier = Supplier(
            id=self.new_id(),
            name=name,
            short_name=None,
            inn=inn,
        )
        self.suppliers[supplier.id] = supplier
        return supplier

    def add_product(
        self,
        supplier: Supplier,
        name: str,
        markup_pct: str,
        retail_price: str,
    ) -> Product:
        product = Product(
            id=self.new_id(),
            supplier_id=supplier.id,
            name=name,
            markup_pct=Decimal(
                value=markup_pct,
            ),
            retail_price=Decimal(
                value=retail_price,
            ),
            # the database default, a fake product is never inserted
            has_price_tag=False,
        )
        self.products[product.id] = product
        self.aliases.append(
            ProductAlias(
                id=self.new_id(),
                product_id=product.id,
                supplier_id=supplier.id,
                alias_normalized=normalize_name(
                    name=name,
                ),
                alias_raw=name,
            ),
        )
        return product
