import logging

from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqEvents, TaskiqState

from aqsi.client import aqsi_client
from core.broker import broker
from core.config import settings
from core.db import get_engine
from traffic.repository import ReceiptRepository
from traffic.service import TrafficService

logger = logging.getLogger(
    name=__name__,
)

# mondays at 4, the shop is closed on mondays and the week before is complete
WEEKLY = "0 4 * * 1"


@broker.task(
    schedule=[
        {
            "cron": WEEKLY,
            "cron_offset": settings.timezone,
        },
    ],
    retry_on_error=True,
)
async def import_receipts() -> None:
    async with AsyncSession(
        bind=get_engine(),
        expire_on_commit=False,
    ) as session:
        service = TrafficService(
            aqsi=aqsi_client(),
            receipts=ReceiptRepository(
                session=session,
            ),
        )
        result = await service.load_new()
    logger.info(
        "receipts of aQsi: %d received, %d new",
        result.received,
        result.loaded,
    )


@broker.on_event(
    TaskiqEvents.WORKER_STARTUP,
)
async def import_receipts_on_start(
    state: TaskiqState,
) -> None:
    """a stopped computer misses the weekly run and an empty base would wait a week"""
    await import_receipts.kiq()
