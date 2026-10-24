from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from core.enums import LedgerKind
from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestRevaluationOnConfirm(InvoiceApi):
    def draft_with_prices(
        self,
        prices: list[int | None],
        quantities: list[str | None],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """the invoice of the known supplier with the given shelf prices and old stock"""
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        for line, price, quantity in zip(
            form["lines"],
            prices,
            quantities,
            strict=True,
        ):
            line["retail_price"] = price
            line["revalue_quantity"] = quantity
        return self.save(
            draft=draft,
            form=form,
        )

    def confirm(
        self,
        draft: dict[str, Any],
        occurred_on: str | None = None,
    ) -> dict[str, Any]:
        response = super().confirm(
            draft=draft,
            occurred_on=occurred_on,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_changed_price_asks_for_the_old_stock(self) -> None:
        self.known_supplier()

        draft = self.draft_with_prices(
            prices=[70, None],
            quantities=[None, None],
        )

        assert draft["ready"]
        assert [line["previous_retail_price"] for line in draft["lines"]] == [
            "65",
            None,
        ]
        assert {
            "line": 1,
            "message": (
                "цена на полке меняется с 65 на 70 ₽, укажите, сколько старого товара "
                "осталось, чтобы переоценить"
            ),
            "blocking": False,
            "code": "price_changed",
        } in draft["issues"]

    def test_old_stock_is_revalued_with_the_invoice(self) -> None:
        _, sugar, salt = self.known_supplier()
        draft = self.draft_with_prices(
            prices=[70, None],
            quantities=["4", None],
        )
        assert [issue["code"] for issue in draft["issues"]] == []

        result = self.confirm(
            draft=draft,
        )

        # 2.5 kg at 70 and the salt at 36, then 4 kg on the shelf go up by 5
        assert (result["retail_total"], result["revaluation"], result["balance"]) == (
            "211.00",
            "20.00",
            "231.00",
        )
        _, entry = self.store.entries
        assert (entry.kind, entry.amount, entry.comment) == (
            LedgerKind.REVALUATION,
            Decimal(
                value="20.00",
            ),
            "по накладной № 00042/А",
        )
        [item] = self.store.revaluations
        assert (
            item.ledger_entry_id,
            item.product_id,
            item.invoice_item_id,
            item.quantity,
            item.old_price,
            item.new_price,
        ) == (
            entry.id,
            sugar.id,
            self.store.items[0].id,
            Decimal(
                value=4,
            ),
            Decimal(
                value=65,
            ),
            Decimal(
                value=70,
            ),
        )
        assert (sugar.retail_price, salt.retail_price) == (
            Decimal(
                value=70,
            ),
            Decimal(
                value=36,
            ),
        )

    def test_new_price_without_old_stock_only_moves_the_shelf_price(self) -> None:
        _, sugar, _ = self.known_supplier()

        result = self.confirm(
            draft=self.draft_with_prices(
                prices=[70, None],
                quantities=[None, None],
            ),
        )

        assert result["revaluation"] is None
        assert (
            [entry.kind for entry in self.store.entries],
            self.store.revaluations,
        ) == ([LedgerKind.INVOICE], [])
        assert sugar.retail_price == Decimal(
            value=70,
        )

    def test_revaluation_is_dated_with_the_inflow(self) -> None:
        self.known_supplier()

        self.confirm(
            draft=self.draft_with_prices(
                prices=[70, None],
                quantities=["4", None],
            ),
            occurred_on="14-10-2026",
        )

        assert [(entry.kind, entry.occurred_on) for entry in self.store.entries] == [
            (
                LedgerKind.INVOICE,
                date(
                    year=2026,
                    month=10,
                    day=14,
                ),
            ),
            (
                LedgerKind.REVALUATION,
                date(
                    year=2026,
                    month=10,
                    day=14,
                ),
            ),
        ]

    def test_only_a_new_shelf_price_resets_the_price_tag(self) -> None:
        _, sugar, salt = self.known_supplier()
        sugar.has_price_tag = True
        salt.has_price_tag = True

        self.confirm(
            draft=self.draft_with_prices(
                prices=[70, None],
                quantities=[None, None],
            ),
        )

        # the salt got a new cost with the same shelf price, its tag is still right
        assert (sugar.has_price_tag, salt.has_price_tag) == (False, True)

    def test_new_product_gets_its_shelf_price(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["retail_price"] = 65
        form["lines"][1]["retail_price"] = 40
        self.confirm(
            draft=self.save(
                draft=draft,
                form=form,
            ),
        )

        assert [product.retail_price for product in self.store.products.values()] == [
            65,
            40,
        ]
        assert [product.has_price_tag for product in self.store.products.values()] == [
            False,
            False,
        ]

    @pytest.mark.parametrize(
        argnames=("prices", "quantities", "expected"),
        argvalues=[
            (
                [None, None, None],
                [None, "2", None],
                [(2, "цена на полке не меняется, переоценивать нечего")],
            ),
            (
                [70, None, None],
                ["4", None, "1"],
                [(3, "переоценка этого товара уже указана в строке 1")],
            ),
            (
                [66, None, None],
                ["0.001", None, None],
                [(1, "переоценка выходит меньше копейки, проверьте количество")],
            ),
        ],
    )
    def test_wrong_old_stock_is_blocking(
        self,
        prices: list[int | None],
        quantities: list[str | None],
        expected: list[tuple[int | None, str]],
    ) -> None:
        self.known_supplier()

        payload = invoice_payload()

        payload["items"].append(
            payload["items"][0] | {"line_no": "3"},
        )

        payload["totals"] = {"base_total": None, "cost_total": "280.00"}

        draft = self.draft_with_prices(
            prices=prices,
            quantities=quantities,
            payload=payload,
        )

        assert (
            self.blocking(
                draft=draft,
            )
            == expected
        )

    def test_draft_saved_before_the_revaluation_still_opens(self) -> None:
        self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        for line in form["lines"]:
            del line["revalue_quantity"]
        self.store.invoices[draft["id"]].form = form

        response = self.client.get(
            url=f"/invoice/{draft['id']}",
        )

        assert response.status_code == 200, response.text
        assert response.json()["ready"]
