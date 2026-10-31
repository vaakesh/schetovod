from fastapi import APIRouter

from core.http import ReportDate
from traffic.schemas import ReceiptImportCreate, ReceiptImportResult, TrafficReport
from traffic.service import TrafficServiceDep

router = APIRouter()


@router.post(
    path="/traffic/import",
    response_model=ReceiptImportResult,
)
async def import_receipts(
    payload: ReceiptImportCreate,
    service: TrafficServiceDep,
) -> ReceiptImportResult:
    return await service.load(
        payload=payload,
    )


@router.get(
    path="/traffic/report",
    response_model=TrafficReport,
)
async def traffic_report(
    service: TrafficServiceDep,
    date_from: ReportDate,
    date_to: ReportDate,
) -> TrafficReport:
    return await service.report(
        date_from=date_from,
        date_to=date_to,
    )
