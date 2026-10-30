from typing import Annotated

from fastapi import APIRouter, Query, Response

from core.http import ReportDate
from reports.pdf import (
    invoices_pdf,
    invoices_pdf_filename,
    report_pdf,
    report_pdf_filename,
)
from reports.schemas import LedgerReport, PeriodReport
from reports.service import ReportServiceDep
from reports.xlsx import report_filename, report_workbook

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"


@router.get(
    path="/ledger/report",
    response_model=LedgerReport,
)
async def ledger_report(
    service: ReportServiceDep,
    date_from: ReportDate,
    date_to: ReportDate,
) -> LedgerReport:
    return await service.report(
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
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
    service: ReportServiceDep,
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


@router.get(
    # not under /invoice/, there the path would be read as an invoice id
    path="/invoices/print.pdf",
    response_class=Response,
    responses={
        200: {
            "content": {
                PDF_MEDIA_TYPE: {},
            },
        },
    },
)
async def invoices_print_pdf(
    service: ReportServiceDep,
    ids: Annotated[
        list[int],
        Query(
            min_length=1,
            max_length=200,
        ),
    ],
) -> Response:
    invoices = await service.printed_invoices(
        invoice_ids=ids,
    )
    filename = invoices_pdf_filename(
        invoices=invoices,
    )
    # inline, the browser opens it in a tab ready to print
    return Response(
        content=invoices_pdf(
            invoices=invoices,
        ),
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get(
    path="/ledger/report/days",
    response_model=PeriodReport,
)
async def ledger_period_report(
    service: ReportServiceDep,
    date_from: ReportDate,
    date_to: ReportDate,
) -> PeriodReport:
    return await service.period_report(
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    path="/ledger/report.pdf",
    response_class=Response,
    responses={
        200: {
            "content": {
                PDF_MEDIA_TYPE: {},
            },
        },
    },
)
async def ledger_report_pdf(
    service: ReportServiceDep,
    date_from: ReportDate,
    date_to: ReportDate,
) -> Response:
    report = await service.period_report(
        date_from=date_from,
        date_to=date_to,
    )
    filename = report_pdf_filename(
        report=report,
    )
    return Response(
        content=report_pdf(
            report=report,
        ),
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
