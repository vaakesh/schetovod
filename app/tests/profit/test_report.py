from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from core.enums import ExpenseBasis, LedgerKind, ReceiptKind
from invoices.models import InvoiceItem
from ledger.models import LedgerEntry
from profit import service as profit_service
from profit.models import OperatingExpense
from tests.fakes import FakeStore
from traffic.models import Receipt

TODAY = date(
    year=2026,
    month=11,
    day=15,
)
FIRST_MONTH = date(
    year=2026,
    month=4,
    day=1,
)


class TestProfit:
    @pytest.fixture(
        autouse=True,
    )
    def setup(
        self,
        store: FakeStore,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.client = client
        self.store = store
        monkeypatch.setattr(
            target=profit_service,
            name="today",
            value=lambda: TODAY,
        )

    def sale(
        self,
        day: date,
        total: str,
        card: str,
        kind: ReceiptKind = ReceiptKind.SALE,
    ) -> None:
        self.store.receipts.append(
            Receipt(
                aqsi_id=uuid4(),
                shift_id=uuid4(),
                processed_at=datetime(
                    year=day.year,
                    month=day.month,
                    day=day.day,
                    hour=12,
                    tzinfo=UTC,
                ),
                kind=kind,
                total=Decimal(
                    value=total,
                ),
                cash=Decimal(
                    value=total,
                )
                - Decimal(
                    value=card,
                ),
                card=Decimal(
                    value=card,
                ),
                positions=1,
            ),
        )

    def purchase(
        self,
        day: date,
        cost: str,
        retail: str,
    ) -> None:
        invoice_id = self.store.new_id()
        self.store.entries.append(
            LedgerEntry(
                kind=LedgerKind.INVOICE,
                occurred_on=day,
                amount=Decimal(
                    value=retail,
                ),
                cash=Decimal(
                    value=0,
                ),
                invoice_id=invoice_id,
            ),
        )
        self.store.items.append(
            InvoiceItem(
                invoice_id=invoice_id,
                quantity=Decimal(
                    value=1,
                ),
                cost_price_total=Decimal(
                    value=cost,
                ),
                retail_price=Decimal(
                    value=retail,
                ),
            ),
        )

    def stock_entry(
        self,
        kind: LedgerKind,
        day: date,
        amount: str,
    ) -> None:
        self.store.entries.append(
            LedgerEntry(
                kind=kind,
                occurred_on=day,
                amount=Decimal(
                    value=amount,
                ),
                cash=Decimal(
                    value=0,
                ),
            ),
        )

    def expense(
        self,
        name: str,
        basis: ExpenseBasis,
        amount: str,
        starts_on: date = FIRST_MONTH,
        ends_on: date | None = None,
    ) -> None:
        self.store.expenses.append(
            OperatingExpense(
                id=len(
                    self.store.expenses,
                )
                + 1,
                name=name,
                basis=basis,
                amount=Decimal(
                    value=amount,
                ),
                starts_on=starts_on,
                ends_on=ends_on,
            ),
        )

    def report(self) -> dict[str, Any]:
        response = self.client.get(
            url="/profit",
        )
        assert response.status_code == 200
        return response.json()

    def month(
        self,
        report: dict[str, Any],
        value: str,
    ) -> dict[str, Any]:
        return next(month for month in report["months"] if month["month"] == value)

    def test_month_takes_every_kind_of_expense(self) -> None:
        october = date(
            year=2026,
            month=10,
            day=27,
        )
        self.sale(
            day=october,
            total="100000",
            card="80000",
        )
        self.purchase(
            day=october,
            cost="660",
            retail="1000",
        )
        self.expense(
            name="Аренда",
            basis=ExpenseBasis.MONTH,
            amount="10000",
        )
        self.expense(
            name="Патент",
            basis=ExpenseBasis.YEAR,
            amount="12000",
        )
        self.expense(
            name="Смена",
            basis=ExpenseBasis.WORK_DAY,
            amount="3500",
        )
        self.expense(
            name="Продавцу",
            basis=ExpenseBasis.REVENUE_PERCENT,
            amount="2",
        )
        self.expense(
            name="Эквайринг",
            basis=ExpenseBasis.CARD_PERCENT,
            amount="3",
        )

        month = self.month(
            report=self.report(),
            value="01-10-2026",
        )

        assert month["in_progress"] is False
        assert month["work_days"] == 1
        assert Decimal(month["margin"]) == Decimal("34.0")
        assert Decimal(month["gross"]) == Decimal(34000)
        assert [Decimal(charge["total"]) for charge in month["charges"]] == [
            Decimal(10000),
            Decimal(1000),
            Decimal(3500),
            Decimal(2000),
            Decimal(2400),
        ]
        assert Decimal(month["profit"]) == Decimal(15100)

    def test_refunds_lower_the_takings_and_a_day_of_refunds_is_no_work(self) -> None:
        self.sale(
            day=date(
                year=2026,
                month=10,
                day=27,
            ),
            total="1000",
            card="400",
        )
        self.sale(
            day=date(
                year=2026,
                month=10,
                day=28,
            ),
            total="100",
            card="100",
            kind=ReceiptKind.REFUND,
        )

        month = self.month(
            report=self.report(),
            value="01-10-2026",
        )

        assert Decimal(month["revenue"]) == Decimal(900)
        assert Decimal(month["card"]) == Decimal(300)
        assert month["work_days"] == 1

    def test_fixed_costs_of_a_running_month_are_for_the_days_gone_by(self) -> None:
        self.sale(
            day=TODAY,
            total="100",
            card="0",
        )
        self.expense(
            name="Аренда",
            basis=ExpenseBasis.MONTH,
            amount="30000",
        )

        month = self.month(
            report=self.report(),
            value="01-11-2026",
        )

        assert month["in_progress"] is True
        assert Decimal(month["expenses"]) == Decimal(15000)

    def test_margin_ignores_invoices_before_the_first_count(self) -> None:
        self.sale(
            day=date(
                year=2026,
                month=10,
                day=27,
            ),
            total="1000",
            card="0",
        )
        self.purchase(
            day=date(
                year=2026,
                month=10,
                day=20,
            ),
            cost="900",
            retail="1000",
        )
        self.purchase(
            day=date(
                year=2026,
                month=10,
                day=27,
            ),
            cost="500",
            retail="1000",
        )

        report = self.report()

        assert Decimal(report["margin"]["percent"]) == Decimal("50.0")

    def test_a_month_without_invoices_borrows_the_first_margin(self) -> None:
        self.sale(
            day=date(
                year=2026,
                month=5,
                day=10,
            ),
            total="1000",
            card="0",
        )
        self.purchase(
            day=date(
                year=2026,
                month=10,
                day=27,
            ),
            cost="500",
            retail="1000",
        )

        may = self.month(
            report=self.report(),
            value="01-05-2026",
        )

        assert may["margin_estimated"] is True
        assert Decimal(may["gross"]) == Decimal(500)

    def test_without_invoices_there_is_no_profit_to_show(self) -> None:
        self.sale(
            day=date(
                year=2026,
                month=10,
                day=27,
            ),
            total="1000",
            card="0",
        )

        report = self.report()

        assert report["margin"] is None
        assert report["months"][1]["profit"] is None
        assert report["average_profit"] is None

    def test_stocktake_moves_the_profit_at_cost_and_write_offs_do_not(self) -> None:
        october = date(
            year=2026,
            month=10,
            day=28,
        )
        self.sale(
            day=october,
            total="1000",
            card="0",
        )
        self.purchase(
            day=october,
            cost="600",
            retail="1000",
        )
        # the first count replaced a made-up balance, it says nothing about the shop
        self.stock_entry(
            kind=LedgerKind.STOCKTAKE,
            day=date(
                year=2026,
                month=10,
                day=25,
            ),
            amount="163980",
        )
        self.stock_entry(
            kind=LedgerKind.STOCKTAKE,
            day=october,
            amount="-100",
        )
        self.stock_entry(
            kind=LedgerKind.WRITE_OFF,
            day=october,
            amount="-50",
        )

        month = self.month(
            report=self.report(),
            value="01-10-2026",
        )

        assert Decimal(month["stock_difference"]) == Decimal(-60)
        assert Decimal(month["write_offs"]) == Decimal(30)
        assert Decimal(month["profit"]) == Decimal(340)

    def test_average_leaves_the_running_month_out(self) -> None:
        self.purchase(
            day=date(
                year=2026,
                month=10,
                day=27,
            ),
            cost="500",
            retail="1000",
        )
        for day, total in (
            (
                date(
                    year=2026,
                    month=9,
                    day=10,
                ),
                "1000",
            ),
            (
                date(
                    year=2026,
                    month=10,
                    day=10,
                ),
                "3000",
            ),
            (
                TODAY,
                "99999",
            ),
        ):
            self.sale(
                day=day,
                total=total,
                card="0",
            )

        report = self.report()

        assert Decimal(report["average_profit"]) == Decimal(1000)

    def test_break_even_day_covers_the_costs_of_a_month(self) -> None:
        october = date(
            year=2026,
            month=10,
            day=27,
        )
        self.sale(
            day=october,
            total="1000",
            card="500",
        )
        self.purchase(
            day=october,
            cost="600",
            retail="1000",
        )
        self.expense(
            name="Аренда",
            basis=ExpenseBasis.MONTH,
            amount="3000",
        )
        self.expense(
            name="Смена",
            basis=ExpenseBasis.WORK_DAY,
            amount="1000",
        )
        self.expense(
            name="Эквайринг",
            basis=ExpenseBasis.CARD_PERCENT,
            amount="20",
        )

        # one working day: 4000 of costs over 0.4 - 0.2 * 0.5 left of a ruble
        assert Decimal(self.report()["break_even_day"]) == Decimal("13333.33")

    def test_new_rate_keeps_the_past_months(self) -> None:
        october = date(
            year=2026,
            month=10,
            day=27,
        )
        self.sale(
            day=october,
            total="100",
            card="0",
        )
        self.sale(
            day=TODAY,
            total="100",
            card="0",
        )
        self.purchase(
            day=october,
            cost="500",
            retail="1000",
        )
        self.expense(
            name="Свет",
            basis=ExpenseBasis.MONTH,
            amount="50000",
        )

        response = self.client.put(
            url="/profit/expenses/1",
            json={
                "name": "Свет",
                "basis": "month",
                "amount": "60000",
                "starts_on": "01-11-2026",
            },
        )

        assert response.status_code == 200
        report = response.json()
        assert len(report["expenses"]) == 1
        assert Decimal(report["expenses"][0]["amount"]) == 60000
        assert self.store.expenses[0].ends_on == date(
            year=2026,
            month=11,
            day=1,
        )
        october_month = self.month(
            report=report,
            value="01-10-2026",
        )
        november = self.month(
            report=report,
            value="01-11-2026",
        )
        assert Decimal(october_month["expenses"]) == Decimal(50000)
        assert Decimal(november["expenses"]) == Decimal(30000)

    def test_change_from_the_first_month_replaces_the_rate(self) -> None:
        self.expense(
            name="Свет",
            basis=ExpenseBasis.MONTH,
            amount="50000",
        )

        response = self.client.put(
            url="/profit/expenses/1",
            json={
                "name": "Электричество",
                "basis": "month",
                "amount": "60000",
                "starts_on": "01-04-2026",
            },
        )

        assert response.status_code == 200
        assert len(self.store.expenses) == 1
        assert self.store.expenses[0].name == "Электричество"
        assert self.store.expenses[0].ends_on is None

    def test_rate_can_not_start_before_the_one_it_replaces(self) -> None:
        self.expense(
            name="Свет",
            basis=ExpenseBasis.MONTH,
            amount="50000",
        )

        response = self.client.put(
            url="/profit/expenses/1",
            json={
                "name": "Свет",
                "basis": "month",
                "amount": "60000",
                "starts_on": "01-03-2026",
            },
        )

        assert response.status_code == 422

    def test_added_expense_is_listed(self) -> None:
        response = self.client.post(
            url="/profit/expenses",
            json={
                "name": "  Вывоз мусора ",
                "basis": "year",
                "amount": "24000",
                "starts_on": "01-11-2026",
            },
        )

        assert response.status_code == 200
        assert response.json()["expenses"][0]["name"] == "Вывоз мусора"

    @pytest.mark.parametrize(
        argnames="payload",
        argvalues=[
            {"amount": "0"},
            {"amount": "101", "basis": "card_percent"},
            {"starts_on": "15-11-2026"},
        ],
    )
    def test_nonsense_expense_is_refused(
        self,
        payload: dict[str, str],
    ) -> None:
        response = self.client.post(
            url="/profit/expenses",
            json={
                "name": "Расход",
                "basis": "month",
                "amount": "100",
                "starts_on": "01-11-2026",
            }
            | payload,
        )

        assert response.status_code == 422
        assert not self.store.expenses

    def test_stopped_expense_stays_in_the_past(self) -> None:
        self.expense(
            name="Свет",
            basis=ExpenseBasis.MONTH,
            amount="50000",
        )

        response = self.client.delete(
            url="/profit/expenses/1",
        )

        assert response.status_code == 200
        assert response.json()["expenses"] == []
        assert self.store.expenses[0].ends_on == date(
            year=2026,
            month=11,
            day=1,
        )

    def test_expense_that_never_applied_is_deleted(self) -> None:
        self.expense(
            name="Свет",
            basis=ExpenseBasis.MONTH,
            amount="50000",
            starts_on=date(
                year=2026,
                month=11,
                day=1,
            ),
        )

        response = self.client.delete(
            url="/profit/expenses/1",
        )

        assert response.status_code == 200
        assert not self.store.expenses

    def test_stopped_expense_can_not_be_changed(self) -> None:
        self.expense(
            name="Свет",
            basis=ExpenseBasis.MONTH,
            amount="50000",
            ends_on=date(
                year=2026,
                month=10,
                day=1,
            ),
        )

        response = self.client.delete(
            url="/profit/expenses/1",
        )

        assert response.status_code == 409

    def test_unknown_expense(self) -> None:
        response = self.client.delete(
            url="/profit/expenses/1",
        )

        assert response.status_code == 404
