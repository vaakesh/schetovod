from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from core.config import settings
from core.enums import ReceiptKind
from tests.fakes.store import FakeStore
from traffic.analytics import HourRow
from traffic.models import Receipt


class FakeReceipts:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def add_new(
        self,
        receipts: Sequence[Receipt],
    ) -> int:
        present = {receipt.aqsi_id for receipt in self.store.receipts}
        added = [receipt for receipt in receipts if receipt.aqsi_id not in present]
        self.store.receipts += added
        return len(added)

    async def hourly(
        self,
        date_from: date,
        date_to: date,
    ) -> list[HourRow]:
        rows: dict[tuple[date, int], HourRow] = {}
        for receipt in self.store.receipts:
            local = receipt.processed_at.astimezone(
                tz=ZoneInfo(
                    key=settings.timezone,
                ),
            )
            if not date_from <= local.date() <= date_to:
                continue
            row = rows.setdefault(
                (local.date(), local.hour),
                HourRow(
                    day=local.date(),
                    hour=local.hour,
                    sales=0,
                    revenue=Decimal(
                        value=0,
                    ),
                ),
            )
            if receipt.kind == ReceiptKind.SALE:
                row.sales += 1
                row.revenue += receipt.total
            else:
                row.revenue -= receipt.total
        return list(
            rows.values(),
        )

    async def last_receipt_at(self) -> datetime | None:
        return max(
            (receipt.processed_at for receipt in self.store.receipts),
            default=None,
        )
