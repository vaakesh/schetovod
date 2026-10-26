from datetime import timedelta
from decimal import Decimal
from typing import Any

from core.enums import OrderStatus
from tests.helpers import InvoiceApi


class TestOrders(InvoiceApi):
    def set_item(
        self,
        product_id: int,
        quantity: Any,
        expected: int = 200,
    ) -> Any:
        response = self.client.put(
            url=f"/order/draft/items/{product_id}",
            json={
                "quantity": quantity,
            },
        )
        assert response.status_code == expected, response.text
        return response.json()

    def remove_item(
        self,
        product_id: int,
        expected: int = 200,
    ) -> Any:
        response = self.client.delete(
            url=f"/order/draft/items/{product_id}",
        )
        assert response.status_code == expected, response.text
        return response.json()

    def draft(self) -> Any:
        response = self.client.get(
            url="/order/draft",
        )
        assert response.status_code == 200, response.text
        return response.json()

    def confirm_order(
        self,
        expected: int = 200,
    ) -> Any:
        response = self.client.post(
            url="/order/draft/confirm",
        )
        assert response.status_code == expected, response.text
        return response.json()

    def orders(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        response = self.client.get(
            url="/orders",
            params={
                "limit": limit,
                "offset": offset,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def posted_supplier(self) -> tuple[int, int]:
        """sugar and salt with a posted invoice, so they have a unit and a cost price"""
        _, sugar, salt = self.known_supplier()
        assert (
            self.confirm(
                draft=self.upload(),
            ).status_code
            == 200
        )
        return sugar.id, salt.id

    def test_no_draft_at_first(self) -> None:
        assert self.draft() is None
        assert self.orders() == {"items": [], "has_more": False}

    def test_the_first_product_starts_the_cart_and_another_quantity_replaces_it(
        self,
    ) -> None:
        sugar, salt = self.posted_supplier()

        first = self.set_item(
            product_id=sugar,
            quantity="3",
        )
        self.set_item(
            product_id=salt,
            quantity="2",
        )
        order = self.set_item(
            product_id=sugar,
            quantity="1.5",
        )

        assert order["id"] == first["id"]
        assert order["status"] == OrderStatus.DRAFT
        assert order["confirmed_at"] is None
        # the fake keeps the quantity as sent, the database pads it
        assert [
            (
                line["name"],
                Decimal(
                    value=line["quantity"],
                ),
                line["unit"],
                line["cost_total"],
            )
            for line in order["lines"]
        ] == [
            (
                "Сахар-песок 1 кг",
                Decimal(
                    value="1.5",
                ),
                "кг",
                "75.00",
            ),
            (
                "Соль",
                Decimal(
                    value=2,
                ),
                "шт",
                "60.00",
            ),
        ]
        assert order["lines"][0]["supplier_name"] == "ООО «Поставщик»"
        assert (order["total"], order["has_unpriced"]) == ("135.00", False)
        assert self.draft() == order

    def test_a_never_posted_product_is_ordered_without_a_price(self) -> None:
        _, sugar, _ = self.known_supplier()

        order = self.set_item(
            product_id=sugar.id,
            quantity="4",
        )

        assert order["lines"][0]["unit"] is None
        assert order["lines"][0]["cost_total"] is None
        assert (order["total"], order["has_unpriced"]) == ("0", True)

    def test_rejects_an_unknown_product_and_a_wrong_quantity(self) -> None:
        _, sugar, _ = self.known_supplier()

        assert self.set_item(
            product_id=999,
            quantity="1",
            expected=404,
        ) == {"detail": "Товар не найден"}
        for quantity in ["0", "abc", "1,5", "1.2345", 2]:
            self.set_item(
                product_id=sugar.id,
                quantity=quantity,
                expected=422,
            )
        assert self.draft() is None

    def test_removing_the_last_line_deletes_the_draft(self) -> None:
        _, sugar, salt = self.known_supplier()
        self.set_item(
            product_id=sugar.id,
            quantity="1",
        )
        self.set_item(
            product_id=salt.id,
            quantity="1",
        )

        order = self.remove_item(
            product_id=sugar.id,
        )
        assert [line["product_id"] for line in order["lines"]] == [salt.id]
        assert self.remove_item(
            product_id=sugar.id,
            expected=404,
        ) == {"detail": "Товара нет в заказе"}

        assert (
            self.remove_item(
                product_id=salt.id,
            )
            is None
        )
        assert self.draft() is None
        assert self.store.orders == {}

    def test_clear_deletes_the_draft(self) -> None:
        _, sugar, _ = self.known_supplier()
        self.set_item(
            product_id=sugar.id,
            quantity="1",
        )

        # clearing an empty cart is not an error
        for _ in range(
            2,
        ):
            response = self.client.delete(
                url="/order/draft",
            )
            assert response.status_code == 204, response.text

        assert self.draft() is None

    def test_confirm_keeps_the_ordered_prices(self) -> None:
        sugar, salt = self.posted_supplier()
        self.set_item(
            product_id=sugar,
            quantity="2",
        )

        order = self.confirm_order()

        assert order["status"] == OrderStatus.CONFIRMED
        assert order["confirmed_at"] is not None
        item = self.store.orders[order["id"]].items[0]
        assert (item.unit, item.cost_price) == (
            "кг",
            Decimal(
                value="50.00",
            ),
        )
        assert self.draft() is None

        # the order reads its own copy, not the last posted line
        item.cost_price = Decimal(
            value="40.00",
        )
        self.store.items.clear()
        stored = self.client.get(
            url=f"/order/{order['id']}",
        ).json()
        assert stored["lines"][0]["cost_total"] == "80.00"

        # the next product starts another cart
        draft = self.set_item(
            product_id=salt,
            quantity="1",
        )
        assert draft["id"] != order["id"]
        assert len(self.store.orders[order["id"]].items) == 1

    def test_confirm_without_a_draft(self) -> None:
        assert self.confirm_order(
            expected=404,
        ) == {"detail": "Заказ пуст, подтверждать нечего"}

    def test_lists_the_confirmed_orders_newest_first(self) -> None:
        sugar, salt = self.posted_supplier()
        ids = []
        for product_id in [sugar, salt, sugar]:
            self.set_item(
                product_id=product_id,
                quantity="1",
            )
            ids.append(
                self.confirm_order()["id"],
            )
        # the fixed clock gives every order the same moment
        for shift, order_id in enumerate(
            ids,
        ):
            confirmed_at = self.store.orders[order_id].confirmed_at
            assert confirmed_at is not None
            self.store.orders[order_id].confirmed_at = confirmed_at + timedelta(
                minutes=shift,
            )
        self.set_item(
            product_id=salt,
            quantity="5",
        )

        first = self.orders(
            limit=2,
        )
        rest = self.orders(
            limit=2,
            offset=2,
        )

        assert [item["id"] for item in first["items"]] == [ids[2], ids[1]]
        assert first["has_more"] is True
        assert [item["id"] for item in rest["items"]] == [ids[0]]
        assert rest["has_more"] is False
        assert first["items"][0]["supplier_names"] == ["ООО «Поставщик»"]
        assert (first["items"][0]["lines"], first["items"][0]["total"]) == (
            1,
            "50.00",
        )

    def test_an_unknown_order(self) -> None:
        response = self.client.get(
            url="/order/999",
        )
        assert response.status_code == 404
