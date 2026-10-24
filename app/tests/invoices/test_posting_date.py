from datetime import date
from decimal import Decimal

from core.enums import InvoiceStatus, LedgerKind
from ledger.models import LedgerEntry
from tests.helpers import InvoiceApi


class TestPostingDate(InvoiceApi):
    def test_posted_on_the_day_the_goods_came(self) -> None:
        """the goods may come days before the invoice is posted"""
        self.known_supplier()
        draft = self.upload()

        response = self.confirm(
            draft=draft,
            occurred_on="14-10-2026",
        )

        assert response.status_code == 200, response.text
        # the clock says 16-10-2026
        assert [entry.occurred_on for entry in self.store.entries] == [
            date(
                year=2026,
                month=10,
                day=14,
            ),
        ]

    def test_future_day_is_rejected(self) -> None:
        self.known_supplier()
        draft = self.upload()

        response = self.confirm(
            draft=draft,
            occurred_on="17-10-2026",
        )

        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "Дата не может быть в будущем"
        assert self.store.entries == []
        assert self.store.invoices[draft["id"]].status == InvoiceStatus.DRAFT

    def test_day_before_the_stocktake_is_rejected(self) -> None:
        self.known_supplier()
        self.store.entries.append(
            LedgerEntry(
                id=self.store.new_id(),
                kind=LedgerKind.STOCKTAKE,
                amount=Decimal(
                    value=0,
                ),
                cash=Decimal(
                    value=0,
                ),
                occurred_on=date(
                    year=2026,
                    month=10,
                    day=15,
                ),
            ),
        )
        draft = self.upload()

        response = self.confirm(
            draft=draft,
            occurred_on="14-10-2026",
        )

        assert response.status_code == 409, response.text
        assert response.json()["detail"] == "Период закрыт переучётом от 15-10-2026"
        assert len(self.store.entries) == 1
        assert self.store.invoices[draft["id"]].status == InvoiceStatus.DRAFT
