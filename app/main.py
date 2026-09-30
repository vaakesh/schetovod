import json
import logging
from typing import Annotated

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from config import settings
from enums import InvoiceStatus, LedgerKind
from report_xlsx import report_filename, report_workbook
from schemas import (
    ConfirmedInvoice,
    DraftForm,
    InvoiceDate,
    InvoiceDraft,
    InvoiceExtraction,
    InvoiceList,
    LedgerBalance,
    LedgerPage,
    LedgerPosted,
    LedgerReport,
    OutflowCreate,
    PostedInvoice,
    ProductSummary,
    RevaluationCreate,
    RevaluationLineOut,
    StocktakeCreate,
    SupplierSummary,
)
from services import InvoiceServiceDep, LedgerServiceDep, SupplierServiceDep
from vision import extract_invoice, read_images

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
ReportDate = Annotated[
    InvoiceDate,
    Query(),
]
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


@app.post(
    path="/invoice/image",
    response_model=InvoiceDraft,
)
async def recognize_invoice(
    files: Annotated[
        list[UploadFile],
        File(),
    ],
    service: InvoiceServiceDep,
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
        # the model output is not saved anywhere else, the log shows what was rejected
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


@app.put(
    path="/invoice/{invoice_id}",
    response_model=InvoiceDraft,
)
async def save_form(
    invoice_id: int,
    form: DraftForm,
    service: InvoiceServiceDep,
) -> InvoiceDraft:
    return await service.save_form(
        invoice_id=invoice_id,
        form=form,
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


@app.get(
    path="/ledger",
    response_model=LedgerPage,
)
async def ledger_history(
    service: LedgerServiceDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> LedgerPage:
    return await service.history(
        limit=limit,
        offset=offset,
    )


@app.get(
    path="/ledger/balance",
    response_model=LedgerBalance,
)
async def ledger_balance(
    service: LedgerServiceDep,
    on: Annotated[
        InvoiceDate | None,
        Query(),
    ] = None,
) -> LedgerBalance:
    return await service.balance_on(
        on=on,
    )


@app.post(
    path="/ledger/sale",
    response_model=LedgerPosted,
)
async def add_sale(
    payload: OutflowCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_outflow(
        kind=LedgerKind.SALE,
        payload=payload,
    )


@app.post(
    path="/ledger/write-off",
    response_model=LedgerPosted,
)
async def add_write_off(
    payload: OutflowCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_outflow(
        kind=LedgerKind.WRITE_OFF,
        payload=payload,
    )


@app.post(
    path="/ledger/stocktake",
    response_model=LedgerPosted,
)
async def add_stocktake(
    payload: StocktakeCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_stocktake(
        payload=payload,
    )


@app.post(
    path="/ledger/revaluation",
    response_model=LedgerPosted,
)
async def add_revaluation(
    payload: RevaluationCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_revaluation(
        payload=payload,
    )


@app.get(
    path="/ledger/{entry_id}/revaluation",
    response_model=list[RevaluationLineOut],
)
async def revaluation_lines(
    entry_id: int,
    service: LedgerServiceDep,
) -> list[RevaluationLineOut]:
    return await service.revaluation_lines(
        entry_id=entry_id,
    )


@app.get(
    path="/ledger/report",
    response_model=LedgerReport,
)
async def ledger_report(
    service: LedgerServiceDep,
    date_from: ReportDate,
    date_to: ReportDate,
) -> LedgerReport:
    return await service.report(
        date_from=date_from,
        date_to=date_to,
    )


@app.get(
    path="/ledger/report.xlsx",
    response_class=Response,
    responses={
        200: {
            "content": {
                XLSX_MEDIA_TYPE: {},
            },
        },
    },
)
async def ledger_report_xlsx(
    service: LedgerServiceDep,
    date_from: ReportDate,
    date_to: ReportDate,
) -> Response:
    report = await service.report(
        date_from=date_from,
        date_to=date_to,
    )
    filename = report_filename(
        report=report,
    )
    return Response(
        content=report_workbook(
            report=report,
        ),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.post(
    path="/ledger/{entry_id}/reverse",
    response_model=LedgerPosted,
)
async def reverse_entry(
    entry_id: int,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.reverse(
        entry_id=entry_id,
    )
