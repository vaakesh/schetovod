from datetime import date
from typing import Any

import pytest

from core.enums import InvoiceStatus
from tests.fakes import INN, invoice_payload
from tests.helpers import InvoiceApi


class TestSaveForm(InvoiceApi):
    def test_new_supplier_and_prices_make_it_ready_without_catalog_writes(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": INN}
        form["lines"][0]["retail_price"] = 65
        form["lines"][1]["retail_price"] = 40

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert draft["ready"], draft["issues"]
        assert [
            (line["new_product"], line["markup_pct"], line["retail_price"])
            for line in draft["lines"]
        ] == [(True, "30.00", "65"), (True, "33.33", "40")]
        assert draft["form"] == form
        assert (self.store.suppliers, self.store.products, self.store.aliases) == (
            {},
            {},
            [],
        )
        invoice = self.store.invoices[draft["id"]]
        assert invoice.form == form
        assert invoice.extracted == invoice_payload()

    def test_header_columns_follow_the_form(self) -> None:
        supplier, _, _ = self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["invoice_number"] = "43"
        form["invoice_date"] = "13-08-2026"

        self.save(
            draft=draft,
            form=form,
        )
        invoice = self.store.invoices[draft["id"]]
        assert (invoice.invoice_number, invoice.invoice_date, invoice.supplier_id) == (
            "43",
            date(
                year=2026,
                month=8,
                day=13,
            ),
            supplier.id,
        )

        form["supplier"] = {"name": "Другой", "inn": None}
        self.save(
            draft=draft,
            form=form,
        )
        assert invoice.supplier_id is None

    def test_edited_lines_are_recalculated(self) -> None:
        self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["cost_price_total"] = "150.00"
        form["lines"][1]["vat_percent"] = "20"

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert [
            (
                line["cost_price"],
                line["base_price_total"],
                line["retail_price"],
            )
            for line in draft["lines"]
        ] == [("60.00", "150.00", "78"), ("30.00", "25.00", "36")]
        # what the model read disagrees now, which is only worth a look
        assert draft["ready"]
        assert [issue["message"] for issue in draft["issues"]] == [
            (
                "цена на полке меняется с 65 на 78 ₽, укажите, сколько старого товара "
                "осталось, чтобы переоценить"
            ),
            "сумма без НДС: в накладной 125.00, по сумме строки 150.00",
            "цена за единицу: в накладной 50.00, по сумме строки 60.00",
            "цена без НДС: в накладной 50.00, по сумме строки 60.00",
            "сумма без НДС: в накладной 30.00, по сумме строки 25.00",
            "итог к оплате: в накладной 155.00, по строкам 180.00",
            "итог без НДС: в накладной 155.00, по строкам 175.00",
        ]

    def test_lines_may_be_added_and_removed(self) -> None:
        self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"] = [
            form["lines"][1],
            # a new line comes without a number and gets the next free one
            form["lines"][1] | {"line_no": None, "name": "Перец", "retail_price": 50},
        ]
        form["totals"] = {"cost_total": "60.00", "base_total": None}

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert draft["issues"] == []
        assert [
            (line["product_name"], line["new_product"]) for line in draft["lines"]
        ] == [("Соль", False), ("Перец", True)]

    def test_spelling_of_a_known_product(self) -> None:
        _, sugar, _ = self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["name"] = "Сахар 1кг"
        form["lines"][0]["product_id"] = sugar.id

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert (
            draft["lines"][0]["product_id"],
            draft["lines"][0]["product_name"],
            draft["lines"][0]["retail_price"],
        ) == (sugar.id, "Сахар-песок 1 кг", "65")
        assert draft["ready"]

    @pytest.mark.parametrize(
        argnames=("change", "problems", "expected_supplier_id"),
        argvalues=[
            ({"supplier": {"id": 999}}, [(None, "продавца с id 999 нет")], None),
            (
                {"supplier": {"name": "Двойник", "inn": INN}},
                [(None, f"продавец с ИНН {INN} уже есть, выберите его")],
                None,
            ),
            ({"invoice_number": None}, [(None, "номер накладной не указан")], 1),
            ({"line": {"quantity": None}}, [(1, "количество не указано")], 1),
            ({"line": {"name": None}}, [(1, "название не указано")], 1),
            (
                {"line": {"name": "Новинка"}},
                [(1, "новый товар, укажите розничную цену")],
                1,
            ),
            ({"line": {"product_id": 7}}, [(1, "у продавца нет товара с id 7")], 1),
            (
                {"line": {"product_id": 4}},
                [(1, "это название уже относится к товару «Сахар-песок 1 кг»")],
                1,
            ),
            (
                {"line": {"retail_price": 40}},
                [
                    (
                        1,
                        (
                            "при цене 40 и закупке 50.00 наценка -20.00%, "
                            "а она должна быть от 0 до 999.99%"
                        ),
                    ),
                ],
                1,
            ),
            (
                {"line": {"cost_price_total": "0.00", "retail_price": 40}},
                [(1, "нет закупочной цены, наценку посчитать не из чего")],
                1,
            ),
            (
                {
                    "second": {"name": "Сахар-песок 1 кг", "retail_price": 70},
                    "line": {"retail_price": 66},
                },
                [(2, "у этого товара уже задана другая цена в строке 1")],
                1,
            ),
        ],
    )
    def test_reports_blocking_problem_and_keeps_draft_unready(
        self,
        change: dict[str, Any],
        problems: list[tuple[int | None, str]],
        expected_supplier_id: int | None,
    ) -> None:
        self.known_supplier()

        stranger = self.store.add_supplier(
            name="Чужой",
            inn=None,
        )

        self.store.add_product(
            supplier=stranger,
            name="Чужой товар",
            markup_pct="10",
            retail_price="100",
        )

        draft = self.upload()

        form = draft["form"] | {
            key: value for key, value in change.items() if key not in ("line", "second")
        }
        form["lines"] = [
            form["lines"][0]
            | change.get(
                "line",
                {},
            ),
            form["lines"][1]
            | change.get(
                "second",
                {},
            ),
        ]
        saved = self.save(
            draft=draft,
            form=form,
        )

        assert (
            self.blocking(
                draft=saved,
            )
            == problems
        )
        assert not saved["ready"]

        assert self.store.invoices[draft["id"]].supplier_id == expected_supplier_id

    @pytest.mark.parametrize(
        argnames=("scope", "change", "location"),
        argvalues=[
            ("line", {"cost_price": "50.00"}, ["body", "lines", 0, "cost_price"]),
            ("root", {"lines": [{"name": "Без остальных полей"}]}, None),
            ("root", {"supplier": {"id": 0}}, None),
            (
                "root",
                {"supplier": {"id": 1, "name": "И то и другое", "inn": None}},
                None,
            ),
            ("root", {"invoice_date": "2026-08-12"}, ["body", "invoice_date"]),
            ("line", {"retail_price": 0}, ["body", "lines", 0, "retail_price"]),
            ("line", {"quantity": 2}, ["body", "lines", 0, "quantity"]),
            ("root", {"status": "confirmed"}, ["body", "status"]),
        ],
    )
    def test_returns_422_when_form_is_invalid(
        self,
        scope: str,
        change: dict[str, Any],
        location: list[str | int] | None,
    ) -> None:
        draft = self.upload()
        form = draft["form"]
        if scope == "line":
            form["lines"][0].update(
                change,
            )
        else:
            form.update(
                change,
            )

        response = self.client.put(
            url=f"/invoice/{draft['id']}",
            json=form,
        )

        assert response.status_code == 422
        errors = response.json()["detail"]
        assert errors
        if location is not None:
            assert [error["loc"] for error in errors] == [location]
        assert self.store.invoices[draft["id"]].form is None

    @pytest.mark.parametrize(
        argnames="method",
        argvalues=("GET", "PUT"),
    )
    def test_returns_404_when_invoice_is_no_longer_a_draft(
        self,
        method: str,
    ) -> None:
        draft = self.upload()

        self.store.invoices[draft["id"]].status = InvoiceStatus.DECLINED

        response = self.client.request(
            method=method,
            url=f"/invoice/{draft['id']}",
            json=draft["form"] if method == "PUT" else None,
        )

        assert response.status_code == 404
