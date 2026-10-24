import json
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from core.config import settings
from core.enums import InvoiceSort, InvoiceStatus
from core.http import PageLimit, PageOffset
from invoices.drafts import InvoiceDraftServiceDep
from invoices.extraction import InvoiceExtraction
from invoices.payments import InvoicePaymentServiceDep
from invoices.posting import InvoicePostingServiceDep
from invoices.queries import InvoiceQueryServiceDep
from invoices.schemas import (
    ConfirmedInvoice,
    DraftForm,
    InvoiceConfirm,
    InvoiceDraft,
    InvoiceList,
    PaymentCreate,
    PostedInvoice,
)
from recognition.images import read_images
from recognition.service import extract_invoice

router = APIRouter()

# uvicorn configures its own logger, a record there reaches the server output
logger = logging.getLogger(
    "uvicorn.error",
)


@router.get(
    path="/invoice",
    response_model=InvoiceList,
)
async def list_invoices(
    service: InvoiceQueryServiceDep,
    status: InvoiceStatus | None = None,
    # only the confirmed invoices not paid in full
    unpaid: bool = False,
    q: str | None = None,
    sort: InvoiceSort = InvoiceSort.NEWEST,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> InvoiceList:
    return await service.list_invoices(
        status=status,
        unpaid=unpaid,
        query=q.strip() if q else None,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.post(
    path="/invoice",
    response_model=InvoiceDraft,
)
async def receive_invoice(
    invoice: InvoiceExtraction,
    request: Request,
    service: InvoiceDraftServiceDep,
) -> InvoiceDraft:
    return await service.receive_invoice(
        invoice=invoice,
        extracted=await request.json(),
    )


@router.post(
    path="/invoice/image",
    response_model=InvoiceDraft,
)
async def recognize_invoice(
    files: Annotated[
        list[UploadFile],
        File(),
    ],
    service: InvoiceDraftServiceDep,
) -> InvoiceDraft:
    if not settings.include_api_openai:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Распознавание по фото выключено: OpenAI API не подключён (INCLUDE_API_OPENAI=0)",
        )
    extracted = await extract_invoice(
        images=await read_images(
            files=files,
        ),
    )
    # the model output passes the same checks as an uploaded JSON
    try:
        invoice = InvoiceExtraction.model_validate(
            obj=extracted,
        )
    except ValidationError as error:
        # the raw model output is archived, the log shows the validation errors
        logger.warning(
            "recognized invoice did not pass validation\nerrors: %s\nextracted: %s",
            error.errors(
                include_url=False,
                include_context=False,
            ),
            json.dumps(
                obj=extracted,
                ensure_ascii=False,
                indent=2,
            ),
        )
        raise RequestValidationError(
            errors=[
                {
                    **detail,
                    "loc": (
                        "body",
                        *detail["loc"],
                    ),
                }
                for detail in error.errors(
                    include_url=False,
                    include_context=False,
                )
            ],
        ) from error
    return await service.receive_invoice(
        invoice=invoice,
        extracted=extracted,
    )


@router.get(
    path="/invoice/{invoice_id}",
    response_model=InvoiceDraft,
)
async def get_draft(
    invoice_id: int,
    service: InvoiceDraftServiceDep,
) -> InvoiceDraft:
    return await service.get_draft(
        invoice_id=invoice_id,
    )


@router.get(
    path="/invoice/{invoice_id}/confirmed",
    response_model=PostedInvoice,
)
async def get_posted(
    invoice_id: int,
    service: InvoiceQueryServiceDep,
) -> PostedInvoice:
    return await service.get_posted(
        invoice_id=invoice_id,
    )


@router.post(
    path="/invoice/{invoice_id}/payments",
    response_model=PostedInvoice,
)
async def add_payment(
    invoice_id: int,
    payload: PaymentCreate,
    service: InvoicePaymentServiceDep,
) -> PostedInvoice:
    return await service.add_payment(
        invoice_id=invoice_id,
        payload=payload,
    )


@router.delete(
    path="/invoice/{invoice_id}/payments/{payment_id}",
    response_model=PostedInvoice,
)
async def delete_payment(
    invoice_id: int,
    payment_id: int,
    service: InvoicePaymentServiceDep,
) -> PostedInvoice:
    return await service.delete_payment(
        invoice_id=invoice_id,
        payment_id=payment_id,
    )


@router.put(
    path="/invoice/{invoice_id}",
    response_model=InvoiceDraft,
)
async def save_form(
    invoice_id: int,
    form: DraftForm,
    service: InvoiceDraftServiceDep,
) -> InvoiceDraft:
    return await service.save_form(
        invoice_id=invoice_id,
        form=form,
    )


@router.post(
    path="/invoice/{invoice_id}/confirm",
    response_model=ConfirmedInvoice,
)
async def confirm_invoice(
    invoice_id: int,
    payload: InvoiceConfirm,
    service: InvoicePostingServiceDep,
) -> ConfirmedInvoice:
    return await service.confirm_invoice(
        invoice_id=invoice_id,
        occurred_on=payload.occurred_on,
    )


@router.post(
    path="/invoice/{invoice_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def decline_invoice(
    invoice_id: int,
    service: InvoiceDraftServiceDep,
) -> None:
    await service.decline_invoice(
        invoice_id=invoice_id,
    )
