import logging

from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqEvents, TaskiqState

from aqsi.client import aqsi_client
from core.broker import broker
from core.config import now, settings
from core.db import get_engine
from core.metrics import receipts_last_success, receipts_loaded
from traffic.repository import ReceiptRepository
from traffic.service import TrafficService

logger = logging.getLogger(
    name=__name__,
)

EVERY_TEN_MINUTES = "*/10 * * * *"


@broker.task(
    schedule=[
        {
            "cron": EVERY_TEN_MINUTES,
            "cron_offset": settings.timezone,
        },
    ],
    # the next run is the retry, delayed attempts would only pile up behind it
    retry_on_error=False,
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
    receipts_loaded.add(
        amount=result.loaded,
    )
    receipts_last_success.set(
        amount=now().timestamp(),
    )
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
    """the receipts missed by a stopped computer arrive at once, not at the next run"""
    await import_receipts.kiq()
