from typing import Any

from tests.ledger.helpers import LedgerApi


class TestRevaluationLines(LedgerApi):
    def lines(
        self,
        entry_id: int,
        expected: int = 200,
    ) -> Any:
        response = self.client.get(
            url=f"/ledger/{entry_id}/revaluation",
        )
        assert response.status_code == expected, response.text
        return response.json()

    def test_shows_what_was_revalued_and_what_the_reversal_takes_back(self) -> None:
        _, sugar, salt = self.known_supplier()
        posted = self.revalue(
            lines=[
                (sugar.id, "4", 60),
                (salt.id, "2.5", 40),
            ],
        )
        reversal = self.reverse(
            entry_id=posted["id"],
        )

        assert self.lines(
            entry_id=posted["id"],
        ) == [
            {
                "product_id": sugar.id,
                "product_name": "Сахар-песок 1 кг",
                "quantity": "4",
                "old_price": "65",
                "new_price": "60",
                "amount": "-20.00",
            },
            {
                "product_id": salt.id,
                "product_name": "Соль",
                "quantity": "2.5",
                "old_price": "36",
                "new_price": "40",
                "amount": "10.00",
            },
        ]
        assert [
            line["amount"]
            for line in self.lines(
                entry_id=reversal["id"],
            )
        ] == ["20.00", "-10.00"]

    def test_other_entries_have_no_lines(self) -> None:
        sale = self.sale(
            amount="10.00",
        )

        self.lines(
            entry_id=sale["id"],
            expected=404,
        )
        self.lines(
            entry_id=999,
            expected=404,
        )
