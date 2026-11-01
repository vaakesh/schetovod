import pytest

from core.enums import LedgerKind
from tests.ledger.helpers import LedgerApi, day


class TestOutflow(LedgerApi):
    def test_sale_and_write_off_take_stock_out(self) -> None:
        self.stock(
            amount="10000.00",
        )

        sale = self.sale(
            amount="1500.00",
            shift=-1,
        )
        write_off = self.post(
            url="/ledger/write-off",
            payload={
                "occurred_on": day(),
                "amount": "200.00",
                "comment": "забрал владелец",
            },
        )

        assert (sale["amount"], sale["balance"]) == ("-1500.00", "8500.00")
        assert (write_off["amount"], write_off["balance"]) == ("-200.00", "8300.00")
        entry = self.store.entries[-1]
        assert (entry.kind, entry.comment) == (LedgerKind.WRITE_OFF, "забрал владелец")
        assert self.store.locks == 2

    def test_stock_in_brings_stock_in_and_leaves_the_till(self) -> None:
        self.stock(
            amount="1000.00",
        )

        stock_in = self.post(
            url="/ledger/stock-in",
            payload={
                "occurred_on": day(),
                "amount": "300.00",
                "comment": "из мяса",
            },
        )

        assert stock_in == {
            "id": self.store.entries[-1].id,
            "amount": "300.00",
            "cash": "0",
            "balance": "1300.00",
            "cash_balance": "0",
        }
        entry = self.store.entries[-1]
        assert (entry.kind, entry.comment) == (LedgerKind.STOCK_IN, "из мяса")

    def test_stock_in_does_not_need_a_comment(self) -> None:
        stock_in = self.post(
            url="/ledger/stock-in",
            payload={
                "occurred_on": day(),
                "amount": "300.00",
                "comment": None,
            },
        )

        assert stock_in["balance"] == "300.00"
        assert self.store.entries[-1].comment is None

    def test_returns_422_when_stock_in_amount_is_not_positive(self) -> None:
        self.post(
            url="/ledger/stock-in",
            payload={
                "occurred_on": day(),
                "amount": "0",
                "comment": None,
            },
            expected=422,
        )

        assert self.store.entries == []

    @pytest.mark.parametrize(
        argnames=("amount", "cash", "shift", "detail"),
        argvalues=[
            ("0", "0.00", 0, "Укажите выручку наличными или безналом"),
            ("10.00", "0.00", 1, "Дата не может быть в будущем"),
            # more cash than the whole sale leaves a negative cashless part
            ("10.00", "15.00", 0, ["body", "card"]),
        ],
    )
    def test_returns_422_when_sale_amount_or_date_is_invalid(
        self,
        amount: str,
        cash: str,
        shift: int,
        detail: str | list[str],
    ) -> None:
        response = self.sale(
            amount=amount,
            cash=cash,
            shift=shift,
            expected=422,
        )

        if isinstance(
            detail,
            str,
        ):
            assert response == {"detail": detail}
        else:
            assert [error["loc"] for error in response["detail"]] == [detail]
        assert self.store.entries == []
