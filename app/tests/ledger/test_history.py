from tests.ledger.helpers import LedgerApi, day


class TestHistory(LedgerApi):
    def test_latest_first_with_running_balance_and_pages(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-2,
        )
        self.sale(
            amount="100.00",
        )
        # entered later but dated earlier, it goes before the sale of today
        self.sale(
            amount="50.00",
            shift=-1,
        )

        page = self.history()
        first = self.client.get(
            url="/ledger",
            params={
                "limit": 2,
            },
        ).json()

        assert [
            (row["occurred_on"], row["amount"], row["balance_after"])
            for row in page["entries"]
        ] == [
            (day(), "-100.00", "850.00"),
            (
                day(
                    shift=-1,
                ),
                "-50.00",
                "950.00",
            ),
            (
                day(
                    shift=-2,
                ),
                "1000.00",
                "1000.00",
            ),
        ]
        assert (page["balance"], page["has_more"]) == ("850.00", False)
        assert (
            len(
                first["entries"],
            ),
            first["has_more"],
        ) == (2, True)
