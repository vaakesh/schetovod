from tests.ledger.helpers import LedgerApi, day


class TestCash(LedgerApi):
    def test_the_till_follows_the_takings_and_the_payments(self) -> None:
        self.stock(
            amount="200000.00",
        )

        sale = self.sale(
            amount="40000.00",
            cash="15000.00",
        )
        taken = self.cash(
            kind="cash-out",
            amount="10000.00",
            comment="забрал владелец",
        )
        put = self.cash(
            kind="cash-in",
            amount="20000.00",
        )
        paid = self.cash(
            kind="cash-out",
            amount="3200.00",
            comment="накладная № 17",
        )

        # the cashless part is gone to the bank, only the cash stays in the till
        assert (
            sale["amount"],
            sale["balance"],
            sale["cash"],
            sale["cash_balance"],
        ) == (
            "-40000.00",
            "160000.00",
            "15000.00",
            "15000.00",
        )
        assert [
            (posted["cash"], posted["cash_balance"], posted["balance"])
            for posted in (taken, put, paid)
        ] == [
            ("-10000.00", "5000.00", "160000.00"),
            ("20000.00", "25000.00", "160000.00"),
            ("-3200.00", "21800.00", "160000.00"),
        ]
        page = self.history()
        assert (page["balance"], page["cash_balance"]) == ("160000.00", "21800.00")
        assert [
            (row["kind"], row["amount"], row["cash"], row["cash_after"])
            for row in page["entries"][:2]
        ] == [
            ("cash_out", "0", "-3200.00", "21800.00"),
            ("cash_in", "0", "20000.00", "25000.00"),
        ]
        assert self.store.entries[-1].comment == "накладная № 17"

    def test_cash_out_needs_a_comment(self) -> None:
        response = self.cash(
            kind="cash-out",
            amount="100.00",
            expected=422,
        )

        assert [error["loc"] for error in response["detail"]] == [["body", "comment"]]
        assert self.store.entries == []

    def test_cash_count_records_the_shortage(self) -> None:
        self.cash(
            kind="cash-in",
            amount="5000.00",
            shift=-1,
        )
        self.sale(
            amount="1000.00",
            cash="600.00",
        )

        posted = self.cash_count(
            counted="5500.00",
        )

        assert (posted["amount"], posted["cash"], posted["cash_balance"]) == (
            "0",
            "-100.00",
            "5500.00",
        )
        balance = self.client.get(
            url="/ledger/balance",
        ).json()
        assert (
            balance["cash_balance"],
            balance["cash_closed_on"],
            balance["closed_on"],
        ) == (
            "5500.00",
            day(),
            None,
        )

    def test_a_count_closes_only_what_it_counted(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        self.stocktake(
            counted="1000.00",
        )
        self.cash_count(
            counted="0",
        )

        # the stock and the cash both closed today
        assert (
            self.post(
                url="/ledger/write-off",
                payload={
                    "occurred_on": day(
                        shift=-1,
                    ),
                    "amount": "10.00",
                    "comment": None,
                },
                expected=409,
            )["detail"]
            == f"Период закрыт переучётом от {day()}"
        )
        assert (
            self.cash(
                kind="cash-in",
                amount="10.00",
                shift=-1,
                expected=409,
            )["detail"]
            == f"Касса закрыта сверкой от {day()}"
        )

    def test_a_cash_count_leaves_the_stock_open(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        self.cash_count(
            counted="0",
        )

        self.post(
            url="/ledger/write-off",
            payload={
                "occurred_on": day(
                    shift=-1,
                ),
                "amount": "10.00",
                "comment": None,
            },
        )
        # a cashless sale does not touch the till
        self.sale(
            amount="20.00",
            shift=-1,
        )
        blocked = self.sale(
            amount="20.00",
            cash="5.00",
            shift=-1,
            expected=409,
        )

        assert blocked["detail"] == f"Касса закрыта сверкой от {day()}"

    def test_a_stocktake_leaves_the_till_open(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        self.stocktake(
            counted="1000.00",
        )

        posted = self.cash(
            kind="cash-in",
            amount="300.00",
            shift=-1,
        )

        assert posted["cash_balance"] == "300.00"

    def test_reversal_of_a_sale_returns_the_stock_and_the_cash(self) -> None:
        self.stock(
            amount="1000.00",
        )
        sale = self.sale(
            amount="400.00",
            cash="150.00",
        )

        reversal = self.reverse(
            entry_id=sale["id"],
        )

        assert (reversal["amount"], reversal["cash"]) == ("400.00", "-150.00")
        assert (reversal["balance"], reversal["cash_balance"]) == ("1000.00", "0.00")

    def test_cash_count_blocks_earlier_cash_reversals(self) -> None:
        put = self.cash(
            kind="cash-in",
            amount="500.00",
            shift=-1,
        )
        sale = self.sale(
            amount="100.00",
            shift=-1,
        )
        self.cash_count(
            counted="500.00",
        )

        blocked = self.reverse(
            entry_id=put["id"],
            expected=409,
        )
        # a cashless sale changed nothing the count saw in the till
        self.reverse(
            entry_id=sale["id"],
        )

        assert (
            blocked["detail"]
            == "После этой записи была сверка кассы, исправьте кассу новой сверкой"
        )
