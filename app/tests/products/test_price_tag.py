from typing import Any

from tests.ledger.helpers import LedgerApi


class TestPriceTag(LedgerApi):
    def mark(
        self,
        product_id: int,
        has_price_tag: bool,
        retail_price: int,
        expected: int = 204,
    ) -> Any:
        response = self.client.put(
            url=f"/product/{product_id}/price-tag",
            json={
                "has_price_tag": has_price_tag,
                "retail_price": retail_price,
            },
        )
        assert response.status_code == expected, response.text
        return response.json() if response.content else None

    def test_marks_and_unmarks_the_tag(self) -> None:
        _, sugar, _ = self.known_supplier()

        self.mark(
            product_id=sugar.id,
            has_price_tag=True,
            retail_price=65,
        )
        assert sugar.has_price_tag is True
        catalog = self.client.get(
            url="/catalog",
        ).json()
        assert [product["has_price_tag"] for product in catalog["products"]] == [
            True,
            False,
        ]

        self.mark(
            product_id=sugar.id,
            has_price_tag=False,
            retail_price=65,
        )
        assert sugar.has_price_tag is False

    def test_a_tag_for_an_older_price_is_rejected(self) -> None:
        _, sugar, _ = self.known_supplier()

        assert self.mark(
            product_id=sugar.id,
            has_price_tag=True,
            retail_price=60,
            expected=409,
        ) == {"detail": "Цена товара изменилась, обновите страницу"}

        assert sugar.has_price_tag is False
        self.mark(
            product_id=999,
            has_price_tag=True,
            retail_price=60,
            expected=404,
        )

    def test_revaluation_and_its_reversal_reset_the_tag(self) -> None:
        _, sugar, salt = self.known_supplier()
        sugar.has_price_tag = True
        salt.has_price_tag = True

        posted = self.revalue(
            lines=[
                (sugar.id, "4", 70),
            ],
        )

        assert (sugar.has_price_tag, salt.has_price_tag) == (False, True)
        sugar.has_price_tag = True
        self.reverse(
            entry_id=posted["id"],
        )
        # the old price is back on the shelf, the tag hung for the new one is wrong
        assert (sugar.retail_price, sugar.has_price_tag) == (65, False)
