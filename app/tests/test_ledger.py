from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from test_invoice import InvoiceApiTestCase

from config import today
from enums import LedgerKind
from models import LedgerEntry
from schemas import format_invoice_date


def shifted(days: int) -> date:
    return today() + timedelta(
        days=days,
    )


def day(shift: int = 0) -> str:
    """a date relative to today in the api format"""
    return format_invoice_date(
        value=shifted(
            days=shift,
        ),
    )


class LedgerTestCase(InvoiceApiTestCase):
    def stock(
        self,
        amount: str,
        shift: int = 0,
    ) -> LedgerEntry:
        """an invoice inflow without the invoice, the fake ledger does not need one"""
        entry = LedgerEntry(
            id=self.store.new_id(),
            kind=LedgerKind.INVOICE,
            amount=Decimal(
                value=amount,
            ),
            occurred_on=shifted(
                days=shift,
            ),
        )
        self.store.entries.append(
            entry,
        )
        return entry

    def post(
        self,
        url: str,
        payload: dict[str, Any] | None = None,
        expected: int = 200,
    ) -> dict[str, Any]:
        response = self.client.post(
            url=url,
            json=payload,
        )
        self.assertEqual(
            first=response.status_code,
            second=expected,
            msg=response.text,
        )
        return response.json()

    def sale(
        self,
        amount: str,
        shift: int = 0,
        expected: int = 200,
    ) -> dict[str, Any]:
        return self.post(
            url="/ledger/sale",
            payload={
                "occurred_on": day(
                    shift=shift,
                ),
                "amount": amount,
                "comment": None,
            },
            expected=expected,
        )

    def stocktake(
        self,
        counted: str,
        shift: int = 0,
    ) -> dict[str, Any]:
        return self.post(
            url="/ledger/stocktake",
            payload={
                "occurred_on": day(
                    shift=shift,
                ),
                "counted": counted,
                "comment": "переучёт",
            },
        )

    def reverse(
        self,
        entry_id: int,
        expected: int = 200,
    ) -> dict[str, Any]:
        return self.post(
            url=f"/ledger/{entry_id}/reverse",
            expected=expected,
        )

    def history(self) -> dict[str, Any]:
        return self.client.get(
            url="/ledger",
        ).json()

    def revalue(
        self,
        lines: list[tuple[int, str, int]],
        shift: int = 0,
        expected: int = 200,
    ) -> dict[str, Any]:
        """product ids with the counted stock and the new price"""
        return self.post(
            url="/ledger/revaluation",
            payload={
                "occurred_on": day(
                    shift=shift,
                ),
                "comment": "акция",
                "lines": [
                    {
                        "product_id": product_id,
                        "quantity": quantity,
                        "new_price": new_price,
                    }
                    for product_id, quantity, new_price in lines
                ],
            },
            expected=expected,
        )


class OutflowTests(LedgerTestCase):
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

        self.assertEqual(
            first=(sale["amount"], sale["balance"]),
            second=("-1500.00", "8500.00"),
        )
        self.assertEqual(
            first=(write_off["amount"], write_off["balance"]),
            second=("-200.00", "8300.00"),
        )
        entry = self.store.entries[-1]
        self.assertEqual(
            first=(entry.kind, entry.comment),
            second=(LedgerKind.WRITE_OFF, "забрал владелец"),
        )
        self.assertEqual(
            first=self.store.locks,
            second=2,
        )

    def test_zero_and_future_amounts_are_rejected(self) -> None:
        self.sale(
            amount="0",
            expected=422,
        )
        self.sale(
            amount="10.00",
            shift=1,
            expected=422,
        )
        self.assertEqual(
            first=self.store.entries,
            second=[],
        )


class StocktakeTests(LedgerTestCase):
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

        self.assertEqual(
            first=(posted["amount"], posted["balance"]),
            second=("-300.00", "8700.00"),
        )
        [latest, *_] = self.history()["entries"]
        self.assertEqual(
            first=(latest["kind"], latest["amount"], latest["balance_after"]),
            second=("stocktake", "-300.00", "8700.00"),
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
        self.assertEqual(
            first=(posted["amount"], posted["balance"]),
            second=("100.00", "4700.00"),
        )

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

        self.assertEqual(
            first=blocked["detail"],
            second=f"Период закрыт переучётом от {day()}",
        )
        self.assertEqual(
            first=self.client.get(
                url="/ledger/balance",
                params={
                    "on": day(
                        shift=-1,
                    ),
                },
            ).json(),
            second={"balance": "1000.00", "closed_on": day()},
        )


class ReverseTests(LedgerTestCase):
    def test_reversal_cancels_the_entry_once(self) -> None:
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

        self.assertEqual(
            first=(reversal["amount"], reversal["balance"]),
            second=("250.00", "1000.00"),
        )
        entry = self.store.entries[-1]
        self.assertEqual(
            first=(entry.kind, entry.reverses_id, entry.comment, entry.occurred_on),
            second=(
                LedgerKind.SALE,
                sale["id"],
                None,
                shifted(
                    days=-2,
                ),
            ),
        )
        [cancelled] = [
            row for row in self.history()["entries"] if row["id"] == sale["id"]
        ]
        self.assertEqual(
            first=cancelled["reversed_by_id"],
            second=reversal["id"],
        )
        for entry_id, detail in (
            (sale["id"], "Запись уже сторнирована"),
            (reversal["id"], "Сторно нельзя сторнировать"),
        ):
            with self.subTest(
                detail=detail,
            ):
                self.assertEqual(
                    first=self.reverse(
                        entry_id=entry_id,
                        expected=409,
                    )["detail"],
                    second=detail,
                )

    def test_invoice_and_unknown_entries_are_not_reversed(self) -> None:
        inflow = self.stock(
            amount="1000.00",
        )

        self.assertEqual(
            first=self.reverse(
                entry_id=inflow.id,
                expected=409,
            )["detail"],
            second="Проведённую накладную нельзя сторнировать",
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

        self.assertEqual(
            first=blocked["detail"],
            second="После этой записи был переучёт, исправьте остаток новым переучётом",
        )
        self.assertEqual(
            first=reversal["balance"],
            second="1000.00",
        )


class HistoryTests(LedgerTestCase):
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

        self.assertEqual(
            first=[
                (row["occurred_on"], row["amount"], row["balance_after"])
                for row in page["entries"]
            ],
            second=[
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
            ],
        )
        self.assertEqual(
            first=(page["balance"], page["has_more"]),
            second=("850.00", False),
        )
        self.assertEqual(
            first=(len(first["entries"]), first["has_more"]),
            second=(2, True),
        )
