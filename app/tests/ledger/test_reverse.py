import pytest

from core.enums import LedgerKind
from tests.ledger.helpers import LedgerApi, shifted


class TestReverse(LedgerApi):
    def test_reversal_cancels_sale_and_links_original_entry(self) -> None:
        self.stock(
            amount="1000.00",
        )
        sale = self.sale(
            amount="250.00",
            shift=-2,
        )

        reversal = self.reverse(
            entry_id=sale["id"],
        )

        assert reversal == {
            "id": self.store.entries[-1].id,
            "amount": "250.00",
            "cash": "0.00",
            "balance": "1000.00",
            "cash_balance": "0.00",
        }
        entry = self.store.entries[-1]
        assert (entry.kind, entry.reverses_id, entry.comment, entry.occurred_on) == (
            LedgerKind.SALE,
            sale["id"],
            None,
            shifted(
                days=-2,
            ),
        )
        [cancelled] = [
            row for row in self.history()["entries"] if row["id"] == sale["id"]
        ]
        assert cancelled["reversed_by_id"] == reversal["id"]

    @pytest.mark.parametrize(
        argnames=("target", "detail"),
        argvalues=[
            ("sale", "Запись уже сторнирована"),
            ("reversal", "Сторно нельзя сторнировать"),
        ],
    )
    def test_returns_409_when_entry_cannot_be_reversed_again(
        self,
        target: str,
        detail: str,
    ) -> None:
        sale = self.sale(
            amount="250.00",
        )
        reversal = self.reverse(
            entry_id=sale["id"],
        )
        entry_id = sale["id"] if target == "sale" else reversal["id"]

        response = self.reverse(
            entry_id=entry_id,
            expected=409,
        )

        assert response == {"detail": detail}

    def test_invoice_and_unknown_entries_are_not_reversed(self) -> None:
        inflow = self.stock(
            amount="1000.00",
        )

        assert (
            self.reverse(
                entry_id=inflow.id,
                expected=409,
            )["detail"]
            == "Проведённую накладную нельзя сторнировать"
        )
        self.reverse(
            entry_id=999,
            expected=404,
        )

    def test_stocktake_blocks_earlier_reversals_until_it_is_reversed(self) -> None:
        self.stock(
            amount="1000.00",
        )
        sale = self.sale(
            amount="100.00",
            shift=-1,
        )
        stocktake = self.stocktake(
            counted="850.00",
        )

        blocked = self.reverse(
            entry_id=sale["id"],
            expected=409,
        )
        self.reverse(
            entry_id=stocktake["id"],
        )
        reversal = self.reverse(
            entry_id=sale["id"],
        )

        assert (
            blocked["detail"]
            == "После этой записи был переучёт, исправьте остаток новым переучётом"
        )
        assert reversal["balance"] == "1000.00"
