from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import ScalarSelect, Select, case, exists, func, or_, select, tuple_
from sqlalchemy.orm import InstrumentedAttribute, aliased, selectinload

from db import SessionDep
from enums import InvoiceSort, InvoiceStatus, LedgerKind
from models import (
    Invoice,
    InvoiceItem,
    InvoicePayment,
    LedgerEntry,
    Product,
    ProductAlias,
    RevaluationItem,
    Supplier,
)

# any constant shared by every writer of the ledger
LEDGER_LOCK = 7_301_001


@dataclass
class InvoiceRow:
    invoice: Invoice
    # the chosen supplier, or the name the model read while there is none
    supplier_name: str | None
    # None until the invoice is confirmed
    retail_total: Decimal | None
    lines: int
    # owed to the supplier, None until the invoice is confirmed
    cost_total: Decimal | None
    paid: Decimal


@dataclass
class DebtRow:
    invoice: Invoice
    supplier_name: str
    supplier_short_name: str | None
    cost_total: Decimal
    paid: Decimal


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


@dataclass
class ProductRow:
    product: Product
    # the last posted line of the product, None while it was never posted
    last_item: InvoiceItem | None


@dataclass
class CatalogRow(ProductRow):
    aliases: list[ProductAlias]


class InvoiceRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def create(
        self,
        invoice: Invoice,
    ) -> Invoice:
        self.session.add(
            instance=invoice,
        )
        await self.session.flush()
        return invoice

    async def get_draft(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        # the row lock keeps a save or a decline from overwriting a draft confirmed meanwhile,
        # after the wait the status is checked again and a confirmed invoice is not found
        return await self.session.scalar(
            statement=select(
                Invoice,
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.status == InvoiceStatus.DRAFT,
            )
            .with_for_update(),
        )

    async def find_confirmed(
        self,
        supplier_id: int,
        invoice_number: str,
        invoice_date: date,
    ) -> Invoice | None:
        return await self.session.scalar(
            statement=select(
                Invoice,
            ).where(
                Invoice.supplier_id == supplier_id,
                Invoice.invoice_number == invoice_number,
                Invoice.invoice_date == invoice_date,
                Invoice.status == InvoiceStatus.CONFIRMED,
            ),
        )

    async def search(
        self,
        status: InvoiceStatus | None,
        unpaid: bool,
        query: str | None,
        sort: InvoiceSort,
        limit: int,
        offset: int,
    ) -> list[InvoiceRow]:
        """the supplier is searched by name and the invoice by number,
        unpaid leaves the confirmed invoices with a debt"""
        # a draft without a chosen supplier shows the name the model read
        supplier_name = func.coalesce(
            Supplier.name,
            Invoice.extracted["supplier"]["name"].astext,
        )
        lines = func.jsonb_array_length(
            func.coalesce(
                Invoice.form["lines"],
                Invoice.extracted["items"],
            ),
        )
        cost_total = _cost_total()
        paid = _paid_total(
            on=None,
        )
        # only a confirmed invoice owes anything
        debt = case(
            (
                Invoice.status == InvoiceStatus.CONFIRMED,
                cost_total - paid,
            ),
            else_=None,
        )
        order = (
            Invoice.created_at.desc(),
            Invoice.id.desc(),
        )
        if sort == InvoiceSort.DEBT:
            order = (
                debt.desc().nulls_last(),
                *order,
            )
        statement = (
            select(
                Invoice,
                supplier_name,
                LedgerEntry.amount,
                lines,
                cost_total,
                paid,
            )
            .outerjoin(
                target=Supplier,
                onclause=Supplier.id == Invoice.supplier_id,
            )
            .outerjoin(
                target=LedgerEntry,
                onclause=LedgerEntry.invoice_id == Invoice.id,
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
        if unpaid:
            statement = statement.where(
                debt > 0,
            )
        if status is not None:
            statement = statement.where(
                Invoice.status == status,
            )
        if query:
            statement = statement.where(
                or_(
                    supplier_name.icontains(
                        other=query,
                        autoescape=True,
                    ),
                    Invoice.invoice_number.icontains(
                        other=query,
                        autoescape=True,
                    ),
                ),
            )
        result = await self.session.execute(
            statement=statement,
        )
        return [
            InvoiceRow(
                invoice=invoice,
                supplier_name=name,
                retail_total=amount,
                lines=count,
                # a draft has no lines yet, its sum would be the sum of nothing
                cost_total=cost if invoice.status == InvoiceStatus.CONFIRMED else None,
                paid=paid,
            )
            for invoice, name, amount, count, cost, paid in result.tuples()
        ]

    async def get_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        """with the supplier and the lines with their products"""
        return await self.session.scalar(
            statement=select(
                Invoice,
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.status == InvoiceStatus.CONFIRMED,
            )
            .options(
                selectinload(
                    Invoice.supplier,
                ),
                selectinload(
                    Invoice.items,
                ).selectinload(
                    InvoiceItem.product,
                ),
            ),
        )

    async def lock_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        """the row lock keeps two payments from overpaying the invoice together"""
        return await self.session.scalar(
            statement=select(
                Invoice,
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.status == InvoiceStatus.CONFIRMED,
            )
            .with_for_update(),
        )

    async def cost_totals(
        self,
        invoice_ids: Collection[int],
    ) -> dict[int, Decimal]:
        """owed to the supplier for each invoice, the sum of its lines"""
        result = await self.session.execute(
            statement=select(
                InvoiceItem.invoice_id,
                func.sum(
                    InvoiceItem.cost_price_total,
                ),
            )
            .where(
                InvoiceItem.invoice_id.in_(
                    other=invoice_ids,
                ),
            )
            .group_by(
                InvoiceItem.invoice_id,
            ),
        )
        return {invoice_id: total for invoice_id, total in result.tuples()}

    async def paid_totals(
        self,
        invoice_ids: Collection[int],
        on: date | None,
    ) -> dict[int, Decimal]:
        """paid for each invoice up to the end of the day, an unpaid one is missing"""
        statement = (
            select(
                InvoicePayment.invoice_id,
                func.sum(
                    InvoicePayment.amount,
                ),
            )
            .where(
                InvoicePayment.invoice_id.in_(
                    other=invoice_ids,
                ),
            )
            .group_by(
                InvoicePayment.invoice_id,
            )
        )
        if on is not None:
            statement = statement.where(
                InvoicePayment.paid_on <= on,
            )
        result = await self.session.execute(
            statement=statement,
        )
        return {invoice_id: total for invoice_id, total in result.tuples()}

    async def paid_between(
        self,
        date_from: date,
        date_to: date,
    ) -> Decimal:
        """paid to the suppliers on the days, for any invoices"""
        total = await self.session.scalar(
            statement=select(
                func.coalesce(
                    func.sum(
                        InvoicePayment.amount,
                    ),
                    0,
                ),
            ).where(
                InvoicePayment.paid_on >= date_from,
                InvoicePayment.paid_on <= date_to,
            ),
        )
        return Decimal(
            value=total or 0,
        )

    async def debts(
        self,
        on: date,
    ) -> list[DebtRow]:
        """invoices posted by the end of the day and not paid in full by then, the oldest first"""
        cost_total = _cost_total()
        paid = _paid_total(
            on=on,
        )
        result = await self.session.execute(
            statement=select(
                Invoice,
                Supplier.name,
                Supplier.short_name,
                cost_total,
                paid,
            )
            .join(
                target=Supplier,
                onclause=Supplier.id == Invoice.supplier_id,
            )
            .join(
                target=LedgerEntry,
                onclause=LedgerEntry.invoice_id == Invoice.id,
            )
            .where(
                LedgerEntry.occurred_on <= on,
                cost_total > paid,
            )
            .order_by(
                Invoice.invoice_date,
                Invoice.id,
            ),
        )
        return [
            DebtRow(
                invoice=invoice,
                supplier_name=name,
                supplier_short_name=short_name,
                cost_total=cost,
                paid=paid_sum,
            )
            for invoice, name, short_name, cost, paid_sum in result.tuples()
        ]

    async def payments_of(
        self,
        invoice_id: int,
    ) -> list[InvoicePayment]:
        result = await self.session.scalars(
            statement=select(
                InvoicePayment,
            )
            .where(
                InvoicePayment.invoice_id == invoice_id,
            )
            .order_by(
                InvoicePayment.paid_on,
                InvoicePayment.id,
            ),
        )
        return list(
            result,
        )

    async def get_payment(
        self,
        invoice_id: int,
        payment_id: int,
    ) -> InvoicePayment | None:
        return await self.session.scalar(
            statement=select(
                InvoicePayment,
            ).where(
                InvoicePayment.id == payment_id,
                InvoicePayment.invoice_id == invoice_id,
            ),
        )

    async def add_payment(
        self,
        payment: InvoicePayment,
    ) -> InvoicePayment:
        self.session.add(
            instance=payment,
        )
        await self.session.flush()
        return payment

    async def delete_payment(
        self,
        payment: InvoicePayment,
    ) -> None:
        await self.session.delete(
            instance=payment,
        )
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def add_items(
        self,
        items: list[InvoiceItem],
    ) -> None:
        self.session.add_all(
            instances=items,
        )
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()


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


class SupplierRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def get(
        self,
        supplier_id: int,
    ) -> Supplier | None:
        return await self.session.get(
            entity=Supplier,
            ident=supplier_id,
        )

    async def get_by_inn(
        self,
        inn: str,
    ) -> Supplier | None:
        return await self.session.scalar(
            statement=select(
                Supplier,
            ).where(
                Supplier.inn == inn,
            ),
        )

    async def search_by_name(
        self,
        name: str,
        only_without_inn: bool,
        limit: int,
    ) -> list[Supplier]:
        statement = (
            select(
                Supplier,
            )
            .where(
                Supplier.name.icontains(
                    other=name,
                    autoescape=True,
                ),
            )
            .order_by(
                Supplier.id,
            )
            .limit(
                limit=limit,
            )
        )
        if only_without_inn:
            statement = statement.where(
                Supplier.inn.is_(
                    other=None,
                ),
            )
        result = await self.session.scalars(
            statement=statement,
        )
        return list(
            result,
        )

    async def search(
        self,
        query: str | None,
        limit: int,
    ) -> list[Supplier]:
        """suppliers by a part of the name or the start of the inn, all of them without a query"""
        statement = (
            select(
                Supplier,
            )
            .order_by(
                Supplier.name,
                Supplier.id,
            )
            .limit(
                limit=limit,
            )
        )
        if query:
            by_name = Supplier.name.icontains(
                other=query,
                autoescape=True,
            )
            if query.isdigit():
                statement = statement.where(
                    or_(
                        by_name,
                        Supplier.inn.startswith(
                            other=query,
                            autoescape=True,
                        ),
                    ),
                )
            else:
                statement = statement.where(
                    by_name,
                )
        result = await self.session.scalars(
            statement=statement,
        )
        return list(
            result,
        )

    async def list_all(self) -> list[Supplier]:
        result = await self.session.scalars(
            statement=select(
                Supplier,
            ).order_by(
                Supplier.name,
                Supplier.id,
            ),
        )
        return list(
            result,
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def rank_by_aliases(
        self,
        aliases: Collection[str],
        only_without_inn: bool,
        limit: int,
    ) -> list[tuple[Supplier, int]]:
        """suppliers that have products with these names, most matches first"""
        if not aliases:
            return []
        matched = func.count(
            ProductAlias.alias_normalized.distinct(),
        )
        statement = (
            select(
                Supplier,
                matched,
            )
            .join(
                target=ProductAlias,
                onclause=ProductAlias.supplier_id == Supplier.id,
            )
            .where(
                ProductAlias.alias_normalized.in_(
                    other=aliases,
                ),
            )
            .group_by(
                Supplier.id,
            )
            .order_by(
                matched.desc(),
                Supplier.id,
            )
            .limit(
                limit=limit,
            )
        )
        if only_without_inn:
            statement = statement.where(
                Supplier.inn.is_(
                    other=None,
                ),
            )
        result = await self.session.execute(
            statement=statement,
        )
        return list(
            result.tuples(),
        )

    async def create(
        self,
        supplier: Supplier,
    ) -> Supplier:
        self.session.add(
            instance=supplier,
        )
        await self.session.flush()
        return supplier


class ProductRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def get(
        self,
        product_id: int,
    ) -> Product | None:
        return await self.session.get(
            entity=Product,
            ident=product_id,
        )

    async def create(
        self,
        product: Product,
    ) -> Product:
        self.session.add(
            instance=product,
        )
        await self.session.flush()
        return product

    async def add_alias(
        self,
        alias: ProductAlias,
    ) -> ProductAlias:
        self.session.add(
            instance=alias,
        )
        await self.session.flush()
        return alias

    async def find_by_aliases(
        self,
        supplier_id: int,
        aliases: Collection[str],
    ) -> dict[str, Product]:
        """supplier products keyed by the normalized alias that matched"""
        if not aliases:
            return {}
        result = await self.session.execute(
            statement=select(
                ProductAlias.alias_normalized,
                Product,
            )
            .join(
                target=Product,
                onclause=ProductAlias.product,
            )
            .where(
                ProductAlias.supplier_id == supplier_id,
                ProductAlias.alias_normalized.in_(
                    other=aliases,
                ),
            ),
        )
        # dict() would take the result for a mapping because it has keys()
        return {alias: product for alias, product in result.tuples()}

    async def aliases_of(
        self,
        supplier_id: int,
    ) -> list[tuple[str, Product]]:
        """every spelling of every supplier product, to compare names in code"""
        result = await self.session.execute(
            statement=select(
                ProductAlias.alias_normalized,
                Product,
            )
            .join(
                target=Product,
                onclause=ProductAlias.product,
            )
            .where(
                ProductAlias.supplier_id == supplier_id,
            ),
        )
        return list(
            result.tuples(),
        )

    async def search(
        self,
        supplier_id: int,
        query: str | None,
        key: str | None,
        limit: int,
    ) -> list[ProductRow]:
        """supplier products by a part of the name or of any spelling, all of them without a query"""
        statement = (
            select_with_last_item()
            .where(
                Product.supplier_id == supplier_id,
            )
            .order_by(
                Product.name,
                Product.id,
            )
            .limit(
                limit=limit,
            )
        )
        if query:
            conditions = [
                Product.name.icontains(
                    other=query,
                    autoescape=True,
                ),
            ]
            if key:
                # another spelling, e.g. the one printed on an earlier invoice
                conditions.append(
                    exists().where(
                        ProductAlias.product_id == Product.id,
                        ProductAlias.alias_normalized.contains(
                            other=key,
                            autoescape=True,
                        ),
                    ),
                )
            statement = statement.where(
                or_(
                    *conditions,
                ),
            )
        result = await self.session.execute(
            statement=statement,
        )
        return [
            ProductRow(
                product=product,
                last_item=item,
            )
            for product, item in result.tuples()
        ]

    async def last_cost_prices(
        self,
        product_ids: Collection[int],
    ) -> dict[int, Decimal]:
        """the cost price of the last posted line of each product, never posted ones are left out"""
        if not product_ids:
            return {}
        result = await self.session.execute(
            statement=select_with_last_item().where(
                Product.id.in_(
                    other=product_ids,
                ),
            ),
        )
        return {
            product.id: item.cost_price
            for product, item in result.tuples()
            if item is not None
        }

    async def catalog(self) -> list[CatalogRow]:
        """every product of every supplier with all its spellings"""
        result = await self.session.execute(
            statement=select_with_last_item()
            .options(
                selectinload(
                    Product.aliases,
                ),
            )
            .order_by(
                Product.name,
                Product.id,
            ),
        )
        return [
            CatalogRow(
                product=product,
                last_item=item,
                aliases=list(
                    product.aliases,
                ),
            )
            for product, item in result.tuples()
        ]


def _cost_total() -> ScalarSelect[Decimal]:
    """owed to the supplier for the invoice of the outer query, zero without lines"""
    return (
        select(
            func.coalesce(
                func.sum(
                    InvoiceItem.cost_price_total,
                ),
                0,
            ),
        )
        .where(
            InvoiceItem.invoice_id == Invoice.id,
        )
        .scalar_subquery()
    )


def _paid_total(on: date | None) -> ScalarSelect[Decimal]:
    """paid for the invoice of the outer query up to the end of the day, or ever"""
    statement = select(
        func.coalesce(
            func.sum(
                InvoicePayment.amount,
            ),
            0,
        ),
    ).where(
        InvoicePayment.invoice_id == Invoice.id,
    )
    if on is not None:
        statement = statement.where(
            InvoicePayment.paid_on <= on,
        )
    return statement.scalar_subquery()


def select_with_last_item() -> Select[Product, InvoiceItem]:
    """products with their last posted line, the line is None while a product was never posted"""
    # the newest line of every product, items exist only for confirmed invoices
    last_item_id = (
        select(
            func.max(
                InvoiceItem.id,
            ),
        )
        .where(
            InvoiceItem.product_id == Product.id,
        )
        .scalar_subquery()
    )
    last_item = aliased(
        InvoiceItem,
    )
    return select(
        Product,
        last_item,
    ).outerjoin(
        target=last_item,
        onclause=last_item.id == last_item_id,
    )


InvoiceRepositoryDep = Annotated[
    InvoiceRepository,
    Depends(
        dependency=InvoiceRepository,
    ),
]
SupplierRepositoryDep = Annotated[
    SupplierRepository,
    Depends(
        dependency=SupplierRepository,
    ),
]
ProductRepositoryDep = Annotated[
    ProductRepository,
    Depends(
        dependency=ProductRepository,
    ),
]
LedgerRepositoryDep = Annotated[
    LedgerRepository,
    Depends(
        dependency=LedgerRepository,
    ),
]
