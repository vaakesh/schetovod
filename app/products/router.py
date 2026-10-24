from fastapi import APIRouter, status

from core.http import PageLimit
from ledger.schemas import LedgerPosted
from products.schemas import (
    Catalog,
    PriceTagMark,
    ProductEdit,
    ProductSummary,
)
from products.service import ProductServiceDep

router = APIRouter()


@router.get(
    path="/supplier/{supplier_id}/products",
    response_model=list[ProductSummary],
)
async def search_products(
    supplier_id: int,
    service: ProductServiceDep,
    q: str | None = None,
    limit: PageLimit = 20,
) -> list[ProductSummary]:
    return await service.search_products(
        supplier_id=supplier_id,
        query=q.strip() if q else None,
        limit=limit,
    )


@router.get(
    path="/catalog",
    response_model=Catalog,
)
async def catalog(
    service: ProductServiceDep,
) -> Catalog:
    return await service.catalog()


@router.put(
    path="/product/{product_id}",
    response_model=LedgerPosted | None,
)
async def edit_product(
    product_id: int,
    payload: ProductEdit,
    service: ProductServiceDep,
) -> LedgerPosted | None:
    return await service.edit_product(
        product_id=product_id,
        payload=payload,
    )


@router.put(
    path="/product/{product_id}/price-tag",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_price_tag(
    product_id: int,
    payload: PriceTagMark,
    service: ProductServiceDep,
) -> None:
    await service.mark_price_tag(
        product_id=product_id,
        payload=payload,
    )
