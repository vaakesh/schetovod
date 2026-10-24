from fastapi import APIRouter

from core.http import PageLimit
from suppliers.schemas import SupplierEdit, SupplierSummary
from suppliers.service import SupplierServiceDep

router = APIRouter()


@router.get(
    path="/supplier",
    response_model=list[SupplierSummary],
)
async def search_suppliers(
    service: SupplierServiceDep,
    q: str | None = None,
    limit: PageLimit = 20,
) -> list[SupplierSummary]:
    return await service.search(
        query=q.strip() if q else None,
        limit=limit,
    )


@router.put(
    path="/supplier/{supplier_id}",
    response_model=SupplierSummary,
)
async def edit_supplier(
    supplier_id: int,
    payload: SupplierEdit,
    service: SupplierServiceDep,
) -> SupplierSummary:
    return await service.edit_supplier(
        supplier_id=supplier_id,
        payload=payload,
    )
