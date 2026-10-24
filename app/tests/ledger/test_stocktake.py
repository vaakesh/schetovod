from tests.ledger.helpers import LedgerApi, day


class TestStocktake(LedgerApi):
    def test_entry_is_the_difference_and_the_balance_becomes_the_count(self) -> None:
        self.stock(
            amount="10000.00",
        )
        self.sale(
            amount="1000.00",
        )

        posted = self.stocktake(
            counted="8700.00",
        )

        assert (posted["amount"], posted["balance"]) == ("-300.00", "8700.00")
        [latest, *_] = self.history()["entries"]
        assert (latest["kind"], latest["amount"], latest["balance_after"]) == (
            "stocktake",
            "-300.00",
            "8700.00",
        )

    def test_counts_against_the_balance_on_its_date(self) -> None:
        self.stock(
            amount="5000.00",
            shift=-3,
        )
        self.sale(
            amount="400.00",
        )

        posted = self.stocktake(
            counted="5100.00",
            shift=-1,
        )

        # the sale of today comes after the stocktake of yesterday
        assert (posted["amount"], posted["balance"]) == ("100.00", "4700.00")

    def test_stocktake_closes_the_period(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        self.stocktake(
            counted="900.00",
        )

        blocked = self.sale(
            amount="10.00",
            shift=-1,
            expected=409,
        )
        self.sale(
            amount="10.00",
        )

        assert blocked["detail"] == f"Период закрыт переучётом от {day()}"
        assert self.client.get(
            url="/ledger/balance",
            params={
                "on": day(
                    shift=-1,
                ),
            },
        ).json() == {
            "balance": "1000.00",
            "cash_balance": "0",
            "closed_on": day(),
            "cash_closed_on": None,
        }
