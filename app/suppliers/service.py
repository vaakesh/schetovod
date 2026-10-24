from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.http import conflict
from suppliers.models import Supplier
from suppliers.repository import SupplierRepositoryDep
from suppliers.schemas import SupplierEdit, SupplierSummary


class SupplierService:
    def __init__(
        self,
        suppliers: SupplierRepositoryDep,
    ) -> None:
        self.suppliers = suppliers

    async def edit_supplier(
        self,
        supplier_id: int,
        payload: SupplierEdit,
    ) -> SupplierSummary:
        supplier = await self.suppliers.get(
            supplier_id=supplier_id,
        )
        if supplier is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Продавец не найден",
            )
        if payload.inn is not None:
            existing = await self.suppliers.get_by_inn(
                inn=payload.inn,
            )
            if existing is not None and existing.id != supplier.id:
                conflict(
                    detail=f"Поставщик с ИНН {payload.inn} уже существует",
                )
        supplier.name = payload.name
        supplier.short_name = payload.short_name
        supplier.inn = payload.inn
        await self.suppliers.commit()
        return supplier_summary(
            supplier=supplier,
        )

    async def search(
        self,
        query: str | None,
        limit: int,
    ) -> list[SupplierSummary]:
        suppliers = await self.suppliers.search(
            query=query,
            limit=limit,
        )
        return [
            supplier_summary(
                supplier=supplier,
            )
            for supplier in suppliers
        ]


SupplierServiceDep = Annotated[
    SupplierService,
    Depends(
        dependency=SupplierService,
    ),
]


def supplier_summary(supplier: Supplier) -> SupplierSummary:
    return SupplierSummary(
        id=supplier.id,
        name=supplier.name,
        short_name=supplier.short_name,
        inn=supplier.inn,
    )
