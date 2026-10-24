from __future__ import annotations

from pydantic import JsonValue

from core.http import invalid
from core.schema_types import MAX_LINE_NO
from invoices.calculations import printed_cost_total_field, source_total_field
from invoices.extraction import InvoiceExtraction, InvoiceItemExtraction
from invoices.models import Invoice
from invoices.schemas import DraftForm
from suppliers.repository import SupplierRepository


async def initial_form(
    suppliers: SupplierRepository,
    draft_invoice: Invoice,
    extraction: InvoiceExtraction,
    numbered_items: dict[int, InvoiceItemExtraction],
) -> DraftForm:
    """the form as the model read it, before the user saves it"""
    supplier_id = draft_invoice.supplier_id
    # a supplier added since the upload is picked up while the draft is untouched
    if supplier_id is None and extraction.supplier.inn is not None:
        supplier = await suppliers.get_by_inn(
            inn=extraction.supplier.inn,
        )
        supplier_id = supplier.id if supplier else None
    read = extraction.model_dump(
        mode="json",
    )
    supplier: dict[str, JsonValue] | None = None
    if supplier_id is not None:
        supplier = {"id": supplier_id}
    elif read["supplier"]["name"] is not None:
        # not found by inn, so the supplier the model read is offered as a new one
        supplier = read["supplier"]
    return DraftForm.model_validate(
        obj={
            "invoice_number": read["invoice_number"],
            "invoice_date": read["invoice_date"],
            "supplier": supplier,
            "totals": {
                "cost_total": read["totals"][
                    printed_cost_total_field(
                        invoice=extraction,
                    )
                ],
                "base_total": read["totals"]["base_total"],
            },
            "lines": [
                {
                    "line_no": line_no,
                    "name": read_item["name"],
                    "quantity": read_item["quantity"],
                    "unit": read_item["unit"],
                    "vat_percent": read_item["vat_percent"],
                    "cost_price_total": read_item[
                        source_total_field(
                            item=item,
                        )
                    ],
                    "product_id": None,
                    "retail_price": None,
                }
                for (line_no, item), read_item in zip(
                    numbered_items.items(),
                    read["items"],
                    strict=True,
                )
            ],
        },
    )


def numbered_extraction(
    extraction: InvoiceExtraction,
) -> dict[int, InvoiceItemExtraction]:
    last_number = max(
        (item.line_no for item in extraction.items if item.line_no is not None),
        default=0,
    )
    numbered: dict[int, InvoiceItemExtraction] = {}
    for item in extraction.items:
        number = item.line_no
        if number is None:
            last_number += 1
            number = last_number
        if number > MAX_LINE_NO:
            invalid(
                detail="Нет свободного номера позиции в допустимом диапазоне",
            )
        if number in numbered:
            invalid(
                detail=f"Номер позиции {number} повторяется в накладной",
            )
        numbered[number] = item
    return numbered


def number_form_lines(
    form: DraftForm,
    source_max: int,
) -> None:
    used: set[int] = set()
    for line in form.lines:
        if line.line_no is None:
            continue
        if line.line_no in used:
            invalid(
                detail=f"Номер позиции {line.line_no} повторяется в накладной",
            )
        used.add(
            line.line_no,
        )
    # legacy forms without any numbers keep their current positions
    legacy = not used
    last_number = max(
        source_max,
        max(
            used,
            default=0,
        ),
    )
    for position, line in enumerate(
        iterable=form.lines,
        start=1,
    ):
        if line.line_no is not None:
            continue
        if legacy:
            number = position
        else:
            last_number += 1
            number = last_number
        if number > MAX_LINE_NO:
            invalid(
                detail="Нет свободного номера позиции в допустимом диапазоне",
            )
        line.line_no = number
