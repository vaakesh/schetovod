from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status

from core.config import today
from core.enums import LedgerKind
from core.http import conflict
from core.schema_types import format_invoice_date
from ledger.models import LedgerEntry
from ledger.repository import LedgerRepository


async def check_date(
    ledger: LedgerRepository,
    on: date,
    stock: bool,
    cash: bool,
) -> None:
    """an entry is checked against the counts of what it changes"""
    if on > today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Дата не может быть в будущем",
        )
    # a count fixes the balance, an entry before it would change what was counted
    for counted, kind, detail in (
        (stock, LedgerKind.STOCKTAKE, "Период закрыт переучётом от {closed}"),
        (cash, LedgerKind.CASH_COUNT, "Касса закрыта сверкой от {closed}"),
    ):
        if not counted:
            continue
        closed_on = await ledger.last_count_on(
            kind=kind,
        )
        if closed_on is not None and on < closed_on:
            conflict(
                detail=detail.format(
                    closed=format_invoice_date(
                        value=closed_on,
                    ),
                ),
            )


def counts_stock(entry: LedgerEntry) -> bool:
    """a stocktake depends on the entry"""
    return entry.amount != 0 or entry.kind == LedgerKind.STOCKTAKE


def counts_cash(entry: LedgerEntry) -> bool:
    """a cash count depends on the entry"""
    return entry.cash != 0 or entry.kind == LedgerKind.CASH_COUNT
