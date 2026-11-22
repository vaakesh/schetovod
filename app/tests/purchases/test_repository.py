from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.schema import CreateSchema

from core.config import settings
from core.db import Base
from core.enums import InvoiceStatus, LedgerKind
from invoices.models import Invoice, InvoiceItem
from ledger.models import LedgerEntry
from products.models import Product
from purchases.repository import HistoryRow, PurchaseRepository, UnitWindow
from purchases.schemas import Period, Sort
from purchases.service import PurchaseService
from suppliers.models import Supplier

AS_OF = date.fromisoformat(
    "2026-03-01",
)
CURRENT_START = date.fromisoformat(
    "2026-01-31",
)
PREVIOUS_END = date.fromisoformat(
    "2026-01-30",
)
PREVIOUS_START = date.fromisoformat(
    "2026-01-01",
)
OLDER = date.fromisoformat(
    "2025-12-31",
)


@pytest_asyncio.fixture
async def repository() -> AsyncIterator[PurchaseRepository]:
    engine = create_async_engine(
        url=settings.database_url,
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"purchase_test_{uuid4().hex}"
                await connection.execute(
                    statement=CreateSchema(
                        name=schema,
                    ),
                )
                await connection.execute(
                    statement=select(
                        func.set_config(
                            "search_path",
                            schema,
                            True,
                        ),
                    ),
                )
                await connection.run_sync(
                    Base.metadata.create_all,
                    tables=[
                        Base.metadata.tables[Supplier.__tablename__],
                        Base.metadata.tables[Product.__tablename__],
                        Base.metadata.tables[Invoice.__tablename__],
                        Base.metadata.tables[InvoiceItem.__tablename__],
                        Base.metadata.tables[LedgerEntry.__tablename__],
                    ],
                )
                async with AsyncSession(
                    bind=connection,
                ) as session:
                    await session.execute(
                        statement=insert(
                            Supplier,
                        ),
                        params=[
                            {"id": 1, "name": "Main supplier", "short_name": "Main"},
                            {"id": 2, "name": "Other supplier", "short_name": None},
                        ],
                    )
                    await session.execute(
                        statement=insert(
                            Product,
                        ),
                        params=[
                            {
                                "id": 1,
                                "supplier_id": 1,
                                "name": "Молоко 2%",
                                "markup_pct": 20,
                                "retail_price": 99,
                            },
                            {
                                "id": 2,
                                "supplier_id": 1,
                                "name": "Молоко 20",
                                "markup_pct": 20,
                                "retail_price": 99,
                            },
                            {
                                "id": 3,
                                "supplier_id": 2,
                                "name": "Молоко 2%",
                                "markup_pct": 20,
                                "retail_price": 99,
                            },
                        ],
                    )
                    yield PurchaseRepository(
                        session=session,
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _invoice(
    *,
    repository: PurchaseRepository,
    invoice_id: int,
    occurred_on: date | None,
    lines: list[tuple[int, str | None, str]],
    supplier_id: int = 1,
    status: InvoiceStatus = InvoiceStatus.CONFIRMED,
) -> None:
    session = repository.session
    await session.execute(
        statement=insert(
            Invoice,
        ).values(
            id=invoice_id,
            supplier_id=supplier_id,
            invoice_date=AS_OF,
            invoice_number=f"#{invoice_id}",
            status=status,
            extracted={},
        ),
    )
    await session.execute(
        statement=insert(
            InvoiceItem,
        ),
        params=[
            {
                "invoice_id": invoice_id,
                "product_id": product_id,
                "supplier_id": supplier_id,
                "line_no": line_no,
                "name": "Milk on the invoice",
                "unit": unit,
                "quantity": 2,
                "cost_price": Decimal(
                    "4.15",
                ),
                "cost_price_total": Decimal(
                    cost_total,
                ),
                "markup_pct": 20,
                "retail_price": 5,
            }
            for line_no, (product_id, unit, cost_total) in enumerate(
                lines,
                start=1,
            )
        ],
    )
    if occurred_on is not None:
        await session.execute(
            statement=insert(
                LedgerEntry,
            ).values(
                occurred_on=occurred_on,
                kind=LedgerKind.INVOICE,
                amount=10,
                invoice_id=invoice_id,
                invoice_status=status,
            ),
        )


class TestOverview:
    async def test_counts_a_shared_invoice_once_and_excludes_old_deliveries(
        self, repository: PurchaseRepository
    ) -> None:
        await _invoice(
            repository=repository,
            invoice_id=1,
            occurred_on=CURRENT_START,
            lines=[(1, "kg", "10.25"), (2, "kg", "15")],
        )
        await _invoice(
            repository=repository,
            invoice_id=2,
            occurred_on=OLDER,
            lines=[(2, "kg", "20")],
        )
        await _invoice(
            repository=repository,
            invoice_id=3,
            supplier_id=2,
            occurred_on=AS_OF,
            lines=[(3, "kg", "30")],
        )

        overview = await repository.overview(
            as_of=AS_OF,
            since=CURRENT_START,
            supplier_id=1,
        )

        assert overview.invoices == 1
        assert overview.spend == Decimal(
            value="25.25",
        )


class TestSummaries:
    @pytest.mark.parametrize(
        ("period", "deliveries", "spend", "change"),
        [
            (Period.DAYS_30, 2, "44", "20.00"),
            (Period.DAYS_60, 3, "60", "50.00"),
            (Period.DAYS_90, 4, "72", "100.00"),
            (Period.ALL, 5, "80", "200.00"),
        ],
    )
    async def test_report_and_history_use_the_selected_period(
        self,
        repository: PurchaseRepository,
        period: Period,
        deliveries: int,
        spend: str,
        change: str,
    ) -> None:
        for invoice_id, day, total in [
            (1, "2026-03-01", "8"),
            (2, "2026-08-01", "12"),
            (3, "2026-09-01", "16"),
            (4, "2026-10-01", "20"),
            (5, "2026-10-15", "24"),
        ]:
            await _invoice(
                repository=repository,
                invoice_id=invoice_id,
                occurred_on=date.fromisoformat(
                    day,
                ),
                lines=[(1, "kg", total)],
            )
        service = PurchaseService(
            repository=repository,
        )
        report = await service.summary(
            period=period,
            sort=Sort.FREQUENCY,
            search=None,
            supplier_id=None,
        )
        detail = await service.history(
            product_id=1,
            period=period,
        )

        [item] = report.items
        assert item == detail.product
        assert item.deliveries == deliveries
        assert (
            len(
                detail.lines,
            )
            == deliveries
        )
        assert item.spend == Decimal(
            value=spend,
        )
        assert item.price_trend.change_pct == Decimal(
            value=change,
        )

    async def test_returns_only_the_six_latest_distinct_delivery_dates(
        self,
        repository: PurchaseRepository,
        daily_receipts: None,
    ) -> None:
        [row] = await repository.summaries(
            as_of=AS_OF,
            since=None,
            search=None,
            supplier_id=None,
        )

        assert [day.day for day in row.recent_days] == [7, 6, 5, 4, 3, 2]

    async def test_counts_invoices_and_preserves_products_without_period_deliveries(
        self,
        repository: PurchaseRepository,
    ) -> None:
        await _invoice(
            repository=repository,
            invoice_id=10,
            occurred_on=OLDER,
            lines=[(2, "kg", "10.01")],
        )
        await _invoice(
            repository=repository,
            invoice_id=11,
            occurred_on=CURRENT_START,
            lines=[(1, "kg", "8.31"), (1, "kg", "8.29")],
        )
        await _invoice(
            repository=repository,
            invoice_id=12,
            occurred_on=CURRENT_START,
            lines=[(1, "kg", "8.31")],
        )

        active, dormant = await repository.summaries(
            as_of=AS_OF,
            since=CURRENT_START,
            search=None,
            supplier_id=None,
        )

        assert active.product_id == 1
        assert active.supplier_name == "Main"
        assert active.deliveries == 2
        assert active.spend == Decimal(
            "24.91",
        )
        assert active.last_on == CURRENT_START
        assert active.recent_days == [CURRENT_START]
        assert dormant.product_id == 2
        assert dormant.deliveries == 0
        assert dormant.spend == 0
        assert dormant.last_on == OLDER
        assert dormant.recent_days == [OLDER]
        assert dormant.units == []

    async def test_groups_normalized_units_on_first_and_last_days_of_period(
        self,
        repository: PurchaseRepository,
    ) -> None:
        await _invoice(
            repository=repository,
            invoice_id=10,
            occurred_on=OLDER,
            lines=[(1, "кг", "90.01")],
        )
        await _invoice(
            repository=repository,
            invoice_id=11,
            occurred_on=PREVIOUS_START,
            lines=[(1, "кг", "7.31")],
        )
        await _invoice(
            repository=repository,
            invoice_id=12,
            occurred_on=PREVIOUS_START,
            lines=[(1, " КГ.\t", "7.29"), (1, "  .  ", "1.00")],
        )
        await _invoice(
            repository=repository,
            invoice_id=13,
            occurred_on=AS_OF,
            lines=[(1, "кг", "8.31"), (1, " Кг. ", "8.29"), (1, None, "1.50")],
        )
        await _invoice(
            repository=repository,
            invoice_id=14,
            occurred_on=AS_OF,
            lines=[(1, "pc", "3.50")],
        )

        [row] = await repository.summaries(
            as_of=AS_OF,
            since=PREVIOUS_START,
            search=None,
            supplier_id=None,
        )

        assert {window.unit: window for window in row.units} == {
            "кг": UnitWindow(
                unit="кг",
                current_cost=Decimal(
                    value="16.60",
                ),
                current_quantity=Decimal(
                    value=4,
                ),
                current_deliveries=1,
                previous_cost=Decimal(
                    value="14.60",
                ),
                previous_quantity=Decimal(
                    value=4,
                ),
                previous_deliveries=2,
            ),
            "pc": UnitWindow(
                unit="pc",
                current_cost=Decimal(
                    value="3.50",
                ),
                current_quantity=Decimal(
                    value=2,
                ),
                current_deliveries=1,
                previous_cost=Decimal(
                    value=0,
                ),
                previous_quantity=Decimal(
                    value=0,
                ),
                previous_deliveries=0,
            ),
            None: UnitWindow(
                unit=None,
                current_cost=Decimal(
                    value="1.50",
                ),
                current_quantity=Decimal(
                    value=2,
                ),
                current_deliveries=1,
                previous_cost=Decimal(
                    value="1.00",
                ),
                previous_quantity=Decimal(
                    value=2,
                ),
                previous_deliveries=1,
            ),
        }

    async def test_search_escapes_wildcards_and_filters_supplier_and_product(
        self,
        repository: PurchaseRepository,
    ) -> None:
        await _invoice(
            repository=repository,
            invoice_id=10,
            occurred_on=AS_OF,
            lines=[(1, "kg", "8.30"), (2, "kg", "8.30")],
        )
        await _invoice(
            repository=repository,
            invoice_id=11,
            occurred_on=AS_OF,
            supplier_id=2,
            lines=[(3, "kg", "8.30")],
        )

        matched = await repository.summaries(
            as_of=AS_OF,
            since=None,
            search="МОЛОКО 2%",
            supplier_id=1,
        )
        detail = await repository.summaries(
            as_of=AS_OF,
            since=None,
            search=None,
            supplier_id=None,
            product_id=3,
        )

        assert [row.product_id for row in matched] == [1]
        assert [row.product_id for row in detail] == [3]
        assert detail[0].supplier_name == "Other supplier"


@pytest_asyncio.fixture
async def daily_receipts(repository: PurchaseRepository) -> None:
    for day in range(
        1,
        8,
    ):
        await _invoice(
            repository=repository,
            invoice_id=day,
            occurred_on=date(
                year=2026,
                month=2,
                day=day,
            ),
            lines=[(1, "kg", "8.30"), (1, "kg", "8.30")],
        )


class TestHistory:
    async def test_returns_exact_lines_in_posting_day_invoice_and_line_order(
        self,
        repository: PurchaseRepository,
    ) -> None:
        await _invoice(
            repository=repository,
            invoice_id=10,
            occurred_on=AS_OF,
            lines=[(1, " КГ. ", "8.31"), (1, None, "8.29")],
        )
        await _invoice(
            repository=repository,
            invoice_id=11,
            occurred_on=AS_OF,
            lines=[(1, "kg", "8.30"), (2, "kg", "8.30")],
        )
        await _invoice(
            repository=repository,
            invoice_id=12,
            occurred_on=CURRENT_START,
            lines=[(1, "kg", "8.30")],
        )

        result = await repository.history(
            product_id=1,
            as_of=AS_OF,
            since=CURRENT_START,
        )

        assert [(row.occurred_on, row.invoice_id, row.line_no) for row in result] == [
            (CURRENT_START, 12, 1),
            (AS_OF, 10, 1),
            (AS_OF, 10, 2),
            (AS_OF, 11, 1),
        ]
        assert result[1] == HistoryRow(
            occurred_on=AS_OF,
            invoice_id=10,
            invoice_number="#10",
            line_no=1,
            unit="кг",
            quantity=Decimal(
                value=2,
            ),
            cost_price=Decimal(
                value="4.15",
            ),
            cost_price_total=Decimal(
                value="8.31",
            ),
            retail_price=Decimal(
                value=5,
            ),
        )

    async def test_excludes_reversed_unposted_future_and_out_of_period_lines(
        self,
        repository: PurchaseRepository,
    ) -> None:
        await _invoice(
            repository=repository,
            invoice_id=10,
            occurred_on=PREVIOUS_END,
            lines=[(1, "kg", "8.30")],
        )
        await _invoice(
            repository=repository,
            invoice_id=11,
            occurred_on=AS_OF,
            status=InvoiceStatus.REVERSED,
            lines=[(1, "kg", "8.30")],
        )
        await _invoice(
            repository=repository,
            invoice_id=12,
            occurred_on=None,
            status=InvoiceStatus.DRAFT,
            lines=[(1, "kg", "8.30")],
        )
        await _invoice(
            repository=repository,
            invoice_id=13,
            occurred_on=AS_OF
            + timedelta(
                days=1,
            ),
            lines=[(1, "kg", "8.30")],
        )

        result = await repository.history(
            product_id=1,
            as_of=AS_OF,
            since=CURRENT_START,
        )

        assert result == []
