from typing import Any

import pytest
from products.pricing import normalize_name

from products.models import ProductAlias
from tests.helpers import InvoiceApi


class TestProductSearch(InvoiceApi):
    def search(
        self,
        supplier_id: int,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        response = self.client.get(
            url=f"/supplier/{supplier_id}/products",
            params=params,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_without_a_query_lists_the_supplier_products_by_name(self) -> None:
        supplier, sugar, salt = self.known_supplier()
        other = self.store.add_supplier(
            name="ИП Иванов",
            inn=None,
        )
        self.store.add_product(
            supplier=other,
            name="Сахар у другого",
            markup_pct="10",
            retail_price="100",
        )

        assert self.search(
            supplier_id=supplier.id,
            params={},
        ) == [
            {
                "id": sugar.id,
                "name": "Сахар-песок 1 кг",
                "markup_pct": "30",
                "unit": None,
                "vat_percent": None,
                "cost_price": None,
                # the shelf price is known before the product is ever posted
                "retail_price": "65",
            },
            {
                "id": salt.id,
                "name": "Соль",
                "markup_pct": "20",
                "unit": None,
                "vat_percent": None,
                "cost_price": None,
                "retail_price": "36",
            },
        ]

    @pytest.mark.parametrize(
        argnames="query",
        argvalues=("САХ", 'песок "русский"'),
    )
    def test_finds_by_a_part_of_the_name_or_of_another_spelling(
        self,
        query: str,
    ) -> None:
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

        assert [
            product["id"]
            for product in self.search(
                supplier_id=supplier.id,
                params={"q": query},
            )
        ] == [sugar.id]

    def test_shows_the_last_posted_line(self) -> None:
        supplier, sugar, _ = self.known_supplier()
        draft = self.upload()
        assert (
            self.confirm(
                draft=draft,
            ).status_code
            == 200
        )

        found = self.search(
            supplier_id=supplier.id,
            params={"q": "сахар"},
        )

        assert found[0] == {
            "id": sugar.id,
            "name": "Сахар-песок 1 кг",
            "markup_pct": "30",
            "unit": "кг",
            "vat_percent": None,
            "cost_price": "50.00",
            "retail_price": "65",
        }

    def test_returns_404_when_supplier_does_not_exist(self) -> None:
        response = self.client.get(
            url="/supplier/999/products",
        )

        assert response.status_code == 404
