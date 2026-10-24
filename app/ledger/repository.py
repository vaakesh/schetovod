from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import exists, func, select, tuple_
from sqlalchemy.orm import InstrumentedAttribute, aliased, selectinload

from core.db import SessionDep
from core.enums import LedgerKind
from invoices.models import Invoice
from ledger.models import LedgerEntry, RevaluationItem
from suppliers.models import Supplier

# any constant shared by every writer of the ledger
LEDGER_LOCK = 7_301_001


@dataclass
class LedgerRow:
    entry: LedgerEntry
    # the running balances in the ledger order, including this entry
    balance_after: Decimal
    cash_after: Decimal
    reversed_by_id: int | None
    invoice_number: str | None
    supplier_name: str | None
    supplier_short_name: str | None


class LedgerRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def create(
        self,
        entry: LedgerEntry,
    ) -> LedgerEntry:
        self.session.add(
            instance=entry,
        )
        await self.session.flush()
        return entry

    async def commit(self) -> None:
        await self.session.commit()

    async def add_revaluation_items(
        self,
        items: list[RevaluationItem],
    ) -> None:
        self.session.add_all(
            instances=items,
        )
        await self.session.flush()

    async def revaluation_items_of(
        self,
        entry_id: int,
    ) -> list[RevaluationItem]:
        """with their products"""
        result = await self.session.scalars(
            statement=select(
                RevaluationItem,
            )
            .where(
                RevaluationItem.ledger_entry_id == entry_id,
            )
            .order_by(
                RevaluationItem.id,
            )
            .options(
                selectinload(
                    RevaluationItem.product,
                ),
            ),
        )
        return list(
            result,
        )

    async def sums_by_kind(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        """signed stock sums of the days, a reversal has the kind of the entry it cancels"""
        return await self._sums_by_kind(
            column=LedgerEntry.amount,
            date_from=date_from,
            date_to=date_to,
        )

    async def cash_sums_by_kind(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        """signed cash sums of the days, a reversal has the kind of the entry it cancels"""
        return await self._sums_by_kind(
            column=LedgerEntry.cash,
            date_from=date_from,
            date_to=date_to,
        )

    async def _sums_by_kind(
        self,
        column: InstrumentedAttribute[Decimal],
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        result = await self.session.execute(
            statement=select(
                LedgerEntry.kind,
                func.sum(
                    column,
                ),
            )
            .where(
                LedgerEntry.occurred_on >= date_from,
                LedgerEntry.occurred_on <= date_to,
            )
            .group_by(
                LedgerEntry.kind,
            ),
        )
        return {kind: amount for kind, amount in result.tuples()}

    async def lock(self) -> None:
        """serializes the writers, a stocktake must see the balance it replaces"""
        await self.session.execute(
            statement=select(
                func.pg_advisory_xact_lock(
                    LEDGER_LOCK,
                ),
            ),
        )

    async def get(
        self,
        entry_id: int,
    ) -> LedgerEntry | None:
        return await self.session.get(
            LedgerEntry,
            entry_id,
        )

    async def get_for_invoice(
        self,
        invoice_id: int,
    ) -> LedgerEntry | None:
        return await self.session.scalar(
            statement=select(
                LedgerEntry,
            ).where(
                LedgerEntry.invoice_id == invoice_id,
            ),
        )

    async def balance(
        self,
        on: date | None = None,
    ) -> Decimal:
        """stock at retail prices, the sum of the signed entries up to the end of the day"""
        return await self._total(
            column=LedgerEntry.amount,
            on=on,
        )

    async def cash_balance(
        self,
        on: date | None = None,
    ) -> Decimal:
        """cash in the till up to the end of the day"""
        return await self._total(
            column=LedgerEntry.cash,
            on=on,
        )

    async def _total(
        self,
        column: InstrumentedAttribute[Decimal],
        on: date | None,
    ) -> Decimal:
        statement = select(
            func.coalesce(
                func.sum(
                    column,
                ),
                0,
            ),
        )
        if on is not None:
            statement = statement.where(
                LedgerEntry.occurred_on <= on,
            )
        balance = await self.session.scalar(
            statement=statement,
        )
        return Decimal(
            value=balance or 0,
        )

    async def is_reversed(
        self,
        entry_id: int,
    ) -> bool:
        return bool(
            await self.session.scalar(
                statement=select(
                    exists().where(
                        LedgerEntry.reverses_id == entry_id,
                    ),
                ),
            ),
        )

    async def last_count_on(
        self,
        kind: LedgerKind,
    ) -> date | None:
        """the day of the latest stocktake or cash count in force,
        nothing it counted may be dated before it"""
        return await self.session.scalar(
            statement=select(
                func.max(
                    LedgerEntry.occurred_on,
                ),
            ).where(
                *_count_in_force(
                    kind=kind,
                ),
            ),
        )

    async def has_count_after(
        self,
        entry: LedgerEntry,
        kind: LedgerKind,
    ) -> bool:
        """a stocktake or a cash count in force comes later in the ledger order"""
        return bool(
            await self.session.scalar(
                statement=select(
                    exists().where(
                        *_count_in_force(
                            kind=kind,
                        ),
                        tuple_(
                            LedgerEntry.occurred_on,
                            LedgerEntry.id,
                        )
                        > tuple_(
                            entry.occurred_on,
                            entry.id,
                        ),
                    ),
                ),
            ),
        )

    async def history(
        self,
        limit: int | None,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        newest_first: bool = True,
    ) -> list[LedgerRow]:
        """each entry with the balance right after it, the days are optional bounds"""
        running = (
            select(
                LedgerEntry.id,
                func.sum(
                    LedgerEntry.amount,
                )
                .over(
                    order_by=(
                        LedgerEntry.occurred_on,
                        LedgerEntry.id,
                    ),
                )
                .label(
                    name="balance_after",
                ),
                func.sum(
                    LedgerEntry.cash,
                )
                .over(
                    order_by=(
                        LedgerEntry.occurred_on,
                        LedgerEntry.id,
                    ),
                )
                .label(
                    name="cash_after",
                ),
            )
        ).subquery()
        reversal = aliased(
            LedgerEntry,
        )
        order = (
            (
                LedgerEntry.occurred_on.desc(),
                LedgerEntry.id.desc(),
            )
            if newest_first
            else (
                LedgerEntry.occurred_on,
                LedgerEntry.id,
            )
        )
        # the bounds go outside the running sum, so it still counts the earlier entries
        statement = (
            select(
                LedgerEntry,
                running.c.balance_after,
                running.c.cash_after,
                reversal.id,
                Invoice.invoice_number,
                Supplier.name,
                Supplier.short_name,
            )
            .join(
                target=running,
                onclause=running.c.id == LedgerEntry.id,
            )
            .outerjoin(
                target=reversal,
                onclause=reversal.reverses_id == LedgerEntry.id,
            )
            .outerjoin(
                target=Invoice,
                onclause=Invoice.id == LedgerEntry.invoice_id,
            )
            .outerjoin(
                target=Supplier,
                onclause=Supplier.id == Invoice.supplier_id,
            )
            .order_by(
                *order,
            )
            .limit(
                limit=limit,
            )
            .offset(
                offset=offset,
            )
        )
        if date_from is not None:
            statement = statement.where(
                LedgerEntry.occurred_on >= date_from,
            )
        if date_to is not None:
            statement = statement.where(
                LedgerEntry.occurred_on <= date_to,
            )
        result = await self.session.execute(
            statement=statement,
        )
        return [
            LedgerRow(
                entry=entry,
                balance_after=balance_after,
                cash_after=cash_after,
                reversed_by_id=reversed_by_id,
                invoice_number=invoice_number,
                supplier_name=supplier_name,
                supplier_short_name=supplier_short_name,
            )
            for (
                entry,
                balance_after,
                cash_after,
                reversed_by_id,
                invoice_number,
                supplier_name,
                supplier_short_name,
            ) in result.tuples()
        ]


def _count_in_force(kind: LedgerKind) -> tuple:
    """a stocktake or a cash count that is neither a reversal nor reversed itself"""
    reversal = aliased(
        LedgerEntry,
    )
    return (
        LedgerEntry.kind == kind,
        LedgerEntry.reverses_id.is_(
            other=None,
        ),
        ~exists().where(
            reversal.reverses_id == LedgerEntry.id,
        ),
    )


LedgerRepositoryDep = Annotated[
    LedgerRepository,
    Depends(
        dependency=LedgerRepository,
    ),
]
