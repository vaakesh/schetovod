import logging
from typing import Annotated

from fastapi import (
    FastAPI,
    Query,
    Request,
    status,
)

from enums import InvoiceStatus
from schemas import (
    ConfirmedInvoice,
    InvoiceDraft,
    InvoiceExtraction,
    InvoiceList,
    PostedInvoice,
    ProductSummary,
    SupplierSummary,
)
from services import InvoiceServiceDep, SupplierServiceDep

app = FastAPI()
# uvicorn configures its own logger, a record there reaches the server output
logger = logging.getLogger(
    "uvicorn.error",
)

PageLimit = Annotated[
    int,
    Query(
        ge=1,
        le=200,
    ),
]
PageOffset = Annotated[
    int,
    Query(
        ge=0,
    ),
]


@app.get(
    path="/invoice",
    response_model=InvoiceList,
)
async def list_invoices(
    service: InvoiceServiceDep,
    status: InvoiceStatus | None = None,
    q: str | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> InvoiceList:
    return await service.list_invoices(
        status=status,
        query=q.strip() if q else None,
        limit=limit,
        offset=offset,
    )


@app.get(
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


@app.get(
    path="/supplier/{supplier_id}/products",
    response_model=list[ProductSummary],
)
async def search_products(
    supplier_id: int,
    service: SupplierServiceDep,
    q: str | None = None,
    limit: PageLimit = 20,
) -> list[ProductSummary]:
    return await service.search_products(
        supplier_id=supplier_id,
        query=q.strip() if q else None,
        limit=limit,
    )


@app.post(
    path="/invoice",
    response_model=InvoiceDraft,
)
async def receive_invoice(
    invoice: InvoiceExtraction,
    request: Request,
    service: InvoiceServiceDep,
) -> InvoiceDraft:
    return await service.receive_invoice(
        invoice=invoice,
        extracted=await request.json(),
    )


@app.get(
    path="/invoice/{invoice_id}",
    response_model=InvoiceDraft,
)
async def get_draft(
    invoice_id: int,
    service: InvoiceServiceDep,
) -> InvoiceDraft:
    return await service.get_draft(
        invoice_id=invoice_id,
    )


@app.get(
    path="/invoice/{invoice_id}/confirmed",
    response_model=PostedInvoice,
)
async def get_posted(
    invoice_id: int,
    service: InvoiceServiceDep,
) -> PostedInvoice:
    return await service.get_posted(
        invoice_id=invoice_id,
    )


@app.post(
    path="/invoice/{invoice_id}/confirm",
    response_model=ConfirmedInvoice,
)
async def confirm_invoice(
    invoice_id: int,
    service: InvoiceServiceDep,
) -> ConfirmedInvoice:
    return await service.confirm_invoice(
        invoice_id=invoice_id,
    )


@app.post(
    path="/invoice/{invoice_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def decline_invoice(
    invoice_id: int,
    service: InvoiceServiceDep,
) -> None:
    await service.decline_invoice(
        invoice_id=invoice_id,
    )
