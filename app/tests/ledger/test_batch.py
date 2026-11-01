from typing import Any

import pytest

from core.enums import LedgerKind
from tests.ledger.helpers import LedgerApi, day


def line(
    amount: str,
    comment: str | None = None,
    shift: int = 0,
) -> dict[str, Any]:
    return {
        "occurred_on": day(
            shift=shift,
        ),
        "amount": amount,
        "comment": comment,
    }


class TestBatch(LedgerApi):
    def batch(
        self,
        kind: str,
        entries: list[dict[str, Any]],
        expected: int = 200,
    ) -> dict[str, Any]:
        return self.post(
            url="/ledger/batch",
            payload={
                "kind": kind,
                "entries": entries,
            },
            expected=expected,
        )

    def test_every_line_is_a_separate_entry_with_its_own_date(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )

        posted = self.batch(
            kind="write_off",
            entries=[
                line(
                    amount="100.00",
                    comment="мясо",
                    shift=-2,
                ),
                line(
                    amount="50.00",
                    comment="просрочка",
                    shift=-1,
                ),
            ],
        )

        assert (posted["balance"], posted["cash_balance"]) == ("850.00", "0")
        first, second = self.store.entries[-2:]
        assert posted["ids"] == [first.id, second.id]
        assert (first.kind, first.comment) == (LedgerKind.WRITE_OFF, "мясо")
        assert (second.kind, second.comment) == (LedgerKind.WRITE_OFF, "просрочка")
        assert first.occurred_on != second.occurred_on
        assert self.store.locks == 1
        assert self.store.commits == 1

    @pytest.mark.parametrize(
        argnames=("kind", "balance", "cash_balance"),
        argvalues=[
            ("write_off", "990.00", "0"),
            ("stock_in", "1010.00", "0"),
            ("cash_in", "1000.00", "10.00"),
            ("cash_out", "1000.00", "-10.00"),
        ],
    )
    def test_each_kind_moves_its_own_side(
        self,
        kind: str,
        balance: str,
        cash_balance: str,
    ) -> None:
        self.stock(
            amount="1000.00",
            shift=-1,
        )

        posted = self.batch(
            kind=kind,
            entries=[
                line(
                    amount="10.00",
                    comment="кэш",
                ),
            ],
        )

        assert (posted["balance"], posted["cash_balance"]) == (balance, cash_balance)

    def test_a_line_of_a_batch_is_reversed_on_its_own(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-1,
        )
        posted = self.batch(
            kind="write_off",
            entries=[
                line(
                    amount="100.00",
                ),
                line(
                    amount="50.00",
                ),
            ],
        )

        reversal = self.reverse(
            entry_id=posted["ids"][0],
        )

        assert reversal["balance"] == "950.00"

    def test_a_bad_line_keeps_the_whole_batch_out(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        self.stocktake(
            counted="1000.00",
        )
        entries = list(
            self.store.entries,
        )

        response = self.batch(
            kind="write_off",
            entries=[
                line(
                    amount="100.00",
                ),
                line(
                    amount="50.00",
                    shift=-1,
                ),
            ],
            expected=409,
        )

        assert response["detail"] == f"Строка 2: Период закрыт переучётом от {day()}"
        assert self.store.entries == entries

    def test_a_cash_count_closes_the_till_and_leaves_the_stock(self) -> None:
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        self.cash_count(
            counted="0",
        )

        self.batch(
            kind="stock_in",
            entries=[
                line(
                    amount="10.00",
                    shift=-1,
                ),
            ],
        )
        blocked = self.batch(
            kind="cash_in",
            entries=[
                line(
                    amount="10.00",
                    shift=-1,
                ),
            ],
            expected=409,
        )

        assert blocked["detail"] == f"Строка 1: Касса закрыта сверкой от {day()}"

    def test_a_cash_out_needs_a_comment_in_every_line(self) -> None:
        response = self.batch(
            kind="cash_out",
            entries=[
                line(
                    amount="10.00",
                    comment="хлеб",
                ),
                line(
                    amount="20.00",
                ),
            ],
            expected=422,
        )

        assert response["detail"] == "Строка 2: укажите, на что выданы деньги"
        assert self.store.entries == []

    @pytest.mark.parametrize(
        argnames=("kind", "entries"),
        argvalues=[
            ("sale", [line(amount="10.00")]),
            ("stocktake", [line(amount="10.00")]),
            ("write_off", []),
            ("write_off", [line(amount="0")]),
        ],
    )
    def test_returns_422_for_a_kind_or_a_line_out_of_the_batch(
        self,
        kind: str,
        entries: list[dict[str, Any]],
    ) -> None:
        self.batch(
            kind=kind,
            entries=entries,
            expected=422,
        )

        assert self.store.entries == []


class TestFrequentComments(LedgerApi):
    def comments(
        self,
        kind: str,
    ) -> list[str]:
        response = self.client.get(
            url="/ledger/comments",
            params={
                "kind": kind,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_repeated_comments_of_the_kind_go_first(self) -> None:
        for comment, count in (("хлеб", 2), ("Кэш", 3), ("бутылки", 1)):
            for _ in range(
                count,
            ):
                self.cash(
                    kind="cash-out",
                    amount="10.00",
                    comment=comment,
                )
        self.cash(
            kind="cash-out",
            amount="10.00",
            comment="кэш ",
        )
        self.post(
            url="/ledger/write-off",
            payload=line(
                amount="10.00",
                comment="мясо",
            ),
        )

        # the latest spelling, a single comment is not a habit
        assert self.comments(
            kind="cash_out",
        ) == ["кэш", "хлеб"]
        assert (
            self.comments(
                kind="write_off",
            )
            == []
        )

    def test_returns_422_for_a_kind_without_comments_hints(self) -> None:
        response = self.client.get(
            url="/ledger/comments",
            params={
                "kind": "sale",
            },
        )

        assert response.status_code == 422
