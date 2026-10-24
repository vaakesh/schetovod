from datetime import date
from decimal import Decimal

from core.config import today
from core.enums import LedgerKind
from ledger.models import LedgerEntry, RevaluationItem
from ledger.repository import LedgerRow
from tests.fakes.store import FakeStore


class FakeLedger:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def lock(self) -> None:
        self.store.locks += 1
        self.store.events.append(
            "lock",
        )

    async def create(
        self,
        entry: LedgerEntry,
    ) -> LedgerEntry:
        entry.id = self.store.new_id()
        # the column defaults are applied on flush, there is none here
        if entry.occurred_on is None:
            entry.occurred_on = today()
        if entry.cash is None:
            entry.cash = Decimal(
                value=0,
            )
        self.store.entries.append(
            entry,
        )
        return entry

    async def add_revaluation_items(
        self,
        items: list[RevaluationItem],
    ) -> None:
        for item in items:
            item.id = self.store.new_id()
        self.store.revaluations += items

    async def revaluation_items_of(
        self,
        entry_id: int,
    ) -> list[RevaluationItem]:
        items = [
            item for item in self.store.revaluations if item.ledger_entry_id == entry_id
        ]
        # what selectinload brings in the real repository
        for item in items:
            item.product = self.store.products[item.product_id]
        return items

    async def sums_by_kind(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        return self.sums(
            field="amount",
            date_from=date_from,
            date_to=date_to,
        )

    async def cash_sums_by_kind(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        return self.sums(
            field="cash",
            date_from=date_from,
            date_to=date_to,
        )

    def sums(
        self,
        field: str,
        date_from: date,
        date_to: date,
    ) -> dict[LedgerKind, Decimal]:
        sums: dict[LedgerKind, Decimal] = {}
        for entry in self.store.entries:
            if date_from <= entry.occurred_on <= date_to:
                sums[entry.kind] = sums.get(
                    entry.kind,
                    Decimal(
                        value=0,
                    ),
                ) + getattr(
                    entry,
                    field,
                )
        return sums

    async def get(
        self,
        entry_id: int,
    ) -> LedgerEntry | None:
        for entry in self.store.entries:
            if entry.id == entry_id:
                return entry
        return None

    async def get_for_invoice(
        self,
        invoice_id: int,
    ) -> LedgerEntry | None:
        for entry in self.store.entries:
            if entry.invoice_id == invoice_id:
                return entry
        return None

    async def balance(
        self,
        on: date | None = None,
    ) -> Decimal:
        return self.total(
            field="amount",
            on=on,
        )

    async def cash_balance(
        self,
        on: date | None = None,
    ) -> Decimal:
        return self.total(
            field="cash",
            on=on,
        )

    def total(
        self,
        field: str,
        on: date | None,
    ) -> Decimal:
        return sum(
            (
                getattr(
                    entry,
                    field,
                )
                for entry in self.store.entries
                if on is None or entry.occurred_on <= on
            ),
            start=Decimal(
                value=0,
            ),
        )

    async def is_reversed(
        self,
        entry_id: int,
    ) -> bool:
        return any(
            (entry.reverses_id == entry_id for entry in self.store.entries),
        )

    def in_force(
        self,
        entry: LedgerEntry,
        kind: LedgerKind,
    ) -> bool:
        return (
            entry.kind == kind
            and entry.reverses_id is None
            and not any(
                (other.reverses_id == entry.id for other in self.store.entries),
            )
        )

    async def last_count_on(
        self,
        kind: LedgerKind,
    ) -> date | None:
        dates = [
            entry.occurred_on
            for entry in self.store.entries
            if self.in_force(
                entry=entry,
                kind=kind,
            )
        ]
        return max(
            dates,
            default=None,
        )

    async def has_count_after(
        self,
        entry: LedgerEntry,
        kind: LedgerKind,
    ) -> bool:
        return any(
            self.in_force(
                entry=other,
                kind=kind,
            )
            and (other.occurred_on, other.id) > (entry.occurred_on, entry.id)
            for other in self.store.entries
        )

    async def history(
        self,
        limit: int | None,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        newest_first: bool = True,
    ) -> list[LedgerRow]:
        ordered = sorted(
            self.store.entries,
            key=lambda entry: (entry.occurred_on, entry.id),
        )
        rows = []
        balance = Decimal(
            value=0,
        )
        cash = Decimal(
            value=0,
        )
        for entry in ordered:
            balance += entry.amount
            cash += entry.cash
            invoice = None
            if entry.invoice_id is not None:
                invoice = self.store.invoices.get(
                    entry.invoice_id,
                )
            supplier = None
            if invoice is not None and invoice.supplier_id is not None:
                supplier = self.store.suppliers.get(
                    invoice.supplier_id,
                )
            reversals = [
                other.id
                for other in self.store.entries
                if other.reverses_id == entry.id
            ]
            rows.append(
                LedgerRow(
                    entry=entry,
                    balance_after=balance,
                    cash_after=cash,
                    reversed_by_id=reversals[0] if reversals else None,
                    invoice_number=invoice.invoice_number if invoice else None,
                    supplier_name=supplier.name if supplier else None,
                    supplier_short_name=supplier.short_name if supplier else None,
                ),
            )
        rows = [
            row
            for row in rows
            if (date_from is None or row.entry.occurred_on >= date_from)
            and (date_to is None or row.entry.occurred_on <= date_to)
        ]
        if newest_first:
            rows.reverse()
        return rows[offset : None if limit is None else offset + limit]
