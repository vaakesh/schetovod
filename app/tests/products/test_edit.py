from typing import Any

import pytest

from core.enums import LedgerKind
from tests.ledger.helpers import LedgerApi, day


class TestProductEdit(LedgerApi):
    def edit(
        self,
        product_id: int,
        name: str,
        retail_price: int,
        quantity: str | None = None,
        shift: int = 0,
        expected: int = 200,
    ) -> Any:
        """without a quantity the price changes without a revaluation"""
        response = self.client.put(
            url=f"/product/{product_id}",
            json={
                "name": name,
                "retail_price": retail_price,
                "revaluation": None
                if quantity is None
                else {
                    "occurred_on": day(
                        shift=shift,
                    ),
                    "quantity": quantity,
                    "comment": None,
                },
            },
        )
        assert response.status_code == expected, response.text
        return response.json()

    def spellings(self, product_id: int) -> list[str]:
        return [
            alias.alias_raw
            for alias in self.store.aliases
            if alias.product_id == product_id
        ]

    def test_corrected_name_keeps_the_old_one_as_a_spelling(self) -> None:
        _, sugar, _ = self.known_supplier()

        assert (
            self.edit(
                product_id=sugar.id,
                name="  Сахар-песок 1 кг ГОСТ ",
                retail_price=65,
            )
            is None
        )

        assert sugar.name == "Сахар-песок 1 кг ГОСТ"
        assert self.spellings(
            product_id=sugar.id,
        ) == ["Сахар-песок 1 кг", "Сахар-песок 1 кг ГОСТ"]
        assert self.store.entries == []
        catalog = self.client.get(
            url="/catalog",
        ).json()
        assert [
            product["spellings"]
            for product in catalog["products"]
            if product["id"] == sugar.id
        ] == [["Сахар-песок 1 кг"]]

    def test_a_case_fix_adds_no_spelling(self) -> None:
        _, sugar, _ = self.known_supplier()

        self.edit(
            product_id=sugar.id,
            name="САХАР-песок 1 кг",
            retail_price=65,
        )

        assert sugar.name == "САХАР-песок 1 кг"
        assert self.spellings(
            product_id=sugar.id,
        ) == ["Сахар-песок 1 кг"]

    def test_name_of_another_product_is_rejected(self) -> None:
        _, sugar, _ = self.known_supplier()

        assert self.edit(
            product_id=sugar.id,
            name="«Соль»",
            retail_price=70,
            expected=409,
        ) == {"detail": "Название ««Соль»» уже у товара «Соль»"}

        assert (sugar.name, sugar.retail_price) == ("Сахар-песок 1 кг", 65)
        assert self.spellings(
            product_id=sugar.id,
        ) == ["Сахар-песок 1 кг"]

    def test_price_without_old_stock_changes_without_an_entry(self) -> None:
        _, sugar, _ = self.known_supplier()

        self.edit(
            product_id=sugar.id,
            name="Сахар-песок 1 кг",
            retail_price=70,
        )

        assert (sugar.retail_price, sugar.markup_pct) == (70, 30)
        assert (self.store.entries, self.store.revaluations) == ([], [])

    def test_price_with_old_stock_revalues_it(self) -> None:
        self.stock(
            amount="1000.00",
        )
        _, sugar, _ = self.known_supplier()

        posted = self.edit(
            product_id=sugar.id,
            name="Сахар 1 кг",
            retail_price=70,
            quantity="4",
        )

        # 4 × (70 − 65)
        assert (posted["amount"], posted["balance"]) == ("20.00", "1020.00")
        assert self.store.entries[-1].kind == LedgerKind.REVALUATION
        assert [
            (item.product_id, item.quantity, item.old_price, item.new_price)
            for item in self.store.revaluations
        ] == [(sugar.id, 4, 65, 70)]
        assert (sugar.name, sugar.retail_price) == ("Сахар 1 кг", 70)

    def test_unchanged_price_is_not_revalued(self) -> None:
        _, sugar, _ = self.known_supplier()

        assert self.edit(
            product_id=sugar.id,
            name="Сахар 1 кг",
            retail_price=65,
            quantity="4",
            expected=422,
        ) == {"detail": "Цена уже 65 ₽, переоценивать нечего"}

        assert (sugar.name, self.store.entries) == ("Сахар-песок 1 кг", [])

    def test_unknown_product_and_closed_period(self) -> None:
        _, sugar, _ = self.known_supplier()
        self.edit(
            product_id=999,
            name="Сахар",
            retail_price=70,
            expected=404,
        )
        self.stocktake(
            counted="0",
        )

        self.edit(
            product_id=sugar.id,
            name="Сахар-песок 1 кг",
            retail_price=70,
            quantity="1",
            shift=-1,
            expected=409,
        )

        assert sugar.retail_price == 65

    @pytest.mark.parametrize(
        argnames=("retail_price", "quantity", "has_price_tag"),
        argvalues=[
            # only the name is corrected, the tag shows the same price
            (65, None, True),
            (70, None, False),
            (70, "4", False),
        ],
    )
    def test_a_new_price_resets_the_price_tag(
        self,
        retail_price: int,
        quantity: str | None,
        has_price_tag: bool,
    ) -> None:
        _, sugar, _ = self.known_supplier()
        sugar.has_price_tag = True

        self.edit(
            product_id=sugar.id,
            name="Сахар 1 кг",
            retail_price=retail_price,
            quantity=quantity,
        )

        assert sugar.has_price_tag is has_price_tag
