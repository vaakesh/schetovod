from decimal import Decimal
from typing import Any

import pymupdf

from tests.fakes import invoice_payload
from tests.ledger.helpers import LedgerApi, day


class TestPeriodReport(LedgerApi):
    def make_ledger(self) -> int:
        """a stock before the period, then sales, a cash-in and a confirmed invoice paid in part"""
        self.stock(
            amount="5000.00",
            shift=-7,
        )
        sale = self.sale(
            amount="700.00",
            cash="700.00",
            shift=-2,
        )
        self.sale(
            amount="300.00",
            cash="100.00",
            shift=-2,
        )
        self.reverse(
            entry_id=sale["id"],
        )
        self.cash(
            kind="cash-in",
            amount="50.00",
            comment="размен",
            shift=-1,
        )
        self.known_supplier()
        draft = self.upload()
        self.post(
            url=f"/invoice/{draft['id']}/confirm",
            payload={
                "occurred_on": day(),
            },
        )
        self.post(
            url=f"/invoice/{draft['id']}/payments",
            payload={
                "paid_on": day(),
                "amount": "100.00",
                "comment": None,
            },
        )
        return draft["id"]

    def days(
        self,
        date_from: str,
        date_to: str,
    ) -> dict[str, Any]:
        response = self.client.get(
            url="/ledger/report/days",
            params={
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_period_by_days(self) -> None:
        self.make_ledger()

        report = self.days(
            date_from=day(
                shift=-3,
            ),
            date_to=day(),
        )

        assert report == {
            "date_from": day(
                shift=-3,
            ),
            "date_to": day(),
            "opening": "5000.00",
            "cash_opening": "0",
            "days": [
                {
                    "day": day(
                        shift=-2,
                    ),
                    "invoices": [],
                    "opening": "5000.00",
                    "cash_opening": "0.00",
                    "stock_movements": [
                        {"kind": "sale", "amount": "-300.00", "comment": None},
                    ],
                    "cash_movements": [
                        {"kind": "sale", "amount": "100.00", "comment": None},
                    ],
                    "sales_cash": "100.00",
                    "sales_card": "200.00",
                    "cash_moves": "0",
                    "cash_notes": [],
                    "cash_after": "100.00",
                    "balance_after": "4700.00",
                },
                {
                    "day": day(
                        shift=-1,
                    ),
                    "invoices": [],
                    "opening": "4700.00",
                    "cash_opening": "100.00",
                    "stock_movements": [],
                    "cash_movements": [
                        {"kind": "cash_in", "amount": "50.00", "comment": "размен"},
                    ],
                    "sales_cash": "0",
                    "sales_card": "0",
                    "cash_moves": "50.00",
                    "cash_notes": [
                        {"kind": "cash_in", "cash": "50.00", "comment": "размен"},
                    ],
                    "cash_after": "150.00",
                    "balance_after": "4700.00",
                },
                {
                    "day": day(),
                    "invoices": [
                        {
                            "supplier_name": "ООО «Поставщик»",
                            "invoice_number": "00042/А",
                            "cost_total": "155.00",
                            "retail_total": "198.50",
                            "paid": "100.00",
                        },
                    ],
                    "opening": "4700.00",
                    "cash_opening": "150.00",
                    "stock_movements": [
                        {"kind": "invoice", "amount": "198.50", "comment": None},
                    ],
                    "cash_movements": [],
                    "sales_cash": "0",
                    "sales_card": "0",
                    "cash_moves": "0",
                    "cash_notes": [],
                    "cash_after": "150.00",
                    "balance_after": "4898.50",
                },
            ],
            "paid_in_period": "100.00",
            "debts": [
                {
                    "supplier_name": "ООО «Поставщик»",
                    "invoice_number": "00042/А",
                    "invoice_date": "12-08-2026",
                    "cost_total": "155.00",
                    "paid": "100.00",
                    "debt": "55.00",
                },
            ],
        }

    def test_all_movements_keep_the_ledger_order_within_the_day(self) -> None:
        _, sugar, _ = self.known_supplier()
        self.stock(
            amount="5000.00",
            shift=-1,
        )
        self.cash(
            kind="cash-in",
            amount="200.00",
            shift=-1,
        )
        self.cash(
            kind="cash-in",
            amount="50.00",
        )
        self.sale(
            amount="300.00",
            cash="100.00",
        )
        self.post(
            url="/ledger/write-off",
            payload={"occurred_on": day(), "amount": "40.00", "comment": "просрочка"},
        )
        self.post(
            url="/ledger/stock-in",
            payload={"occurred_on": day(), "amount": "60.00", "comment": None},
        )
        self.revalue(
            lines=[(sugar.id, "2", 70)],
        )
        self.cash(
            kind="cash-out",
            amount="30.00",
            comment="пакеты",
        )
        self.stocktake(
            counted="4800.00",
        )
        self.cash_count(
            counted="310.00",
        )
        self.sale(
            amount="20.00",
        )
        self.stock(
            amount="1000.00",
        )

        report = self.days(
            date_from=day(),
            date_to=day(),
        )

        assert report == {
            "date_from": day(),
            "date_to": day(),
            "opening": "5000.00",
            "cash_opening": "200.00",
            "days": [
                {
                    "day": day(),
                    "invoices": [],
                    "opening": "5000.00",
                    "cash_opening": "200.00",
                    "stock_movements": [
                        {"kind": "sale", "amount": "-300.00", "comment": None},
                        {
                            "kind": "write_off",
                            "amount": "-40.00",
                            "comment": "просрочка",
                        },
                        {"kind": "stock_in", "amount": "60.00", "comment": None},
                        {
                            "kind": "revaluation",
                            "amount": "10.00",
                            "comment": "акция",
                        },
                        {
                            "kind": "stocktake",
                            "amount": "70.00",
                            "comment": "переучёт",
                        },
                        {"kind": "sale", "amount": "-20.00", "comment": None},
                        {"kind": "invoice", "amount": "1000.00", "comment": None},
                    ],
                    "cash_movements": [
                        {"kind": "cash_in", "amount": "50.00", "comment": None},
                        {"kind": "sale", "amount": "100.00", "comment": None},
                        {
                            "kind": "cash_out",
                            "amount": "-30.00",
                            "comment": "пакеты",
                        },
                        {"kind": "cash_count", "amount": "-10.00", "comment": None},
                    ],
                    "sales_cash": "100.00",
                    "sales_card": "220.00",
                    "cash_moves": "10.00",
                    "cash_notes": [
                        {"kind": "cash_in", "cash": "50.00", "comment": None},
                        {"kind": "cash_out", "cash": "-30.00", "comment": "пакеты"},
                        {"kind": "cash_count", "cash": "-10.00", "comment": None},
                    ],
                    "cash_after": "310.00",
                    "balance_after": "5780.00",
                },
            ],
            "paid_in_period": "0",
            "debts": [],
        }

    def test_zero_counts_are_shown_but_a_cashless_sale_has_no_cash_movement(
        self,
    ) -> None:
        self.stock(
            amount="1000.00",
            shift=-1,
        )
        self.cash_count(
            counted="0.00",
        )
        self.stocktake(
            counted="1000.00",
        )
        self.sale(
            amount="20.00",
        )

        report = self.days(
            date_from=day(),
            date_to=day(),
        )

        assert report == {
            "date_from": day(),
            "date_to": day(),
            "opening": "1000.00",
            "cash_opening": "0",
            "days": [
                {
                    "day": day(),
                    "invoices": [],
                    "opening": "1000.00",
                    "cash_opening": "0.00",
                    "stock_movements": [
                        {
                            "kind": "stocktake",
                            "amount": "0.00",
                            "comment": "переучёт",
                        },
                        {"kind": "sale", "amount": "-20.00", "comment": None},
                    ],
                    "cash_movements": [
                        {"kind": "cash_count", "amount": "0.00", "comment": None},
                    ],
                    "sales_cash": "0.00",
                    "sales_card": "20.00",
                    "cash_moves": "0.00",
                    "cash_notes": [
                        {"kind": "cash_count", "cash": "0.00", "comment": None},
                    ],
                    "cash_after": "0.00",
                    "balance_after": "980.00",
                },
            ],
            "paid_in_period": "0",
            "debts": [],
        }

    def test_a_day_with_only_cancelled_movements_keeps_its_actual_balances(
        self,
    ) -> None:
        self.known_supplier()
        self.stock(
            amount="1000.00",
            shift=-2,
        )
        sale = self.sale(
            amount="300.00",
            cash="100.00",
            shift=-1,
        )
        cash = self.cash(
            kind="cash-in",
            amount="50.00",
            shift=-1,
        )
        self.reverse(
            entry_id=sale["id"],
        )
        self.reverse(
            entry_id=cash["id"],
        )
        draft = self.upload()
        self.post(
            url=f"/invoice/{draft['id']}/confirm",
            payload={
                "occurred_on": day(
                    shift=-1,
                ),
            },
        )
        self.post(
            url=f"/invoice/{draft['id']}/reverse",
            payload={"copy_to_draft": False},
        )

        report = self.days(
            date_from=day(
                shift=-1,
            ),
            date_to=day(),
        )

        assert report == {
            "date_from": day(
                shift=-1,
            ),
            "date_to": day(),
            "opening": "1000.00",
            "cash_opening": "0",
            "days": [
                {
                    "day": day(
                        shift=-1,
                    ),
                    "invoices": [],
                    "opening": "1000.00",
                    "cash_opening": "0.00",
                    "stock_movements": [],
                    "cash_movements": [],
                    "sales_cash": "0.00",
                    "sales_card": "0.00",
                    "cash_moves": "0.00",
                    "cash_notes": [],
                    "cash_after": "0.00",
                    "balance_after": "1000.00",
                },
            ],
            "paid_in_period": "0",
            "debts": [],
        }

    def test_active_invoices_are_combined_at_the_first_active_invoice(self) -> None:
        self.known_supplier()
        self.stock(
            amount="1000.00",
            shift=-1,
        )
        self.cash(
            kind="cash-in",
            amount="200.00",
            shift=-1,
        )
        cancelled_payload = invoice_payload()
        cancelled_payload["invoice_number"] = "41"
        cancelled = self.upload(
            payload=cancelled_payload,
        )
        self.post(
            url=f"/invoice/{cancelled['id']}/confirm",
            payload={"occurred_on": day()},
        )
        self.post(
            url=f"/invoice/{cancelled['id']}/reverse",
            payload={"copy_to_draft": False},
        )
        self.sale(
            amount="100.00",
            cash="30.00",
        )
        first = self.upload()
        self.post(
            url=f"/invoice/{first['id']}/confirm",
            payload={"occurred_on": day()},
        )
        self.post(
            url="/ledger/write-off",
            payload={"occurred_on": day(), "amount": "20.00", "comment": None},
        )
        second_payload = invoice_payload()
        second_payload["invoice_number"] = "43"
        second = self.upload(
            payload=second_payload,
        )
        self.post(
            url=f"/invoice/{second['id']}/confirm",
            payload={"occurred_on": day()},
        )
        self.post(
            url="/ledger/stock-in",
            payload={"occurred_on": day(), "amount": "50.00", "comment": None},
        )

        report = self.days(
            date_from=day(),
            date_to=day(),
        )

        assert report == {
            "date_from": day(),
            "date_to": day(),
            "opening": "1000.00",
            "cash_opening": "200.00",
            "days": [
                {
                    "day": day(),
                    "invoices": [
                        {
                            "supplier_name": "ООО «Поставщик»",
                            "invoice_number": "00042/А",
                            "cost_total": "155.00",
                            "retail_total": "198.50",
                            "paid": "0",
                        },
                        {
                            "supplier_name": "ООО «Поставщик»",
                            "invoice_number": "43",
                            "cost_total": "155.00",
                            "retail_total": "198.50",
                            "paid": "0",
                        },
                    ],
                    "opening": "1000.00",
                    "cash_opening": "200.00",
                    "stock_movements": [
                        {"kind": "sale", "amount": "-100.00", "comment": None},
                        {"kind": "invoice", "amount": "397.00", "comment": None},
                        {"kind": "write_off", "amount": "-20.00", "comment": None},
                        {"kind": "stock_in", "amount": "50.00", "comment": None},
                    ],
                    "cash_movements": [
                        {"kind": "sale", "amount": "30.00", "comment": None},
                    ],
                    "sales_cash": "30.00",
                    "sales_card": "70.00",
                    "cash_moves": "0",
                    "cash_notes": [],
                    "cash_after": "230.00",
                    "balance_after": "1327.00",
                },
            ],
            "paid_in_period": "0",
            "debts": [
                {
                    "supplier_name": "ООО «Поставщик»",
                    "invoice_number": "00042/А",
                    "invoice_date": "12-08-2026",
                    "cost_total": "155.00",
                    "paid": "0",
                    "debt": "155.00",
                },
                {
                    "supplier_name": "ООО «Поставщик»",
                    "invoice_number": "43",
                    "invoice_date": "12-08-2026",
                    "cost_total": "155.00",
                    "paid": "0",
                    "debt": "155.00",
                },
            ],
        }

        response = self.client.get(
            url="/ledger/report.pdf",
            params={"date_from": day(), "date_to": day()},
        )
        assert response.status_code == 200, response.text
        with pymupdf.open(
            stream=response.content,
            filetype="pdf",
        ) as pdf:
            text = pdf[0].get_text()

        assert "+397,00\nнакладные" in text
        assert "№00042/А" in text
        assert "№43" in text
        assert "№41" not in text
        assert (
            text.count(
                "198,50",
            )
            == 2
        )

    def test_reports_print_the_short_name(self) -> None:
        self.make_ledger()
        [supplier] = self.store.suppliers.values()
        response = self.client.put(
            url=f"/supplier/{supplier.id}",
            json={
                "name": supplier.name,
                "short_name": "Поставщик",
                "inn": supplier.inn,
            },
        )
        assert response.status_code == 200, response.text

        days = self.days(
            date_from=day(),
            date_to=day(),
        )
        report = self.client.get(
            url="/ledger/report",
            params={
                "date_from": day(),
                "date_to": day(),
            },
        ).json()
        ledger = self.client.get(
            url="/ledger",
        ).json()

        assert [row["supplier_name"] for row in days["days"][0]["invoices"]] == [
            "Поставщик",
        ]
        assert [debt["supplier_name"] for debt in days["debts"]] == ["Поставщик"]
        assert [
            entry["supplier_name"]
            for entry in report["entries"]
            if entry["kind"] == "invoice"
        ] == ["Поставщик"]
        # the ledger keeps the full name, the stock before the period has no invoice
        assert [
            entry["supplier_name"]
            for entry in ledger["entries"]
            if entry["invoice_id"] is not None
        ] == ["ООО «Поставщик»"]

    def test_debt_is_counted_on_the_last_day(self) -> None:
        self.make_ledger()

        report = self.days(
            date_from=day(
                shift=-3,
            ),
            date_to=day(
                shift=-1,
            ),
        )

        # the invoice was posted today, the day before nothing was owed
        assert report["debts"] == []
        assert (
            Decimal(
                value=report["paid_in_period"],
            )
            == 0
        )

    def test_pdf(self) -> None:
        self.make_ledger()

        response = self.client.get(
            url="/ledger/report.pdf",
            params={
                "date_from": day(
                    shift=-3,
                ),
                "date_to": day(),
            },
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="otchet_{day(shift=-3)}_{day()}.pdf"'
        )
        assert response.content.startswith(
            b"%PDF",
        )

    def test_pdf_of_an_empty_period(self) -> None:
        response = self.client.get(
            url="/ledger/report.pdf",
            params={
                "date_from": day(),
                "date_to": day(),
            },
        )

        assert response.status_code == 200, response.text
        assert response.content.startswith(
            b"%PDF",
        )

    def test_reversed_period_is_rejected(self) -> None:
        response = self.client.get(
            url="/ledger/report.pdf",
            params={
                "date_from": day(),
                "date_to": day(
                    shift=-1,
                ),
            },
        )

        assert response.status_code == 422
