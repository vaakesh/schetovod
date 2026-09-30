from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
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


class RevaluationTests(LedgerTestCase):
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
        self.assertEqual(
            first=(posted["amount"], posted["balance"]),
            second=("-10.00", "990.00"),
        )
        entry = self.store.entries[-1]
        self.assertEqual(
            first=(entry.kind, entry.comment),
            second=(LedgerKind.REVALUATION, "акция"),
        )
        self.assertEqual(
            first=[
                (item.product_id, item.old_price, item.new_price, item.invoice_item_id)
                for item in self.store.revaluations
            ],
            second=[
                (sugar.id, 65, 60, None),
                (salt.id, 36, 40, None),
            ],
        )
        self.assertEqual(
            first=(sugar.retail_price, salt.retail_price, sugar.markup_pct),
            second=(60, 40, 30),
        )

    def test_rejects_unknown_repeated_and_unchanged_products(self) -> None:
        _, sugar, _ = self.known_supplier()
        cases = [
            ([(999, "1", 10)], "Товара с id 999 нет"),
            (
                [(sugar.id, "1", 70), (sugar.id, "2", 70)],
                "Товар «Сахар-песок 1 кг» указан дважды",
            ),
            ([(sugar.id, "1", 65)], "Цена товара «Сахар-песок 1 кг» уже 65 ₽"),
        ]
        for lines, detail in cases:
            with self.subTest(
                detail=detail,
            ):
                self.assertEqual(
                    first=self.revalue(
                        lines=lines,
                        expected=422,
                    )["detail"],
                    second=detail,
                )
        self.assertEqual(
            first=(self.store.entries, sugar.retail_price),
            second=([], 65),
        )

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

        self.assertEqual(
            first=(reversal["amount"], reversal["balance"]),
            second=("-24.00", "0.00"),
        )
        self.assertEqual(
            first=(sugar.retail_price, salt.retail_price),
            second=(65, 45),
        )


class RevaluationLinesTests(LedgerTestCase):
    def lines(
        self,
        entry_id: int,
        expected: int = 200,
    ) -> Any:
        response = self.client.get(
            url=f"/ledger/{entry_id}/revaluation",
        )
        self.assertEqual(
            first=response.status_code,
            second=expected,
            msg=response.text,
        )
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

        self.assertEqual(
            first=self.lines(
                entry_id=posted["id"],
            ),
            second=[
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
            ],
        )
        self.assertEqual(
            first=[
                line["amount"]
                for line in self.lines(
                    entry_id=reversal["id"],
                )
            ],
            second=["20.00", "-10.00"],
        )

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


class ReportTests(LedgerTestCase):
    def report(
        self,
        date_from: str,
        date_to: str,
        url: str = "/ledger/report",
    ) -> Any:
        return self.client.get(
            url=url,
            params={
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    def make_ledger(self) -> None:
        """a week ago before the period, the rest inside it"""
        self.stock(
            amount="5000.00",
            shift=-7,
        )
        self.stock(
            amount="1000.00",
            shift=-3,
        )
        sale = self.sale(
            amount="700.00",
            shift=-2,
        )
        self.sale(
            amount="300.00",
            shift=-2,
        )
        self.reverse(
            entry_id=sale["id"],
        )
        self.post(
            url="/ledger/write-off",
            payload={
                "occurred_on": day(
                    shift=-1,
                ),
                "amount": "50.00",
                "comment": None,
            },
        )
        _, sugar, _ = self.known_supplier()
        self.revalue(
            lines=[
                (sugar.id, "2", 70),
            ],
            shift=-1,
        )
        self.stocktake(
            counted="5600.00",
        )
        # after the stocktake on the same day
        self.stock(
            amount="100.00",
            shift=0,
        )

    def test_totals_add_up_from_the_opening_to_the_closing(self) -> None:
        self.make_ledger()

        report = self.report(
            date_from=day(
                shift=-3,
            ),
            date_to=day(),
        ).json()

        self.assertEqual(
            first={
                key: report[key]
                for key in (
                    "opening",
                    "invoices",
                    "sales",
                    "write_offs",
                    "stocktakes",
                    "revaluations",
                    "closing",
                )
            },
            second={
                "opening": "5000.00",
                # the inflow of today is in the period too
                "invoices": "1100.00",
                # the reversed sale cancels out
                "sales": "-300.00",
                "write_offs": "-50.00",
                "stocktakes": "-60.00",
                "revaluations": "10.00",
                "closing": "5700.00",
            },
        )
        self.assertEqual(
            first=[
                (row["kind"], row["amount"], row["balance_after"])
                for row in report["entries"]
            ],
            second=[
                ("invoice", "1000.00", "6000.00"),
                ("sale", "-700.00", "5300.00"),
                ("sale", "-300.00", "5000.00"),
                ("sale", "700.00", "5700.00"),
                ("write_off", "-50.00", "5650.00"),
                ("revaluation", "10.00", "5660.00"),
                ("stocktake", "-60.00", "5600.00"),
                ("invoice", "100.00", "5700.00"),
            ],
        )

    def test_period_bounds_are_inclusive_and_ordered(self) -> None:
        self.make_ledger()

        report = self.report(
            date_from=day(
                shift=-2,
            ),
            date_to=day(
                shift=-2,
            ),
        ).json()
        backwards = self.report(
            date_from=day(),
            date_to=day(
                shift=-1,
            ),
        )

        self.assertEqual(
            first=(report["opening"], report["sales"], report["closing"]),
            second=("6000.00", "-300.00", "5700.00"),
        )
        self.assertEqual(
            first=(backwards.status_code, backwards.json()["detail"]),
            second=(422, "Начало периода позже его конца"),
        )

    def test_xlsx_has_the_totals_and_the_entries(self) -> None:
        self.make_ledger()

        response = self.report(
            date_from=day(
                shift=-3,
            ),
            date_to=day(),
            url="/ledger/report.xlsx",
        )

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        self.assertEqual(
            first=response.headers["content-disposition"],
            second=f'attachment; filename="otchet_{day(shift=-3)}_{day()}.xlsx"',
        )
        workbook = load_workbook(
            filename=BytesIO(
                initial_bytes=response.content,
            ),
        )
        self.assertEqual(
            first=workbook.sheetnames,
            second=["Итоги", "Записи"],
        )
        totals = {
            label: amount
            for label, amount in workbook["Итоги"].iter_rows(
                min_row=3,
                values_only=True,
            )
        }
        self.assertEqual(
            first=(totals["Остаток на начало"], totals["Остаток на конец"]),
            second=(5000, 5700),
        )
        rows = list(
            workbook["Записи"].iter_rows(
                min_row=2,
                values_only=True,
            ),
        )
        self.assertEqual(
            first=[(row[2], row[5]) for row in rows[1:4]],
            second=[
                ("Касса, сторнирована", -700),
                ("Касса", -300),
                (f"Касса, сторно №{rows[1][0]}", 700),
            ],
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
