from fastapi import APIRouter

from aqsi.schemas import ShiftImportCreate, ShiftImportResult
from aqsi.service import ShiftImportServiceDep

router = APIRouter()


@router.post(
    path="/ledger/import-shifts",
    response_model=ShiftImportResult,
)
async def import_shifts(
    payload: ShiftImportCreate,
    service: ShiftImportServiceDep,
) -> ShiftImportResult:
    return await service.load(
        payload=payload,
    )
