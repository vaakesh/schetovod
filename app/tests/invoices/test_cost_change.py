from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestCostChange(InvoiceApi):
    def test_line_shows_the_cost_of_the_last_delivery(self) -> None:
        self.known_supplier()
        assert (
            self.confirm(
                draft=self.upload(),
            ).status_code
            == 200
        )
        payload = invoice_payload()
        payload["invoice_number"] = "00043/А"
        # the sugar comes at 60 instead of 50, the salt at the same 30
        payload["items"][0] |= {
            "cost_price_total": "150.00",
            "base_price_total": "150.00",
        }
        payload["totals"] = {"base_total": "180.00", "cost_total": None}

        draft = self.upload(
            payload=payload,
        )

        assert [
            (line["cost_price"], line["previous_cost_price"]) for line in draft["lines"]
        ] == [
            ("60.00", "50.00"),
            ("30.00", None),
        ]

    def test_never_posted_product_has_no_previous_cost(self) -> None:
        self.known_supplier()

        draft = self.upload()

        assert [line["previous_cost_price"] for line in draft["lines"]] == [None, None]
