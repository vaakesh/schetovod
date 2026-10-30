from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from core.enums import InvoiceStatus
from tests.fakes import INN, invoice_payload
from tests.helpers import InvoiceApi


class TestAddProducts(InvoiceApi):
    def add(
        self,
        draft: dict[str, Any],
    ) -> Any:
        client: TestClient = self.client
        return client.post(
            url=f"/invoice/{draft['id']}/products",
        )

    def new_supplier_draft(
        self,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """a draft of an unknown supplier with a price on every line"""
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": INN}
        for line in form["lines"]:
            line["retail_price"] = 65
        return self.save(
            draft=draft,
            form=form,
        )

    def test_adds_new_products_without_a_trace_in_the_books(self) -> None:
        draft = self.new_supplier_draft()
        assert draft["products_ready"] is True

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"created": 2, "skipped": 0}
        products = {product.name: product for product in self.store.products.values()}
        assert set(products) == {"Сахар-песок 1 кг", "Соль"}
        sugar = products["Сахар-песок 1 кг"]
        assert sugar.retail_price == Decimal(
            value=65,
        )
        assert sugar.markup_pct == Decimal(
            value="30.00",
        )
        assert sugar.has_price_tag is False
        assert len(self.store.suppliers) == 1
        assert {alias.alias_raw for alias in self.store.aliases} == set(products)
        assert self.store.items == []
        assert self.store.entries == []
        assert self.store.invoices == {}

    def test_deleted_draft_is_gone_from_the_list(self) -> None:
        draft = self.new_supplier_draft()
        self.add(
            draft=draft,
        )

        listed = self.client.get(
            url="/invoice",
        )
        opened = self.client.get(
            url=f"/invoice/{draft['id']}",
        )

        assert listed.json()["items"] == []
        assert opened.status_code == 404

    def test_known_products_stay_untouched(self) -> None:
        _, sugar, _ = self.known_supplier()
        price = sugar.retail_price
        payload = invoice_payload()
        payload["items"][0]["cost_price_total"] = "200.00"
        payload["items"].append(
            payload["items"][1] | {"line_no": "3", "name": "Перец"},
        )
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        form["lines"][2]["retail_price"] = 40
        draft = self.save(
            draft=draft,
            form=form,
        )
        aliases = len(self.store.aliases)

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"created": 1, "skipped": 2}
        assert sugar.retail_price == price
        assert len(self.store.aliases) == aliases + 1

    def test_document_issues_do_not_stop_it(self) -> None:
        payload = invoice_payload()
        payload["invoice_number"] = None
        payload["invoice_date"] = None
        draft = self.new_supplier_draft(
            payload=payload,
        )
        assert draft["ready"] is False
        assert draft["products_ready"] is True

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 200, response.text

    def test_a_posted_copy_does_not_stop_it(self) -> None:
        posted = self.new_supplier_draft()
        assert (
            self.confirm(
                draft=posted,
            ).status_code
            == 200
        )
        payload = invoice_payload()
        payload["items"].append(
            payload["items"][1] | {"line_no": "3", "name": "Перец"},
        )
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        form["lines"][2]["retail_price"] = 40
        draft = self.save(
            draft=draft,
            form=form,
        )
        assert draft["ready"] is False

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"created": 1, "skipped": 2}

    def test_needs_a_supplier(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["supplier"] = None
        draft = self.save(
            draft=draft,
            form=form,
        )
        assert draft["products_ready"] is False

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 409
        assert "продавец не выбран" in response.json()["detail"]
        assert self.store.products == {}
        assert draft["id"] in self.store.invoices

    def test_needs_a_price_of_every_new_line(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": INN}
        form["lines"][0]["retail_price"] = 65
        draft = self.save(
            draft=draft,
            form=form,
        )
        assert draft["products_ready"] is False

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 409
        assert "укажите розничную цену" in response.json()["detail"]
        assert self.store.products == {}

    def test_nothing_new_to_add(self) -> None:
        self.known_supplier()
        draft = self.upload()
        assert draft["products_ready"] is False

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "Новых товаров в накладной нет"
        assert self.store.invoices[draft["id"]].status == InvoiceStatus.DRAFT

    def test_one_name_on_two_lines_is_one_product(self) -> None:
        payload = invoice_payload()
        payload["items"].append(
            payload["items"][0] | {"line_no": "3", "name": "САХАР-ПЕСОК  1 кг"},
        )
        payload["totals"] = {"base_total": None, "cost_total": "280.00"}
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": INN}
        # the price entered on the second spelling decides
        form["lines"][1]["retail_price"] = 40
        form["lines"][2]["retail_price"] = 65
        draft = self.save(
            draft=draft,
            form=form,
        )

        response = self.add(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"created": 2, "skipped": 0}
        assert {product.retail_price for product in self.store.products.values()} == {
            Decimal(
                value=40,
            ),
            Decimal(
                value=65,
            ),
        }
        assert len(self.store.aliases) == 2
