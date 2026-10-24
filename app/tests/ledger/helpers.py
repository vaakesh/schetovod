from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from core.config import today
from core.enums import LedgerKind
from core.schema_types import format_invoice_date
from ledger.models import LedgerEntry
from tests.helpers import InvoiceApi


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


class LedgerApi(InvoiceApi):
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
            cash=Decimal(
                value=0,
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
        assert response.status_code == expected, response.text
        return response.json()

    def sale(
        self,
        amount: str,
        cash: str = "0.00",
        shift: int = 0,
        expected: int = 200,
    ) -> dict[str, Any]:
        """the whole sale, the cash part goes into the till and the rest is cashless"""
        card = Decimal(
            value=amount,
        ) - Decimal(
            value=cash,
        )
        return self.post(
            url="/ledger/sale",
            payload={
                "occurred_on": day(
                    shift=shift,
                ),
                "cash": cash,
                "card": str(
                    card,
                ),
                "comment": None,
            },
            expected=expected,
        )

    def cash(
        self,
        kind: str,
        amount: str,
        comment: str | None = None,
        shift: int = 0,
        expected: int = 200,
    ) -> dict[str, Any]:
        """a cash-in or a cash-out"""
        return self.post(
            url=f"/ledger/{kind}",
            payload={
                "occurred_on": day(
                    shift=shift,
                ),
                "amount": amount,
                "comment": comment,
            },
            expected=expected,
        )

    def cash_count(
        self,
        counted: str,
        shift: int = 0,
        expected: int = 200,
    ) -> dict[str, Any]:
        return self.post(
            url="/ledger/cash-count",
            payload={
                "occurred_on": day(
                    shift=shift,
                ),
                "counted": counted,
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
