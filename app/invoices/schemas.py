from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
)

from core.enums import InvoiceStatus
from core.schema_types import (
    MAX_LINE_NO,
    FormModel,
    Inn,
    InvoiceDate,
    Money,
    OutputDate,
    Quantity,
    Text,
    VatPercent,
)
from invoices.extraction import InvoiceExtraction
from suppliers.schemas import SupplierSummary


class SupplierRef(FormModel):
    id: Annotated[
        int,
        Field(
            gt=0,
        ),
    ]


# created when the invoice is confirmed
class NewSupplier(FormModel):
    name: Text
    inn: Inn | None


class FormLine(FormModel):
    # saved drafts without this field keep their current numbering
    line_no: (
        Annotated[
            int,
            Field(
                gt=0,
                le=MAX_LINE_NO,
            ),
        ]
        | None
    ) = None
    name: Text | None
    quantity: Quantity | None
    unit: Text | None
    vat_percent: VatPercent | None
    # the line total actually paid, with VAT if any, every price is derived from it
    cost_price_total: Money | None
    # None to find the product by name, a product of the supplier this line is another spelling of
    product_id: (
        Annotated[
            int,
            Field(
                gt=0,
            ),
        ]
        | None
    )
    # None to keep the current markup of the product, whole rubles to set a new one
    retail_price: (
        Annotated[
            int,
            Field(
                gt=0,
            ),
        ]
        | None
    )
    # the old stock on the shelf that takes the new price, a draft saved before has no key
    revalue_quantity: Quantity | None = None


# as printed on the invoice, only to check the lines against
class FormTotals(FormModel):
    cost_total: Money | None
    base_total: Money | None


class DraftForm(FormModel):
    invoice_number: Text | None
    invoice_date: InvoiceDate | None
    supplier: SupplierRef | NewSupplier | None
    totals: FormTotals
    lines: list[FormLine]


class Issue(BaseModel):
    # stable line number, None means the issue is about the whole invoice
    line: int | None
    message: str
    # a blocking issue prevents confirming the invoice, the others are worth a look
    blocking: bool = True
    # set for the issues a client may show its own way, e.g. similar_product
    code: str | None = None


class SimilarProduct(BaseModel):
    id: int
    name: str
    # percent of matching characters of the normalized names
    similarity: int


class DraftLine(BaseModel):
    # stable line number from the form
    line: int
    # derived from the line total and rounded to kopecks
    cost_price: Decimal | None
    base_price: Decimal | None
    base_price_total: Decimal | None
    # None for a product that is created when the invoice is confirmed
    product_id: int | None
    product_name: str | None
    new_product: bool
    markup_pct: Decimal | None
    retail_price: Decimal | None
    retail_price_total: Decimal | None
    # the cost with VAT of the last delivery of the product, None when it is the same or unknown
    previous_cost_price: Decimal | None
    # the shelf price of the product when the line changes it, None when it stays
    previous_retail_price: Decimal | None
    # supplier products with a close name while the line has none, most similar first
    similar: list[SimilarProduct]


class DraftTotals(BaseModel):
    # sums of the line values, None while any line has no value
    base_total: Decimal | None
    cost_total: Decimal | None
    retail_total: Decimal | None


class SupplierCandidate(SupplierSummary):
    # lines of this invoice that match the supplier product names
    matched_lines: int


class ConfirmedInvoice(BaseModel):
    id: int
    ledger_entry_id: int
    # the inflow written to the ledger
    retail_total: Decimal
    # the revaluation of the old stock, None when nothing was revalued
    revaluation: Decimal | None
    # stock at retail prices after this invoice
    balance: Decimal


class InvoiceDraft(BaseModel):
    id: int
    # no blocking issues, the invoice can be confirmed
    ready: bool
    issues: list[Issue]
    # edit and send back to save the draft
    form: DraftForm
    lines: list[DraftLine]
    totals: DraftTotals
    # the existing supplier chosen in the form, None while it is new or not chosen
    supplier: SupplierSummary | None
    # existing suppliers that look alike while the form has a new one or none
    supplier_candidates: list[SupplierCandidate]
    # what the model read, for reference
    extraction: InvoiceExtraction


class InvoiceListItem(BaseModel):
    id: int
    status: InvoiceStatus
    invoice_number: str | None
    invoice_date: OutputDate | None
    # the chosen supplier, or the name the model read while there is none
    supplier_name: str | None
    # the inflow at retail prices, None until the invoice is confirmed
    retail_total: Decimal | None
    # owed to the supplier and not paid yet, None until the invoice is confirmed
    debt: Decimal | None
    lines: int
    created_at: datetime


class InvoiceList(BaseModel):
    items: list[InvoiceListItem]
    has_more: bool


class PostedLine(BaseModel):
    line_no: int
    # as printed on the invoice
    name: str
    # the catalog product the line was posted to
    product_name: str
    quantity: Decimal
    unit: str | None
    vat_percent: Decimal | None
    base_price: Decimal | None
    cost_price: Decimal
    cost_price_total: Decimal
    markup_pct: Decimal
    retail_price: Decimal
    retail_price_total: Decimal


class PaymentOut(BaseModel):
    id: int
    paid_on: OutputDate
    amount: Decimal
    comment: str | None


class PostedInvoice(BaseModel):
    id: int
    invoice_number: str
    invoice_date: OutputDate
    supplier: SupplierSummary
    lines: list[PostedLine]
    # owed to the supplier
    cost_total: Decimal
    retail_total: Decimal
    ledger_entry_id: int
    paid: Decimal
    debt: Decimal
    payments: list[PaymentOut]


class InvoiceConfirm(FormModel):
    # the day the goods came, the inflow goes into the ledger on it
    occurred_on: InvoiceDate


class PaymentCreate(FormModel):
    paid_on: InvoiceDate
    amount: Annotated[
        Money,
        Field(
            gt=0,
        ),
    ]
    comment: Text | None
