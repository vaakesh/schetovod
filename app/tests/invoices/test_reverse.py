from decimal import Decimal
from typing import Any

import pytest

from core.config import today
from core.enums import InvoiceStatus, LedgerKind
from core.schema_types import format_invoice_date
from profit import calculations as profit_calculations
from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestReverse(InvoiceApi):
    def posted(
        self,
        revalue: bool = False,
    ) -> dict[str, Any]:
        """the invoice of the known supplier, the sugar may get a new price with its old stock"""
        self.known_supplier()
        draft = self.upload()
        if revalue:
            form = draft["form"]
            form["lines"][0]["retail_price"] = 70
            form["lines"][0]["revalue_quantity"] = "4"
            draft = self.save(
                draft=draft,
                form=form,
            )
        response = self.confirm(
            draft=draft,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def reverse(
        self,
        invoice_id: int,
        copy_to_draft: bool = False,
        expected: int = 200,
    ) -> Any:
        response = self.client.post(
            url=f"/invoice/{invoice_id}/reverse",
            json={"copy_to_draft": copy_to_draft},
        )
        assert response.status_code == expected, response.text
        return response.json()

    def posted_page(
        self,
        invoice_id: int,
    ) -> dict[str, Any]:
        response = self.client.get(
            url=f"/invoice/{invoice_id}/confirmed",
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_reversal_cancels_the_inflow_on_the_same_day(self) -> None:
        posted = self.posted()
        entry = self.store.entries[-1]

        result = self.reverse(
            invoice_id=posted["id"],
        )

        reversal = self.store.entries[-1]
        assert (
            reversal.kind,
            reversal.amount,
            reversal.occurred_on,
            reversal.reverses_id,
            reversal.invoice_id,
        ) == (
            LedgerKind.INVOICE,
            -entry.amount,
            entry.occurred_on,
            entry.id,
            posted["id"],
        )
        assert result == {
            "id": posted["id"],
            "reversal_entry_id": reversal.id,
            "draft_id": None,
            "balance": "0.00",
        }
        assert self.store.invoices[posted["id"]].status == InvoiceStatus.REVERSED
        assert {entry.invoice_status, reversal.invoice_status} == {
            InvoiceStatus.REVERSED,
        }
        page = self.posted_page(
            invoice_id=posted["id"],
        )
        assert (page["status"], page["reverse_block"], page["debt"]) == (
            "reversed",
            "Накладная уже сторнирована",
            "0",
        )

    def test_copy_is_a_ready_draft_with_the_posted_lines(self) -> None:
        posted = self.posted()

        result = self.reverse(
            invoice_id=posted["id"],
            copy_to_draft=True,
        )

        draft = self.client.get(
            url=f"/invoice/{result['draft_id']}",
        ).json()
        assert draft["ready"], draft["issues"]
        assert (
            draft["form"]["invoice_number"],
            draft["form"]["invoice_date"],
            [
                (
                    line["name"],
                    Decimal(
                        value=line["quantity"],
                    ),
                    Decimal(
                        value=line["cost_price_total"],
                    ),
                    line["retail_price"],
                )
                for line in draft["form"]["lines"]
            ],
        ) == (
            "00042/А",
            "12-08-2026",
            [
                (
                    "Сахар-песок 1 кг",
                    Decimal(
                        value="2.5",
                    ),
                    Decimal(
                        value=125,
                    ),
                    65,
                ),
                (
                    "Соль",
                    Decimal(
                        value=1,
                    ),
                    Decimal(
                        value=30,
                    ),
                    36,
                ),
            ],
        )

        # the same number may be posted again once the first posting is reversed
        response = self.confirm(
            draft=draft,
        )
        assert response.status_code == 200, response.text
        assert response.json()["balance"] == posted["balance"]

    def test_stocktake_after_the_invoice_blocks_the_reversal(self) -> None:
        posted = self.posted()
        response = self.client.post(
            url="/ledger/stocktake",
            json={
                "occurred_on": format_invoice_date(
                    value=today(),
                ),
                "counted": posted["balance"],
                "comment": None,
            },
        )
        assert response.status_code == 200, response.text

        assert (
            self.posted_page(
                invoice_id=posted["id"],
            )["reverse_block"]
            == "После накладной был переучёт, сторнировать её уже нельзя"
        )
        assert self.reverse(
            invoice_id=posted["id"],
            expected=409,
        ) == {"detail": "После накладной был переучёт, сторнировать её уже нельзя"}

    def test_payments_block_the_reversal(self) -> None:
        posted = self.posted()
        response = self.client.post(
            url=f"/invoice/{posted['id']}/payments",
            json={
                "paid_on": format_invoice_date(
                    value=today(),
                ),
                "amount": "100.00",
                "comment": None,
            },
        )
        assert response.status_code == 200, response.text

        assert self.reverse(
            invoice_id=posted["id"],
            expected=409,
        ) == {"detail": "По накладной есть оплаты на 100.00 ₽, сначала удалите их"}

    def test_reversed_invoice_is_not_reversed_again(self) -> None:
        posted = self.posted()
        self.reverse(
            invoice_id=posted["id"],
        )

        self.reverse(
            invoice_id=posted["id"],
            expected=404,
        )

    def test_revaluation_is_reversed_with_the_invoice(self) -> None:
        posted = self.posted(
            revalue=True,
        )
        sugar = next(
            product
            for product in self.store.products.values()
            if product.name == "Сахар-песок 1 кг"
        )
        assert sugar.retail_price == 70

        result = self.reverse(
            invoice_id=posted["id"],
        )

        revaluations = [
            (entry.id, entry.reverses_id, entry.amount)
            for entry in self.store.entries
            if entry.kind == LedgerKind.REVALUATION
        ]
        assert len(revaluations) == 2
        assert revaluations[1][1:] == (revaluations[0][0], -revaluations[0][2])
        assert sugar.retail_price == 65
        assert result["balance"] == "0.00"

    def second_posted(self) -> dict[str, Any]:
        """another invoice of the same supplier, the sugar costs 60 instead of 50"""
        payload = invoice_payload()
        payload["invoice_number"] = "43"
        payload["items"][0]["cost_price_total"] = "150.00"
        payload["items"][0]["base_price_total"] = "150.00"
        response = self.confirm(
            draft=self.upload(
                payload=payload,
            ),
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_catalog_takes_the_cost_of_the_last_delivery_that_stays(self) -> None:
        self.posted()
        second = self.second_posted()

        def sugar_cost() -> str:
            catalog = self.client.get(
                url="/catalog",
            ).json()
            return next(
                product["cost_price"]
                for product in catalog["products"]
                if product["name"] == "Сахар-песок 1 кг"
            )

        assert Decimal(sugar_cost()) == 60
        self.reverse(
            invoice_id=second["id"],
        )
        assert Decimal(sugar_cost()) == 50

    def test_margin_leaves_the_reversed_invoice_out(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # the frozen clock is before the first count, the margin starts from it
        monkeypatch.setattr(
            target=profit_calculations,
            name="COUNTED_ON",
            value=today(),
        )
        self.posted()
        second = self.second_posted()

        def margin() -> tuple[Decimal, Decimal]:
            report = self.client.get(
                url="/profit",
            ).json()
            return (
                Decimal(report["margin"]["cost"]),
                Decimal(report["margin"]["retail"]),
            )

        both = margin()
        self.reverse(
            invoice_id=second["id"],
        )

        # the first invoice alone: 125 + 30 at cost, 2.5 * 65 + 36 at retail
        assert margin() == (155, Decimal("198.5"))
        assert both != margin()

    def test_profit_and_debts_leave_the_reversed_invoice_out(self) -> None:
        posted = self.posted()
        self.reverse(
            invoice_id=posted["id"],
        )

        listed = self.client.get(
            url="/invoice",
            params={"unpaid": "true"},
        ).json()
        assert listed["items"] == []
        report = self.client.get(
            url="/ledger/report/days",
            params={
                "date_from": format_invoice_date(
                    value=today(),
                ),
                "date_to": format_invoice_date(
                    value=today(),
                ),
            },
        ).json()
        assert [day["invoices"] for day in report["days"]] == [[]]
        assert report["debts"] == []
        assert Decimal(report["days"][0]["balance_after"]) == 0
