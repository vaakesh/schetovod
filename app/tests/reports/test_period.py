from decimal import Decimal
from typing import Any

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

        sums = (
            "sales_cash",
            "sales_card",
            "cash_moves",
            "cash_after",
            "balance_after",
        )
        assert [
            Decimal(
                value=report[key],
            )
            for key in ("opening", "cash_opening")
        ] == [5000, 0]
        assert [
            (
                row["day"],
                *[
                    Decimal(
                        value=row[key],
                    )
                    for key in sums
                ],
            )
            for row in report["days"]
        ] == [
            (day(shift=-2), 100, 200, 0, 100, 4700),
            (day(shift=-1), 0, 0, 50, 150, 4700),
            # the invoice is on the day it was posted
            (
                day(),
                0,
                0,
                0,
                150,
                Decimal(
                    value="4898.50",
                ),
            ),
        ]
        assert report["days"][1]["cash_notes"] == [
            {"kind": "cash_in", "cash": "50.00", "comment": "размен"},
        ]
        assert report["days"][2]["invoices"] == [
            {
                "supplier_name": "ООО «Поставщик»",
                "invoice_number": "00042/А",
                "cost_total": "155.00",
                "retail_total": "198.50",
                "paid": "100.00",
            },
        ]
        assert report["paid_in_period"] == "100.00"
        assert [(debt["supplier_name"], debt["debt"]) for debt in report["debts"]] == [
            ("ООО «Поставщик»", "55.00"),
        ]

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
