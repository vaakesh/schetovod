from typing import Any

from products.pricing import normalize_name

from products.models import ProductAlias
from tests.fakes import INN
from tests.helpers import InvoiceApi


class TestCatalog(InvoiceApi):
    def catalog(self) -> dict[str, Any]:
        response = self.client.get(
            url="/catalog",
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_empty_without_suppliers(self) -> None:
        assert self.catalog() == {"suppliers": [], "products": []}

    def test_lists_every_supplier_and_every_product_by_name(self) -> None:
        supplier, sugar, salt = self.known_supplier()
        other = self.store.add_supplier(
            name="Агроторг",
            inn=None,
        )
        flour = self.store.add_product(
            supplier=other,
            name="Мука",
            markup_pct="10",
            retail_price="90",
        )
        empty = self.store.add_supplier(
            name="ИП Петров",
            inn=None,
        )

        catalog = self.catalog()

        assert catalog["suppliers"] == [
            {"id": other.id, "name": "Агроторг", "short_name": None, "inn": None},
            {"id": empty.id, "name": "ИП Петров", "short_name": None, "inn": None},
            {
                "id": supplier.id,
                "name": "ООО «Поставщик»",
                "short_name": None,
                "inn": INN,
            },
        ]
        assert [
            (product["id"], product["supplier_id"]) for product in catalog["products"]
        ] == [
            (flour.id, other.id),
            (sugar.id, supplier.id),
            (salt.id, supplier.id),
        ]

    def test_shows_the_last_posted_line_and_other_spellings(self) -> None:
        supplier, sugar, _ = self.known_supplier()
        self.store.aliases.append(
            ProductAlias(
                id=self.store.new_id(),
                product_id=sugar.id,
                supplier_id=supplier.id,
                alias_normalized=normalize_name(
                    name="Песок «Русский» 1кг",
                ),
                alias_raw="Песок «Русский» 1кг",
            ),
        )
        draft = self.upload()
        assert (
            self.confirm(
                draft=draft,
            ).status_code
            == 200
        )

        assert self.catalog()["products"][0] == {
            "id": sugar.id,
            "name": "Сахар-песок 1 кг",
            "markup_pct": "30",
            "unit": "кг",
            "vat_percent": None,
            "cost_price": "50.00",
            "retail_price": "65",
            "supplier_id": supplier.id,
            # the spelling that is the name itself is not repeated
            "spellings": ["Песок «Русский» 1кг"],
            "has_price_tag": False,
        }
