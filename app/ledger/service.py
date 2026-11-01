from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.enums import LedgerKind
from core.http import conflict, invalid
from ledger.models import LedgerEntry
from ledger.repository import LedgerRepositoryDep, LedgerRow
from ledger.rules import check_date, counts_cash, counts_stock
from ledger.schemas import (
    BatchKind,
    CashCountCreate,
    CashOutCreate,
    LedgerBalance,
    LedgerBatchCreate,
    LedgerBatchPosted,
    LedgerEntryOut,
    LedgerPage,
    LedgerPosted,
    OutflowCreate,
    SaleCreate,
    StocktakeCreate,
)
from products.pricing import reprice

# what an entry made by hand does to the stock or to the till
STOCK_SIGNS = {
    LedgerKind.WRITE_OFF: -1,
    LedgerKind.STOCK_IN: 1,
}
CASH_SIGNS = {
    LedgerKind.CASH_IN: 1,
    LedgerKind.CASH_OUT: -1,
}
# the buttons under the comment of a ledger entry
COMMENT_HINTS = 6


def manual_entry(
    kind: LedgerKind,
    payload: OutflowCreate | CashOutCreate,
) -> LedgerEntry:
    """an entry moves either the stock or the till, never both"""
    if kind in STOCK_SIGNS:
        return LedgerEntry(
            kind=kind,
            occurred_on=payload.occurred_on,
            amount=STOCK_SIGNS[kind] * payload.amount,
            comment=payload.comment,
        )
    return LedgerEntry(
        kind=kind,
        occurred_on=payload.occurred_on,
        amount=0,
        cash=CASH_SIGNS[kind] * payload.amount,
        comment=payload.comment,
    )


class LedgerService:
    def __init__(
        self,
        ledger: LedgerRepositoryDep,
    ) -> None:
        self.ledger = ledger

    async def history(
        self,
        limit: int,
        offset: int,
    ) -> LedgerPage:
        # one row more tells whether there is another page
        rows = await self.ledger.history(
            limit=limit + 1,
            offset=offset,
        )
        return LedgerPage(
            balance=await self.ledger.balance(),
            cash_balance=await self.ledger.cash_balance(),
            entries=[
                ledger_entry_out(
                    row=row,
                )
                for row in rows[:limit]
            ],
            has_more=len(rows) > limit,
        )

    async def balance_on(
        self,
        on: date | None,
    ) -> LedgerBalance:
        return LedgerBalance(
            balance=await self.ledger.balance(
                on=on,
            ),
            cash_balance=await self.ledger.cash_balance(
                on=on,
            ),
            closed_on=await self.ledger.last_count_on(
                kind=LedgerKind.STOCKTAKE,
            ),
            cash_closed_on=await self.ledger.last_count_on(
                kind=LedgerKind.CASH_COUNT,
            ),
        )

    async def add_sale(
        self,
        payload: SaleCreate,
    ) -> LedgerPosted:
        """the stock goes down by the whole sale, the till gets the cash part only"""
        total = payload.cash + payload.card
        if not total:
            invalid(
                detail="Укажите выручку наличными или безналом",
            )
        await self.ledger.lock()
        await check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=payload.cash > 0,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.SALE,
                occurred_on=payload.occurred_on,
                amount=-total,
                cash=payload.cash,
                comment=payload.comment,
            ),
        )

    async def add_write_off(
        self,
        payload: OutflowCreate,
    ) -> LedgerPosted:
        """the stock goes down by the amount"""
        return await self._add_manual(
            kind=LedgerKind.WRITE_OFF,
            payload=payload,
        )

    async def add_stock_in(
        self,
        payload: OutflowCreate,
    ) -> LedgerPosted:
        """the stock goes up by the amount, the opposite of a write-off"""
        return await self._add_manual(
            kind=LedgerKind.STOCK_IN,
            payload=payload,
        )

    async def add_cash_in(
        self,
        payload: OutflowCreate,
    ) -> LedgerPosted:
        """money put into the till"""
        return await self._add_manual(
            kind=LedgerKind.CASH_IN,
            payload=payload,
        )

    async def add_cash_out(
        self,
        payload: CashOutCreate,
    ) -> LedgerPosted:
        """money taken from the till, the comment says what for"""
        return await self._add_manual(
            kind=LedgerKind.CASH_OUT,
            payload=payload,
        )

    async def add_batch(
        self,
        payload: LedgerBatchCreate,
    ) -> LedgerBatchPosted:
        """every line is checked first, then all of them go in one commit or none does"""
        await self.ledger.lock()
        for position, line in enumerate(
            payload.entries,
            start=1,
        ):
            if payload.kind == LedgerKind.CASH_OUT and line.comment is None:
                invalid(
                    detail=f"Строка {position}: укажите, на что выданы деньги",
                )
            try:
                await self._check_manual(
                    kind=payload.kind,
                    on=line.occurred_on,
                )
            except HTTPException as error:
                raise HTTPException(
                    status_code=error.status_code,
                    detail=f"Строка {position}: {error.detail}",
                ) from error
        entries = [
            await self.ledger.create(
                entry=manual_entry(
                    kind=payload.kind,
                    payload=line,
                ),
            )
            for line in payload.entries
        ]
        balance = await self.ledger.balance()
        cash_balance = await self.ledger.cash_balance()
        await self.ledger.commit()
        return LedgerBatchPosted(
            ids=[entry.id for entry in entries],
            balance=balance,
            cash_balance=cash_balance,
        )

    async def frequent_comments(
        self,
        kind: BatchKind,
    ) -> list[str]:
        return await self.ledger.frequent_comments(
            kind=kind,
            limit=COMMENT_HINTS,
        )

    async def _add_manual(
        self,
        kind: LedgerKind,
        payload: OutflowCreate | CashOutCreate,
    ) -> LedgerPosted:
        await self.ledger.lock()
        await self._check_manual(
            kind=kind,
            on=payload.occurred_on,
        )
        return await self._post(
            entry=manual_entry(
                kind=kind,
                payload=payload,
            ),
        )

    async def _check_manual(
        self,
        kind: LedgerKind,
        on: date,
    ) -> None:
        await check_date(
            ledger=self.ledger,
            on=on,
            stock=kind in STOCK_SIGNS,
            cash=kind in CASH_SIGNS,
        )

    async def add_stocktake(
        self,
        payload: StocktakeCreate,
    ) -> LedgerPosted:
        """the entry is the shortage or the surplus, after it the balance is the counted stock"""
        await self.ledger.lock()
        await check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=False,
        )
        expected = await self.ledger.balance(
            on=payload.occurred_on,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.STOCKTAKE,
                occurred_on=payload.occurred_on,
                amount=payload.counted - expected,
                comment=payload.comment,
            ),
        )

    async def add_cash_count(
        self,
        payload: CashCountCreate,
    ) -> LedgerPosted:
        """the entry is the shortage or the surplus of the till, after it the cash is as counted"""
        await self.ledger.lock()
        await check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=False,
            cash=True,
        )
        expected = await self.ledger.cash_balance(
            on=payload.occurred_on,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.CASH_COUNT,
                occurred_on=payload.occurred_on,
                amount=0,
                cash=payload.counted - expected,
                comment=payload.comment,
            ),
        )

    async def reverse(
        self,
        entry_id: int,
    ) -> LedgerPosted:
        """the ledger is never edited, a mistake is cancelled by an opposite entry on the same day"""
        await self.ledger.lock()
        entry = await self.ledger.get(
            entry_id=entry_id,
        )
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Запись журнала не найдена",
            )
        if entry.kind == LedgerKind.INVOICE:
            conflict(
                detail="Проведённую накладную нельзя сторнировать",
            )
        if entry.reverses_id is not None:
            conflict(
                detail="Сторно нельзя сторнировать",
            )
        if await self.ledger.is_reversed(
            entry_id=entry.id,
        ):
            conflict(
                detail="Запись уже сторнирована",
            )
        if counts_stock(
            entry=entry,
        ) and await self.ledger.has_count_after(
            entry=entry,
            kind=LedgerKind.STOCKTAKE,
        ):
            conflict(
                detail="После этой записи был переучёт, исправьте остаток новым переучётом",
            )
        if counts_cash(
            entry=entry,
        ) and await self.ledger.has_count_after(
            entry=entry,
            kind=LedgerKind.CASH_COUNT,
        ):
            conflict(
                detail="После этой записи была сверка кассы, исправьте кассу новой сверкой",
            )
        if entry.kind == LedgerKind.REVALUATION:
            for item in await self.ledger.revaluation_items_of(
                entry_id=entry.id,
            ):
                # a price changed again since then is left as it is
                if item.product.retail_price == item.new_price:
                    reprice(
                        product=item.product,
                        price=item.old_price,
                    )
        return await self._post(
            entry=LedgerEntry(
                kind=entry.kind,
                occurred_on=entry.occurred_on,
                amount=-entry.amount,
                cash=-entry.cash,
                # reverses_id already says what it cancels
                comment=None,
                reverses_id=entry.id,
            ),
        )

    async def _post(
        self,
        entry: LedgerEntry,
    ) -> LedgerPosted:
        return await self.finish(
            entry=await self.ledger.create(
                entry=entry,
            ),
        )

    async def finish(
        self,
        entry: LedgerEntry,
    ) -> LedgerPosted:
        """commits the created entry and reports the balances after it"""
        balance = await self.ledger.balance()
        cash_balance = await self.ledger.cash_balance()
        await self.ledger.commit()
        return LedgerPosted(
            id=entry.id,
            amount=entry.amount,
            cash=entry.cash,
            balance=balance,
            cash_balance=cash_balance,
        )


LedgerServiceDep = Annotated[
    LedgerService,
    Depends(
        dependency=LedgerService,
    ),
]


def entry_supplier_name(row: LedgerRow) -> str | None:
    """the reports print the short name of the supplier when it has one"""
    return row.supplier_short_name or row.supplier_name


def ledger_entry_out(
    row: LedgerRow,
    short_names: bool = False,
) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=row.entry.id,
        occurred_on=row.entry.occurred_on,
        kind=row.entry.kind,
        amount=row.entry.amount,
        cash=row.entry.cash,
        balance_after=row.balance_after,
        cash_after=row.cash_after,
        comment=row.entry.comment,
        reverses_id=row.entry.reverses_id,
        reversed_by_id=row.reversed_by_id,
        invoice_id=row.entry.invoice_id,
        invoice_number=row.invoice_number,
        supplier_name=entry_supplier_name(
            row=row,
        )
        if short_names
        else row.supplier_name,
    )
