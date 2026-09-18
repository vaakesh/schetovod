from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import exists, func, literal, or_, select, tuple_
from sqlalchemy.orm import aliased, selectinload

from db import SessionDep
from enums import InvoiceStatus, LedgerKind
from models import (
    Invoice,
    InvoiceItem,
    LedgerEntry,
    Product,
    ProductAlias,
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


@dataclass
class LedgerRow:
    entry: LedgerEntry
    # the running balance in the ledger order, including this entry
    balance_after: Decimal
    reversed_by_id: int | None
    invoice_number: str | None
    supplier_name: str | None


@dataclass
class ProductRow:
    product: Product
    # the last posted line of the product, None while it was never posted
    last_item: InvoiceItem | None


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
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[InvoiceRow]:
        """newest uploads first, the supplier is searched by name and the invoice by number"""
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
        statement = (
            select(
                Invoice,
                supplier_name,
                LedgerEntry.amount,
                lines,
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
                Invoice.created_at.desc(),
                Invoice.id.desc(),
            )
            .limit(
                limit=limit,
            )
            .offset(
                offset=offset,
            )
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
            )
            for invoice, name, amount, count in result.tuples()
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
        statement = select(
            func.coalesce(
                func.sum(
                    LedgerEntry.amount,
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

    async def last_stocktake_on(self) -> date | None:
        """the day of the latest stocktake in force, nothing may be dated before it"""
        return await self.session.scalar(
            statement=select(
                func.max(
                    LedgerEntry.occurred_on,
                ),
            ).where(
                *_stocktake_in_force(),
            ),
        )

    async def has_stocktake_after(
        self,
        entry: LedgerEntry,
    ) -> bool:
        """a stocktake in force comes later in the ledger order"""
        return bool(
            await self.session.scalar(
                statement=select(
                    exists().where(
                        *_stocktake_in_force(),
                        tuple_(
                            LedgerEntry.occurred_on,
                            LedgerEntry.id,
                        )
                        > tuple_(
                            literal(
                                value=entry.occurred_on,
                            ),
                            literal(
                                value=entry.id,
                            ),
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
                reversal.id,
                Invoice.invoice_number,
                Supplier.name,
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
                reversed_by_id=reversed_by_id,
                invoice_number=invoice_number,
                supplier_name=supplier_name,
            )
            for entry, balance_after, reversed_by_id, invoice_number, supplier_name in result.tuples()
        ]


def _stocktake_in_force() -> tuple:
    """a stocktake that is neither a reversal nor reversed itself"""
    reversal = aliased(
        LedgerEntry,
    )
    return (
        LedgerEntry.kind == LedgerKind.STOCKTAKE,
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
        statement = (
            select(
                Product,
                last_item,
            )
            .outerjoin(
                target=last_item,
                onclause=last_item.id == last_item_id,
            )
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
