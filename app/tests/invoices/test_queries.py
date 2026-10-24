from decimal import Decimal
from typing import Any

from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestInvoiceList(InvoiceApi):
    def confirmed(self) -> dict[str, Any]:
        """an invoice of the known supplier, posted at the current markups"""
        self.known_supplier()
        draft = self.upload()
        response = self.confirm(
            draft=draft,
        )
        assert response.status_code == 200, response.text
        return draft

    def test_lists_newest_first_with_filter_and_search(self) -> None:
        posted = self.confirmed()
        payload = invoice_payload()
        payload["supplier"] = {"name": "ИП Иванов", "inn": None}
        payload["invoice_number"] = "777"
        draft = self.upload(
            payload=payload,
        )

        everything = self.client.get(
            url="/invoice",
        ).json()
        confirmed = self.client.get(
            url="/invoice",
            params={"status": "confirmed"},
        ).json()
        found = self.client.get(
            url="/invoice",
            params={"q": "иванов"},
        ).json()
        first_page = self.client.get(
            url="/invoice",
            params={"limit": 1},
        ).json()

        assert [
            (
                item["id"],
                item["status"],
                item["supplier_name"],
                item["retail_total"],
                item["lines"],
            )
            for item in everything["items"]
        ] == [
            (draft["id"], "draft", "ИП Иванов", None, 2),
            (posted["id"], "confirmed", "ООО «Поставщик»", "198.50", 2),
        ]
        assert [item["id"] for item in confirmed["items"]] == [posted["id"]]
        assert [item["id"] for item in found["items"]] == [draft["id"]]
        assert (
            [item["id"] for item in first_page["items"]],
            first_page["has_more"],
        ) == ([draft["id"]], True)

    def test_posted_invoice_shows_the_lines_as_posted(self) -> None:
        draft = self.confirmed()

        response = self.client.get(
            url=f"/invoice/{draft['id']}/confirmed",
        )

        assert response.status_code == 200, response.text
        posted = response.json()
        assert (
            posted["invoice_number"],
            posted["invoice_date"],
            posted["supplier"]["name"],
            posted["cost_total"],
            posted["retail_total"],
            posted["ledger_entry_id"],
        ) == (
            "00042/А",
            "12-08-2026",
            "ООО «Поставщик»",
            "155.00",
            "198.50",
            self.store.entries[0].id,
        )
        assert [
            (
                line["line_no"],
                line["product_name"],
                Decimal(
                    value=line["retail_price"],
                ),
                Decimal(
                    value=line["retail_price_total"],
                ),
            )
            for line in posted["lines"]
        ] == [
            (
                1,
                "Сахар-песок 1 кг",
                Decimal(
                    value=65,
                ),
                Decimal(
                    value="162.50",
                ),
            ),
            (
                2,
                "Соль",
                Decimal(
                    value=36,
                ),
                Decimal(
                    value=36,
                ),
            ),
        ]
        assert self.store.locks == 1

    def test_draft_is_not_a_posted_invoice(self) -> None:
        draft = self.upload()

        assert (
            self.client.get(
                url=f"/invoice/{draft['id']}/confirmed",
            ).status_code
            == 404
        )
