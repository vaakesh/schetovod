from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy import (
    ColumnElement,
    Select,
    SQLColumnExpression,
    and_,
    func,
    select,
    true,
)
from sqlalchemy.sql.elements import Grouping
from sqlalchemy.sql.selectable import CTE, Subquery

from core.db import SessionDep
from core.enums import InvoiceStatus, LedgerKind
from invoices.models import Invoice, InvoiceItem
from ledger.models import LedgerEntry
from products.models import Product
from purchases.schemas import PurchaseOverview
from suppliers.models import Supplier

# use Unicode case rules even if the database was initialized with the C collation
UNICODE_COLLATION = "und-x-icu"


@dataclass
class UnitWindow:
    unit: str | None
    current_cost: Decimal
    current_quantity: Decimal
    current_deliveries: int
    previous_cost: Decimal
    previous_quantity: Decimal
    previous_deliveries: int


@dataclass
class SummaryRow:
    product_id: int
    name: str
    supplier_id: int
    supplier_name: str
    deliveries: int
    lifetime_deliveries: int
    spend: Decimal
    last_on: date
    recent_days: list[date]
    units: list[UnitWindow]


@dataclass
class HistoryRow:
    occurred_on: date
    invoice_id: int
    invoice_number: str | None
    line_no: int
    unit: str | None
    quantity: Decimal
    cost_price: Decimal
    cost_price_total: Decimal
    retail_price: Decimal


class PurchaseRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def overview(
        self,
        *,
        as_of: date,
        since: date | None,
        supplier_id: int | None,
    ) -> PurchaseOverview:
        statement = _posted_lines(
            as_of=as_of,
        ).add_columns(
            func.count(
                InvoiceItem.invoice_id.distinct(),
            ).label(
                name="invoices",
            ),
            func.coalesce(
                func.sum(
                    InvoiceItem.cost_price_total,
                ),
                0,
            ).label(
                name="spend",
            ),
        )
        if since is not None:
            statement = statement.where(
                LedgerEntry.occurred_on >= since,
            )
        if supplier_id is not None:
            statement = statement.where(
                InvoiceItem.supplier_id == supplier_id,
            )
        result = await self.session.execute(
            statement=statement,
        )
        return PurchaseOverview.model_validate(
            obj=result.mappings().one(),
        )

    async def summaries(
        self,
        *,
        as_of: date,
        since: date | None,
        search: str | None,
        supplier_id: int | None,
        product_id: int | None = None,
    ) -> list[SummaryRow]:
        lines = _posted_lines(
            as_of=as_of,
        ).add_columns(
            InvoiceItem.product_id,
            InvoiceItem.invoice_id,
            LedgerEntry.occurred_on,
            InvoiceItem.cost_price_total,
            InvoiceItem.quantity,
            InvoiceItem.unit,
        )
        if product_id is not None:
            lines = lines.where(
                InvoiceItem.product_id == product_id,
            )
        if supplier_id is not None:
            lines = lines.where(
                InvoiceItem.supplier_id == supplier_id,
            )
        if search:
            lines = lines.join(
                target=Product,
                onclause=Product.id == InvoiceItem.product_id,
            ).where(
                Product.name.collate(
                    collation=UNICODE_COLLATION,
                ).icontains(
                    other=search,
                    autoescape=True,
                ),
            )
        receipts = lines.cte(
            name="receipts",
        )
        totals = _totals(
            receipts=receipts,
            since=since,
        )
        windows = _unit_windows(
            receipts=receipts,
            totals=totals,
        )
        result = await self.session.execute(
            statement=select(
                Product.id.label(
                    name="product_id",
                ),
                Product.name,
                Product.supplier_id,
                Supplier.name.label(
                    name="supplier_name",
                ),
                Supplier.short_name,
                totals.c.deliveries,
                totals.c.lifetime_deliveries,
                totals.c.spend,
                totals.c.last_on,
                totals.c.recent_days,
                windows.c.unit,
                windows.c.current_cost,
                windows.c.current_quantity,
                windows.c.current_deliveries,
                windows.c.previous_cost,
                windows.c.previous_quantity,
                windows.c.previous_deliveries,
            )
            .join(
                target=totals,
                onclause=totals.c.product_id == Product.id,
            )
            .join(
                target=Supplier,
                onclause=Supplier.id == Product.supplier_id,
            )
            .outerjoin(
                target=windows,
                onclause=windows.c.product_id == Product.id,
            )
            .order_by(
                Product.id,
                windows.c.unit,
            ),
        )
        summaries: dict[int, SummaryRow] = {}
        for row in result:
            summary = summaries.get(
                row.product_id,
            )
            if summary is None:
                summary = SummaryRow(
                    product_id=row.product_id,
                    name=row.name,
                    supplier_id=row.supplier_id,
                    supplier_name=row.short_name or row.supplier_name,
                    deliveries=row.deliveries,
                    lifetime_deliveries=row.lifetime_deliveries,
                    spend=row.spend,
                    last_on=row.last_on,
                    recent_days=row.recent_days,
                    units=[],
                )
                summaries[row.product_id] = summary
            if row.current_deliveries is not None:
                summary.units.append(
                    UnitWindow(
                        unit=row.unit,
                        current_cost=row.current_cost,
                        current_quantity=row.current_quantity,
                        current_deliveries=row.current_deliveries,
                        previous_cost=row.previous_cost,
                        previous_quantity=row.previous_quantity,
                        previous_deliveries=row.previous_deliveries,
                    ),
                )
        return list(
            summaries.values(),
        )

    async def history(
        self,
        *,
        product_id: int,
        as_of: date,
        since: date | None,
    ) -> list[HistoryRow]:
        statement = (
            _posted_lines(
                as_of=as_of,
            )
            .add_columns(
                LedgerEntry.occurred_on,
                InvoiceItem.invoice_id,
                Invoice.invoice_number,
                InvoiceItem.line_no,
                _normalized_unit(
                    value=InvoiceItem.unit,
                ),
                InvoiceItem.quantity,
                InvoiceItem.cost_price,
                InvoiceItem.cost_price_total,
                InvoiceItem.retail_price,
            )
            .join(
                target=Invoice,
                onclause=Invoice.id == InvoiceItem.invoice_id,
            )
            .where(
                InvoiceItem.product_id == product_id,
            )
            .order_by(
                LedgerEntry.occurred_on,
                InvoiceItem.invoice_id,
                InvoiceItem.line_no,
            )
        )
        if since is not None:
            statement = statement.where(
                LedgerEntry.occurred_on >= since,
            )
        result = await self.session.execute(
            statement=statement,
        )
        return [
            HistoryRow(
                occurred_on=row.occurred_on,
                invoice_id=row.invoice_id,
                invoice_number=row.invoice_number,
                line_no=row.line_no,
                unit=row.unit,
                quantity=row.quantity,
                cost_price=row.cost_price,
                cost_price_total=row.cost_price_total,
                retail_price=row.retail_price,
            )
            for row in result
        ]


def _posted_lines(
    *,
    as_of: date,
) -> Select[()]:
    return (
        select()
        .select_from(
            InvoiceItem,
        )
        .join(
            target=LedgerEntry,
            onclause=LedgerEntry.invoice_id == InvoiceItem.invoice_id,
        )
        .where(
            LedgerEntry.kind == LedgerKind.INVOICE,
            LedgerEntry.invoice_status == InvoiceStatus.CONFIRMED,
            LedgerEntry.reverses_id.is_(
                other=None,
            ),
            LedgerEntry.occurred_on <= as_of,
        )
    )


def _totals(
    *,
    receipts: CTE,
    since: date | None,
) -> CTE:
    occurred_on = receipts.c.occurred_on
    in_period = true() if since is None else occurred_on >= since
    recent_days = func.array_agg(
        occurred_on.distinct(),
    ).aggregate_order_by(
        occurred_on.desc(),
    )
    return (
        select(
            receipts.c.product_id,
            func.min(
                occurred_on,
            )
            .filter(
                in_period,
            )
            .label(
                name="first_in_period",
            ),
            func.count(
                receipts.c.invoice_id.distinct(),
            )
            .filter(
                in_period,
            )
            .label(
                name="deliveries",
            ),
            func.count(
                receipts.c.invoice_id.distinct(),
            ).label(
                name="lifetime_deliveries",
            ),
            func.coalesce(
                func.sum(
                    receipts.c.cost_price_total,
                ).filter(
                    in_period,
                ),
                0,
            ).label(
                name="spend",
            ),
            func.max(
                occurred_on,
            ).label(
                name="last_on",
            ),
            Grouping(
                element=recent_days,
            )[1:6].label(
                name="recent_days",
            ),
        )
        .group_by(
            receipts.c.product_id,
        )
        .cte()
    )


def _unit_windows(
    *,
    receipts: CTE,
    totals: CTE,
) -> Subquery:
    current = receipts.c.occurred_on == totals.c.last_on
    previous = and_(
        receipts.c.occurred_on == totals.c.first_in_period,
        totals.c.first_in_period < totals.c.last_on,
    )
    unit = _normalized_unit(
        value=receipts.c.unit,
    )
    return (
        select(
            receipts.c.product_id,
            unit,
            *_window_columns(
                receipts=receipts,
                within=current,
                prefix="current",
            ),
            *_window_columns(
                receipts=receipts,
                within=previous,
                prefix="previous",
            ),
        )
        .join(
            target=totals,
            onclause=totals.c.product_id == receipts.c.product_id,
        )
        .where(
            receipts.c.occurred_on >= totals.c.first_in_period,
        )
        .group_by(
            receipts.c.product_id,
            unit,
        )
        .subquery()
    )


def _normalized_unit(
    *,
    value: SQLColumnExpression[str | None],
) -> ColumnElement[str | None]:
    return func.nullif(
        func.regexp_replace(
            func.lower(
                value.collate(
                    collation=UNICODE_COLLATION,
                ),
            ),
            r"^[[:space:]]+|[[:space:].]+$",
            "",
            "g",
        ),
        "",
    ).label(
        name="unit",
    )


def _window_columns(
    *,
    receipts: CTE,
    within: ColumnElement[bool],
    prefix: str,
) -> tuple[ColumnElement, ColumnElement, ColumnElement]:
    return (
        func.coalesce(
            func.sum(
                receipts.c.cost_price_total,
            ).filter(
                within,
            ),
            0,
        ).label(
            name=f"{prefix}_cost",
        ),
        func.coalesce(
            func.sum(
                receipts.c.quantity,
            ).filter(
                within,
            ),
            0,
        ).label(
            name=f"{prefix}_quantity",
        ),
        func.count(
            receipts.c.invoice_id.distinct(),
        )
        .filter(
            within,
        )
        .label(
            name=f"{prefix}_deliveries",
        ),
    )


PurchaseRepositoryDep = Annotated[
    PurchaseRepository,
    Depends(
        dependency=PurchaseRepository,
    ),
]
