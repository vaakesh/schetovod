from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from pydantic import JsonValue

from core.enums import InvoiceStatus
from invoices.calculations import sum_known, to_kopecks
from invoices.extraction import InvoiceExtraction
from invoices.forms import number_form_lines, numbered_extraction
from invoices.models import Invoice
from invoices.planning import InvoicePlanner, PlannedLine
from invoices.queries import get_draft_invoice
from invoices.repository import InvoiceRepositoryDep
from invoices.schemas import (
    DraftForm,
    DraftLine,
    DraftTotals,
    InvoiceDraft,
    SupplierRef,
)
from products.repository import ProductRepositoryDep
from suppliers.repository import SupplierRepositoryDep
from suppliers.service import supplier_summary


class InvoiceDraftService:
    def __init__(
        self,
        invoices: InvoiceRepositoryDep,
        suppliers: SupplierRepositoryDep,
        products: ProductRepositoryDep,
    ) -> None:
        self.invoices = invoices
        self.suppliers = suppliers
        self.products = products
        self.planner = InvoicePlanner(
            invoices=invoices,
            suppliers=suppliers,
            products=products,
        )

    async def receive_invoice(
        self,
        invoice: InvoiceExtraction,
        extracted: dict[str, JsonValue],
    ) -> InvoiceDraft:
        # only an exact inn match is trusted, a name may belong to someone else
        supplier = None
        if invoice.supplier.inn is not None:
            supplier = await self.suppliers.get_by_inn(
                inn=invoice.supplier.inn,
            )
        draft_invoice = await self.invoices.create(
            invoice=Invoice(
                supplier_id=supplier.id if supplier else None,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                status=InvoiceStatus.DRAFT,
                extracted=extracted,
                form=None,
            ),
        )
        draft = await self._draft(
            draft_invoice=draft_invoice,
        )
        await self.invoices.commit()
        return draft

    async def get_draft(
        self,
        invoice_id: int,
    ) -> InvoiceDraft:
        return await self._draft(
            draft_invoice=await get_draft_invoice(
                invoices=self.invoices,
                invoice_id=invoice_id,
            ),
        )

    async def save_form(
        self,
        invoice_id: int,
        form: DraftForm,
    ) -> InvoiceDraft:
        draft_invoice = await get_draft_invoice(
            invoices=self.invoices,
            invoice_id=invoice_id,
        )
        extraction = InvoiceExtraction.model_validate(
            obj=draft_invoice.extracted,
        )
        numbered_items = numbered_extraction(
            extraction=extraction,
        )
        number_form_lines(
            form=form,
            source_max=max(
                numbered_items,
                default=0,
            ),
        )
        draft_invoice.form = form.model_dump(
            mode="json",
        )
        # the columns behind the checks and the uniqueness of confirmed invoices follow the form
        draft_invoice.invoice_number = form.invoice_number
        draft_invoice.invoice_date = form.invoice_date
        supplier = None
        if isinstance(
            form.supplier,
            SupplierRef,
        ):
            supplier = await self.suppliers.get(
                supplier_id=form.supplier.id,
            )
        draft_invoice.supplier_id = supplier.id if supplier else None
        draft = await self._draft(
            draft_invoice=draft_invoice,
        )
        await self.invoices.commit()
        return draft

    async def decline_invoice(
        self,
        invoice_id: int,
    ) -> None:
        draft_invoice = await get_draft_invoice(
            invoices=self.invoices,
            invoice_id=invoice_id,
        )
        draft_invoice.status = InvoiceStatus.DECLINED
        await self.invoices.commit()

    async def _draft(
        self,
        draft_invoice: Invoice,
    ) -> InvoiceDraft:
        plan = await self.planner.plan(
            draft_invoice=draft_invoice,
        )
        return InvoiceDraft(
            id=draft_invoice.id,
            ready=plan.ready,
            issues=plan.issues,
            form=plan.form,
            lines=[
                _draft_line(
                    line=line,
                    catalog_known=plan.catalog_known,
                )
                for line in plan.lines
            ],
            totals=DraftTotals(
                base_total=sum_known(
                    values=(
                        to_kopecks(
                            value=line.prices.base_price_total,
                        )
                        for line in plan.lines
                    ),
                ),
                cost_total=sum_known(
                    values=(line.prices.cost_price_total for line in plan.lines),
                ),
                retail_total=sum_known(
                    values=(line.retail_price_total for line in plan.lines),
                ),
            ),
            supplier=None
            if plan.supplier is None
            else supplier_summary(
                supplier=plan.supplier,
            ),
            supplier_candidates=plan.candidates,
            extraction=plan.extraction,
        )


InvoiceDraftServiceDep = Annotated[
    InvoiceDraftService,
    Depends(
        dependency=InvoiceDraftService,
    ),
]


def _draft_line(
    line: PlannedLine,
    catalog_known: bool,
) -> DraftLine:
    return DraftLine(
        line=line.position,
        cost_price=line.cost_price,
        base_price=to_kopecks(
            value=line.prices.base_price,
        ),
        base_price_total=to_kopecks(
            value=line.prices.base_price_total,
        ),
        product_id=line.product.id if line.product else None,
        product_name=line.product.name if line.product else line.form.name,
        new_product=catalog_known and line.product is None and line.key is not None,
        markup_pct=line.markup_pct,
        retail_price=line.retail_price,
        retail_price_total=line.retail_price_total,
        previous_cost_price=line.previous_cost_price,
        previous_retail_price=line.previous_retail_price,
        similar=line.similar,
    )
