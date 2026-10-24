from decimal import Decimal

import pytest

from core.enums import LedgerKind
from tests.ledger.helpers import LedgerApi


class TestRevaluation(LedgerApi):
    def test_reprices_the_stock_on_the_shelf(self) -> None:
        self.stock(
            amount="1000.00",
        )
        _, sugar, salt = self.known_supplier()

        posted = self.revalue(
            lines=[
                (sugar.id, "4", 60),
                (salt.id, "2.5", 40),
            ],
        )

        # sugar 4 × (60 − 65) and salt 2.5 × (40 − 36)
        assert (posted["amount"], posted["balance"]) == ("-10.00", "990.00")
        entry = self.store.entries[-1]
        assert (entry.kind, entry.comment) == (LedgerKind.REVALUATION, "акция")
        assert [
            (item.product_id, item.old_price, item.new_price, item.invoice_item_id)
            for item in self.store.revaluations
        ] == [
            (sugar.id, 65, 60, None),
            (salt.id, 36, 40, None),
        ]
        assert (sugar.retail_price, salt.retail_price, sugar.markup_pct) == (60, 40, 30)

    @pytest.mark.parametrize(
        argnames=("lines", "detail"),
        argvalues=[
            ([(999, "1", 10)], "Товара с id 999 нет"),
            (
                [(2, "1", 70), (2, "2", 70)],
                "Товар «Сахар-песок 1 кг» указан дважды",
            ),
            ([(2, "1", 65)], "Цена товара «Сахар-песок 1 кг» уже 65 ₽"),
        ],
    )
    def test_rejects_unknown_repeated_and_unchanged_products(
        self,
        lines: list[tuple[int, str, int]],
        detail: str,
    ) -> None:
        _, sugar, _ = self.known_supplier()

        assert (
            self.revalue(
                lines=lines,
                expected=422,
            )["detail"]
            == detail
        )

        assert (self.store.entries, sugar.retail_price) == ([], 65)

    def test_closed_period_is_not_revalued(self) -> None:
        _, sugar, _ = self.known_supplier()
        self.stocktake(
            counted="0",
        )

        self.revalue(
            lines=[
                (sugar.id, "1", 70),
            ],
            shift=-1,
            expected=409,
        )

    def test_reversal_returns_the_old_price(self) -> None:
        _, sugar, salt = self.known_supplier()
        posted = self.revalue(
            lines=[
                (sugar.id, "4", 70),
                (salt.id, "1", 40),
            ],
        )
        # the salt got another price since, it is not rolled back
        salt.retail_price = Decimal(
            value=45,
        )

        reversal = self.reverse(
            entry_id=posted["id"],
        )

        assert (reversal["amount"], reversal["balance"]) == ("-24.00", "0.00")
        assert (sugar.retail_price, salt.retail_price) == (65, 45)
